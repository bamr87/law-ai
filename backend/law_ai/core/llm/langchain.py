"""LangChain chat-model adapter for the LLM provider chain (spec 035).

:class:`ChatProviderChain` is a genuine :class:`~langchain_core.language_models.
chat_models.BaseChatModel`, so anything built on LangChain or LangGraph — the
``LegalWorkflow`` StateGraph, LCEL pipelines, future CrewAI integrations —
can run on the constitution-§1 provider chain (Claude over OAuth, Claude over
an API key, local Ollama) without knowing the chain exists. This replaces the
duck-typed ``ChainRunnable`` shim as the default engine's LLM: a real chat
model participates in LangChain's callback/tracing machinery and returns
``AIMessage`` objects carrying provider metadata, instead of bare strings.

Usage::

    from law_ai.core.llm import ChatProviderChain

    model = ChatProviderChain(agent="legal_workflow")
    reply = await model.ainvoke("Summarise the holding of Marbury v. Madison")
    reply.response_metadata["model_label"]   # e.g. "claude_code/claude-opus-5"

``astream`` is a real token stream (BL-20260811-26), not the buffered
fallback ``BaseChatModel`` supplies for a model without ``_astream``::

    async for chunk in model.astream("Summarise the holding"):
        render(chunk.content)

Provenance is unchanged: every call still routes through
:func:`law_ai.core.llm.router.aroute` (or :func:`~law_ai.core.llm.router.astream`
for a streamed one), which writes the ``llm_call`` audit event
(constitution §5).
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Mapping, Sequence
from typing import Any

from langchain_core.callbacks import (
    AsyncCallbackManagerForLLMRun,
    CallbackManagerForLLMRun,
)
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import (
    AIMessage,
    AIMessageChunk,
    BaseMessage,
    SystemMessage,
)
from langchain_core.messages.ai import UsageMetadata
from langchain_core.outputs import ChatGeneration, ChatGenerationChunk, ChatResult

from law_ai.core.llm import router
from law_ai.core.llm.base import LLMResult


def _content_text(message: BaseMessage) -> str:
    """Flatten a LangChain message's content to plain text."""
    content = message.content
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(
            part.get("text", "") if isinstance(part, dict) else str(part)
            for part in content
        )
    return str(content)


def _usage_metadata(result: LLMResult) -> UsageMetadata | None:
    """LangChain's ``UsageMetadata`` for a routed result, when it is complete.

    ``UsageMetadata`` requires all three counts, so a provider that reported
    only one half yields ``None`` here and is still recorded in full under
    ``response_metadata['usage']``.
    """
    usage = result.usage
    if usage is None or usage.input_tokens is None or usage.output_tokens is None:
        return None
    return UsageMetadata(
        input_tokens=usage.input_tokens,
        output_tokens=usage.output_tokens,
        total_tokens=usage.input_tokens + usage.output_tokens,
    )


class ChatProviderChain(BaseChatModel):
    """LangChain chat model backed by the ordered LLM provider chain.

    System messages (and the ``system`` field) become the request's system
    prompt; the remaining conversation is rendered into the user prompt — a
    single human turn passes through verbatim, the common case for the
    prompt-per-node style the LangGraph workflows use.
    """

    system: str | None = None
    """Baseline system prompt, prepended before any SystemMessage content."""

    json_mode: bool = False
    """Ask providers for JSON output (Ollama JSON mode; prompt-level on Claude)."""

    response_schema: dict[str, Any] | None = None
    """JSON Schema pinning the reply to schema-valid JSON (BL-20260905-80).

    The strict form of :attr:`json_mode`: ``core.llm.agenerate`` has taken one
    since spec 034, and the adapter dropped it, so a LangGraph node could not
    ask for the structured output every other call site can. Passed through
    unchanged on all three paths — buffered, sync and streamed — so a schema
    does not quietly evaporate when a caller switches to ``astream``.
    """

    agent: str | None = None
    """Caller name recorded on the ``llm_call`` provenance event."""

    models: Mapping[str, str] | None = None
    """Per-provider model overrides, keyed by provider name."""

    providers: Sequence[str] | None = None
    """Restrict the chain to these providers, in order (None = configured chain)."""

    max_tokens: int | None = None
    temperature: float = 0.0

    @property
    def _llm_type(self) -> str:
        return "law_ai_provider_chain"

    @property
    def _identifying_params(self) -> dict[str, Any]:
        return {
            "chain": list(router.chain_names(self.providers)),
            "json_mode": self.json_mode,
            "response_schema": self.response_schema,
            "agent": self.agent,
        }

    # ------------------------------------------------------------------
    # Request assembly
    # ------------------------------------------------------------------

    def _split(self, messages: list[BaseMessage]) -> tuple[str | None, str]:
        """Fold messages into ``(system, prompt)`` for the chain's request."""
        system_parts: list[str] = []
        if self.system:
            system_parts.append(self.system)
        turns: list[tuple[str, str]] = []
        for message in messages:
            text = _content_text(message)
            if isinstance(message, SystemMessage):
                if text:
                    system_parts.append(text)
            elif text:
                turns.append((message.type, text))

        system = "\n\n".join(system_parts) or None
        if len(turns) == 1:
            return system, turns[0][1]
        # Multi-turn: render an explicit transcript rather than silently
        # dropping history the caller chose to send.
        prompt = "\n\n".join(f"{role}: {text}" for role, text in turns)
        return system, prompt

    def _to_result(self, result: LLMResult) -> ChatResult:
        metadata: dict[str, Any] = {
            "provider": result.provider,
            "model": result.model,
            "model_label": result.model_label,
            "fell_back": result.fell_back,
        }
        if result.usage is not None:
            # Both shapes on purpose: LangChain callbacks and LangSmith read
            # ``usage_metadata``, while ``response_metadata['usage']`` keeps the
            # raw counts next to the rest of the routing metadata for anything
            # that just inspects the message (BL-20260811-21).
            metadata["usage"] = result.usage.as_dict()
        message = AIMessage(
            content=result.text,
            response_metadata=metadata,
            usage_metadata=_usage_metadata(result),
        )
        return ChatResult(
            generations=[ChatGeneration(message=message)],
            llm_output=metadata,
        )

    # ------------------------------------------------------------------
    # Generation
    # ------------------------------------------------------------------

    async def _agenerate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: AsyncCallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        system, prompt = self._split(messages)
        result = await router.agenerate(
            prompt,
            system=system,
            json_mode=self.json_mode,
            response_schema=self.response_schema,
            max_tokens=self.max_tokens,
            temperature=self.temperature,
            models=self.models,
            providers=self.providers,
            agent=self.agent,
        )
        return self._to_result(result)

    async def _astream(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: AsyncCallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> AsyncIterator[ChatGenerationChunk]:
        """Stream the chain's deltas as LangChain chunks (BL-20260811-26).

        Without this, ``BaseChatModel.astream`` silently falls back to
        :meth:`_agenerate` and hands the caller the whole answer as one chunk —
        a streaming API that does not stream. Routing, fallback and the
        ``llm_call`` provenance event are unchanged: this is the same
        :func:`router.astream` every other caller uses.

        Each chunk carries the serving ``provider``/``model_label`` in
        ``response_metadata`` rather than only the last one, because the tier
        is chosen lazily and a consumer rendering tokens needs the label with
        the first of them, not after the answer is complete.
        """
        system, prompt = self._split(messages)
        async for chunk in router.astream(
            prompt,
            system=system,
            json_mode=self.json_mode,
            response_schema=self.response_schema,
            max_tokens=self.max_tokens,
            temperature=self.temperature,
            models=self.models,
            providers=self.providers,
            agent=self.agent,
        ):
            if run_manager is not None:
                await run_manager.on_llm_new_token(chunk.text)
            yield ChatGenerationChunk(
                message=AIMessageChunk(
                    content=chunk.text,
                    response_metadata={
                        "provider": chunk.provider,
                        "model": chunk.model,
                        "model_label": chunk.model_label,
                    },
                )
            )

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        system, prompt = self._split(messages)
        # router.generate refuses inside a running event loop (async callers
        # must use ainvoke); letting that RuntimeError propagate is correct.
        result = router.generate(
            prompt,
            system=system,
            json_mode=self.json_mode,
            response_schema=self.response_schema,
            max_tokens=self.max_tokens,
            temperature=self.temperature,
            models=self.models,
            providers=self.providers,
            agent=self.agent,
        )
        return self._to_result(result)


__all__ = ["ChatProviderChain"]
