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


class TestPydanticContracts:
    def test_input_caps_count_at_10(self) -> None:
        from lawgraph.agents_runtime.crews.lsat_content_author import (
            GenerateQuestionsInput,
        )

        with pytest.raises(ValidationError):
            GenerateQuestionsInput(section="LR", difficulty="med", count=11)

    def test_draft_requires_5_choices_in_order(self) -> None:
        from lawgraph.agents_runtime.crews.lsat_content_author import (
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
        from lawgraph.agents_runtime.crews.lsat_content_author import (
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
        from lawgraph.agents_runtime.crews import lsat_content_author as mod

        agent = mod.LSATContentAuthor()
        with (
            patch.object(
                mod,
                "_ollama_generate",
                new=AsyncMock(return_value=_valid_drafts_payload(2)),
            ) as mock_ollama,
            patch.object(
                mod.provenance, "log_agent_call", return_value="trace-abc"
            ) as mock_log,
        ):
            out = await agent.run(
                {"section": "LR", "difficulty": "med", "count": 2, "concepts": []}
            )
        assert mock_ollama.await_count == 1
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
        from lawgraph.agents_runtime.crews import lsat_content_author as mod

        agent = mod.LSATContentAuthor()
        with (
            patch.object(
                mod,
                "_ollama_generate",
                new=AsyncMock(return_value=_valid_drafts_payload(1)),
            ),
            patch.object(mod.provenance, "log_agent_call", return_value="trace-pad"),
        ):
            out = await agent.run({"section": "LR", "difficulty": "med", "count": 3})
        assert len(out.drafts) == 3


class TestRunFallback:
    @pytest.mark.asyncio
    async def test_degrades_to_offline_on_ollama_error(self) -> None:
        import httpx

        from lawgraph.agents_runtime.crews import lsat_content_author as mod

        agent = mod.LSATContentAuthor()
        boom = AsyncMock(side_effect=httpx.ConnectError("nope"))
        with (
            patch.object(mod, "_ollama_generate", new=boom),
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
        from lawgraph.agents_runtime.crews import lsat_content_author as mod

        agent = mod.LSATContentAuthor()
        with (
            patch.object(
                mod, "_ollama_generate", new=AsyncMock(return_value="not json")
            ),
            patch.object(mod.provenance, "log_agent_call", return_value="trace-bad"),
        ):
            out = await agent.run({"section": "LR", "difficulty": "med", "count": 1})
        assert out.degraded is True
        assert out.model == "fallback/offline"


class TestRunViaClaudeCode:
    """Dev-time opt-in: the agent runs against Claude Code instead of Ollama."""

    @pytest.mark.asyncio
    async def test_routes_to_claude_code_when_active(self) -> None:
        from lawgraph.agents_runtime.crews import lsat_content_author as mod

        agent = mod.LSATContentAuthor()
        gen = AsyncMock(return_value=_valid_drafts_payload(1))
        with (
            patch.object(mod.claude_code, "is_active", return_value=True),
            patch.object(mod.claude_code, "model", return_value="claude-opus-4-8"),
            patch.object(mod.claude_code, "generate", new=gen),
            patch.object(mod, "_ollama_generate", new=AsyncMock()) as mock_ollama,
            patch.object(mod.provenance, "log_agent_call", return_value="trace-cc"),
        ):
            out = await agent.run({"section": "LR", "difficulty": "med", "count": 1})
        assert gen.await_count == 1
        assert mock_ollama.await_count == 0  # Ollama must not be touched
        assert out.degraded is False
        assert out.model == "claude_code/claude-opus-4-8"
        assert len(out.drafts) == 1

    @pytest.mark.asyncio
    async def test_strips_markdown_fence_from_claude_output(self) -> None:
        from lawgraph.agents_runtime.crews import lsat_content_author as mod

        agent = mod.LSATContentAuthor()
        fenced = "```json\n" + _valid_drafts_payload(1) + "\n```"
        with (
            patch.object(mod.claude_code, "is_active", return_value=True),
            patch.object(mod.claude_code, "model", return_value="claude-opus-4-8"),
            patch.object(
                mod.claude_code, "generate", new=AsyncMock(return_value=fenced)
            ),
            patch.object(mod.provenance, "log_agent_call", return_value="trace-fence"),
        ):
            out = await agent.run({"section": "LR", "difficulty": "med", "count": 1})
        assert out.degraded is False
        assert out.model == "claude_code/claude-opus-4-8"

    @pytest.mark.asyncio
    async def test_degrades_when_claude_code_unavailable(self) -> None:
        from lawgraph.agents_runtime.crews import lsat_content_author as mod

        agent = mod.LSATContentAuthor()
        boom = AsyncMock(
            side_effect=mod.claude_code.ClaudeCodeUnavailableError("no token")
        )
        with (
            patch.object(mod.claude_code, "is_active", return_value=True),
            patch.object(mod.claude_code, "generate", new=boom),
            patch.object(mod.provenance, "log_agent_call", return_value="trace-ccfail"),
        ):
            out = await agent.run({"section": "LR", "difficulty": "med", "count": 1})
        assert out.degraded is True
        assert out.model == "fallback/offline"

    @pytest.mark.asyncio
    async def test_normalizes_extra_choice_from_claude(self) -> None:
        """A stray empty 6th choice (a real Opus quirk) is trimmed to A-E, not dropped."""
        from lawgraph.agents_runtime.crews import lsat_content_author as mod

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
            patch.object(mod.claude_code, "is_active", return_value=True),
            patch.object(mod.claude_code, "model", return_value="claude-opus-4-8"),
            patch.object(
                mod.claude_code, "generate", new=AsyncMock(return_value=payload)
            ),
            patch.object(mod.provenance, "log_agent_call", return_value="trace-norm"),
        ):
            out = await agent.run({"section": "LR", "difficulty": "med", "count": 1})
        assert out.degraded is False
        assert out.model == "claude_code/claude-opus-4-8"
        assert [c.label for c in out.drafts[0].choices] == ["A", "B", "C", "D", "E"]
        assert out.drafts[0].choices[0].text == "first"


class TestNormalizeChoices:
    def test_trims_extra_empty_duplicate(self) -> None:
        from lawgraph.agents_runtime.crews import lsat_content_author as mod

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
        from lawgraph.agents_runtime.crews import lsat_content_author as mod

        item = {"choices": [{"label": "A", "text": "a"}, {"label": "B", "text": "b"}]}
        mod._normalize_choices(item)
        # Not all of A-E present → untouched, so DraftQuestion can reject it.
        assert len(item["choices"]) == 2
