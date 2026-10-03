"""LSATQuestionEditor — rewrites one bank item to a judge's objections (spec 054).

The judge tier could say what was wrong with an item; nothing could fix it.
This crew takes a bank question and a critique — the objections the judge
raised — and returns the minimal rewrite that answers them, keeping the
item's type, difficulty and (where a contrast set depends on it) its
stimulus. The rewrite is filed as a ``rewrite`` proposal and promoted in
place by a human, so the question keeps its id and its learners' history.

Same contract as the other crews: the provider chain via ``law_ai.core.llm``,
one ``provenance.log_agent_call`` per run, no draft when no provider
answers, and shape errors reported as objections the loop can revise on.
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
from law_ai.lsat.factory.taxonomy import get_archetype
from law_ai.lsat.services.bank import (
    ChoiceLabel,
    Difficulty,
    Section,
    load_bank,
    load_passages,
)
from law_ai.lsat.services.contrast import contrast_set
from law_ai.lsat.services.playbooks import load_playbooks

logger = logging.getLogger("law_ai.agents.lsat_question_editor")

PROMPT_VERSION = "lsat_question_editor/1"
PROMPT_PATH = (
    Path(__file__).resolve().parent.parent / "prompts" / "lsat_question_editor.v1.md"
)

_CHOICE_LABELS: tuple[ChoiceLabel, ...] = ("A", "B", "C", "D", "E")
_MAX_PASSAGE_CHARS = 4000
_MAX_CRITIQUE_ITEMS = 12

_LLM_SYSTEM = (
    "You are a senior LSAT test editor making the minimal rewrite that answers "
    "a reviewer's objections. Respond with a single JSON object only — no "
    "preamble and no markdown code fences."
)

_RESPONSE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "edited": {
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
                "change_summary": {"type": "string"},
                "confidence": {"type": "number"},
            },
            "required": [
                "stem",
                "choices",
                "correct",
                "explanation",
                "concepts",
                "change_summary",
                "confidence",
            ],
            "additionalProperties": False,
        }
    },
    "required": ["edited"],
    "additionalProperties": False,
}


class EditInput(BaseModel):
    question_id: str
    critique: list[str] = Field(default_factory=list, max_length=_MAX_CRITIQUE_ITEMS)


class EditChoice(BaseModel):
    label: ChoiceLabel
    text: str = Field(max_length=400)


class EditedDraft(BaseModel):
    """The rewritten item, still addressed to its bank id."""

    question_id: str
    section: Section
    difficulty: Difficulty
    stem: str = Field(max_length=2500)
    choices: list[EditChoice] = Field(min_length=5, max_length=5)
    correct: ChoiceLabel
    explanation: str = Field(max_length=2000)
    concepts: list[str] = Field(default_factory=list)
    passage_id: str | None = None
    change_summary: str = Field(max_length=800)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)

    @model_validator(mode="after")
    def _check_labels(self) -> EditedDraft:
        if [c.label for c in self.choices] != list(_CHOICE_LABELS):
            raise ValueError("choices must be labelled A,B,C,D,E in order")
        return self


class EditOutput(BaseModel):
    draft: EditedDraft | None
    issues: list[str] = Field(default_factory=list)
    model: str = "fallback/offline"
    latency_ms: float = 0.0
    degraded: bool = False
    trace_id: str | None = None


def _load_prompt_template() -> str:
    if not PROMPT_PATH.is_file():  # pragma: no cover - prompts ship with code
        raise FileNotFoundError(f"missing prompt file: {PROMPT_PATH}")
    return PROMPT_PATH.read_text(encoding="utf-8")


def build_payload(inp: EditInput) -> dict[str, Any]:
    """The item, its type's playbook, whether its stimulus is shared, the critique.

    >>> build_payload(EditInput(question_id="lr-002", critique=["x"]))["shares_stimulus"]
    True
    """
    q = load_bank()[inp.question_id]
    book = load_playbooks().get(q.archetype or "")
    archetype = get_archetype(q.archetype) if q.archetype else None
    payload: dict[str, Any] = {
        "item": {
            "id": q.id,
            "section": q.section,
            "difficulty": q.difficulty,
            "stem": q.stem,
            "choices": [c.model_dump() for c in q.choices],
            "correct": q.correct,
            "explanation": q.explanation,
            "concepts": list(q.concepts),
        },
        "type": {
            "archetype_id": q.archetype,
            "name": archetype.name if archetype else None,
            "task": book.task if book else None,
            "cues": list(book.cues) if book else [],
            "item_writing_guidance": archetype.guidance if archetype else None,
        },
        "shares_stimulus": len(contrast_set(q.id)) > 1,
        "critique": list(inp.critique),
    }
    passage = load_passages().get(q.passage_id) if q.passage_id else None
    if passage is not None:
        payload["passage"] = {
            "title": passage.title,
            "passage": (passage.passage or "")[:_MAX_PASSAGE_CHARS],
            "setup": (passage.setup or "")[:_MAX_PASSAGE_CHARS],
            "rules": list(passage.rules),
        }
    return payload


def _parse(raw: str, *, inp: EditInput) -> EditedDraft:
    try:
        obj = llm.loads_first_json(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"LLM response not JSON: {exc}") from exc
    body = obj.get("edited") if isinstance(obj, dict) else None
    if not isinstance(body, dict):
        raise ValueError("LLM response missing 'edited' object")
    q = load_bank()[inp.question_id]
    data = dict(body)
    data["question_id"] = q.id
    data["section"] = q.section
    data["difficulty"] = q.difficulty
    data["passage_id"] = q.passage_id
    return EditedDraft.model_validate(data)


class LSATQuestionEditor:
    """Minimal rewrite of one bank item to a critique (spec 054). HITL-gated."""

    name = "LSATQuestionEditor"
    description = (
        "Rewrites an existing LSAT bank question to answer a judge's objections "
        "while keeping its type, difficulty and shared stimulus. The rewrite is "
        "a pending proposal a human promotes in place; the crew never touches "
        "the bank."
    )
    human_approval_required = True

    async def run(self, input_data: dict[str, Any]) -> EditOutput:
        inp = EditInput.model_validate(input_data)
        started = time.perf_counter()
        prompt = (
            _load_prompt_template()
            + "\n\n## Request\n\n```json\n"
            + json.dumps(build_payload(inp), indent=2, ensure_ascii=False)
            + "\n```\n"
        )
        draft: EditedDraft | None = None
        issues: list[str] = []
        degraded = False
        model_used = "fallback/offline"
        try:
            result = await llm.agenerate(
                prompt,
                system=_LLM_SYSTEM,
                response_schema=_RESPONSE_SCHEMA,
                agent="lsat_question_editor",
            )
            model_used = result.model_label
            draft = _parse(result.text, inp=inp)
        except ValidationError as exc:
            issues = [
                f"{'.'.join(str(p) for p in err.get('loc', ()))}: {err.get('msg')}"[
                    :300
                ]
                for err in exc.errors()
            ]
            logger.info("LSATQuestionEditor draft rejected: %s", issues)
        except (
            TimeoutError,
            httpx.HTTPError,
            OSError,
            ValueError,
            claude_code.ClaudeCodeUnavailableError,
            llm.LLMUnavailableError,
        ) as exc:
            logger.info("LSATQuestionEditor degraded: %s", exc)
            degraded = True
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning(
                "LSATQuestionEditor unexpected error: %s", exc, exc_info=True
            )
            degraded = True
        latency_ms = (time.perf_counter() - started) * 1000.0
        trace_id = provenance.log_agent_call(
            agent_name=self.name,
            input_data={
                "question_id": inp.question_id,
                "critique_items": len(inp.critique),
            },
            output_data={
                "drafted": draft is not None,
                "model": model_used,
                "degraded": degraded,
                "issues": len(issues),
            },
            model=model_used,
            latency_ms=latency_ms,
            confidence=draft.confidence if draft else 0.0,
            sources=[{"question_id": inp.question_id}],
        )
        return EditOutput(
            draft=draft,
            issues=issues,
            model=model_used,
            latency_ms=round(latency_ms, 2),
            degraded=degraded,
            trace_id=trace_id,
        )
