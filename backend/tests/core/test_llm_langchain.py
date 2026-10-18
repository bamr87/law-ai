"""Tests for ChatProviderChain — the LangChain face of the provider chain.

What matters: it is a *real* LangChain chat model (LangGraph/LCEL can bind
it), it folds messages into the chain's (system, prompt) shape faithfully,
and the returned AIMessage carries the provider metadata auditors rely on.
Routing itself is covered by test_llm_chain.py; here the router is stubbed.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, patch

from langchain_core.callbacks import AsyncCallbackHandler
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import (
    AIMessage,
    AIMessageChunk,
    HumanMessage,
    SystemMessage,
)

from law_ai.core.llm import ChatProviderChain
from law_ai.core.llm.base import LLMChunk, LLMResult
from law_ai.core.usage import LLMUsage


def _result(text: str = "ok", provider: str = "claude_code") -> LLMResult:
    return LLMResult(
        text=text, provider=provider, model="claude-opus-5-5", latency_ms=1.0
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
        assert reply.response_metadata["model_label"] == "claude_code/claude-opus-5-5"
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


class TestResponseSchema:
    """BL-20260905-80: the adapter is feature-equivalent with core.llm."""

    SCHEMA = {
        "type": "object",
        "properties": {"issue": {"type": "string"}},
        "required": ["issue"],
    }

    async def test_ainvoke_passes_the_schema_to_the_router(self) -> None:
        model = ChatProviderChain(agent="legal_workflow", response_schema=self.SCHEMA)
        with patch(
            "law_ai.core.llm.router.agenerate",
            new=AsyncMock(return_value=_result('{"issue": "x"}')),
        ) as agen:
            await model.ainvoke("q")

        assert agen.call_args.kwargs["response_schema"] == self.SCHEMA

    async def test_no_schema_is_the_default(self) -> None:
        model = ChatProviderChain()
        with patch(
            "law_ai.core.llm.router.agenerate",
            new=AsyncMock(return_value=_result("prose")),
        ) as agen:
            await model.ainvoke("q")

        assert agen.call_args.kwargs["response_schema"] is None

    async def test_the_streamed_path_carries_it_too(self) -> None:
        """A schema must not evaporate when the caller switches to astream."""
        model = ChatProviderChain(response_schema=self.SCHEMA)
        seen: dict[str, Any] = {}

        def _astream(prompt: str, **kwargs: Any) -> Any:
            seen.update(kwargs)

            async def _gen() -> Any:
                yield _chunk("x", first=True)

            return _gen()

        with patch("law_ai.core.llm.router.astream", new=_astream):
            [chunk async for chunk in model.astream("q")]

        assert seen["response_schema"] == self.SCHEMA

    def test_it_is_part_of_the_identifying_params(self) -> None:
        """LangChain caches on these, so two different schemas are two models."""
        model = ChatProviderChain(response_schema=self.SCHEMA)
        assert model._identifying_params["response_schema"] == self.SCHEMA


class TestUsageMetadata:
    """Token counts must reach LangChain's own accounting surface."""

    async def test_usage_metadata_and_response_metadata_carry_tokens(self) -> None:
        result = LLMResult(
            text="ok",
            provider="claude_code",
            model="claude-opus-5-5",
            latency_ms=1.0,
            usage=LLMUsage(input_tokens=100, output_tokens=20),
        )
        model = ChatProviderChain()
        with patch(
            "law_ai.core.llm.router.agenerate", new=AsyncMock(return_value=result)
        ):
            reply = await model.ainvoke("q")

        assert reply.usage_metadata == {
            "input_tokens": 100,
            "output_tokens": 20,
            "total_tokens": 120,
        }
        assert reply.response_metadata["usage"]["total_tokens"] == 120

    async def test_no_usage_leaves_the_metadata_absent(self) -> None:
        model = ChatProviderChain()
        with patch(
            "law_ai.core.llm.router.agenerate",
            new=AsyncMock(return_value=_result("ok")),
        ):
            reply = await model.ainvoke("q")

        assert reply.usage_metadata is None
        assert "usage" not in reply.response_metadata

    async def test_a_half_reported_usage_is_kept_only_in_response_metadata(
        self,
    ) -> None:
        """``UsageMetadata`` needs all three counts; the raw record does not."""
        result = LLMResult(
            text="ok",
            provider="ollama",
            model="mistral",
            latency_ms=1.0,
            usage=LLMUsage(output_tokens=7),
        )
        model = ChatProviderChain()
        with patch(
            "law_ai.core.llm.router.agenerate", new=AsyncMock(return_value=result)
        ):
            reply = await model.ainvoke("q")

        assert reply.usage_metadata is None
        assert reply.response_metadata["usage"] == {
            "input_tokens": None,
            "output_tokens": 7,
            "total_tokens": 7,
        }


# ---------------------------------------------------------------------------
# Streaming (BL-20260811-26)
# ---------------------------------------------------------------------------


def _fake_stream(*chunks: LLMChunk) -> Any:
    """Patch router.astream with a fixed sequence of chain chunks."""

    def _astream(prompt: str, **kwargs: Any) -> Any:
        async def _gen() -> Any:
            for chunk in chunks:
                yield chunk

        return _gen()

    return patch("law_ai.core.llm.router.astream", new=_astream)


def _chunk(text: str, first: bool = False) -> LLMChunk:
    return LLMChunk(
        text=text, provider="claude_code", model="claude-opus-5-5", first=first
    )


class TestStreaming:
    async def test_astream_yields_one_chunk_per_delta(self) -> None:
        model = ChatProviderChain(agent="legal_workflow")

        with _fake_stream(_chunk("Mar", first=True), _chunk("bury")):
            pieces = [chunk async for chunk in model.astream("q")]

        # More than one chunk is the whole point: without _astream,
        # BaseChatModel buffers _agenerate and yields the answer as one.
        # (The trailing empty chunk is BaseChatModel's own end-of-stream
        # marker, appended after _astream is exhausted.)
        assert [str(p.content) for p in pieces if p.content] == ["Mar", "bury"]
        assert isinstance(pieces[0], AIMessageChunk)

    async def test_every_chunk_names_the_serving_tier(self) -> None:
        model = ChatProviderChain()

        with _fake_stream(_chunk("a", first=True), _chunk("b")):
            pieces = [chunk async for chunk in model.astream("q")]

        labelled = [p for p in pieces if p.content]
        assert labelled
        for piece in labelled:
            assert (
                piece.response_metadata["model_label"] == "claude_code/claude-opus-5-5"
            )

    async def test_the_chain_receives_the_models_configuration(self) -> None:
        model = ChatProviderChain(
            agent="lsat_tutor", system="be terse", json_mode=True, max_tokens=64
        )
        seen: dict[str, Any] = {}

        def _astream(prompt: str, **kwargs: Any) -> Any:
            seen.update(kwargs, prompt=prompt)

            async def _gen() -> Any:
                yield _chunk("x", first=True)

            return _gen()

        with patch("law_ai.core.llm.router.astream", new=_astream):
            [chunk async for chunk in model.astream("q")]

        assert seen["agent"] == "lsat_tutor"
        assert seen["system"] == "be terse"
        assert seen["json_mode"] is True
        assert seen["max_tokens"] == 64

    async def test_callbacks_see_each_token(self) -> None:
        """LangChain tracing/streaming callbacks depend on on_llm_new_token."""
        model = ChatProviderChain()
        handler = _TokenRecorder()

        with _fake_stream(_chunk("Mar", first=True), _chunk("bury")):
            async for _ in model.astream("q", config={"callbacks": [handler]}):
                pass

        assert [t for t in handler.tokens if t] == ["Mar", "bury"]

    async def test_accumulates_into_the_full_answer(self) -> None:
        model = ChatProviderChain()

        with _fake_stream(_chunk("half ", first=True), _chunk("an answer")):
            pieces = [chunk async for chunk in model.astream("q")]

        merged = pieces[0]
        for piece in pieces[1:]:
            merged = merged + piece
        assert merged.content == "half an answer"


class _TokenRecorder(AsyncCallbackHandler):
    def __init__(self) -> None:
        self.tokens: list[str] = []

    async def on_llm_new_token(self, token: str, **kwargs: Any) -> None:
        self.tokens.append(token)
