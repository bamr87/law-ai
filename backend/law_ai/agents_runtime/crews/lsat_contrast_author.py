"""LSATContrastAuthor — re-asks one bank question as a different type (spec 054).

A contrast variation keeps a question's stimulus verbatim and rewrites the
question sentence, the choices, the key and the explanation for a *different*
archetype, plus a note for the learner on what moved and why. The pair is the
teaching instrument: the same argument, weakened and then strengthened, shows
the task moving the key better than any article can.

Mirrors the other LSAT crews — the provider chain via ``law_ai.core.llm``
(never a transport), one ``provenance.log_agent_call`` per run, and a
``degraded`` output when no provider answers. Unlike ``LSATContentAuthor`` it
has **no offline placeholder draft**: a fabricated variation would sit next to
a real question and claim kinship with it, so a degraded run returns no draft
and the caller files nothing.

It accepts a ``critique`` — the objections a previous round's gates and judge
raised — which is what lets :mod:`law_ai.lsat.factory.revise` improve a draft
instead of merely annotating it. Every draft is HITL-gated; the crew never
touches the bank.
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any

import httpx
from pydantic import BaseModel, Field, ValidationError, model_validator

from law_ai.core import claude_code, llm
from law_ai.core.provenance import provenance
from law_ai.lsat.factory.blueprints import select_exemplars
from law_ai.lsat.factory.coverage import GenerationTarget
from law_ai.lsat.factory.taxonomy import get_archetype
from law_ai.lsat.services.bank import ChoiceLabel, Difficulty, Section, load_bank
from law_ai.lsat.services.contrast import stimulus_of
from law_ai.lsat.services.playbooks import load_playbooks, load_traps, question_sentence

logger = logging.getLogger("law_ai.agents.lsat_contrast_author")

PROMPT_VERSION = "lsat_contrast_author/1"
PROMPT_PATH = (
    Path(__file__).resolve().parent.parent / "prompts" / "lsat_contrast_author.v1.md"
)

_CHOICE_LABELS: tuple[ChoiceLabel, ...] = ("A", "B", "C", "D", "E")
_MAX_STEM_CHARS = 2500
_MAX_CHOICE_CHARS = 400
_MAX_EXPLANATION_CHARS = 2000
_MAX_NOTE_CHARS = 2000
_MAX_CRITIQUE_ITEMS = 12

_LLM_SYSTEM = (
    "You are an LSAT item writer producing a contrast variation of an existing "
    "question. Keep the stimulus verbatim and change only the task. Respond with "
    "a single JSON object only — no preamble and no markdown code fences."
)

_RESPONSE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "variation": {
            "type": "object",
            "properties": {
                "stem": {"type": "string"},
                "choices": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "label": {"type": "string", "enum": list(_CHOICE_LABELS)},
                            "text": {"type": "string"},
                        },
                        "required": ["label", "text"],
                        "additionalProperties": False,
                    },
                },
                "correct": {"type": "string", "enum": list(_CHOICE_LABELS)},
                "explanation": {"type": "string"},
                "concepts": {"type": "array", "items": {"type": "string"}},
                "contrast_note": {"type": "string"},
                # Structured outputs rejects free-form maps, so the traps travel
                # as a list of pairs and are folded into a dict at parse time.
                "distractor_traps": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "label": {"type": "string", "enum": list(_CHOICE_LABELS)},
                            "trap_id": {"type": "string"},
                        },
                        "required": ["label", "trap_id"],
                        "additionalProperties": False,
                    },
                },
                "confidence": {"type": "number"},
            },
            "required": [
                "stem",
                "choices",
                "correct",
                "explanation",
                "concepts",
                "contrast_note",
                "distractor_traps",
                "confidence",
            ],
            "additionalProperties": False,
        }
    },
    "required": ["variation"],
    "additionalProperties": False,
}


class ContrastInput(BaseModel):
    """One source question and the type to re-ask it as."""

    question_id: str
    target_archetype_id: str
    #: Objections from a previous round (gates + judge), to be fixed.
    critique: list[str] = Field(default_factory=list, max_length=_MAX_CRITIQUE_ITEMS)


class ContrastChoice(BaseModel):
    label: ChoiceLabel
    text: str = Field(max_length=_MAX_CHOICE_CHARS)


class ContrastDraft(BaseModel):
    """A ``DraftQuestion`` plus its lineage and teaching note."""

    section: Section
    difficulty: Difficulty
    stem: str = Field(max_length=_MAX_STEM_CHARS)
    choices: list[ContrastChoice] = Field(min_length=5, max_length=5)
    correct: ChoiceLabel
    explanation: str = Field(max_length=_MAX_EXPLANATION_CHARS)
    concepts: list[str] = Field(default_factory=list)
    passage_id: str | None = None
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    variation_of: str
    target_archetype_id: str
    contrast_note: str = Field(max_length=_MAX_NOTE_CHARS)
    #: ``{label: trap_id}`` for each distractor, as the author reports it.
    distractor_traps: dict[str, str] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _check_labels(self) -> ContrastDraft:
        labels = [c.label for c in self.choices]
        if labels != list(_CHOICE_LABELS):
            raise ValueError("choices must be labelled A,B,C,D,E in order")
        return self


class ContrastOutput(BaseModel):
    draft: ContrastDraft | None
    #: Why a model answer could not become a draft (shape errors), when it
    #: answered at all. These are objections the next round can fix, unlike
    #: ``degraded``, which means nobody answered.
    issues: list[str] = Field(default_factory=list)
    model: str = "fallback/offline"
    latency_ms: float = 0.0
    degraded: bool = False
    trace_id: str | None = None


def _load_prompt_template() -> str:
    if not PROMPT_PATH.is_file():  # pragma: no cover - prompts ship with code
        raise FileNotFoundError(f"missing prompt file: {PROMPT_PATH}")
    return PROMPT_PATH.read_text(encoding="utf-8")


def build_payload(inp: ContrastInput) -> dict[str, Any]:
    """Everything the writer needs: the source, the target's playbook, one exemplar.

    >>> payload = build_payload(ContrastInput(question_id="lr-002", target_archetype_id="lr-strengthen"))
    >>> payload["target"]["archetype_id"]
    'lr-strengthen'
    """
    source = load_bank()[inp.question_id]
    target = get_archetype(inp.target_archetype_id)
    book = load_playbooks()[target.id]
    traps = load_traps()
    source_book = load_playbooks().get(source.archetype or "")
    exemplars = select_exemplars(
        GenerationTarget(
            section=target.section,
            archetype_id=target.id,
            difficulty=source.difficulty,
            count=1,
            concepts=list(target.concepts),
            tier="standard",
            priority=1.0,
            rationale="contrast exemplar",
        ),
        k=1,
    )
    payload: dict[str, Any] = {
        "source": {
            "id": source.id,
            "section": source.section,
            "difficulty": source.difficulty,
            "stimulus": stimulus_of(source.stem),
            "question_sentence": question_sentence(source.stem),
            "choices": [c.model_dump() for c in source.choices],
            "correct": source.correct,
            "explanation": source.explanation,
            "type": {
                "archetype_id": source.archetype,
                "name": (
                    get_archetype(source.archetype).name if source.archetype else None
                ),
                "task": source_book.task if source_book else None,
            },
        },
        "target": {
            "archetype_id": target.id,
            "name": target.name,
            "primary_concept": target.concepts[0],
            "concepts": list(target.concepts),
            "item_writing_guidance": target.guidance,
            "cues": list(book.cues),
            "task": book.task,
            "method": list(book.method),
            "traps": [
                {"id": t, "name": traps[t].name, "summary": traps[t].summary}
                for t in book.trap_ids
            ],
        },
        "exemplar": (
            {
                "stem": exemplars[0].stem,
                "choices": [c.model_dump() for c in exemplars[0].choices],
                "correct": exemplars[0].correct,
            }
            if exemplars
            else None
        ),
    }
    if inp.critique:
        payload["critique"] = list(inp.critique)
    return payload


def _parse(
    raw: str,
    *,
    inp: ContrastInput,
    source_section: Section,
    difficulty: Difficulty,
    passage_id: str | None,
) -> ContrastDraft:
    try:
        obj = llm.loads_first_json(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"LLM response not JSON: {exc}") from exc
    body = obj.get("variation") if isinstance(obj, dict) else None
    if not isinstance(body, dict):
        raise ValueError("LLM response missing 'variation' object")
    data = dict(body)
    data["section"] = source_section
    data["difficulty"] = difficulty
    data["passage_id"] = passage_id
    data["variation_of"] = inp.question_id
    data["target_archetype_id"] = inp.target_archetype_id
    data["distractor_traps"] = _fold_traps(data.get("distractor_traps"))
    return ContrastDraft.model_validate(data)


def _fold_traps(raw: Any) -> dict[str, str]:
    """``{label: trap_id}`` from either the schema's pair list or a plain map."""
    if isinstance(raw, dict):
        return {str(k): str(v) for k, v in raw.items()}
    out: dict[str, str] = {}
    if isinstance(raw, list):
        for pair in raw:
            if isinstance(pair, dict) and pair.get("label") and pair.get("trap_id"):
                out[str(pair["label"])] = str(pair["trap_id"])
    return out


class LSATContrastAuthor:
    """Drafts one contrast variation of one bank question (spec 054).

    HITL-gated like every LSAT crew: the caller files the draft as a pending
    proposal; nothing here writes to the bank.
    """

    name = "LSATContrastAuthor"
    description = (
        "Re-asks an existing LSAT question as a different question type on the "
        "same stimulus, with a learner-facing note on what changed. Accepts a "
        "critique from the gates and the judge so a draft can be revised. Every "
        "draft is HITL-gated."
    )
    human_approval_required = True

    async def run(self, input_data: dict[str, Any]) -> ContrastOutput:
        inp = ContrastInput.model_validate(input_data)
        started = time.perf_counter()
        source = load_bank()[inp.question_id]
        prompt = (
            _load_prompt_template()
            + "\n\n## Request\n\n```json\n"
            + json.dumps(build_payload(inp), indent=2, ensure_ascii=False)
            + "\n```\n"
        )
        draft: ContrastDraft | None = None
        issues: list[str] = []
        degraded = False
        model_used = "fallback/offline"
        try:
            result = await llm.agenerate(
                prompt,
                system=_LLM_SYSTEM,
                response_schema=_RESPONSE_SCHEMA,
                agent="lsat_contrast_author",
            )
            model_used = result.model_label
            draft = _parse(
                result.text,
                inp=inp,
                source_section=source.section,
                difficulty=source.difficulty,
                passage_id=source.passage_id,
            )
        except ValidationError as exc:
            # The model answered but the draft is malformed (a field over its
            # cap, a bad label). That is a critique, not an outage.
            issues = [
                f"{'.'.join(str(p) for p in err.get('loc', ()))}: {err.get('msg')}"[
                    :300
                ]
                for err in exc.errors()
            ]
            logger.info("LSATContrastAuthor draft rejected: %s", issues)
        except (
            TimeoutError,
            httpx.HTTPError,
            OSError,
            ValueError,
            claude_code.ClaudeCodeUnavailableError,
            llm.LLMUnavailableError,
        ) as exc:
            logger.info("LSATContrastAuthor degraded: %s", exc)
            degraded = True
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning(
                "LSATContrastAuthor unexpected error: %s", exc, exc_info=True
            )
            degraded = True

        latency_ms = (time.perf_counter() - started) * 1000.0
        trace_id = provenance.log_agent_call(
            agent_name=self.name,
            input_data={
                "question_id": inp.question_id,
                "target_archetype_id": inp.target_archetype_id,
                "critique_items": len(inp.critique),
                "round": "revision" if inp.critique else "initial",
            },
            output_data={
                "drafted": draft is not None,
                "model": model_used,
                "degraded": degraded,
                "confidence": draft.confidence if draft else 0.0,
            },
            model=model_used,
            latency_ms=latency_ms,
            confidence=draft.confidence if draft else 0.0,
            sources=[{"question_id": inp.question_id}],
        )
        return ContrastOutput(
            draft=draft,
            issues=issues,
            model=model_used,
            latency_ms=round(latency_ms, 2),
            degraded=degraded,
            trace_id=trace_id,
        )
