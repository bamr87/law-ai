"""Tests for the LSATDraftJudge crew (BL-20260702-02).

No provider is ever called: every test patches ``llm.agenerate``.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from django.conf import settings


@pytest.fixture(autouse=True)
def _isolate_audit(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "AUDIT_PATH", str(tmp_path / "audit.jsonl"))


def _draft(correct: str = "B") -> dict[str, Any]:
    return {
        "section": "LR",
        "difficulty": "med",
        "stem": "Attendance rose after the policy; the director credits it. "
        "Which one of the following, if true, most weakens the claim?",
        "choices": [
            {"label": label, "text": f"choice {label}"}
            for label in ("A", "B", "C", "D", "E")
        ],
        "correct": correct,
        "explanation": "The key severs the causal link; the rest do not.",
        "concepts": ["weaken"],
        "confidence": 0.8,
    }


def _verdict_payload(**overrides: Any) -> str:
    body = {
        "verdict": "flag",
        "single_best_answer": False,
        "solved_key": "B",
        "ambiguity": 0.4,
        "issues": ["Choice (D) is defensible under the same reading as (B)."],
        "confidence": 0.75,
        "rationale": "Two choices weaken the causal claim equally.",
    }
    body.update(overrides)
    return json.dumps({"verdict": body})


def _llm_result(text: str) -> Any:
    from law_ai.core.llm.base import LLMResult

    return LLMResult(
        text=text, provider="claude_code", model="claude-fable-5", latency_ms=1.0
    )


@pytest.mark.asyncio
async def test_run_returns_a_structured_verdict() -> None:
    from law_ai.agents_runtime.crews import lsat_draft_judge as mod

    with patch.object(
        mod.llm,
        "agenerate",
        new=AsyncMock(return_value=_llm_result(_verdict_payload())),
    ):
        out = await mod.LSATDraftJudge().run({"draft": _draft()})

    assert out.verdict.verdict == "flag"
    assert out.verdict.single_best_answer is False
    assert out.verdict.ambiguity == pytest.approx(0.4)
    assert out.verdict.issues == [
        "Choice (D) is defensible under the same reading as (B)."
    ]
    assert out.verdict.model == "claude_code/claude-fable-5"
    assert out.degraded is False
    assert out.trace_id


@pytest.mark.asyncio
async def test_key_agreement_is_computed_not_taken_from_the_model() -> None:
    """The judge's own key is compared here, so a lying model cannot claim agreement."""
    from law_ai.agents_runtime.crews import lsat_draft_judge as mod

    payload = json.loads(_verdict_payload(solved_key="E", verdict="fail"))
    payload["verdict"]["key_agrees"] = True  # the model asserts agreement
    with patch.object(
        mod.llm,
        "agenerate",
        new=AsyncMock(return_value=_llm_result(json.dumps(payload))),
    ):
        out = await mod.LSATDraftJudge().run({"draft": _draft(correct="B")})

    assert out.verdict.solved_key == "E"
    assert out.verdict.key_agrees is False


@pytest.mark.asyncio
async def test_matching_key_agrees() -> None:
    from law_ai.agents_runtime.crews import lsat_draft_judge as mod

    with patch.object(
        mod.llm,
        "agenerate",
        new=AsyncMock(
            return_value=_llm_result(_verdict_payload(solved_key="B", verdict="pass"))
        ),
    ):
        out = await mod.LSATDraftJudge().run({"draft": _draft(correct="B")})

    assert out.verdict.key_agrees is True


@pytest.mark.asyncio
async def test_unavailable_provider_degrades_instead_of_raising() -> None:
    from law_ai.agents_runtime.crews import lsat_draft_judge as mod

    with patch.object(
        mod.llm,
        "agenerate",
        new=AsyncMock(side_effect=mod.llm.LLMUnavailableError("no provider")),
    ):
        out = await mod.LSATDraftJudge().run({"draft": _draft()})

    assert out.degraded is True
    assert out.verdict.degraded is True
    # An unreachable judge must not read as a clean bill of health.
    assert out.verdict.verdict == "flag"
    assert out.verdict.confidence == 0.0
    assert out.verdict.issues and "[OFFLINE]" in out.verdict.issues[0]


@pytest.mark.asyncio
async def test_unparseable_response_degrades() -> None:
    from law_ai.agents_runtime.crews import lsat_draft_judge as mod

    with patch.object(
        mod.llm, "agenerate", new=AsyncMock(return_value=_llm_result("not json at all"))
    ):
        out = await mod.LSATDraftJudge().run({"draft": _draft()})

    assert out.degraded is True


@pytest.mark.asyncio
async def test_issue_list_is_capped() -> None:
    from law_ai.agents_runtime.crews import lsat_draft_judge as mod

    with patch.object(
        mod.llm,
        "agenerate",
        new=AsyncMock(
            return_value=_llm_result(
                _verdict_payload(issues=[f"issue {i}" for i in range(50)])
            )
        ),
    ):
        out = await mod.LSATDraftJudge().run({"draft": _draft()})

    assert len(out.verdict.issues) == mod._MAX_ISSUES


@pytest.mark.asyncio
async def test_run_writes_one_provenance_event() -> None:
    from law_ai.agents_runtime.crews import lsat_draft_judge as mod
    from law_ai.core import audit_jsonl as audit_store

    with patch.object(
        mod.llm,
        "agenerate",
        new=AsyncMock(return_value=_llm_result(_verdict_payload())),
    ):
        await mod.LSATDraftJudge().run({"draft": _draft(), "proposal_id": "prop-x"})

    events = [
        ev
        for ev in audit_store.tail(20)
        if ev.get("agent") == "LSATDraftJudge"
        or ev.get("agent_name") == "LSATDraftJudge"
    ]
    assert len(events) == 1


def test_agent_is_hitl_gated_and_registered() -> None:
    from law_ai.agents_runtime import registry
    from law_ai.agents_runtime.crews.lsat_draft_judge import LSATDraftJudge

    assert LSATDraftJudge.human_approval_required is True
    registry.register_all_agents()
    assert registry.get_agent("LSATDraftJudge") is not None
