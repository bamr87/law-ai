"""LSATQuestionEditor (spec 054 FR-11). No provider is ever called."""

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


def _llm_result(text: str) -> Any:
    from law_ai.core.llm.base import LLMResult

    return LLMResult(
        text=text, provider="claude_code", model="claude-fable-5-1", latency_ms=1.0
    )


def _payload(**over: Any) -> str:
    from law_ai.lsat.services.bank import load_bank

    q = load_bank()["lr-002"]
    body = {
        "stem": q.stem,
        "choices": [c.model_dump() for c in q.choices],
        "correct": q.correct,
        "explanation": q.explanation + " Tightened.",
        "concepts": list(q.concepts),
        "change_summary": "Tightened the explanation to name why A is out of scope.",
        "confidence": 0.85,
    }
    body.update(over)
    return json.dumps({"edited": body})


@pytest.mark.asyncio
async def test_run_returns_an_edit_addressed_to_the_bank_id() -> None:
    from law_ai.agents_runtime.crews import lsat_question_editor as mod

    fake = AsyncMock(return_value=_llm_result(_payload()))
    with patch.object(mod.llm, "agenerate", new=fake):
        out = await mod.LSATQuestionEditor().run(
            {"question_id": "lr-002", "critique": ["Choice A is vague."]}
        )
    assert out.draft is not None and not out.degraded
    assert out.draft.question_id == "lr-002" and out.draft.section == "LR"
    assert out.draft.change_summary.startswith("Tightened")
    prompt = fake.call_args.args[0]
    assert "Choice A is vague." in prompt and '"shares_stimulus": true' in prompt
    assert out.trace_id


@pytest.mark.asyncio
async def test_shape_errors_are_issues_and_outages_degrade() -> None:
    from law_ai.agents_runtime.crews import lsat_question_editor as mod

    with patch.object(
        mod.llm,
        "agenerate",
        new=AsyncMock(return_value=_llm_result(_payload(correct="Z"))),
    ):
        out = await mod.LSATQuestionEditor().run({"question_id": "lr-002"})
    assert (
        out.draft is None
        and not out.degraded
        and out.issues
        and "correct" in out.issues[0]
    )
    with patch.object(
        mod.llm,
        "agenerate",
        new=AsyncMock(side_effect=mod.llm.LLMUnavailableError("down")),
    ):
        out = await mod.LSATQuestionEditor().run({"question_id": "lr-002"})
    assert out.degraded and out.draft is None


def test_registered() -> None:
    from law_ai.agents_runtime import registry
    from law_ai.agents_runtime.crews import lsat_question_editor as mod

    registry.register_all_agents()
    assert registry.AGENT_REGISTRY["LSATQuestionEditor"] is mod.LSATQuestionEditor
