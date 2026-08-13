"""Spec 038 — the Claude OAuth sidecar proxy for the Phoenix playground.

The upstream Anthropic API is respx-mocked; the ASGI app is exercised
through ``httpx.ASGITransport`` so the full request/response path runs.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import httpx
import pytest
import respx

from scripts import claude_oauth_proxy

UPSTREAM = "https://api.anthropic.com"
TOKEN = "sk-ant-oat01-unit-test-token"


@pytest.fixture(autouse=True)
def _proxy_env(monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[None]:
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", TOKEN)
    monkeypatch.delenv("ANTHROPIC_BASE_URL", raising=False)
    # The module caches its upstream client; reset so each test's respx mock
    # and env take effect.
    monkeypatch.setattr(claude_oauth_proxy, "_client", None)
    yield


def _proxy_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=claude_oauth_proxy.application),
        base_url="http://proxy.test",
    )


async def test_health_ok_with_token() -> None:
    async with _proxy_client() as client:
        response = await client.get("/health")
    assert response.status_code == 200


async def test_health_503_without_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "")
    async with _proxy_client() as client:
        response = await client.get("/health")
    assert response.status_code == 503


@respx.mock
async def test_swaps_placeholder_key_for_oauth_pair() -> None:
    route = respx.post(f"{UPSTREAM}/v1/messages").mock(
        httpx.Response(200, json={"content": [{"type": "text", "text": "ok"}]})
    )
    async with _proxy_client() as client:
        response = await client.post(
            "/v1/messages",
            json={"model": "claude-opus-5", "max_tokens": 1, "messages": []},
            headers={"x-api-key": "oauth-via-claude-oauth-proxy"},
        )
    assert response.status_code == 200
    sent = route.calls.last.request
    assert "x-api-key" not in sent.headers
    assert sent.headers["authorization"] == f"Bearer {TOKEN}"
    assert sent.headers["anthropic-beta"] == "oauth-2025-04-20"
    assert sent.headers["anthropic-version"] == "2023-06-01"
    assert b"claude-opus-5" in sent.content


@respx.mock
async def test_merges_caller_beta_flags_after_oauth() -> None:
    route = respx.post(f"{UPSTREAM}/v1/messages").mock(httpx.Response(200, json={}))
    async with _proxy_client() as client:
        await client.post(
            "/v1/messages",
            json={},
            headers={"anthropic-beta": "context-1m-2026, oauth-2025-04-20"},
        )
    beta = route.calls.last.request.headers["anthropic-beta"]
    assert beta == "oauth-2025-04-20,context-1m-2026"


@respx.mock
async def test_relays_status_and_rate_limit_headers() -> None:
    respx.post(f"{UPSTREAM}/v1/messages").mock(
        httpx.Response(
            429,
            json={"error": {"type": "rate_limit_error"}},
            headers={"retry-after": "13", "x-should-not-leak": "1"},
        )
    )
    async with _proxy_client() as client:
        response = await client.post("/v1/messages", json={})
    assert response.status_code == 429
    assert response.headers["retry-after"] == "13"
    assert "x-should-not-leak" not in response.headers
    assert response.json()["error"]["type"] == "rate_limit_error"


@respx.mock
async def test_streams_sse_body_through() -> None:
    sse = b'event: message_start\ndata: {"type":"message_start"}\n\n'
    respx.post(f"{UPSTREAM}/v1/messages").mock(
        httpx.Response(200, content=sse, headers={"content-type": "text/event-stream"})
    )
    async with _proxy_client() as client:
        response = await client.post("/v1/messages", json={"stream": True})
    assert response.headers["content-type"] == "text/event-stream"
    assert response.content == sse


@respx.mock
async def test_upstream_unreachable_is_502() -> None:
    respx.post(f"{UPSTREAM}/v1/messages").mock(side_effect=httpx.ConnectError)
    async with _proxy_client() as client:
        response = await client.post("/v1/messages", json={})
    assert response.status_code == 502


async def test_api_route_without_token_is_503(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("CLAUDE_CODE_OAUTH_TOKEN")
    async with _proxy_client() as client:
        response = await client.post("/v1/messages", json={})
    assert response.status_code == 503
