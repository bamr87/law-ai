"""Tests for the LSATContentAuthor crew (spec 019 T-001)."""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest


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

        with pytest.raises(Exception):
            GenerateQuestionsInput(section="LR", difficulty="med", count=11)

    def test_draft_requires_5_choices_in_order(self) -> None:
        from lawgraph.agents_runtime.crews.lsat_content_author import (
            DraftChoice,
            DraftQuestion,
        )

        choices = [DraftChoice(label=l, text="x") for l in ["A", "B", "C", "D"]]
        with pytest.raises(Exception):
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

        with pytest.raises(Exception):
            DraftQuestion(
                section="LR",
                difficulty="med",
                stem="x",
                choices=[DraftChoice(label=l, text="x") for l in ["A", "B", "C", "D", "E"]],
                correct="F",  # type: ignore[arg-type]
                explanation="x",
            )


class TestRunSuccess:
    @pytest.mark.asyncio
    async def test_returns_drafts_and_logs_provenance(self) -> None:
        from lawgraph.agents_runtime.crews import lsat_content_author as mod

        agent = mod.LSATContentAuthor()
        with patch.object(
            mod, "_ollama_generate", new=AsyncMock(return_value=_valid_drafts_payload(2))
        ) as mock_ollama, patch.object(
            mod.provenance, "log_agent_call", return_value="trace-abc"
        ) as mock_log:
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
        with patch.object(
            mod, "_ollama_generate", new=AsyncMock(return_value=_valid_drafts_payload(1))
        ), patch.object(mod.provenance, "log_agent_call", return_value="trace-pad"):
            out = await agent.run(
                {"section": "LR", "difficulty": "med", "count": 3}
            )
        assert len(out.drafts) == 3


class TestRunFallback:
    @pytest.mark.asyncio
    async def test_degrades_to_offline_on_ollama_error(self) -> None:
        import httpx

        from lawgraph.agents_runtime.crews import lsat_content_author as mod

        agent = mod.LSATContentAuthor()
        boom = AsyncMock(side_effect=httpx.ConnectError("nope"))
        with patch.object(mod, "_ollama_generate", new=boom), patch.object(
            mod.provenance, "log_agent_call", return_value="trace-fallback"
        ) as mock_log:
            out = await agent.run(
                {"section": "RC", "difficulty": "hard", "count": 1}
            )
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
        with patch.object(
            mod, "_ollama_generate", new=AsyncMock(return_value="not json")
        ), patch.object(mod.provenance, "log_agent_call", return_value="trace-bad"):
            out = await agent.run(
                {"section": "LR", "difficulty": "med", "count": 1}
            )
        assert out.degraded is True
        assert out.model == "fallback/offline"
