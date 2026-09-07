"""LSATContentReviewer — blind pre-review of authored drafts (BL-20260527-04).

No provider is ever contacted: every case stubs ``law_ai.core.llm.agenerate``.
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from law_ai.agents_runtime.crews import lsat_content_reviewer as mod


def _draft(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "section": "LR",
        "difficulty": "med",
        "stem": "Which one of the following most weakens the argument above?",
        "choices": [
            {"label": "A", "text": "Alpha option text."},
            {"label": "B", "text": "Bravo option text."},
            {"label": "C", "text": "Charlie option text."},
            {"label": "D", "text": "Delta option text."},
            {"label": "E", "text": "Echo option text."},
        ],
        "correct": "C",
        "explanation": "Because C removes the causal link.",
        "concepts": ["weaken"],
        "confidence": 0.7,
    }
    base.update(overrides)
    return base


def _llm_result(text: str):  # type: ignore[no-untyped-def]
    from law_ai.core.llm.base import LLMResult

    return LLMResult(
        text=text, provider="claude_code", model="claude-opus-5", latency_ms=1.0
    )


_GOOD = json.dumps(
    {
        "clarity": 0.9,
        "ambiguity": 0.85,
        "single_best_answer": 0.8,
        "overall": 0.85,
        "flags": [],
        "rationale": "Stem names the task; only C is defensible.",
    }
)

_WEAK = json.dumps(
    {
        "clarity": 0.4,
        "ambiguity": 0.3,
        "single_best_answer": 0.2,
        "overall": 0.3,
        "flags": ["two-defensible-answers", "ambiguous-stem"],
        "rationale": "B and C are both defensible under the stem as written.",
    }
)


class TestBlindness:
    def test_payload_withholds_the_key_and_the_explanation(self) -> None:
        payload = mod._blind_payload(_draft(), None)
        assert "correct" not in payload
        assert "explanation" not in payload
        assert [c["label"] for c in payload["choices"]] == ["A", "B", "C", "D", "E"]

    @pytest.mark.asyncio
    async def test_prompt_sent_to_the_model_contains_no_answer_key(self) -> None:
        gen = AsyncMock(return_value=_llm_result(_GOOD))
        with (
            patch.object(mod.llm, "agenerate", new=gen),
            patch.object(mod.provenance, "log_agent_call", return_value="t"),
        ):
            await mod.LSATContentReviewer().run({"draft": _draft()})
        sent = gen.call_args.args[0]
        assert "Because C removes the causal link." not in sent
        assert '"correct"' not in sent


class TestScoring:
    @pytest.mark.asyncio
    async def test_strong_draft_is_not_flagged(self) -> None:
        with (
            patch.object(
                mod.llm, "agenerate", new=AsyncMock(return_value=_llm_result(_GOOD))
            ),
            patch.object(mod.provenance, "log_agent_call", return_value="t") as log,
        ):
            out = await mod.LSATContentReviewer().run({"draft": _draft()})

        assert out.overall == pytest.approx(0.85)
        assert out.flagged is False
        assert out.degraded is False
        assert out.model == "claude_code/claude-opus-5"
        assert out.prompt_version == mod.PROMPT_VERSION
        assert out.trace_id == "t"
        # Provenance names the real model, never a placeholder.
        assert log.call_args.kwargs["model"] == "claude_code/claude-opus-5"

    @pytest.mark.asyncio
    async def test_weak_draft_is_pre_flagged_but_never_rejected(self) -> None:
        with (
            patch.object(
                mod.llm, "agenerate", new=AsyncMock(return_value=_llm_result(_WEAK))
            ),
            patch.object(mod.provenance, "log_agent_call", return_value="t"),
        ):
            out = await mod.LSATContentReviewer().run({"draft": _draft()})

        assert out.flagged is True
        assert "two-defensible-answers" in out.flags
        # The agent has no reject/approve surface at all — pre-flag only.
        assert not hasattr(out, "rejected")
        assert not hasattr(mod.LSATContentReviewer, "reject")

    @pytest.mark.asyncio
    async def test_scores_are_clamped_and_flags_bounded(self) -> None:
        wild = json.dumps(
            {
                "clarity": 7,
                "ambiguity": -3,
                "single_best_answer": "nope",
                "overall": 1.5,
                "flags": ["x"] * 40,
                "rationale": "y" * 5000,
            }
        )
        with (
            patch.object(
                mod.llm, "agenerate", new=AsyncMock(return_value=_llm_result(wild))
            ),
            patch.object(mod.provenance, "log_agent_call", return_value="t"),
        ):
            out = await mod.LSATContentReviewer().run({"draft": _draft()})
        assert out.clarity == 1.0
        assert out.ambiguity == 0.0
        assert out.single_best_answer == 0.0
        assert out.overall == 1.0
        assert len(out.flags) == 10
        assert len(out.rationale) <= 1200

    @pytest.mark.asyncio
    async def test_threshold_is_settings_driven(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(mod.settings, "LSAT_REVIEW_FLAG_THRESHOLD", 0.95)
        with (
            patch.object(
                mod.llm, "agenerate", new=AsyncMock(return_value=_llm_result(_GOOD))
            ),
            patch.object(mod.provenance, "log_agent_call", return_value="t"),
        ):
            out = await mod.LSATContentReviewer().run({"draft": _draft()})
        assert out.flagged is True


class TestOfflineFallback:
    @pytest.mark.asyncio
    async def test_unreachable_chain_degrades_to_lint_only(self) -> None:
        from law_ai.core import llm as llm_pkg

        boom = AsyncMock(side_effect=llm_pkg.LLMUnavailableError("all down"))
        with (
            patch.object(mod.llm, "agenerate", new=boom),
            patch.object(mod.provenance, "log_agent_call", return_value="t") as log,
        ):
            out = await mod.LSATContentReviewer().run({"draft": _draft()})

        assert out.degraded is True
        assert out.overall == 0.0
        # Degraded rows are flagged so a human still looks, but the rationale
        # says the scores are absent rather than zero-quality.
        assert out.flagged is True
        assert "NOT judged" in out.rationale
        assert log.call_args.kwargs["model"] == "fallback/offline"
        assert log.call_args.kwargs["confidence"] == 0.0

    def test_lint_catches_what_a_regex_honestly_can(self) -> None:
        out = mod._lint_review(
            _draft(
                stem="Why?",
                choices=[
                    {"label": "A", "text": "Short."},
                    {"label": "B", "text": "Short."},
                    {"label": "C", "text": "x" * 200},
                    {"label": "D", "text": "Short."},
                    {"label": "E", "text": "Other."},
                ],
            )
        )
        assert "ambiguous-stem" in out.flags
        assert "unbalanced-choice-length" in out.flags
        assert "duplicate-choice" in out.flags

    def test_rc_draft_without_a_passage_is_flagged(self) -> None:
        out = mod._lint_review(_draft(section="RC", passage_id=None))
        assert "passage-missing" in out.flags


class TestBatchHelper:
    @pytest.mark.asyncio
    async def test_disabled_setting_skips_every_call(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(mod.settings, "LSAT_CONTENT_REVIEW", False)
        gen = AsyncMock()
        with patch.object(mod.llm, "agenerate", new=gen):
            out = await mod.review_drafts([_draft(), _draft()])
        assert out == [None, None]
        gen.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_a_reviewer_failure_does_not_lose_the_draft(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(mod.settings, "LSAT_CONTENT_REVIEW", True)
        with patch.object(
            mod.LSATContentReviewer, "run", new=AsyncMock(side_effect=RuntimeError("x"))
        ):
            out = await mod.review_drafts([_draft()])
        assert out == [None]

    @pytest.mark.asyncio
    async def test_returns_one_review_per_draft_in_order(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(mod.settings, "LSAT_CONTENT_REVIEW", True)
        with (
            patch.object(
                mod.llm,
                "agenerate",
                new=AsyncMock(side_effect=[_llm_result(_GOOD), _llm_result(_WEAK)]),
            ),
            patch.object(mod.provenance, "log_agent_call", return_value="t"),
        ):
            out = await mod.review_drafts([_draft(), _draft()])
        assert len(out) == 2
        assert out[0] is not None and out[0]["flagged"] is False
        assert out[1] is not None and out[1]["flagged"] is True


def test_reviewer_is_registered() -> None:
    from law_ai.agents_runtime.registry import AGENT_REGISTRY, register_all_agents

    register_all_agents()
    assert AGENT_REGISTRY["LSATContentReviewer"] is mod.LSATContentReviewer
    assert mod.LSATContentReviewer.human_approval_required is True


def test_missing_draft_is_a_programming_error_not_a_silent_pass() -> None:
    import asyncio

    with pytest.raises(ValueError, match="requires input_data"):
        asyncio.run(mod.LSATContentReviewer().run({}))
