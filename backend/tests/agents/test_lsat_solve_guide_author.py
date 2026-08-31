"""Tests for the LSATSolveGuideAuthor crew (spec 041 T-005, AC-6)."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from django.conf import settings


@pytest.fixture(autouse=True)
def _isolate_audit(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "AUDIT_PATH", str(tmp_path / "audit.jsonl"))


def _question_id() -> str:
    from law_ai.lsat.services.bank import load_bank

    return next(iter(load_bank()))


def _valid_guide_payload(question_id: str) -> str:
    from law_ai.lsat.services.bank import load_bank

    correct = load_bank()[question_id].correct
    return json.dumps(
        {
            "guide": {
                "question_id": "wrong-id-the-agent-must-override",
                "method": "Symbolize then eliminate",
                "steps": [
                    {"kind": "orient", "title": "Read", "text": "Read the stem."},
                    {
                        "kind": "symbolize",
                        "title": "Notate",
                        "text": "Turn the rule into arrows.",
                        "representation": {
                            "rep_type": "notation",
                            "rules": [
                                {"rule_text": "If P then Q.", "symbols": "P → Q"}
                            ],
                        },
                    },
                    {"kind": "infer", "title": "Chain", "text": "Apply it."},
                    {
                        "kind": "answer",
                        "title": "Answer",
                        "text": f"So the answer is {correct}.",
                        "spoiler": True,
                    },
                ],
            }
        }
    )


def _llm_result(text: str):
    from law_ai.core.llm.base import LLMResult

    return LLMResult(
        text=text, provider="claude_code", model="claude-opus-5", latency_ms=1.0
    )


@pytest.mark.asyncio
async def test_run_returns_validated_guide() -> None:
    from law_ai.agents_runtime.crews import lsat_solve_guide_author as mod
    from law_ai.lsat.services.guides import SolveGuide

    qid = _question_id()
    with patch.object(
        mod.llm,
        "agenerate",
        new=AsyncMock(return_value=_llm_result(_valid_guide_payload(qid))),
    ):
        output = await mod.LSATSolveGuideAuthor().run({"question_id": qid})

    assert output.degraded is False
    assert output.model == "claude_code/claude-opus-5"
    guide = SolveGuide.model_validate(output.guide.model_dump(by_alias=True))
    # The agent binds the guide to the requested question, not the echoed id.
    assert guide.question_id == qid
    assert guide.steps[-1].kind == "answer"
    assert guide.steps[-1].spoiler is True
    assert output.trace_id


@pytest.mark.asyncio
async def test_run_degrades_offline_with_zero_confidence() -> None:
    from law_ai.agents_runtime.crews import lsat_solve_guide_author as mod

    async def boom(*args: object, **kwargs: object) -> object:
        raise mod.llm.LLMUnavailableError("every provider failed")

    qid = _question_id()
    with patch.object(mod.llm, "agenerate", new=boom):
        output = await mod.LSATSolveGuideAuthor().run({"question_id": qid})

    assert output.degraded is True
    assert output.confidence == 0.0
    assert output.model == "fallback/offline"
    assert "OFFLINE FALLBACK" in output.guide.steps[0].text


@pytest.mark.asyncio
async def test_run_rejects_guide_without_answer_step() -> None:
    from law_ai.agents_runtime.crews import lsat_solve_guide_author as mod

    qid = _question_id()
    bad = json.dumps(
        {
            "guide": {
                "question_id": qid,
                "method": "m",
                "steps": [
                    {"kind": "orient", "title": "Read", "text": "Read."},
                    {"kind": "infer", "title": "Think", "text": "Think."},
                ],
            }
        }
    )
    with patch.object(
        mod.llm, "agenerate", new=AsyncMock(return_value=_llm_result(bad))
    ):
        output = await mod.LSATSolveGuideAuthor().run({"question_id": qid})
    # Malformed guides degrade to the fallback instead of shipping bad steps.
    assert output.degraded is True


@pytest.mark.asyncio
async def test_run_unknown_question_raises() -> None:
    from law_ai.agents_runtime.crews import lsat_solve_guide_author as mod

    with pytest.raises(KeyError):
        await mod.LSATSolveGuideAuthor().run({"question_id": "nope"})


def test_agent_declares_hitl_gate() -> None:
    from law_ai.agents_runtime.crews.lsat_solve_guide_author import (
        LSATSolveGuideAuthor,
    )

    assert LSATSolveGuideAuthor.human_approval_required is True


def test_agent_registered() -> None:
    from law_ai.agents_runtime import registry

    registry.register_all_agents()
    assert registry.get_agent("LSATSolveGuideAuthor") is not None


@pytest.mark.asyncio
async def test_run_rejects_answer_leak_in_early_step() -> None:
    """FR-11: a draft naming the answer before the answer step degrades."""
    from law_ai.agents_runtime.crews import lsat_solve_guide_author as mod
    from law_ai.lsat.services.bank import load_bank

    qid = _question_id()
    correct = load_bank()[qid].correct
    leaky = json.dumps(
        {
            "guide": {
                "question_id": qid,
                "method": "m",
                "steps": [
                    {
                        "kind": "orient",
                        "title": "Leak",
                        "text": f"Note early that the answer is {correct}.",
                    },
                    {
                        "kind": "answer",
                        "title": "Answer",
                        "text": f"{correct} is correct.",
                        "spoiler": True,
                    },
                ],
            }
        }
    )
    with patch.object(
        mod.llm, "agenerate", new=AsyncMock(return_value=_llm_result(leaky))
    ):
        output = await mod.LSATSolveGuideAuthor().run({"question_id": qid})
    assert output.degraded is True
    assert output.confidence == 0.0
