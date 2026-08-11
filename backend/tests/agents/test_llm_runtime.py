"""Tests for law_ai.agents_runtime.llm — the shared LangChain layer (spec 027)."""

from __future__ import annotations

from unittest.mock import patch

import httpx
import pytest

from law_ai.agents_runtime import llm


@pytest.fixture(autouse=True)
def _fresh_probe_cache() -> None:
    llm.reset_probe_cache()


class TestBuildChatOllama:
    def test_returns_retry_wrapped_runnable(self) -> None:
        pytest.importorskip("langchain_ollama")
        runnable = llm.build_chat_ollama(model="mistral:7b-instruct-q4_K_M")
        # with_retry wraps the chat model in a RunnableRetry.
        from langchain_core.runnables.retry import RunnableRetry

        assert isinstance(runnable, RunnableRetry)
        assert runnable.max_attempt_number == llm.RETRY_ATTEMPTS

    def test_retries_disabled_returns_bare_model(self) -> None:
        pytest.importorskip("langchain_ollama")
        from langchain_ollama import ChatOllama

        runnable = llm.build_chat_ollama(retries=1)
        assert isinstance(runnable, ChatOllama)

    def test_json_mode_sets_format(self) -> None:
        pytest.importorskip("langchain_ollama")
        runnable = llm.build_chat_ollama(output_format="json", retries=1)
        assert runnable.format == "json"


class TestCoerceText:
    def test_handles_strings_none_and_message_objects(self) -> None:
        class Msg:
            content = "hi"

        assert llm.coerce_text("hi") == "hi"
        assert llm.coerce_text(None) == ""
        assert llm.coerce_text(Msg()) == "hi"


class TestOllamaAvailable:
    def test_unreachable_returns_false_and_caches(self) -> None:
        calls: list[str] = []

        def boom(url: str, timeout: float) -> httpx.Response:
            calls.append(url)
            raise httpx.ConnectError("down")

        with patch.object(llm.httpx, "get", side_effect=boom):
            assert llm.ollama_available(base_url="http://nowhere:11434") is False
            # Second call hits the TTL cache — no new probe.
            assert llm.ollama_available(base_url="http://nowhere:11434") is False
        assert len(calls) == 1

    def test_reachable_returns_true(self) -> None:
        ok = httpx.Response(200, request=httpx.Request("GET", "http://x/api/tags"))
        with patch.object(llm.httpx, "get", return_value=ok):
            assert llm.ollama_available(base_url="http://up:11434") is True

    @pytest.mark.asyncio
    async def test_async_probe_shares_cache_with_sync(self) -> None:
        ok = httpx.Response(200, request=httpx.Request("GET", "http://x/api/tags"))
        with patch.object(llm.httpx, "get", return_value=ok):
            assert llm.ollama_available(base_url="http://shared:11434") is True
        # Async twin must serve the cached verdict without a new probe
        # (AsyncClient is NOT patched — a real request would fail).
        assert await llm.ollama_available_async(base_url="http://shared:11434") is True
