"""LSATSolveGuideAuthor — drafts solve guides for existing LSAT questions.

Spec 045 (FR-9). Given one bank question, drafts a :class:`SolveGuide` —
an ordered hint walkthrough with typed diagram payloads — for HITL review.
Mirrors :mod:`lsat_content_author`: provider chain via ``law_ai.core.llm``
(never a direct transport), deterministic offline fallback with confidence
0.0, one ``provenance.log_agent_call`` parent event per run, and a
class-level ``human_approval_required = True`` so the registry surfaces the
gate. The draft is persisted by the caller as a ``proposal_kind="guide"``
proposal; nothing this agent produces can serve to learners until a
reviewer promotes it via ``promote_guide_to_bank``.
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any

import httpx
from pydantic import BaseModel, Field

from law_ai.core import claude_code, llm
from law_ai.core.provenance import provenance
from law_ai.lsat.services.bank import PassageContext, Question, load_passages
from law_ai.lsat.services.guides import (
    SolveGuide,
    SolveStep,
    validate_guide_quality,
)

logger = logging.getLogger("law_ai.agents.lsat_solve_guide_author")

PROMPT_VERSION = "lsat_solve_guide_author/1"
PROMPT_PATH = (
    Path(__file__).resolve().parent.parent / "prompts" / "lsat_solve_guide_author.v1.md"
)

_MAX_PASSAGE_CHARS = 4000

_LLM_SYSTEM = (
    "You are an LSAT methods instructor writing a step-by-step solve guide. "
    "Follow the instructions exactly and respond with a single JSON object "
    "only — no preamble and no markdown code fences. Steps before the final "
    "answer step must never reveal the correct choice."
)


class GenerateGuideInput(BaseModel):
    """Caller-supplied target: one existing bank question."""

    question_id: str


class GenerateGuideOutput(BaseModel):
    guide: SolveGuide
    model: str
    confidence: float = Field(0.0, ge=0.0, le=1.0)
    latency_ms: float = 0.0
    degraded: bool = Field(
        False,
        description="True when every provider failed and the fallback was used.",
    )
    trace_id: str | None = None


def _load_prompt_template() -> str:
    if not PROMPT_PATH.is_file():  # pragma: no cover - prompts ship with code
        raise FileNotFoundError(f"missing prompt file: {PROMPT_PATH}")
    return PROMPT_PATH.read_text(encoding="utf-8")


def _build_user_payload(q: Question, passage: PassageContext | None) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "question": {
            "id": q.id,
            "section": q.section,
            "difficulty": q.difficulty,
            "stem": q.stem,
            "choices": [{"label": c.label, "text": c.text} for c in q.choices],
            "correct": q.correct,
            "explanation": q.explanation,
            "concepts": list(q.concepts),
        }
    }
    if passage is not None:
        payload["passage"] = {
            "title": passage.title,
            "passage": (passage.passage or "")[:_MAX_PASSAGE_CHARS],
            "setup": (passage.setup or "")[:_MAX_PASSAGE_CHARS],
            "rules": list(passage.rules),
        }
    return payload


def _parse_guide(raw: str, *, question: Question) -> SolveGuide:
    try:
        obj = llm.loads_first_json(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"LLM response not JSON: {exc}") from exc
    guide_obj = obj.get("guide") if isinstance(obj, dict) else None
    if not isinstance(guide_obj, dict):
        raise ValueError("LLM response missing 'guide' object")
    # The agent owns the binding to the requested question; never trust the
    # model to echo the right id.
    guide_obj["question_id"] = question.id
    guide_obj["source"] = f"LSATSolveGuideAuthor ({PROMPT_VERSION})"
    guide = SolveGuide.model_validate(guide_obj)
    if len(guide.steps) < 2:
        raise ValueError("guide must have at least two steps")
    # Content-level validation (spec 045 FR-11): answer-leak, elimination
    # completeness, board consistency. A draft that fails degrades to the
    # offline fallback instead of entering the queue looking plausible.
    problems = validate_guide_quality(guide, question)
    if problems:
        raise ValueError("guide failed quality checks: " + "; ".join(problems))
    return guide


def _fallback_guide(q: Question) -> SolveGuide:
    """Deterministic placeholder when every provider fails.

    Confidence 0.0 and an unmistakable offline label so reviewers always
    reject it; it exists to keep the cycle auditable, not to ship content.
    """
    return SolveGuide(
        question_id=q.id,
        method="[OFFLINE FALLBACK] author a walkthrough by hand",
        steps=[
            SolveStep(
                kind="orient",
                title="Offline fallback",
                text=(
                    "[OFFLINE FALLBACK — no LLM provider reachable] Draft a "
                    f"step-by-step solve guide for {q.section} question "
                    f"{q.id} by hand. This draft MUST be rejected by a "
                    "reviewer."
                ),
            ),
            SolveStep(
                kind="answer",
                title="Placeholder answer step",
                text="Offline fallback — no real walkthrough was generated.",
                spoiler=True,
            ),
        ],
        source=f"LSATSolveGuideAuthor ({PROMPT_VERSION}, offline fallback)",
    )


class LSATSolveGuideAuthor:
    """Drafts a progressive solve guide for one bank question (spec 045 FR-9)."""

    name = "LSATSolveGuideAuthor"
    description = (
        "Drafts step-by-step solve guides (hints + diagrams) for existing "
        "LSAT questions. Every draft is HITL-gated; nothing serves to "
        "learners without explicit reviewer approval."
    )
    human_approval_required = True

    async def run(self, input_data: dict[str, Any]) -> GenerateGuideOutput:
        from law_ai.lsat.services.bank import load_bank

        inp = GenerateGuideInput.model_validate(input_data)
        q = load_bank().get(inp.question_id)
        if q is None:
            raise KeyError(f"unknown question {inp.question_id!r}")
        started = time.perf_counter()

        passage: PassageContext | None = None
        if q.passage_id:
            passage = load_passages().get(q.passage_id)

        prompt = (
            _load_prompt_template()
            + "\n\n## Request\n\n```json\n"
            + json.dumps(_build_user_payload(q, passage), indent=2)
            + "\n```\n"
        )

        degraded = False
        model_used = "fallback/offline"
        confidence = 0.0
        try:
            result = await llm.agenerate(
                prompt, system=_LLM_SYSTEM, agent="lsat_guide_author"
            )
            model_used = result.model_label
            guide = _parse_guide(result.text, question=q)
            confidence = 0.7
        except (
            TimeoutError,
            httpx.HTTPError,
            OSError,
            ValueError,
            claude_code.ClaudeCodeUnavailableError,
            llm.LLMUnavailableError,
        ) as exc:
            logger.info("LSATSolveGuideAuthor falling back to offline: %s", exc)
            degraded = True
            model_used = "fallback/offline"
            guide = _fallback_guide(q)
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning(
                "LSATSolveGuideAuthor unexpected error: %s", exc, exc_info=True
            )
            degraded = True
            model_used = "fallback/offline"
            guide = _fallback_guide(q)

        latency_ms = (time.perf_counter() - started) * 1000.0
        trace_id = provenance.log_agent_call(
            agent_name=self.name,
            input_data={"question_id": q.id, "section": q.section},
            output_data={
                "step_count": len(guide.steps),
                "model": model_used,
                "confidence": confidence,
                "degraded": degraded,
            },
            model=model_used,
            latency_ms=latency_ms,
            confidence=confidence,
            sources=[],
        )

        return GenerateGuideOutput(
            guide=guide,
            model=model_used,
            confidence=confidence,
            latency_ms=round(latency_ms, 2),
            degraded=degraded,
            trace_id=trace_id,
        )
