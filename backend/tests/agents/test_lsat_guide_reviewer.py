"""LSATGuideReviewer — judge tier for solve-guide drafts (BL-20260830-15).

Offline by construction: every case stubs ``law_ai.core.llm.agenerate``.
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from law_ai.agents_runtime.crews import lsat_guide_reviewer as mod


class _Choice:
    def __init__(self, label: str, text: str) -> None:
        self.label = label
        self.text = text


class _Question:
    id = "lr-001"
    section = "LR"
    difficulty = "med"
    stem = "Which one of the following most weakens the argument?"
    choices = [_Choice(x, f"{x} text") for x in "ABCDE"]
    correct = "C"
    passage_id = None


class _Step:
    def __init__(self, kind: str, title: str, text: str) -> None:
        self.kind = kind
        self.title = title
        self.text = text
        self.representation = None


class _Guide:
    question_id = "lr-001"
    method = "Weaken by breaking the causal link"
    steps = [
        _Step("setup", "Read the stimulus", "The argument claims A causes B."),
        _Step("answer", "Pick C", "C is correct because it severs A from B."),
    ]


def _llm_result(text: str):  # type: ignore[no-untyped-def]
    from law_ai.core.llm.base import LLMResult

    return LLMResult(
        text=text, provider="claude_code", model="claude-opus-5-5", latency_ms=1.0
    )


def _payload(**over: Any) -> str:
    base: dict[str, Any] = {
        "verdict": "pass",
        "symbolization_faithful": True,
        "step_findings": [
            {"index": 1, "follows": True, "note": ""},
            {"index": 2, "follows": True, "note": ""},
        ],
        "summary": "Each step follows; the answer step is justified.",
        "confidence": 0.8,
    }
    base.update(over)
    return json.dumps(base)


async def _run(text: str):  # type: ignore[no-untyped-def]
    with (
        patch.object(
            mod.llm, "agenerate", new=AsyncMock(return_value=_llm_result(text))
        ),
        patch.object(mod.provenance, "log_agent_call", return_value="t"),
    ):
        return await mod.LSATGuideReviewer().run(
            {"guide": _Guide(), "question": _Question()}
        )


class TestVerdicts:
    @pytest.mark.asyncio
    async def test_sound_guide_passes(self) -> None:
        out = await _run(_payload())
        assert out.verdict == "pass"
        assert out.symbolization_faithful is True
        assert [f.index for f in out.step_findings] == [1, 2]
        assert out.confidence == pytest.approx(0.8)
        assert out.model == "claude_code/claude-opus-5"
        assert out.degraded is False
        assert out.trace_id == "t"

    @pytest.mark.asyncio
    async def test_a_broken_step_cannot_be_a_pass(self) -> None:
        """The gate is ours, not the model's: `pass` + a broken step ⇒ revise."""
        out = await _run(
            _payload(
                step_findings=[
                    {"index": 1, "follows": True, "note": ""},
                    {"index": 2, "follows": False, "note": "rule 2 gives C→B, not B→C"},
                ]
            )
        )
        assert out.verdict == "revise"
        broken = [f for f in out.step_findings if not f.follows]
        assert broken and "rule 2" in broken[0].note

    @pytest.mark.asyncio
    async def test_unfaithful_symbolization_is_surfaced(self) -> None:
        out = await _run(_payload(verdict="reject", symbolization_faithful=False))
        assert out.verdict == "reject"
        assert out.symbolization_faithful is False

    @pytest.mark.asyncio
    async def test_unknown_verdict_reads_as_unreviewed_not_pass(self) -> None:
        out = await _run(_payload(verdict="looks-fine"))
        assert out.verdict == "unreviewed"

    @pytest.mark.asyncio
    async def test_out_of_range_step_indices_are_dropped(self) -> None:
        out = await _run(
            _payload(
                step_findings=[
                    {"index": 1, "follows": True, "note": ""},
                    {"index": 99, "follows": False, "note": "phantom step"},
                    {"index": 0, "follows": False, "note": "zero"},
                ]
            )
        )
        assert [f.index for f in out.step_findings] == [1]


class TestOfflineFallback:
    @pytest.mark.asyncio
    async def test_no_provider_is_unreviewed_never_approved(self) -> None:
        from law_ai.core import llm as llm_pkg

        with (
            patch.object(
                mod.llm,
                "agenerate",
                new=AsyncMock(side_effect=llm_pkg.LLMUnavailableError("down")),
            ),
            patch.object(mod.provenance, "log_agent_call", return_value="t") as log,
        ):
            out = await mod.LSATGuideReviewer().run(
                {"guide": _Guide(), "question": _Question()}
            )

        assert out.verdict == "unreviewed"
        assert out.degraded is True
        assert out.confidence == 0.0
        assert "NOT judged" in out.summary
        assert log.call_args.kwargs["model"] == "fallback/offline"

    @pytest.mark.asyncio
    async def test_review_guide_helper_never_loses_the_draft(self) -> None:
        with patch.object(
            mod.LSATGuideReviewer, "run", new=AsyncMock(side_effect=RuntimeError("x"))
        ):
            assert await mod.review_guide(_Guide()) is None


class TestProvenanceAndPayload:
    @pytest.mark.asyncio
    async def test_prompt_carries_the_question_and_every_step(self) -> None:
        gen = AsyncMock(return_value=_llm_result(_payload()))
        with (
            patch.object(mod.llm, "agenerate", new=gen),
            patch.object(mod.provenance, "log_agent_call", return_value="t"),
        ):
            await mod.LSATGuideReviewer().run(
                {"guide": _Guide(), "question": _Question()}
            )
        sent = gen.call_args.args[0]
        assert "Which one of the following most weakens" in sent
        assert "Weaken by breaking the causal link" in sent
        assert '"index": 2' in sent

    @pytest.mark.asyncio
    async def test_one_provenance_event_per_run(self) -> None:
        with (
            patch.object(
                mod.llm,
                "agenerate",
                new=AsyncMock(return_value=_llm_result(_payload())),
            ),
            patch.object(mod.provenance, "log_agent_call", return_value="t") as log,
        ):
            await mod.LSATGuideReviewer().run(
                {"guide": _Guide(), "question": _Question()}
            )
        assert log.call_count == 1
        assert log.call_args.kwargs["agent_name"] == "LSATGuideReviewer"
        assert log.call_args.kwargs["input_data"]["question_id"] == "lr-001"
        assert log.call_args.kwargs["input_data"]["step_count"] == 2


def test_reviewer_is_registered_and_advisory() -> None:
    from law_ai.agents_runtime.registry import AGENT_REGISTRY, register_all_agents

    register_all_agents()
    assert AGENT_REGISTRY["LSATGuideReviewer"] is mod.LSATGuideReviewer
    assert mod.LSATGuideReviewer.human_approval_required is True
    # No promotion surface at all: promotion stays in proposals.py, human-only.
    assert not hasattr(mod.LSATGuideReviewer, "promote")
    assert not hasattr(mod.LSATGuideReviewer, "approve")


def test_missing_guide_is_a_programming_error() -> None:
    import asyncio

    with pytest.raises(ValueError, match="requires input_data"):
        asyncio.run(mod.LSATGuideReviewer().run({}))
