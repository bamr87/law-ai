"""LSATContentAuthor — drafts new LSAT (LR/RC/LG) questions for HITL review.

Spec 019 (T-001). Always returns a populated ``GenerateQuestionsOutput`` —
falls back to a deterministic placeholder draft when Ollama is unreachable so
the autonomy beat schedule never hard-fails. Every invocation emits a single
``provenance.log_agent_call`` event whose ``child_trace_ids`` list the
per-draft trace ids the proposals service assigns when it persists each row.

Hard contract (constitution §1, §4, §5):
* Local Ollama only — no closed-source fallback.
* Every draft is persisted as a ``pending`` proposal; the agent never writes
  to the live ``*_bank.json`` files.
* The class-level ``requires_human_approval = True`` flag is read by the
  agent registry so the dashboard surfaces the HITL gate.
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any

import httpx
from pydantic import BaseModel, Field, model_validator

from lawgraph.core import claude_code
from lawgraph.core.provenance import provenance
from lawgraph.core.settings_proxy import settings_proxy as settings
from lawgraph.lsat.services.bank import (
    ChoiceLabel,
    Concept,
    Difficulty,
    PassageContext,
    Section,
    load_concepts,
    load_passages,
)

logger = logging.getLogger("lawgraph.agents.lsat_content_author")

PROMPT_VERSION = "lsat_content_author/2"
PROMPT_PATH = (
    Path(__file__).resolve().parent.parent / "prompts" / "lsat_content_author.v2.md"
)

# Choice labels in canonical order; used to spread fallback answer keys across
# A-E instead of always defaulting to "A" (see _fallback_draft).
_CHOICE_LABELS: tuple[ChoiceLabel, ...] = ("A", "B", "C", "D", "E")

_MAX_COUNT = 10
_MAX_STEM_CHARS = 1500
_MAX_CHOICE_CHARS = 400
_MAX_EXPLANATION_CHARS = 2000
_MAX_PASSAGE_CHARS = 4000


# ---------------------------------------------------------------------------
# Pydantic contracts (spec 019 FR-1)
# ---------------------------------------------------------------------------


class GenerateQuestionsInput(BaseModel):
    """Caller-supplied target for a generation cycle."""

    section: Section
    difficulty: Difficulty
    count: int = Field(default=1, ge=1, le=_MAX_COUNT)
    concepts: list[str] = Field(default_factory=list)
    passage_id: str | None = None


class DraftChoice(BaseModel):
    label: ChoiceLabel
    text: str = Field(max_length=_MAX_CHOICE_CHARS)


class DraftQuestion(BaseModel):
    """Mirror of :class:`lawgraph.lsat.services.bank.Question` (no ``id``)."""

    section: Section
    difficulty: Difficulty
    stem: str = Field(max_length=_MAX_STEM_CHARS)
    choices: list[DraftChoice] = Field(min_length=5, max_length=5)
    correct: ChoiceLabel
    explanation: str = Field(max_length=_MAX_EXPLANATION_CHARS)
    concepts: list[str] = Field(default_factory=list)
    passage_id: str | None = None
    confidence: float = Field(0.0, ge=0.0, le=1.0)

    @model_validator(mode="after")
    def _check_choice_labels(self) -> DraftQuestion:
        labels = [c.label for c in self.choices]
        if labels != ["A", "B", "C", "D", "E"]:
            raise ValueError("choices must be labelled A,B,C,D,E in order")
        if self.correct not in labels:
            raise ValueError("correct label must be one of A..E")
        return self


class GenerateQuestionsOutput(BaseModel):
    drafts: list[DraftQuestion]
    model: str
    confidence: float = Field(0.0, ge=0.0, le=1.0)
    latency_ms: float = 0.0
    degraded: bool = Field(
        False,
        description="True when Ollama was unreachable and a fallback draft was used.",
    )
    trace_id: str | None = None


# ---------------------------------------------------------------------------
# Prompt loading + payload construction
# ---------------------------------------------------------------------------


def _load_prompt_template() -> str:
    if not PROMPT_PATH.is_file():  # pragma: no cover - prompts ship with code
        raise FileNotFoundError(f"missing prompt file: {PROMPT_PATH}")
    return PROMPT_PATH.read_text(encoding="utf-8")


def _build_user_payload(
    inp: GenerateQuestionsInput,
    *,
    catalog: list[Concept],
    passage: PassageContext | None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "section": inp.section,
        "difficulty": inp.difficulty,
        "count": inp.count,
        "target_concepts": list(inp.concepts),
        "concept_catalog": [
            {"id": c.id, "name": c.name, "summary": c.summary} for c in catalog
        ],
    }
    if passage is not None:
        payload["passage"] = {
            "title": passage.title,
            "passage": (passage.passage or "")[:_MAX_PASSAGE_CHARS],
            "setup": (passage.setup or "")[:_MAX_PASSAGE_CHARS],
            "rules": list(passage.rules),
        }
    return payload


# Short system steer used only on the Claude Code path (Ollama's /api/generate
# has no system role, so its instructions live in the prompt template instead).
_LLM_SYSTEM = (
    "You are an LSAT item writer. Follow the instructions exactly and respond "
    "with a single JSON object only — no preamble and no markdown code fences. "
    "Each question must have exactly five answer choices labeled A, B, C, D, and "
    "E in that order, with no duplicate labels and no empty choices."
)

# JSON Schema for the drafts response, used as a structured-output constraint on
# the Claude Code path so Opus returns schema-valid JSON every time (no prose,
# no truncated objects). Structured outputs forbids length/size constraints, so
# the exact 5-choice rule and field caps are still enforced by DraftQuestion
# (Pydantic) after parsing. ``passage_id`` is intentionally omitted — the agent
# owns it — so ``additionalProperties: false`` keeps it out of the model output.
_DRAFTS_RESPONSE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "drafts": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "section": {"type": "string", "enum": ["LR", "RC", "LG"]},
                    "difficulty": {
                        "type": "string",
                        "enum": ["easy", "med", "hard"],
                    },
                    "stem": {"type": "string"},
                    "choices": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "label": {
                                    "type": "string",
                                    "enum": list(_CHOICE_LABELS),
                                },
                                "text": {"type": "string"},
                            },
                            "required": ["label", "text"],
                            "additionalProperties": False,
                        },
                    },
                    "correct": {"type": "string", "enum": list(_CHOICE_LABELS)},
                    "explanation": {"type": "string"},
                    "concepts": {"type": "array", "items": {"type": "string"}},
                    "confidence": {"type": "number"},
                },
                "required": [
                    "section",
                    "difficulty",
                    "stem",
                    "choices",
                    "correct",
                    "explanation",
                    "concepts",
                    "confidence",
                ],
                "additionalProperties": False,
            },
        }
    },
    "required": ["drafts"],
    "additionalProperties": False,
}


# ---------------------------------------------------------------------------
# Ollama client (lightweight; mirrors lsat.services.tutor pattern)
# ---------------------------------------------------------------------------


async def _ollama_generate(prompt: str, *, model: str) -> str:
    url = settings.OLLAMA_BASE_URL.rstrip("/") + "/api/generate"
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": 0.4},
        "format": "json",
    }
    timeout = httpx.Timeout(settings.OLLAMA_REQUEST_TIMEOUT_S)
    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.post(url, json=payload)
        resp.raise_for_status()
        data = resp.json()
    return str(data.get("response") or "").strip()


async def _generate(prompt: str) -> tuple[str, str]:
    """Route generation to the configured provider; return ``(raw, model_label)``.

    Uses the dev-time Claude Code OAuth provider when an operator has opted in
    (:func:`claude_code.is_active`); otherwise local Ollama — the product
    default. Raises on provider/transport failure so :meth:`LSATContentAuthor.run`
    degrades to the deterministic offline draft.
    """
    if claude_code.is_active():
        raw = await claude_code.generate(
            prompt, system=_LLM_SYSTEM, response_schema=_DRAFTS_RESPONSE_SCHEMA
        )
        return raw, claude_code.model_label()
    raw = await _ollama_generate(prompt, model=settings.OLLAMA_DEFAULT_MODEL)
    return raw, settings.OLLAMA_DEFAULT_MODEL


def _normalize_choices(item: dict[str, Any]) -> None:
    """Coerce ``item['choices']`` to the canonical A-E set when possible.

    Models occasionally emit a stray, empty, or duplicate choice (structured
    outputs can't cap array length). When every label A-E has non-empty text,
    rebuild exactly five choices in order (first non-empty text per label wins);
    otherwise leave it for ``DraftQuestion`` to reject.
    """
    raw_choices = item.get("choices")
    if not isinstance(raw_choices, list):
        return
    by_label: dict[str, str] = {}
    for ch in raw_choices:
        if not isinstance(ch, dict):
            continue
        label = ch.get("label")
        text = str(ch.get("text") or "").strip()
        if label in _CHOICE_LABELS and label not in by_label and text:
            by_label[label] = text
    if all(label in by_label for label in _CHOICE_LABELS):
        item["choices"] = [
            {"label": label, "text": by_label[label]} for label in _CHOICE_LABELS
        ]


def _parse_drafts(
    raw: str, *, section: Section, difficulty: Difficulty
) -> list[DraftQuestion]:
    try:
        obj = claude_code.loads_first_json(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"LLM response not JSON: {exc}") from exc
    raw_drafts = obj.get("drafts") if isinstance(obj, dict) else None
    if not isinstance(raw_drafts, list) or not raw_drafts:
        raise ValueError("LLM response missing non-empty 'drafts' list")
    out: list[DraftQuestion] = []
    for item in raw_drafts:
        if not isinstance(item, dict):
            continue
        # Backfill required fields the LLM sometimes drops.
        item.setdefault("section", section)
        item.setdefault("difficulty", difficulty)
        _normalize_choices(item)
        try:
            out.append(DraftQuestion.model_validate(item))
        except Exception as exc:
            logger.warning("LSATContentAuthor: discarding malformed draft: %s", exc)
    if not out:
        raise ValueError("no valid drafts parsed from LLM response")
    return out


# ---------------------------------------------------------------------------
# Offline fallback (NFR-AUDIT-2)
# ---------------------------------------------------------------------------


def _fallback_draft(inp: GenerateQuestionsInput, index: int = 0) -> DraftQuestion:
    """Deterministic placeholder used when Ollama is unreachable.

    The draft is intentionally low-quality and labelled with confidence 0.0
    so reviewers always reject it; the point is to keep the autonomy cycle
    auditable rather than to ship real content from the fallback path.

    ``index`` rotates the placeholder answer key across A-E so a batch of
    fallback drafts never collapses onto a single label (the same positional
    bias we guard against for real content).
    """
    correct = _CHOICE_LABELS[index % len(_CHOICE_LABELS)]
    return DraftQuestion(
        section=inp.section,
        difficulty=inp.difficulty,
        stem=(
            "[OFFLINE FALLBACK — Ollama unreachable] Author a "
            f"{inp.section} ({inp.difficulty}) question by hand from this seed."
        ),
        choices=[
            DraftChoice(label="A", text="placeholder choice A"),
            DraftChoice(label="B", text="placeholder choice B"),
            DraftChoice(label="C", text="placeholder choice C"),
            DraftChoice(label="D", text="placeholder choice D"),
            DraftChoice(label="E", text="placeholder choice E"),
        ],
        correct=correct,
        explanation=(
            "Offline fallback draft. The author agent could not reach Ollama; "
            "this row exists solely to keep the autonomy cycle auditable and "
            "MUST be rejected by a reviewer."
        ),
        concepts=list(inp.concepts),
        passage_id=inp.passage_id,
        confidence=0.0,
    )


# ---------------------------------------------------------------------------
# Public crew
# ---------------------------------------------------------------------------


class LSATContentAuthor:
    """Drafts LSAT questions targeted at a `(section, difficulty, concepts)` tuple.

    See spec 019 FR-1..FR-3. The crew is **always** HITL-gated; persisting
    drafts to the live bank is the caller's responsibility (proposals.py).
    """

    name = "LSATContentAuthor"
    description = (
        "Drafts new LSAT (LR/RC/LG) questions for human review. "
        "Every draft is HITL-gated; nothing reaches the live bank without "
        "explicit approval."
    )
    human_approval_required = True

    async def run(self, input_data: dict[str, Any]) -> GenerateQuestionsOutput:
        inp = GenerateQuestionsInput.model_validate(input_data)
        started = time.perf_counter()

        catalog_full = load_concepts()
        # Filter the catalog to entries that apply to the target section so the
        # prompt stays small; if the caller listed specific concepts, keep
        # those first so the LLM picks the right ids.
        catalog = [c for c in catalog_full.values() if inp.section in c.sections]
        if inp.concepts:
            wanted = set(inp.concepts)
            catalog.sort(key=lambda c: (0 if c.id in wanted else 1, c.id))
        catalog = catalog[:25]

        passage: PassageContext | None = None
        if inp.passage_id:
            passage = load_passages().get(inp.passage_id)

        template = _load_prompt_template()
        user_payload = _build_user_payload(inp, catalog=catalog, passage=passage)
        prompt = (
            template
            + "\n\n## Request\n\n```json\n"
            + json.dumps(user_payload, indent=2)
            + "\n```\n"
        )

        drafts: list[DraftQuestion] = []
        degraded = False
        model_used = (
            claude_code.model_label()
            if claude_code.is_active()
            else settings.OLLAMA_DEFAULT_MODEL
        )
        try:
            raw, model_used = await _generate(prompt)
            drafts = _parse_drafts(raw, section=inp.section, difficulty=inp.difficulty)
            drafts = drafts[: inp.count]
            # Pad with fallback drafts if the LLM returned fewer than asked.
            while len(drafts) < inp.count:
                drafts.append(_fallback_draft(inp, len(drafts)))
        except (
            TimeoutError,
            httpx.HTTPError,
            OSError,
            ValueError,
            claude_code.ClaudeCodeUnavailableError,
        ) as exc:
            logger.info("LSATContentAuthor falling back to offline: %s", exc)
            degraded = True
            model_used = "fallback/offline"
            drafts = [_fallback_draft(inp, i) for i in range(inp.count)]
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("LSATContentAuthor unexpected error: %s", exc, exc_info=True)
            degraded = True
            model_used = "fallback/offline"
            drafts = [_fallback_draft(inp, i) for i in range(inp.count)]

        latency_ms = (time.perf_counter() - started) * 1000.0
        # Aggregate confidence = mean draft confidence (0.0 on degraded path).
        confidence = (
            round(sum(d.confidence for d in drafts) / max(1, len(drafts)), 4)
            if not degraded
            else 0.0
        )

        # Provenance: one parent event; child trace ids assigned by the
        # proposals service when each draft is persisted (FR-3, FR-4). We log
        # before persistence so the parent trace is always present even if
        # persistence then fails.
        trace_id = provenance.log_agent_call(
            agent_name=self.name,
            input_data={
                "section": inp.section,
                "difficulty": inp.difficulty,
                "count": inp.count,
                "passage_id": inp.passage_id,
                "target_concepts": list(inp.concepts),
                "degraded": degraded,
            },
            output_data={
                "draft_count": len(drafts),
                "model": model_used,
                "confidence": confidence,
                "degraded": degraded,
            },
            model=model_used,
            latency_ms=latency_ms,
            confidence=confidence,
            sources=[],
        )

        return GenerateQuestionsOutput(
            drafts=drafts,
            model=model_used,
            confidence=confidence,
            latency_ms=round(latency_ms, 2),
            degraded=degraded,
            trace_id=trace_id,
        )
