"""Tests for law_ai.agents_runtime.llm — the Ollama reachability probe.

Spec 027 originally put a second ``ChatOllama`` transport here; BL-20260810-05
removed it in favour of the one shared client
(``law_ai.core.llm.providers.OllamaProvider``), leaving this module with the
availability probe and ``coerce_text``.
"""

from __future__ import annotations

import time
from unittest.mock import patch

import httpx
import pytest

from law_ai.agents_runtime import llm


@pytest.fixture(autouse=True)
def _fresh_probe_cache() -> None:
    llm.reset_probe_cache()


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


class TestSharedProbeVerdict:
    """BL-20260810-15: the verdict is shared across workers via the Django cache.

    The in-process dict stays L1; the Django cache (Redis in production,
    LocMem in the suite) is L2. Clearing L1 alone simulates a second OS process
    that has never probed.
    """

    @staticmethod
    def _ok() -> httpx.Response:
        return httpx.Response(200, request=httpx.Request("GET", "http://x/api/tags"))

    @staticmethod
    def _forbid_probe(url: str, timeout: float) -> httpx.Response:
        raise AssertionError(f"a second process re-probed {url}")

    def test_second_process_adopts_the_shared_verdict(self) -> None:
        with patch.object(llm.httpx, "get", return_value=self._ok()):
            assert llm.ollama_available(base_url="http://shared-l2:11434") is True

        llm._probe_cache.clear()  # a fresh worker: empty L1, shared L2 intact
        with patch.object(llm.httpx, "get", side_effect=self._forbid_probe):
            assert llm.ollama_available(base_url="http://shared-l2:11434") is True
        # L1 was repopulated, so the next call does not even touch L2.
        assert "http://shared-l2:11434" in llm._probe_cache

    def test_negative_verdict_is_shared_too(self) -> None:
        def boom(url: str, timeout: float) -> httpx.Response:
            raise httpx.ConnectError("down")

        with patch.object(llm.httpx, "get", side_effect=boom):
            assert llm.ollama_available(base_url="http://shared-down:11434") is False

        llm._probe_cache.clear()
        with patch.object(llm.httpx, "get", side_effect=self._forbid_probe):
            assert llm.ollama_available(base_url="http://shared-down:11434") is False

    @pytest.mark.asyncio
    async def test_async_twin_adopts_the_shared_verdict(self) -> None:
        with patch.object(llm.httpx, "get", return_value=self._ok()):
            assert llm.ollama_available(base_url="http://shared-async:11434") is True

        llm._probe_cache.clear()
        # AsyncClient is NOT patched — a real request would fail, so a True
        # here can only have come from the shared cache.
        assert (
            await llm.ollama_available_async(base_url="http://shared-async:11434")
            is True
        )

    def test_shared_entry_honours_the_remaining_ttl(self) -> None:
        """An L2 entry older than the TTL is a miss, not a stale verdict."""
        url = "http://shared-stale:11434"
        llm._shared_cache().set(
            llm._shared_key(url), {"up": True, "at": time.time() - 60.0}, timeout=300
        )
        calls: list[str] = []

        def probe(u: str, timeout: float) -> httpx.Response:
            calls.append(u)
            raise httpx.ConnectError("down")

        with patch.object(llm.httpx, "get", side_effect=probe):
            assert llm.ollama_available(base_url=url, ttl_s=15.0) is False
        assert len(calls) == 1

    def test_broken_cache_backend_falls_back_to_in_process(self) -> None:
        """A Redis outage must leave behaviour exactly as before: L1 only."""

        class _Broken:
            def get(self, key: str) -> None:
                raise ConnectionError("redis down")

            async def aget(self, key: str) -> None:
                raise ConnectionError("redis down")

            def set(self, key: str, value: object, timeout: float) -> None:
                raise ConnectionError("redis down")

            async def aset(self, key: str, value: object, timeout: float) -> None:
                raise ConnectionError("redis down")

            def delete_many(self, keys: list[str]) -> None:
                raise ConnectionError("redis down")

        calls: list[str] = []

        def probe(u: str, timeout: float) -> httpx.Response:
            calls.append(u)
            return self._ok()

        with (
            patch.object(llm, "_shared_cache", return_value=_Broken()),
            patch.object(llm.httpx, "get", side_effect=probe),
        ):
            assert llm.ollama_available(base_url="http://l1-only:11434") is True
            # Served from L1 despite the dead L2.
            assert llm.ollama_available(base_url="http://l1-only:11434") is True
            llm.reset_probe_cache()  # must not raise either
        assert len(calls) == 1

    def test_reset_clears_the_shared_verdict(self) -> None:
        url = "http://shared-reset:11434"
        with patch.object(llm.httpx, "get", return_value=self._ok()):
            assert llm.ollama_available(base_url=url) is True
        llm.reset_probe_cache()
        assert llm._shared_cache().get(llm._shared_key(url)) is None
        calls: list[str] = []

        def probe(u: str, timeout: float) -> httpx.Response:
            calls.append(u)
            return self._ok()

        with patch.object(llm.httpx, "get", side_effect=probe):
            assert llm.ollama_available(base_url=url) is True
        assert len(calls) == 1
