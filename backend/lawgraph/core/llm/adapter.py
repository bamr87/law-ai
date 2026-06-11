"""Adapter exposing :class:`LLMClient` through the ``_LLMLike`` protocol.

``LegalWorkflow`` nodes call ``await llm.ainvoke(prompt)`` (the protocol at
``lawgraph.agents_runtime.graphs.legal_workflow._LLMLike``). This adapter
lets the workflow run on the unified audited client instead of
``langchain_ollama.ChatOllama`` without touching any node code.

Example::

    from lawgraph.core.llm import LLMClientAdapter

    llm = LLMClientAdapter(temperature=0.0, caller="legal_workflow")
    text = await llm.ainvoke("Return JSON: {\"ok\": true}")
"""

from __future__ import annotations

from lawgraph.core.llm.client import LLMClient, get_llm_client

__all__ = ["LLMClientAdapter"]


class LLMClientAdapter:
    """``ainvoke``-shaped wrapper around the unified Ollama client."""

    def __init__(
        self,
        client: LLMClient | None = None,
        *,
        model: str | None = None,
        temperature: float | None = None,
        caller: str = "legal_workflow",
    ) -> None:
        self._client = client or get_llm_client()
        self._model = model
        self._temperature = temperature
        self._caller = caller

    async def ainvoke(self, prompt: str) -> str:
        """Run a one-shot completion and return the raw response text."""
        return await self._client.generate(
            prompt,
            model=self._model,
            temperature=self._temperature,
            caller=self._caller,
        )
