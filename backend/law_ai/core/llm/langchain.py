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

Provenance is unchanged: every call still routes through
:func:`law_ai.core.llm.router.aroute`, which writes the ``llm_call`` audit
event (constitution §5).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from langchain_core.callbacks import (
    AsyncCallbackManagerForLLMRun,
    CallbackManagerForLLMRun,
)
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, SystemMessage
from langchain_core.outputs import ChatGeneration, ChatResult

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
        metadata = {
            "provider": result.provider,
            "model": result.model,
            "model_label": result.model_label,
            "fell_back": result.fell_back,
        }
        message = AIMessage(content=result.text, response_metadata=metadata)
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
            max_tokens=self.max_tokens,
            temperature=self.temperature,
            models=self.models,
            providers=self.providers,
            agent=self.agent,
        )
        return self._to_result(result)

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
            max_tokens=self.max_tokens,
            temperature=self.temperature,
            models=self.models,
            providers=self.providers,
            agent=self.agent,
        )
        return self._to_result(result)


__all__ = ["ChatProviderChain"]
