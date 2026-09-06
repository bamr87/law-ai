"""Transport-level tests for the chain's Ollama provider (BL-20260810-05).

The routing contract lives in ``test_llm_chain.py``; this file covers what
one provider does *inside* a single routed call — specifically that the local
tier survives a transient hiccup (a 5xx while a model loads, a dropped
connection) with bounded backoff, and that it does not retry what waiting
cannot fix. No real network: the reachability probe is stubbed and
``/api/generate`` is served by respx.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock

import httpx
import pytest
import respx

from law_ai.agents_runtime import llm as llm_runtime
from law_ai.core.llm import providers
from law_ai.core.llm.base import LLMRequest, LLMUnavailableError
from law_ai.core.usage import LLMUsage, usage_of

_BASE = "http://ollama.test:11434"
_GENERATE = f"{_BASE}/api/generate"


def _ok(text: str) -> httpx.Response:
    return httpx.Response(200, json={"response": text, "done": True})


@pytest.fixture()
def ollama_up(settings, monkeypatch: pytest.MonkeyPatch) -> providers.OllamaProvider:
    """An OllamaProvider whose reachability probe says 'up' and never sleeps."""
    settings.OLLAMA_BASE_URL = _BASE
    settings.OLLAMA_DEFAULT_MODEL = "mistral:7b-instruct-q4_K_M"
    settings.OLLAMA_REQUEST_TIMEOUT_S = 5.0
    monkeypatch.setattr(
        llm_runtime, "ollama_available_async", AsyncMock(return_value=True)
    )
    monkeypatch.setattr(providers.asyncio, "sleep", AsyncMock())  # no real wait
    return providers.OllamaProvider()


class TestOllamaProviderRetry:
    @respx.mock
    async def test_retries_a_5xx_then_succeeds(self, ollama_up, settings) -> None:
        settings.OLLAMA_MAX_RETRIES = 2
        route = respx.post(_GENERATE).mock(
            side_effect=[httpx.Response(503, json={"error": "loading"}), _ok("hi")]
        )
        assert await ollama_up.agenerate(LLMRequest(prompt="q")) == "hi"
        assert route.call_count == 2

    @respx.mock
    async def test_retries_a_transport_error_then_succeeds(
        self, ollama_up, settings
    ) -> None:
        settings.OLLAMA_MAX_RETRIES = 3
        route = respx.post(_GENERATE).mock(
            side_effect=[httpx.ReadTimeout("slow model"), _ok("recovered")]
        )
        assert await ollama_up.agenerate(LLMRequest(prompt="q")) == "recovered"
        assert route.call_count == 2

    @respx.mock
    async def test_raises_after_exhausting_attempts(self, ollama_up, settings) -> None:
        settings.OLLAMA_MAX_RETRIES = 2
        route = respx.post(_GENERATE).mock(return_value=httpx.Response(500, json={}))
        with pytest.raises(httpx.HTTPStatusError):
            await ollama_up.agenerate(LLMRequest(prompt="q"))
        assert route.call_count == 2

    @respx.mock
    async def test_does_not_retry_a_missing_model(self, ollama_up, settings) -> None:
        """A 404 is 'model not pulled' — waiting will not pull it."""
        settings.OLLAMA_MAX_RETRIES = 3
        route = respx.post(_GENERATE).mock(
            return_value=httpx.Response(404, json={"error": "model not found"})
        )
        with pytest.raises(httpx.HTTPStatusError):
            await ollama_up.agenerate(LLMRequest(prompt="q"))
        assert route.call_count == 1

    @respx.mock
    async def test_one_attempt_disables_retry(self, ollama_up, settings) -> None:
        settings.OLLAMA_MAX_RETRIES = 1
        route = respx.post(_GENERATE).mock(return_value=httpx.Response(503, json={}))
        with pytest.raises(httpx.HTTPStatusError):
            await ollama_up.agenerate(LLMRequest(prompt="q"))
        assert route.call_count == 1

    @respx.mock
    async def test_backoff_is_bounded(self, ollama_up, settings, monkeypatch) -> None:
        """The tail of the chain must not add a long wait on top of two failed tiers."""
        settings.OLLAMA_MAX_RETRIES = 4
        sleeps: list[float] = []

        async def record(seconds: float) -> None:
            sleeps.append(seconds)

        monkeypatch.setattr(providers.asyncio, "sleep", record)
        respx.post(_GENERATE).mock(
            side_effect=[
                httpx.Response(503, json={}),
                httpx.Response(503, json={}),
                httpx.Response(503, json={}),
                _ok("finally"),
            ]
        )
        assert await ollama_up.agenerate(LLMRequest(prompt="q")) == "finally"
        assert len(sleeps) == 3
        assert sleeps == sorted(sleeps)  # exponential, never shrinking
        assert all(0.0 < s <= providers._OLLAMA_BACKOFF_CAP_S + 0.25 for s in sleeps)

    async def test_unreachable_server_short_circuits_before_any_request(
        self, settings, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        settings.OLLAMA_BASE_URL = _BASE
        monkeypatch.setattr(
            llm_runtime, "ollama_available_async", AsyncMock(return_value=False)
        )
        with pytest.raises(LLMUnavailableError, match="unreachable"):
            await providers.OllamaProvider().agenerate(LLMRequest(prompt="q"))

    @respx.mock
    async def test_json_mode_and_schema_set_format(self, ollama_up) -> None:
        route = respx.post(_GENERATE).mock(return_value=_ok("{}"))
        await ollama_up.agenerate(LLMRequest(prompt="q", json_mode=True))
        sent = route.calls.last.request
        assert b'"format":"json"' in sent.content.replace(b" ", b"")


class TestOllamaUsage:
    """Ollama reports counts at the top level, not in a ``usage`` object."""

    @respx.mock
    async def test_eval_counts_become_token_usage(self, ollama_up) -> None:
        respx.post(_GENERATE).mock(
            return_value=httpx.Response(
                200,
                json={
                    "response": "local answer",
                    "done": True,
                    "prompt_eval_count": 57,
                    "eval_count": 14,
                },
            )
        )

        reply = await ollama_up.agenerate(LLMRequest(prompt="q"))

        assert reply == "local answer"
        assert usage_of(reply) == LLMUsage(input_tokens=57, output_tokens=14)

    @respx.mock
    async def test_missing_counts_are_not_an_error(self, ollama_up) -> None:
        respx.post(_GENERATE).mock(return_value=_ok("local answer"))

        reply = await ollama_up.agenerate(LLMRequest(prompt="q"))

        assert reply == "local answer"
        assert usage_of(reply) is None


# ---------------------------------------------------------------------------
# Streaming (BL-20260811-20)
# ---------------------------------------------------------------------------


def _ndjson(*frames: dict) -> httpx.Response:
    """Ollama's streaming body: one JSON object per line, not SSE."""
    return httpx.Response(
        200,
        content="\n".join(json.dumps(frame) for frame in frames).encode(),
        headers={"content-type": "application/x-ndjson"},
    )


async def _drain(stream) -> list[str]:
    return [chunk async for chunk in stream]


class TestOllamaStreaming:
    @respx.mock
    async def test_yields_deltas_and_final_usage(self, ollama_up) -> None:
        route = respx.post(_GENERATE).mock(
            return_value=_ndjson(
                {"response": "loc", "done": False},
                {"response": "al", "done": False},
                {
                    "response": "",
                    "done": True,
                    "prompt_eval_count": 7,
                    "eval_count": 2,
                },
            )
        )

        chunks = await _drain(ollama_up.astream(LLMRequest(prompt="q")))

        assert [str(c) for c in chunks] == ["loc", "al", ""]
        assert json.loads(route.calls.last.request.content)["stream"] is True
        assert usage_of(chunks[-1]) == LLMUsage(input_tokens=7, output_tokens=2)

    @respx.mock
    async def test_json_schema_still_pins_the_format(self, ollama_up) -> None:
        route = respx.post(_GENERATE).mock(
            return_value=_ndjson({"response": "{}", "done": True})
        )
        schema = {"type": "object"}

        await _drain(ollama_up.astream(LLMRequest(prompt="q", response_schema=schema)))

        assert json.loads(route.calls.last.request.content)["format"] == schema

    @respx.mock
    async def test_an_error_frame_raises(self, ollama_up) -> None:
        respx.post(_GENERATE).mock(
            return_value=_ndjson({"error": "model not found"}),
        )

        with pytest.raises(LLMUnavailableError, match="model not found"):
            await _drain(ollama_up.astream(LLMRequest(prompt="q")))

    async def test_an_unreachable_server_fails_before_the_first_token(
        self, ollama_up, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """So the chain can still fall through: nothing was emitted yet."""
        monkeypatch.setattr(
            llm_runtime, "ollama_available_async", AsyncMock(return_value=False)
        )

        with pytest.raises(LLMUnavailableError):
            await _drain(ollama_up.astream(LLMRequest(prompt="q")))

    @respx.mock
    async def test_a_blank_line_is_skipped_not_fatal(self, ollama_up) -> None:
        respx.post(_GENERATE).mock(
            return_value=httpx.Response(
                200,
                content=b'\n{"response": "x", "done": true}\n\n',
            )
        )

        chunks = await _drain(ollama_up.astream(LLMRequest(prompt="q")))

        assert [str(c) for c in chunks] == ["x", ""]
