"""LSATGuideReviewer — LLM judge tier for drafted solve guides (BL-20260830-15).

``validate_guide_quality`` (spec 045 FR-11) is a deterministic lint: it checks
shape — the guide ends with an answer step, names the correct choice, keeps
spoiler discipline, and its diagrams parse. What a lint cannot check is
whether the guide *teaches*: whether each step actually follows from the ones
before it, and whether a conditional chain or a sequence board faithfully
encodes the rules it claims to.

This agent adds that judgment before a human editor sees the draft. It is
advisory in the strictest sense (constitution §5): the verdict rides along in
the proposal's ``meta.review``, ``human_approval_required`` stays True on the
author, and ``promote_guide_to_bank`` remains human-triggered. Nothing here
can approve, publish, or reject a guide.

Mirrors :mod:`lsat_writing_evaluator`: the provider chain via
``law_ai.core.llm`` (never a direct transport), a deterministic offline
fallback at confidence 0.0, and one ``provenance.log_agent_call`` per run.
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any, Literal

import httpx
from pydantic import BaseModel, Field

from law_ai.core import claude_code, llm
from law_ai.core.provenance import provenance

logger = logging.getLogger("law_ai.agents.lsat_guide_reviewer")

PROMPT_VERSION = "lsat_guide_reviewer/1"
PROMPT_PATH = (
    Path(__file__).resolve().parent.parent / "prompts" / "lsat_guide_reviewer.v1.md"
)

_MAX_PASSAGE_CHARS = 6_000

Verdict = Literal["pass", "revise", "reject", "unreviewed"]

_LLM_SYSTEM = (
    "You are an experienced LSAT instructor reviewing a drafted solve guide "
    "for pedagogical soundness. Follow the instructions exactly and respond "
    "with a single JSON object only — no preamble and no markdown code fences."
)


class StepFinding(BaseModel):
    """Whether one step of the guide follows from what precedes it."""

    index: int = Field(ge=1)
    follows: bool = True
    note: str = ""


class GuideReview(BaseModel):
    """Advisory pedagogical review of one drafted solve guide."""

    verdict: Verdict = "unreviewed"
    symbolization_faithful: bool = True
    step_findings: list[StepFinding] = Field(default_factory=list)
    summary: str = ""
    confidence: float = Field(0.0, ge=0.0, le=1.0)
    model: str = "fallback/offline"
    prompt_version: str = PROMPT_VERSION
    degraded: bool = Field(
        default=False,
        description="True when no provider answered and no judgment was made.",
    )
    latency_ms: float = 0.0
    trace_id: str | None = None


def _load_prompt_template() -> str:
    if not PROMPT_PATH.is_file():  # pragma: no cover - prompts ship with code
        raise FileNotFoundError(f"missing prompt file: {PROMPT_PATH}")
    return PROMPT_PATH.read_text(encoding="utf-8")


def _question_payload(question: Any, passage: Any = None) -> dict[str, Any]:
    text = ""
    rules: list[str] = []
    if passage is not None:
        text = str(getattr(passage, "passage", "") or getattr(passage, "setup", ""))
        rules = [str(r) for r in (getattr(passage, "rules", None) or [])]
    return {
        "id": str(getattr(question, "id", "")),
        "section": str(getattr(question, "section", "")),
        "difficulty": str(getattr(question, "difficulty", "")),
        "stem": str(getattr(question, "stem", "")),
        "choices": [
            {"label": str(c.label), "text": str(c.text)}
            for c in (getattr(question, "choices", None) or [])
        ],
        "correct": str(getattr(question, "correct", "")),
        "passage": text[:_MAX_PASSAGE_CHARS] or None,
        "rules": rules,
    }


def _guide_payload(guide: Any) -> dict[str, Any]:
    steps = getattr(guide, "steps", None) or []
    return {
        "method": str(getattr(guide, "method", "")),
        "steps": [
            {
                "index": i,
                "kind": str(getattr(s, "kind", "")),
                "title": str(getattr(s, "title", "")),
                "text": str(getattr(s, "text", "")),
                "representation": (
                    s.representation.model_dump()
                    if getattr(s, "representation", None) is not None
                    else None
                ),
            }
            for i, s in enumerate(steps, start=1)
        ],
    }


def _parse_review(text: str, *, step_count: int) -> GuideReview:
    payload = llm.loads_first_json(text)
    if not isinstance(payload, dict):
        raise ValueError("guide reviewer response was not a JSON object")
    raw_verdict = str(payload.get("verdict") or "").strip().lower()
    verdict: Verdict = (
        raw_verdict  # type: ignore[assignment]
        if raw_verdict in ("pass", "revise", "reject")
        else "unreviewed"
    )
    findings: list[StepFinding] = []
    for entry in payload.get("step_findings") or []:
        if not isinstance(entry, dict):
            continue
        try:
            index = int(entry.get("index", 0))
        except (TypeError, ValueError):
            continue
        if not 1 <= index <= step_count:
            continue
        findings.append(
            StepFinding(
                index=index,
                follows=bool(entry.get("follows", True)),
                note=str(entry.get("note") or "").strip()[:400],
            )
        )
    # Hard rule 3: a guide with a broken step cannot pass, whatever the model
    # wrote in `verdict`. The gate is ours, not the model's.
    if verdict == "pass" and any(not f.follows for f in findings):
        verdict = "revise"
    try:
        confidence = min(1.0, max(0.0, float(payload.get("confidence", 0.0))))
    except (TypeError, ValueError):
        confidence = 0.0
    return GuideReview(
        verdict=verdict,
        symbolization_faithful=bool(payload.get("symbolization_faithful", True)),
        step_findings=findings,
        summary=str(payload.get("summary") or "").strip()[:1_200],
        confidence=confidence,
    )


def _offline_review() -> GuideReview:
    """No provider answered — say so; never let silence read as approval."""
    return GuideReview(
        verdict="unreviewed",
        summary=(
            "No provider was reachable, so no pedagogical review was performed. "
            "The deterministic lint still ran; step-by-step soundness and "
            "symbolization fidelity were NOT judged."
        ),
        confidence=0.0,
        degraded=True,
    )


class LSATGuideReviewer:
    """Judge tier for solve-guide drafts. Advisory only — never promotes."""

    name = "LSATGuideReviewer"
    description = (
        "Reads one drafted LSAT solve guide against its question and judges "
        "pedagogical soundness: does each step follow, and is the "
        "symbolization faithful to the rules? Runs after the deterministic "
        "lint and before a human editor. Advisory only — it never approves "
        "or promotes a guide (constitution §5)."
    )
    human_approval_required = True

    async def run(self, input_data: dict[str, Any]) -> GuideReview:
        guide = input_data.get("guide")
        if guide is None:
            raise ValueError("LSATGuideReviewer requires input_data['guide']")
        question = input_data.get("question")
        if question is None:
            question = self._load_question(
                str(input_data.get("question_id") or getattr(guide, "question_id", ""))
            )
        passage = input_data.get("passage")
        if passage is None and getattr(question, "passage_id", None):
            passage = self._load_passage(str(question.passage_id))

        started = time.perf_counter()
        payload = {
            "question": _question_payload(question, passage),
            "guide": _guide_payload(guide),
        }
        step_count = len(payload["guide"]["steps"])
        full_prompt = (
            _load_prompt_template()
            + "\n\n## Request\n\n```json\n"
            + json.dumps(payload, indent=2)
            + "\n```\n"
        )

        try:
            result = await llm.agenerate(
                full_prompt,
                system=_LLM_SYSTEM,
                json_mode=True,
                agent="lsat_guide_reviewer",
            )
            review = _parse_review(result.text, step_count=step_count)
            review.model = result.model_label
        except (
            TimeoutError,
            httpx.HTTPError,
            OSError,
            ValueError,
            claude_code.ClaudeCodeUnavailableError,
            llm.LLMUnavailableError,
        ) as exc:
            logger.info("LSATGuideReviewer falling back to offline: %s", exc)
            review = _offline_review()
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("LSATGuideReviewer unexpected error: %s", exc, exc_info=True)
            review = _offline_review()

        review.latency_ms = (time.perf_counter() - started) * 1000.0
        review.trace_id = provenance.log_agent_call(
            agent_name=self.name,
            input_data={
                "question_id": payload["question"]["id"],
                "step_count": step_count,
                "prompt_version": PROMPT_VERSION,
            },
            output_data=review.model_dump(),
            model=review.model,
            latency_ms=review.latency_ms,
            confidence=review.confidence,
        )
        return review

    @staticmethod
    def _load_question(question_id: str) -> Any:
        from law_ai.lsat.services.bank import load_bank

        question = load_bank().get(question_id)
        if question is None:
            raise KeyError(f"unknown question {question_id!r}")
        return question

    @staticmethod
    def _load_passage(passage_id: str) -> Any:
        from law_ai.lsat.services.bank import load_passages

        return load_passages().get(passage_id)


async def review_guide(guide: Any, *, question: Any = None) -> dict[str, Any] | None:
    """Review one guide, returning the review dict or ``None`` on failure.

    The entry point ``GuideGenerateView`` and ``lsat_guide_backfill`` use. A
    reviewer failure must never lose the draft, so it degrades to ``None`` and
    the proposal is filed unreviewed.
    """
    try:
        review = await LSATGuideReviewer().run({"guide": guide, "question": question})
        return review.model_dump()
    except Exception as exc:
        logger.warning("guide review failed: %s", exc, exc_info=True)
        return None
