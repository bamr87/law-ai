"""LSATDraftJudge — adversarial review of one drafted LSAT item.

BL-20260702-02 (spec 024's ``judge`` tier, extending BL-20260527-04's
reviewer-agent idea to the factory path). The content factory's intake gates
are mechanical — schema, concept lint, dedup, key balance. None of them can
say whether an item *works*: whether the keyed choice is really the only
defensible one, whether two choices are both arguable, whether the stem gives
the answer away. This agent asks a model to attack the draft on those axes and
returns a structured verdict.

The verdict is **advisory metadata**. It rides on the proposal's
``meta.factory.judge`` block so a human reviewer sees the objection before
deciding, and it never promotes, rejects, or reorders anything: the HITL gate
(constitution §5) stays exactly where it was. Auto-promotion on a ``pass``
verdict is spec 047 FR-20's separate, gated decision.

Mirrors the other LSAT crews: the provider chain via ``law_ai.core.llm``
(never a direct transport), one ``provenance.log_agent_call`` per run, and a
degraded verdict — never an exception — when every provider is unavailable, so
an offline factory run still finishes with an auditable trail.
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
from law_ai.lsat.services.bank import ChoiceLabel, PassageContext, load_passages

logger = logging.getLogger("law_ai.agents.lsat_draft_judge")

PROMPT_VERSION = "lsat_draft_judge/1"
PROMPT_PATH = (
    Path(__file__).resolve().parent.parent / "prompts" / "lsat_draft_judge.v1.md"
)

_MAX_PASSAGE_CHARS = 4000
_MAX_ISSUES = 12
_MAX_ISSUE_CHARS = 400

Verdict = Literal["pass", "flag", "fail"]

_LLM_SYSTEM = (
    "You are a hostile LSAT test-development reviewer. Solve the item "
    "yourself before judging it. Respond with a single JSON object only — no "
    "preamble and no markdown code fences."
)

_VERDICT_RESPONSE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "verdict": {
            "type": "object",
            "properties": {
                "verdict": {"type": "string", "enum": ["pass", "flag", "fail"]},
                "single_best_answer": {"type": "boolean"},
                "solved_key": {
                    "type": "string",
                    "enum": ["A", "B", "C", "D", "E"],
                },
                "ambiguity": {"type": "number"},
                "issues": {"type": "array", "items": {"type": "string"}},
                "confidence": {"type": "number"},
                "rationale": {"type": "string"},
            },
            "required": [
                "verdict",
                "single_best_answer",
                "ambiguity",
                "issues",
                "confidence",
                "rationale",
            ],
            "additionalProperties": False,
        }
    },
    "required": ["verdict"],
    "additionalProperties": False,
}


class JudgeVerdict(BaseModel):
    """One adversarial review of one draft."""

    verdict: Verdict = Field(
        description="pass = publishable, flag = a reviewer must resolve "
        "something, fail = key wrong / two defensible choices / unanswerable."
    )
    single_best_answer: bool = Field(
        default=True,
        description="False when a second choice is defensible under the stem.",
    )
    solved_key: ChoiceLabel | None = Field(
        default=None,
        description="The key the judge reached on its own, before reading the "
        "drafted one; None when the judge did not report it.",
    )
    key_agrees: bool | None = Field(
        default=None,
        description="Whether solved_key matches the draft's stated key "
        "(computed here, never taken from the model).",
    )
    ambiguity: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="0 = airtight, 1 = coin flip between two choices.",
    )
    issues: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    rationale: str = ""
    model: str = "fallback/offline"
    prompt_version: str = PROMPT_VERSION
    degraded: bool = Field(
        default=False,
        description="True when no provider answered and the verdict is a "
        "placeholder that decides nothing.",
    )


class JudgeDraftInput(BaseModel):
    """One draft to review (a ``DraftQuestion``-shaped dict) plus its context."""

    draft: dict[str, Any]
    passage_id: str | None = None
    proposal_id: str | None = None
    #: Spec 054: pin the Claude tiers to one model id — how the final review
    #: runs on Fable regardless of the deployment's default tier model.
    model_override: str | None = None


def model_overrides(model_id: str | None) -> dict[str, str]:
    """``models=`` mapping pinning both Claude tiers to ``model_id`` (empty when None).

    >>> model_overrides("claude-fable-5-1")["claude_code"]
    'claude-fable-5-1'
    """
    if not model_id:
        return {}
    return {"claude_code": model_id, "anthropic_api": model_id}


class JudgeDraftOutput(BaseModel):
    verdict: JudgeVerdict
    model: str = "fallback/offline"
    latency_ms: float = 0.0
    degraded: bool = False
    trace_id: str | None = None


def _load_prompt_template() -> str:
    if not PROMPT_PATH.is_file():  # pragma: no cover - prompts ship with code
        raise FileNotFoundError(f"missing prompt file: {PROMPT_PATH}")
    return PROMPT_PATH.read_text(encoding="utf-8")


def _build_user_payload(
    draft: dict[str, Any], passage: PassageContext | None
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "item": {
            "section": draft.get("section"),
            "difficulty": draft.get("difficulty"),
            "stem": draft.get("stem"),
            "choices": draft.get("choices"),
            "stated_key": draft.get("correct"),
            "explanation": draft.get("explanation"),
            "concepts": draft.get("concepts"),
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


def _parse_verdict(raw: str, *, stated_key: str | None) -> JudgeVerdict:
    """Validate the model's verdict; the key comparison is computed here."""
    try:
        obj = llm.loads_first_json(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"judge response not JSON: {exc}") from exc
    body = obj.get("verdict") if isinstance(obj, dict) else None
    if not isinstance(body, dict):
        raise ValueError("judge response missing 'verdict' object")
    data = dict(body)
    issues = data.get("issues")
    if isinstance(issues, list):
        data["issues"] = [
            str(issue)[:_MAX_ISSUE_CHARS] for issue in issues[:_MAX_ISSUES]
        ]
    # Never let the model self-report agreement with the key it was shown.
    data.pop("key_agrees", None)
    data.pop("degraded", None)
    verdict = JudgeVerdict.model_validate(data)
    if verdict.solved_key is not None and stated_key:
        verdict = verdict.model_copy(
            update={"key_agrees": verdict.solved_key == stated_key}
        )
    return verdict


def _degraded_verdict(detail: str) -> JudgeVerdict:
    """Placeholder verdict used when no provider answered.

    ``flag`` rather than ``pass`` or ``fail``: an unavailable judge must never
    look like a clean bill of health, and must never look like a defect
    either. Confidence 0.0 marks it as deciding nothing.
    """
    return JudgeVerdict(
        verdict="flag",
        single_best_answer=True,
        ambiguity=0.0,
        issues=[f"[OFFLINE] judge unavailable — item not reviewed ({detail})"[:400]],
        confidence=0.0,
        rationale="No provider answered; this item reached the queue unjudged.",
        model="fallback/offline",
        degraded=True,
    )


class LSATDraftJudge:
    """Adversarially reviews one drafted LSAT item (BL-20260702-02).

    Advisory only: the verdict is attached to the proposal's meta for the
    human reviewer. Nothing here promotes or rejects a draft.
    """

    name = "LSATDraftJudge"
    description = (
        "Adversarially reviews a drafted LSAT item for single-best-answer "
        "violations, ambiguity, weak distractors, and answer leakage. The "
        "verdict is advisory metadata on the HITL proposal — it never "
        "promotes or rejects anything."
    )
    human_approval_required = True

    async def run(self, input_data: dict[str, Any]) -> JudgeDraftOutput:
        inp = JudgeDraftInput.model_validate(input_data)
        started = time.perf_counter()

        passage: PassageContext | None = None
        passage_id = inp.passage_id or inp.draft.get("passage_id")
        if passage_id:
            passage = load_passages().get(str(passage_id))

        prompt = (
            _load_prompt_template()
            + "\n\n## Item under review\n\n```json\n"
            + json.dumps(_build_user_payload(inp.draft, passage), indent=2)
            + "\n```\n"
        )

        stated_key = inp.draft.get("correct")
        try:
            result = await llm.agenerate(
                prompt,
                system=_LLM_SYSTEM,
                response_schema=_VERDICT_RESPONSE_SCHEMA,
                agent="lsat_draft_judge",
                models=model_overrides(inp.model_override),
            )
            verdict = _parse_verdict(
                result.text, stated_key=str(stated_key) if stated_key else None
            )
            verdict = verdict.model_copy(update={"model": result.model_label})
        except (
            TimeoutError,
            httpx.HTTPError,
            OSError,
            ValueError,
            claude_code.ClaudeCodeUnavailableError,
            llm.LLMUnavailableError,
        ) as exc:
            logger.info("LSATDraftJudge degraded: %s", exc)
            verdict = _degraded_verdict(str(exc)[:200])
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("LSATDraftJudge unexpected error: %s", exc, exc_info=True)
            verdict = _degraded_verdict(str(exc)[:200])

        latency_ms = (time.perf_counter() - started) * 1000.0
        trace_id = provenance.log_agent_call(
            agent_name=self.name,
            input_data={
                "proposal_id": inp.proposal_id,
                "section": inp.draft.get("section"),
                "difficulty": inp.draft.get("difficulty"),
                "passage_id": passage_id,
                "model_override": inp.model_override,
            },
            output_data={
                "verdict": verdict.verdict,
                "single_best_answer": verdict.single_best_answer,
                "ambiguity": verdict.ambiguity,
                "issue_count": len(verdict.issues),
                "key_agrees": verdict.key_agrees,
                "degraded": verdict.degraded,
            },
            model=verdict.model,
            latency_ms=latency_ms,
            confidence=verdict.confidence,
            sources=[],
        )

        return JudgeDraftOutput(
            verdict=verdict,
            model=verdict.model,
            latency_ms=round(latency_ms, 2),
            degraded=verdict.degraded,
            trace_id=trace_id,
        )
