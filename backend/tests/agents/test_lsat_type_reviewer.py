"""LSATTypeReviewer (spec 054). No provider is ever called."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from django.conf import settings


@pytest.fixture(autouse=True)
def _isolate(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "AUDIT_PATH", str(tmp_path / "audit.jsonl"))
    monkeypatch.setattr(
        settings, "LSAT_RESPONSE_CACHE_DIR", str(tmp_path / "cache"), raising=False
    )


def _llm_result(text: str) -> Any:
    from law_ai.core.llm.base import LLMResult

    return LLMResult(
        text=text, provider="claude_code", model="claude-fable-5", latency_ms=1.0
    )


@pytest.mark.asyncio
async def test_agreement_and_disagreement_are_computed_here_and_cached() -> None:
    from law_ai.agents_runtime.crews import lsat_type_reviewer as mod

    fake = AsyncMock(
        return_value=_llm_result(
            json.dumps(
                {
                    "archetype_id": "lr-causal-flaw",
                    "rationale": "flawed because",
                    "confidence": 0.7,
                }
            )
        )
    )
    with patch.object(mod.llm, "agenerate", new=fake):
        out = await mod.LSATTypeReviewer().run({"question_id": "lr-002"})
        again = await mod.LSATTypeReviewer().run({"question_id": "lr-002"})
    r = out.review
    assert r.stamped_archetype == "lr-weaken" and r.cue_archetype == "lr-weaken"
    assert r.model_archetype == "lr-causal-flaw" and r.agrees is False
    assert r.used_llm and not r.cached and out.trace_id
    assert again.review.cached and again.review.agrees is False
    assert fake.await_count == 1
    prompt = fake.call_args.args[0]
    assert "lr-weaken" in prompt  # on the menu
    assert '"stamped' not in prompt  # never shown the stamp


@pytest.mark.asyncio
async def test_off_menu_pick_and_outage_degrade() -> None:
    from law_ai.agents_runtime.crews import lsat_type_reviewer as mod

    with patch.object(
        mod.llm,
        "agenerate",
        new=AsyncMock(
            return_value=_llm_result(
                json.dumps(
                    {"archetype_id": "rc-main-point", "rationale": "", "confidence": 1}
                )
            )
        ),
    ):
        r = (await mod.LSATTypeReviewer().run({"question_id": "lr-002"})).review
    assert r.degraded and not r.used_llm and r.agrees is None
    with patch.object(
        mod.llm,
        "agenerate",
        new=AsyncMock(side_effect=mod.llm.LLMUnavailableError("down")),
    ):
        r = (
            await mod.LSATTypeReviewer().run({"question_id": "lr-002", "refresh": True})
        ).review
    assert r.degraded and r.model == "fallback/offline"


def test_registered() -> None:
    from law_ai.agents_runtime import registry
    from law_ai.agents_runtime.crews import lsat_type_reviewer as mod

    registry.register_all_agents()
    assert registry.AGENT_REGISTRY["LSATTypeReviewer"] is mod.LSATTypeReviewer
