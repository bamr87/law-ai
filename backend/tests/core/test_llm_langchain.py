"""Tests for ChatProviderChain — the LangChain face of the provider chain.

What matters: it is a *real* LangChain chat model (LangGraph/LCEL can bind
it), it folds messages into the chain's (system, prompt) shape faithfully,
and the returned AIMessage carries the provider metadata auditors rely on.
Routing itself is covered by test_llm_chain.py; here the router is stubbed.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from law_ai.core.llm import ChatProviderChain
from law_ai.core.llm.base import LLMResult


def _result(text: str = "ok", provider: str = "claude_code") -> LLMResult:
    return LLMResult(
        text=text, provider=provider, model="claude-opus-5", latency_ms=1.0
    )


class TestIsARealChatModel:
    def test_subclasses_base_chat_model(self) -> None:
        assert issubclass(ChatProviderChain, BaseChatModel)

    def test_llm_type_names_the_chain(self) -> None:
        assert ChatProviderChain()._llm_type == "law_ai_provider_chain"


class TestMessageFolding:
    def test_single_human_message_passes_through(self) -> None:
        system, prompt = ChatProviderChain()._split([HumanMessage(content="q")])
        assert system is None
        assert prompt == "q"

    def test_system_messages_fold_into_system(self) -> None:
        model = ChatProviderChain(system="base rules")
        system, prompt = model._split(
            [SystemMessage(content="be terse"), HumanMessage(content="q")]
        )
        assert system == "base rules\n\nbe terse"
        assert prompt == "q"

    def test_multi_turn_renders_a_transcript(self) -> None:
        system, prompt = ChatProviderChain()._split(
            [
                HumanMessage(content="first"),
                AIMessage(content="reply"),
                HumanMessage(content="second"),
            ]
        )
        assert system is None
        # History must not be silently dropped.
        assert "human: first" in prompt
        assert "ai: reply" in prompt
        assert "human: second" in prompt

    def test_list_content_parts_are_flattened(self) -> None:
        msg = HumanMessage(
            content=[
                {"type": "text", "text": "part one "},
                {"type": "text", "text": "part two"},
            ]
        )
        _, prompt = ChatProviderChain()._split([msg])
        assert prompt == "part one part two"


class TestGeneration:
    async def test_ainvoke_returns_aimessage_with_provider_metadata(self) -> None:
        model = ChatProviderChain(agent="legal_workflow")
        with patch(
            "law_ai.core.llm.router.agenerate",
            new=AsyncMock(return_value=_result("the holding")),
        ) as agen:
            reply = await model.ainvoke("Summarise the holding")

        assert isinstance(reply, AIMessage)
        assert reply.content == "the holding"
        assert reply.response_metadata["model_label"] == "claude_code/claude-opus-5"
        assert reply.response_metadata["fell_back"] is False
        assert agen.call_args.kwargs["agent"] == "legal_workflow"
        assert agen.call_args.kwargs["system"] is None
        assert agen.call_args.args == ("Summarise the holding",)

    async def test_metadata_names_the_fallback_tier(self) -> None:
        model = ChatProviderChain()
        fell_back = LLMResult(
            text="local answer",
            provider="ollama",
            model="mistral",
            latency_ms=1.0,
            attempts=(),
        )
        with patch(
            "law_ai.core.llm.router.agenerate",
            new=AsyncMock(return_value=fell_back),
        ):
            reply = await model.ainvoke("q")
        assert reply.response_metadata["model_label"] == "ollama/mistral"

    async def test_works_as_the_legal_workflow_llm(self) -> None:
        """The default engine consumes it through _coerce_text unchanged."""
        from law_ai.agents_runtime.graphs.legal_workflow import _coerce_text

        model = ChatProviderChain(agent="legal_workflow")
        with patch(
            "law_ai.core.llm.router.agenerate",
            new=AsyncMock(return_value=_result('{"analysis": "..."}')),
        ):
            reply = await model.ainvoke("prompt")
        assert _coerce_text(reply) == '{"analysis": "..."}'
