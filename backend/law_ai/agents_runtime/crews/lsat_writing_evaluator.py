"""LSATWritingEvaluator — rubric-scored feedback on an LSAT writing draft.

Spec 047 FR-4. Given one writing prompt and a learner's response, produces a
band, an evidence quotation, and one concrete revision *per rubric criterion*.
Mirrors :mod:`lsat_solve_guide_author`: the provider chain via
``law_ai.core.llm`` (never a direct transport), a deterministic offline
fallback at confidence 0.0, and one ``provenance.log_agent_call`` parent event
per run.

``human_approval_required`` is ``True`` at the class level so the agent
registry surfaces the gate. The flag means something different here than on
the authoring crews: this output is formative feedback shown to one learner
and is never promoted into the bank, so the gate is the *display* contract —
NFR-PROV-1 requires the producing model and prompt version to travel with the
bands, and the bands are never presented as an official LSAT result (the
writing section is not scored by LSAC at all).
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any

import httpx
from pydantic import BaseModel, Field, model_validator

from law_ai.core import claude_code, llm
from law_ai.core.provenance import provenance
from law_ai.lsat.services.writing import (
    WritingPrompt,
    WritingRubric,
    load_writing_prompts,
    rubric_for,
)

logger = logging.getLogger("law_ai.agents.lsat_writing_evaluator")

PROMPT_VERSION = "lsat_writing_evaluator/1"
PROMPT_PATH = (
    Path(__file__).resolve().parent.parent / "prompts" / "lsat_writing_evaluator.v1.md"
)

#: Responses longer than this are truncated before the model sees them. A
#: 35-minute handwritten-equivalent essay runs well under 1000 words; the cap
#: bounds cost and blocks prompt-stuffing through the response field.
MAX_RESPONSE_CHARS = 12_000

#: Below this many characters there is nothing to evaluate; the API rejects
#: shorter submissions rather than spending a model call on them.
MIN_RESPONSE_CHARS = 200

_LLM_SYSTEM = (
    "You are an experienced writing instructor giving rubric-based diagnostic "
    "feedback on a practice argumentative essay. Follow the instructions "
    "exactly and respond with a single JSON object only — no preamble and no "
    "markdown code fences."
)


class EvaluateWritingInput(BaseModel):
    """Caller-supplied target: one prompt id plus the learner's draft."""

    prompt_id: str
    response: str = Field(min_length=MIN_RESPONSE_CHARS)


class CriterionScore(BaseModel):
    criterion_id: str
    band: int = Field(ge=1)
    evidence: str
    improvement: str


class WritingEvaluation(BaseModel):
    """The diagnostic reading itself (no model/provenance fields — see output)."""

    prompt_id: str
    rubric_id: str
    position_taken: str | None = Field(
        default=None,
        description="Position id the response argues for; None when the "
        "reader cannot tell, which is itself a finding.",
    )
    summary: str
    criteria: list[CriterionScore] = Field(min_length=1)
    strengths: list[str] = Field(default_factory=list)
    priorities: list[str] = Field(default_factory=list)
    weighted_band: float = Field(
        default=0.0,
        description="Criterion bands averaged by rubric weight. A study "
        "instrument only — the LSAT writing section carries no score.",
    )

    @model_validator(mode="after")
    def _one_score_per_criterion(self) -> WritingEvaluation:
        ids = [c.criterion_id for c in self.criteria]
        if len(set(ids)) != len(ids):
            raise ValueError("evaluation scores a criterion more than once")
        return self


class EvaluateWritingOutput(BaseModel):
    evaluation: WritingEvaluation
    model: str
    prompt_version: str = PROMPT_VERSION
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


def _build_user_payload(
    prompt: WritingPrompt, rubric: WritingRubric, response: str
) -> dict[str, Any]:
    return {
        "prompt": {
            "id": prompt.id,
            "issue": prompt.issue,
            "context": prompt.context,
            "positions": [p.model_dump() for p in prompt.positions],
            "perspectives": [p.model_dump() for p in prompt.perspectives],
            "task": prompt.task,
        },
        "rubric": {
            "id": rubric.id,
            "bands": [b.model_dump() for b in rubric.bands],
            "criteria": [c.model_dump() for c in rubric.criteria],
        },
        "response": response[:MAX_RESPONSE_CHARS],
    }


def weighted_band(scores: list[CriterionScore], rubric: WritingRubric) -> float:
    """Bands averaged by criterion weight, rounded to two places."""
    weights = {c.id: c.weight for c in rubric.criteria}
    total = sum(s.band * weights.get(s.criterion_id, 0.0) for s in scores)
    return round(total, 2)


def _parse_evaluation(
    raw: str, *, prompt: WritingPrompt, rubric: WritingRubric
) -> WritingEvaluation:
    """Parse + validate a model response against the rubric it was given.

    The rubric is the contract: a reading that skips a criterion, invents one,
    or lands outside the declared bands is rejected outright rather than shown
    to a learner as though it were complete.
    """
    try:
        obj = llm.loads_first_json(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"LLM response not JSON: {exc}") from exc
    body = obj.get("evaluation") if isinstance(obj, dict) else None
    if not isinstance(body, dict):
        raise ValueError("LLM response missing 'evaluation' object")

    # The agent owns the binding to the requested prompt and rubric; never
    # trust the model to echo them back correctly.
    body["prompt_id"] = prompt.id
    body["rubric_id"] = rubric.id
    body.pop("weighted_band", None)

    position_ids = {p.id for p in prompt.positions}
    if body.get("position_taken") not in position_ids:
        body["position_taken"] = None

    evaluation = WritingEvaluation.model_validate(body)

    expected = list(rubric.criterion_ids)
    scored = [c.criterion_id for c in evaluation.criteria]
    if sorted(scored) != sorted(expected):
        raise ValueError(
            f"evaluation must score exactly the rubric's criteria "
            f"{expected}, got {scored}"
        )
    levels = set(rubric.band_levels)
    outside = sorted({c.band for c in evaluation.criteria} - levels)
    if outside:
        raise ValueError(f"evaluation uses band(s) outside the rubric: {outside}")

    # Restore the rubric's own criterion order so the UI is stable regardless
    # of the order the model happened to emit.
    order = {cid: i for i, cid in enumerate(expected)}
    evaluation.criteria.sort(key=lambda c: order[c.criterion_id])
    evaluation.weighted_band = weighted_band(evaluation.criteria, rubric)
    return evaluation


def _fallback_evaluation(
    prompt: WritingPrompt, rubric: WritingRubric
) -> WritingEvaluation:
    """Deterministic placeholder when every provider fails.

    Bands sit at the rubric's lowest level with an unmistakable offline label
    and confidence 0.0, so the learner is told plainly that no reading
    happened rather than being handed feedback that looks real. Every self-
    check item in the prompt still works with no model at all — that is the
    fallback that matters (NFR-OFFLINE-1).
    """
    lowest = min(rubric.band_levels)
    return WritingEvaluation(
        prompt_id=prompt.id,
        rubric_id=rubric.id,
        position_taken=None,
        summary=(
            "[OFFLINE FALLBACK — no LLM provider reachable] Your response was "
            "not read. Score it yourself against the rubric using the "
            "self-check questions shipped with this prompt, then compare it "
            "with the annotated model response."
        ),
        criteria=[
            CriterionScore(
                criterion_id=c.id,
                band=lowest,
                evidence="[offline fallback — no evidence gathered]",
                improvement=(f"Self-score '{c.name}' against the rubric's band notes."),
            )
            for c in rubric.criteria
        ],
        strengths=[],
        priorities=["Re-run the evaluation when a model provider is reachable."],
        weighted_band=0.0,
    )


class LSATWritingEvaluator:
    """Scores one LSAT writing draft against its rubric (spec 047 FR-4)."""

    name = "LSATWritingEvaluator"
    description = (
        "Reads a learner's LSAT Argumentative Writing response against an "
        "explicit rubric and returns a band, supporting evidence, and one "
        "concrete revision per criterion. Formative feedback for a single "
        "learner — never promoted into the question bank, and never presented "
        "as an official LSAT result (the writing section is unscored)."
    )
    human_approval_required = True

    async def run(self, input_data: dict[str, Any]) -> EvaluateWritingOutput:
        inp = EvaluateWritingInput.model_validate(input_data)
        prompt = load_writing_prompts().get(inp.prompt_id)
        if prompt is None:
            raise KeyError(f"unknown writing prompt {inp.prompt_id!r}")
        rubric = rubric_for(prompt)
        started = time.perf_counter()

        full_prompt = (
            _load_prompt_template()
            + "\n\n## Request\n\n```json\n"
            + json.dumps(_build_user_payload(prompt, rubric, inp.response), indent=2)
            + "\n```\n"
        )

        degraded = False
        model_used = "fallback/offline"
        confidence = 0.0
        try:
            result = await llm.agenerate(
                full_prompt, system=_LLM_SYSTEM, agent="lsat_writing_evaluator"
            )
            model_used = result.model_label
            evaluation = _parse_evaluation(result.text, prompt=prompt, rubric=rubric)
            confidence = 0.7
        except (
            TimeoutError,
            httpx.HTTPError,
            OSError,
            ValueError,
            claude_code.ClaudeCodeUnavailableError,
            llm.LLMUnavailableError,
        ) as exc:
            logger.info("LSATWritingEvaluator falling back to offline: %s", exc)
            degraded = True
            model_used = "fallback/offline"
            evaluation = _fallback_evaluation(prompt, rubric)
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning(
                "LSATWritingEvaluator unexpected error: %s", exc, exc_info=True
            )
            degraded = True
            model_used = "fallback/offline"
            evaluation = _fallback_evaluation(prompt, rubric)

        latency_ms = (time.perf_counter() - started) * 1000.0
        trace_id = provenance.log_agent_call(
            agent_name=self.name,
            input_data={
                "prompt_id": prompt.id,
                "rubric_id": rubric.id,
                "response_chars": len(inp.response),
            },
            output_data={
                "weighted_band": evaluation.weighted_band,
                "criteria_scored": len(evaluation.criteria),
                "model": model_used,
                "confidence": confidence,
                "degraded": degraded,
            },
            model=model_used,
            latency_ms=latency_ms,
            confidence=confidence,
            sources=[],
        )

        return EvaluateWritingOutput(
            evaluation=evaluation,
            model=model_used,
            confidence=confidence,
            latency_ms=round(latency_ms, 2),
            degraded=degraded,
            trace_id=trace_id,
        )
