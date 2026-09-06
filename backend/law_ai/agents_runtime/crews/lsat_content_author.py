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
from collections import Counter
from collections.abc import Iterable
from pathlib import Path
from typing import Any

import httpx
from pydantic import BaseModel, Field, model_validator

from law_ai.core import claude_code, llm, xai
from law_ai.core.settings_proxy import settings_proxy as settings
from law_ai.core.provenance import provenance
from law_ai.lsat.services.bank import (
    ChoiceLabel,
    Concept,
    Difficulty,
    PassageContext,
    Section,
    load_concepts,
    load_passages,
)

logger = logging.getLogger("law_ai.agents.lsat_content_author")

PROMPT_VERSION = "lsat_content_author/2"
PROMPT_PATH = (
    Path(__file__).resolve().parent.parent / "prompts" / "lsat_content_author.v2.md"
)

# Choice labels in canonical order; used to spread fallback answer keys across
# A-E instead of always defaulting to "A" (see _fallback_draft).
_CHOICE_LABELS: tuple[ChoiceLabel, ...] = ("A", "B", "C", "D", "E")

# Answer-key balance (BL-20260606-02). A batch smaller than this carries no
# signal: 2 drafts keyed the same are a coin flip, not a skew.
_MIN_BALANCE_SAMPLE = 3
_DEFAULT_BALANCE_TOLERANCE = 0.40

_MAX_COUNT = 10
_MAX_STEM_CHARS = 1500
_MAX_CHOICE_CHARS = 400
_MAX_EXPLANATION_CHARS = 2000
_MAX_PASSAGE_CHARS = 4000


# ---------------------------------------------------------------------------
# Answer-key balance (BL-20260606-02)
# ---------------------------------------------------------------------------


def default_balance_tolerance() -> float:
    """Share of one answer key above which a batch counts as skewed.

    Read from ``LSAT_FACTORY_BALANCE_TOLERANCE`` so the direct
    ``LSATContentAuthor`` paths (autonomy beat, ``POST
    /api/lsat/proposals/generate``) and the content factory — which passes its
    own :class:`~law_ai.lsat.factory.config.FactoryConfig` value — agree on
    what "skewed" means.
    """
    try:
        return float(
            getattr(
                settings, "LSAT_FACTORY_BALANCE_TOLERANCE", _DEFAULT_BALANCE_TOLERANCE
            )
        )
    except (TypeError, ValueError):  # pragma: no cover - defensive
        return _DEFAULT_BALANCE_TOLERANCE


def answer_key_skew(
    labels: Iterable[str], tolerance: float | None = None
) -> str | None:
    """Describe the answer-key skew of a batch, or ``None`` when it is spread.

    BL-20260606-02: the prompt *asks* for an A-E spread, so every batch that
    reaches the HITL queue is checked for one — the content factory's Gate 4
    and the direct agent paths both call this. Flag, never reject (factory
    AC-4): rewriting a key would desynchronise the explanation that names it.
    """
    keys = Counter(labels)
    total = sum(keys.values())
    if total < _MIN_BALANCE_SAMPLE:
        return None
    limit = default_balance_tolerance() if tolerance is None else tolerance
    label, top = keys.most_common(1)[0]
    share = top / total
    if share <= limit:
        return None
    return (
        f"answer-key skew: {top}/{total} drafts keyed {label!r} "
        f"(share {share:.2f} > tolerance {limit:.2f})"
    )


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
    stream_id: str | None = Field(
        default=None,
        min_length=1,
        max_length=64,
        pattern=r"^[A-Za-z0-9._-]+$",
        description=(
            "Client-chosen WebSocket correlation id (BL-20260906-76). "
            "Subscribe to /ws/agents/<stream_id> BEFORE posting and the "
            "drafting call relays its deltas there as ``authoring_token`` "
            "events, so a 68-second wait is visible instead of a spinner. "
            "Progress only: the REST body is still the authoritative result."
        ),
    )


class DraftChoice(BaseModel):
    label: ChoiceLabel
    text: str = Field(max_length=_MAX_CHOICE_CHARS)


class DraftQuestion(BaseModel):
    """Mirror of :class:`law_ai.lsat.services.bank.Question` (no ``id``)."""

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
    balance_flag: str | None = Field(
        None,
        description="Set when the batch's answer keys are skewed past the "
        "tolerance (BL-20260606-02). Advisory: the drafts still reach the "
        "HITL queue, carrying the flag in their proposal meta.",
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


async def _emit_delta(stream_id: str, payload: dict[str, Any]) -> None:
    """Relay one progress event; never fatal (BL-20260906-76).

    Fire-and-forget like every other event on this socket: a Redis outage must
    not cost an author the drafts the chain already produced.
    """
    try:
        from law_ai.agentsapi.streaming import emit_stream_event

        await emit_stream_event(stream_id, payload, source="lsat_content_author")
    except Exception:  # pragma: no cover - defensive
        logger.debug("authoring delta not delivered", exc_info=True)


async def _generate(prompt: str, stream_id: str | None = None) -> tuple[str, str]:
    """Generate drafts through the shared provider chain (spec 034).

    Claude first, the Anthropic API key second, local Ollama last, with
    structured outputs pinning schema-valid JSON on the Claude tiers. Returns
    ``(raw, model_label)`` and raises when every provider fails, so
    :meth:`LSATContentAuthor.run` degrades to the deterministic offline draft.

    Buffered by default — batch callers, the factory, tests. With a
    ``stream_id`` the same call is streamed and each delta relayed as an
    ``authoring_token`` event (BL-20260906-76), so the 68-second authoring
    wait is visible the way the IRAC one is. Either way the caller parses one
    complete JSON payload: the deltas are progress, never the result.
    """
    # Authoring runs with an author waiting on the page — measured at 68s
    # on the xAI tier — so it takes the faster Grok id when one is
    # configured, like the other user-facing calls (BL-20260905-11).
    overrides = xai.interactive_overrides()
    if not stream_id:
        result = await llm.agenerate(
            prompt,
            system=_LLM_SYSTEM,
            response_schema=_DRAFTS_RESPONSE_SCHEMA,
            agent="lsat_content_author",
            models=overrides,
        )
        return result.text, result.model_label

    parts: list[str] = []
    label = "(provider chain)"
    chars = 0
    async for chunk in llm.astream(
        prompt,
        system=_LLM_SYSTEM,
        response_schema=_DRAFTS_RESPONSE_SCHEMA,
        agent="lsat_content_author",
        models=overrides,
    ):
        parts.append(chunk.text)
        label = chunk.model_label
        chars += len(chunk.text)
        await _emit_delta(
            stream_id,
            {
                "type": "authoring_token",
                "agent": "LSATContentAuthor",
                "text": chunk.text,
                "chars": chars,
                "model": chunk.model_label,
            },
        )
    return "".join(parts), label


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
        obj = llm.loads_first_json(raw)
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
        # Overwritten by the real label as soon as a provider answers; this
        # placeholder only survives if _generate raises before returning.
        model_used = "fallback/offline"
        try:
            raw, model_used = await _generate(prompt, inp.stream_id)
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
            llm.LLMUnavailableError,
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
        # BL-20260606-02: check the finished batch (LLM *and* fallback drafts)
        # for A-E spread instead of trusting the prompt to have produced one.
        balance_flag = answer_key_skew(d.correct for d in drafts)
        if balance_flag:
            logger.info("LSATContentAuthor batch flagged: %s", balance_flag)
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
                "balance_flag": balance_flag,
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
            balance_flag=balance_flag,
            trace_id=trace_id,
        )
