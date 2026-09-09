"""LSATContrastAuthor (spec 054). No provider is ever called."""

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
        text=text, provider="claude_code", model="claude-fable-5", latency_ms=1.0
    )


def _payload() -> str:
    from law_ai.lsat.services.bank import load_bank

    seeded = load_bank()["lr-097"]
    return json.dumps(
        {
            "variation": {
                "stem": seeded.stem,
                "choices": [c.model_dump() for c in seeded.choices],
                "correct": seeded.correct,
                "explanation": seeded.explanation,
                "concepts": list(seeded.concepts),
                "contrast_note": seeded.contrast_note,
                "distractor_traps": {"B": "out-of-scope"},
                "confidence": 0.8,
            }
        }
    )


@pytest.mark.asyncio
async def test_run_returns_a_draft_with_lineage_and_logs_provenance() -> None:
    from law_ai.agents_runtime.crews import lsat_contrast_author as mod

    fake = AsyncMock(return_value=_llm_result(_payload()))
    with patch.object(mod.llm, "agenerate", new=fake):
        out = await mod.LSATContrastAuthor().run(
            {
                "question_id": "lr-002",
                "target_archetype_id": "lr-strengthen",
                "critique": ["fix X"],
            }
        )
    assert out.draft is not None and not out.degraded
    assert out.draft.variation_of == "lr-002"
    assert out.draft.target_archetype_id == "lr-strengthen"
    assert out.draft.section == "LR" and out.draft.difficulty == "med"
    assert out.draft.distractor_traps == {"B": "out-of-scope"}
    assert out.model == "claude_code/claude-fable-5" and out.trace_id
    prompt = fake.call_args.args[0]
    assert '"critique"' in prompt and "fix X" in prompt
    assert "most weakens" in prompt  # the source is shown, stimulus included
    assert "Attack or defend the link" in prompt or "traps" in prompt


@pytest.mark.asyncio
async def test_degraded_returns_no_draft_and_never_a_placeholder() -> None:
    from law_ai.agents_runtime.crews import lsat_contrast_author as mod

    with patch.object(
        mod.llm,
        "agenerate",
        new=AsyncMock(side_effect=mod.llm.LLMUnavailableError("down")),
    ):
        out = await mod.LSATContrastAuthor().run(
            {"question_id": "lr-002", "target_archetype_id": "lr-strengthen"}
        )
    assert out.degraded and out.draft is None and out.model == "fallback/offline"


@pytest.mark.asyncio
async def test_malformed_response_degrades() -> None:
    from law_ai.agents_runtime.crews import lsat_contrast_author as mod

    with patch.object(
        mod.llm, "agenerate", new=AsyncMock(return_value=_llm_result('{"nope": 1}'))
    ):
        out = await mod.LSATContrastAuthor().run(
            {"question_id": "lr-002", "target_archetype_id": "lr-strengthen"}
        )
    assert out.degraded and out.draft is None


def test_registered() -> None:
    from law_ai.agents_runtime import registry
    from law_ai.agents_runtime.crews import lsat_contrast_author as mod

    registry.register_all_agents()
    assert registry.AGENT_REGISTRY["LSATContrastAuthor"] is mod.LSATContrastAuthor
    assert mod.LSATContrastAuthor.human_approval_required is True
