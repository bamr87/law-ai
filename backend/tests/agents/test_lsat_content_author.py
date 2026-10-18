"""Tests for the LSATContentAuthor crew (spec 019 T-001)."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest
from pydantic import ValidationError


def _valid_drafts_payload(count: int = 1, section: str = "LR") -> str:
    return json.dumps(
        {
            "drafts": [
                {
                    "section": section,
                    "difficulty": "med",
                    "stem": f"Sample LSAT stem #{i}.",
                    "choices": [
                        {"label": "A", "text": "First choice"},
                        {"label": "B", "text": "Second choice"},
                        {"label": "C", "text": "Third choice"},
                        {"label": "D", "text": "Fourth choice"},
                        {"label": "E", "text": "Fifth choice"},
                    ],
                    "correct": "A",
                    "explanation": (
                        "Correct A because reasoning. B fails, C fails, D fails, E fails."
                    ),
                    "concepts": ["parallel-reasoning"],
                    "confidence": 0.8,
                }
                for i in range(count)
            ]
        }
    )


def _llm_result(
    text: str, *, provider: str = "claude_code", model: str = "claude-opus-5-5"
):
    """Build the LLMResult the provider chain hands back."""
    from law_ai.core.llm.base import LLMResult

    return LLMResult(text=text, provider=provider, model=model, latency_ms=1.0)


class TestPydanticContracts:
    def test_input_caps_count_at_10(self) -> None:
        from law_ai.agents_runtime.crews.lsat_content_author import (
            GenerateQuestionsInput,
        )

        with pytest.raises(ValidationError):
            GenerateQuestionsInput(section="LR", difficulty="med", count=11)

    def test_draft_requires_5_choices_in_order(self) -> None:
        from law_ai.agents_runtime.crews.lsat_content_author import (
            DraftChoice,
            DraftQuestion,
        )

        choices = [DraftChoice(label=label, text="x") for label in ["A", "B", "C", "D"]]
        with pytest.raises(ValidationError):
            DraftQuestion(
                section="LR",
                difficulty="med",
                stem="x",
                choices=choices,  # type: ignore[arg-type]
                correct="A",
                explanation="x",
            )

    def test_draft_correct_must_be_one_of_labels(self) -> None:
        # `correct: ChoiceLabel` is already a Literal — Pydantic rejects "F".
        from law_ai.agents_runtime.crews.lsat_content_author import (
            DraftChoice,
            DraftQuestion,
        )

        with pytest.raises(ValidationError):
            DraftQuestion(
                section="LR",
                difficulty="med",
                stem="x",
                choices=[
                    DraftChoice(label=label, text="x")
                    for label in ["A", "B", "C", "D", "E"]
                ],
                correct="F",  # type: ignore[arg-type]
                explanation="x",
            )


class TestRunSuccess:
    @pytest.mark.asyncio
    async def test_returns_drafts_and_logs_provenance(self) -> None:
        from law_ai.agents_runtime.crews import lsat_content_author as mod

        agent = mod.LSATContentAuthor()
        with (
            patch.object(
                mod.llm,
                "agenerate",
                new=AsyncMock(return_value=_llm_result(_valid_drafts_payload(2))),
            ) as mock_llm,
            patch.object(
                mod.provenance, "log_agent_call", return_value="trace-abc"
            ) as mock_log,
        ):
            out = await agent.run(
                {"section": "LR", "difficulty": "med", "count": 2, "concepts": []}
            )
        assert mock_llm.await_count == 1
        assert mock_log.call_count == 1
        kwargs = mock_log.call_args.kwargs
        assert kwargs["agent_name"] == "LSATContentAuthor"
        assert kwargs["input_data"]["count"] == 2
        assert kwargs["input_data"]["degraded"] is False
        assert out.trace_id == "trace-abc"
        assert len(out.drafts) == 2
        assert out.degraded is False
        assert out.confidence > 0

    @pytest.mark.asyncio
    async def test_pads_to_count_when_llm_returns_fewer(self) -> None:
        from law_ai.agents_runtime.crews import lsat_content_author as mod

        agent = mod.LSATContentAuthor()
        with (
            patch.object(
                mod.llm,
                "agenerate",
                new=AsyncMock(return_value=_llm_result(_valid_drafts_payload(1))),
            ),
            patch.object(mod.provenance, "log_agent_call", return_value="trace-pad"),
        ):
            out = await agent.run({"section": "LR", "difficulty": "med", "count": 3})
        assert len(out.drafts) == 3


class TestRunFallback:
    @pytest.mark.asyncio
    async def test_degrades_to_offline_on_chain_error(self) -> None:
        import httpx

        from law_ai.agents_runtime.crews import lsat_content_author as mod

        agent = mod.LSATContentAuthor()
        boom = AsyncMock(side_effect=httpx.ConnectError("nope"))
        with (
            patch.object(mod.llm, "agenerate", new=boom),
            patch.object(
                mod.provenance, "log_agent_call", return_value="trace-fallback"
            ) as mock_log,
        ):
            out = await agent.run({"section": "RC", "difficulty": "hard", "count": 1})
        assert out.degraded is True
        assert out.model == "fallback/offline"
        assert out.confidence == 0.0
        assert len(out.drafts) == 1
        assert out.drafts[0].confidence == 0.0
        kwargs = mock_log.call_args.kwargs
        assert kwargs["input_data"]["degraded"] is True
        assert kwargs["model"] == "fallback/offline"

    @pytest.mark.asyncio
    async def test_degrades_when_llm_returns_invalid_json(self) -> None:
        from law_ai.agents_runtime.crews import lsat_content_author as mod

        agent = mod.LSATContentAuthor()
        with (
            patch.object(
                mod.llm,
                "agenerate",
                new=AsyncMock(return_value=_llm_result("not json")),
            ),
            patch.object(mod.provenance, "log_agent_call", return_value="trace-bad"),
        ):
            out = await agent.run({"section": "LR", "difficulty": "med", "count": 1})
        assert out.degraded is True
        assert out.model == "fallback/offline"


class TestRunViaProviderChain:
    """Whatever tier the chain picks, the agent records that tier honestly."""

    @pytest.mark.asyncio
    async def test_uses_the_label_the_chain_reports(self) -> None:
        from law_ai.agents_runtime.crews import lsat_content_author as mod

        agent = mod.LSATContentAuthor()
        gen = AsyncMock(return_value=_llm_result(_valid_drafts_payload(1)))
        with (
            patch.object(mod.llm, "agenerate", new=gen),
            patch.object(mod.provenance, "log_agent_call", return_value="trace-cc"),
        ):
            out = await agent.run({"section": "LR", "difficulty": "med", "count": 1})
        assert gen.await_count == 1
        assert out.degraded is False
        assert out.model == "claude_code/claude-opus-5"
        assert len(out.drafts) == 1

    @pytest.mark.asyncio
    async def test_records_the_fallback_tier_when_claude_is_down(self) -> None:
        from law_ai.agents_runtime.crews import lsat_content_author as mod

        agent = mod.LSATContentAuthor()
        fell_back = _llm_result(
            _valid_drafts_payload(1), provider="ollama", model="mistral"
        )
        with (
            patch.object(mod.llm, "agenerate", new=AsyncMock(return_value=fell_back)),
            patch.object(mod.provenance, "log_agent_call", return_value="t"),
        ):
            out = await agent.run({"section": "LR", "difficulty": "med", "count": 1})
        assert out.model == "ollama/mistral"
        assert out.degraded is False

    @pytest.mark.asyncio
    async def test_strips_markdown_fence_from_model_output(self) -> None:
        from law_ai.agents_runtime.crews import lsat_content_author as mod

        agent = mod.LSATContentAuthor()
        fenced = "```json\n" + _valid_drafts_payload(1) + "\n```"
        with (
            patch.object(
                mod.llm, "agenerate", new=AsyncMock(return_value=_llm_result(fenced))
            ),
            patch.object(mod.provenance, "log_agent_call", return_value="trace-fence"),
        ):
            out = await agent.run({"section": "LR", "difficulty": "med", "count": 1})
        assert out.degraded is False
        assert out.model == "claude_code/claude-opus-5"

    @pytest.mark.asyncio
    async def test_degrades_when_the_whole_chain_is_unavailable(self) -> None:
        from law_ai.agents_runtime.crews import lsat_content_author as mod
        from law_ai.core import llm as llm_pkg

        agent = mod.LSATContentAuthor()
        boom = AsyncMock(side_effect=llm_pkg.LLMUnavailableError("all down"))
        with (
            patch.object(mod.llm, "agenerate", new=boom),
            patch.object(mod.provenance, "log_agent_call", return_value="trace-ccfail"),
        ):
            out = await agent.run({"section": "LR", "difficulty": "med", "count": 1})
        assert out.degraded is True
        assert out.model == "fallback/offline"

    @pytest.mark.asyncio
    async def test_normalizes_extra_choice_from_model(self) -> None:
        """A stray empty 6th choice (a real Opus quirk) is trimmed to A-E."""
        from law_ai.agents_runtime.crews import lsat_content_author as mod

        payload = json.dumps(
            {
                "drafts": [
                    {
                        "section": "LR",
                        "difficulty": "med",
                        "stem": "A sample logical reasoning stem.",
                        "choices": [
                            {"label": "A", "text": "first"},
                            {"label": "B", "text": "second"},
                            {"label": "C", "text": "third"},
                            {"label": "D", "text": "fourth"},
                            {"label": "E", "text": "fifth"},
                            {"label": "A", "text": ""},  # stray empty duplicate
                        ],
                        "correct": "B",
                        "explanation": "Because reasoning.",
                        "concepts": ["weaken"],
                        "confidence": 0.9,
                    }
                ]
            }
        )
        agent = mod.LSATContentAuthor()
        with (
            patch.object(
                mod.llm, "agenerate", new=AsyncMock(return_value=_llm_result(payload))
            ),
            patch.object(mod.provenance, "log_agent_call", return_value="trace-norm"),
        ):
            out = await agent.run({"section": "LR", "difficulty": "med", "count": 1})
        assert out.degraded is False
        assert [c.label for c in out.drafts[0].choices] == ["A", "B", "C", "D", "E"]
        assert out.drafts[0].choices[0].text == "first"


class TestNormalizeChoices:
    def test_trims_extra_empty_duplicate(self) -> None:
        from law_ai.agents_runtime.crews import lsat_content_author as mod

        item = {
            "choices": [
                {"label": "A", "text": "a"},
                {"label": "B", "text": "b"},
                {"label": "C", "text": "c"},
                {"label": "D", "text": "d"},
                {"label": "E", "text": "e"},
                {"label": "A", "text": ""},
            ]
        }
        mod._normalize_choices(item)
        assert [c["label"] for c in item["choices"]] == ["A", "B", "C", "D", "E"]
        assert item["choices"][0]["text"] == "a"

    def test_leaves_incomplete_set_for_validation(self) -> None:
        from law_ai.agents_runtime.crews import lsat_content_author as mod

        item = {"choices": [{"label": "A", "text": "a"}, {"label": "B", "text": "b"}]}
        mod._normalize_choices(item)
        # Not all of A-E present → untouched, so DraftQuestion can reject it.
        assert len(item["choices"]) == 2


def _keyed_drafts_payload(keys: list[str], section: str = "LR") -> str:
    """A batch whose answer keys are exactly *keys* (one draft per key)."""
    return json.dumps(
        {
            "drafts": [
                {
                    "section": section,
                    "difficulty": "med",
                    "stem": f"Balance stem #{i} about {key}.",
                    "choices": [
                        {"label": label, "text": f"{label} choice"}
                        for label in ["A", "B", "C", "D", "E"]
                    ],
                    "correct": key,
                    "explanation": (
                        f"Correct {key} because reasoning. The others each fail."
                    ),
                    "concepts": ["parallel-reasoning"],
                    "confidence": 0.8,
                }
                for i, key in enumerate(keys)
            ]
        }
    )


class TestAnswerKeySkew:
    """BL-20260606-02: batches are *checked* for A-E spread, not just asked."""

    def test_flags_a_dominant_key(self) -> None:
        from law_ai.agents_runtime.crews.lsat_content_author import answer_key_skew

        flag = answer_key_skew(["C", "C", "C", "A"])
        assert flag is not None
        assert "skew" in flag and "3/4" in flag and "'C'" in flag

    def test_spread_batch_is_not_flagged(self) -> None:
        from law_ai.agents_runtime.crews.lsat_content_author import answer_key_skew

        assert answer_key_skew(["A", "C", "E"]) is None

    def test_batch_below_sample_size_carries_no_signal(self) -> None:
        from law_ai.agents_runtime.crews.lsat_content_author import answer_key_skew

        assert answer_key_skew(["B", "B"]) is None
        assert answer_key_skew([]) is None

    def test_explicit_tolerance_wins_over_the_default(self) -> None:
        from law_ai.agents_runtime.crews.lsat_content_author import answer_key_skew

        keys = ["A", "A", "B", "C"]  # top share 0.50
        assert answer_key_skew(keys, 0.60) is None
        assert answer_key_skew(keys, 0.25) is not None

    def test_default_tolerance_tracks_the_factory_setting(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Factory and direct paths must agree on what "skewed" means."""
        from django.conf import settings

        from law_ai.agents_runtime.crews.lsat_content_author import (
            answer_key_skew,
            default_balance_tolerance,
        )

        monkeypatch.setattr(
            settings, "LSAT_FACTORY_BALANCE_TOLERANCE", 0.9, raising=False
        )
        assert default_balance_tolerance() == 0.9
        assert answer_key_skew(["A", "A", "A", "B"]) is None


class TestRunBalanceFlag:
    @pytest.mark.asyncio
    async def test_skewed_llm_batch_is_flagged_not_rejected(self) -> None:
        from law_ai.agents_runtime.crews import lsat_content_author as mod

        agent = mod.LSATContentAuthor()
        with (
            patch.object(
                mod.llm,
                "agenerate",
                new=AsyncMock(
                    return_value=_llm_result(_keyed_drafts_payload(["D"] * 4))
                ),
            ),
            patch.object(
                mod.provenance, "log_agent_call", return_value="trace-skew"
            ) as mock_log,
        ):
            out = await agent.run(
                {"section": "LR", "difficulty": "med", "count": 4, "concepts": []}
            )
        assert len(out.drafts) == 4, "flag, don't reject"
        assert out.balance_flag is not None and "'D'" in out.balance_flag
        assert (
            mock_log.call_args.kwargs["output_data"]["balance_flag"] == out.balance_flag
        )

    @pytest.mark.asyncio
    async def test_spread_llm_batch_has_no_flag(self) -> None:
        from law_ai.agents_runtime.crews import lsat_content_author as mod

        agent = mod.LSATContentAuthor()
        with (
            patch.object(
                mod.llm,
                "agenerate",
                new=AsyncMock(
                    return_value=_llm_result(_keyed_drafts_payload(["A", "C", "E"]))
                ),
            ),
            patch.object(mod.provenance, "log_agent_call", return_value="trace-ok"),
        ):
            out = await agent.run(
                {"section": "LR", "difficulty": "med", "count": 3, "concepts": []}
            )
        assert out.balance_flag is None
        assert len(out.drafts) == 3

    @pytest.mark.asyncio
    async def test_offline_fallback_batch_is_checked_too(self) -> None:
        """The fallback rotates keys, so the degraded path stays unflagged."""
        from law_ai.agents_runtime.crews import lsat_content_author as mod

        agent = mod.LSATContentAuthor()

        async def boom(*args: object, **kwargs: object) -> object:
            raise mod.llm.LLMUnavailableError("chain down")

        with (
            patch.object(mod.llm, "agenerate", new=boom),
            patch.object(mod.provenance, "log_agent_call", return_value="trace-off"),
        ):
            out = await agent.run({"section": "LR", "difficulty": "med", "count": 4})
        assert out.degraded is True
        assert out.balance_flag is None


class TestInteractiveStreaming:
    """BL-20260906-76 — the 68-second authoring wait is visible while it waits."""

    @pytest.mark.asyncio
    async def test_a_stream_id_relays_the_drafting_deltas(self) -> None:
        from law_ai.agents_runtime.crews import lsat_content_author as mod
        from law_ai.core.llm.base import LLMChunk

        payload = _valid_drafts_payload(2)
        emitted: list[dict] = []

        async def fake_emit(stream_key, event, source=""):  # type: ignore[no-untyped-def]
            emitted.append({"key": stream_key, **event, "source": source})

        async def fake_astream(prompt, **kwargs):  # type: ignore[no-untyped-def]
            for i in range(0, len(payload), 40):
                yield LLMChunk(
                    text=payload[i : i + 40],
                    provider="xai",
                    model="grok-4.6",
                    first=i == 0,
                )

        agent = mod.LSATContentAuthor()
        with (
            patch("law_ai.agentsapi.streaming.emit_stream_event", new=fake_emit),
            patch.object(mod.llm, "astream", new=fake_astream),
            patch.object(mod.provenance, "log_agent_call", return_value="trace-1"),
        ):
            out = await agent.run(
                {
                    "section": "LR",
                    "difficulty": "med",
                    "count": 2,
                    "stream_id": "author-42",
                }
            )

        # The drafts are still parsed from one complete payload…
        assert len(out.drafts) == 2
        assert out.degraded is False
        # …and every delta reached this run's group as progress.
        assert len(emitted) > 1
        assert {e["type"] for e in emitted} == {"authoring_token"}
        assert emitted[0]["key"] == "author-42"
        assert emitted[0]["agent"] == "LSATContentAuthor"
        assert emitted[0]["source"] == "lsat_content_author"
        assert [e["chars"] for e in emitted] == sorted(e["chars"] for e in emitted)
        assert emitted[-1]["chars"] == len(payload)
        assert "".join(e["text"] for e in emitted) == payload

    @pytest.mark.asyncio
    async def test_without_a_stream_id_the_call_stays_buffered(self) -> None:
        from law_ai.agents_runtime.crews import lsat_content_author as mod

        buffered = AsyncMock(return_value=_llm_result(_valid_drafts_payload(1)))
        exploding = AsyncMock(side_effect=AssertionError("must not stream"))
        agent = mod.LSATContentAuthor()
        with (
            patch.object(mod.llm, "agenerate", new=buffered),
            patch.object(mod.llm, "astream", new=exploding),
            patch.object(mod.provenance, "log_agent_call", return_value="trace-2"),
        ):
            out = await agent.run({"section": "LR", "difficulty": "med", "count": 1})
        assert len(out.drafts) == 1
        assert buffered.await_count == 1

    @pytest.mark.asyncio
    async def test_a_dead_socket_never_costs_the_author_their_drafts(self) -> None:
        from law_ai.agents_runtime.crews import lsat_content_author as mod
        from law_ai.core.llm.base import LLMChunk

        payload = _valid_drafts_payload(1)

        async def dead_emit(*args: object, **kwargs: object) -> None:
            raise RuntimeError("channel layer down")

        async def fake_astream(prompt, **kwargs):  # type: ignore[no-untyped-def]
            yield LLMChunk(text=payload, provider="xai", model="grok-4.6", first=True)

        agent = mod.LSATContentAuthor()
        with (
            patch("law_ai.agentsapi.streaming.emit_stream_event", new=dead_emit),
            patch.object(mod.llm, "astream", new=fake_astream),
            patch.object(mod.provenance, "log_agent_call", return_value="trace-3"),
        ):
            out = await agent.run(
                {
                    "section": "LR",
                    "difficulty": "med",
                    "count": 1,
                    "stream_id": "author-43",
                }
            )
        assert len(out.drafts) == 1
        assert out.degraded is False
