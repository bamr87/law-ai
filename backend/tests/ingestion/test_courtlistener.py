"""Unit tests for CourtListenerClient (T-002).

Network is mocked with respx; no real HTTP calls.
"""

from __future__ import annotations

import httpx
import pytest
import respx

from lexgraph.ingestionapp.services.courtlistener import (
    BASE_URL,
    CourtListenerClient,
    CourtListenerError,
)


@pytest.mark.asyncio
@respx.mock
async def test_fetch_opinion_returns_payload() -> None:
    respx.get(f"{BASE_URL}/opinions/42/").mock(
        return_value=httpx.Response(200, json={"id": 42, "case_name": "Foo"})
    )
    async with CourtListenerClient(api_token=None) as c:
        payload = await c.fetch_opinion(42)
    assert payload["id"] == 42


@pytest.mark.asyncio
@respx.mock
async def test_fetch_opinion_retries_on_503_then_succeeds() -> None:
    route = respx.get(f"{BASE_URL}/opinions/7/").mock(
        side_effect=[
            httpx.Response(503),
            httpx.Response(503),
            httpx.Response(200, json={"id": 7, "case_name": "Bar"}),
        ]
    )
    async with CourtListenerClient(api_token=None) as c:
        payload = await c.fetch_opinion(7)
    assert payload["id"] == 7
    assert route.call_count == 3


@pytest.mark.asyncio
@respx.mock
async def test_fetch_opinion_raises_on_404() -> None:
    respx.get(f"{BASE_URL}/opinions/9999/").mock(
        return_value=httpx.Response(404, text="nope")
    )
    async with CourtListenerClient(api_token=None) as c:
        with pytest.raises(CourtListenerError):
            await c.fetch_opinion(9999)


@pytest.mark.asyncio
@respx.mock
async def test_list_opinions_paginates_and_caps_at_limit() -> None:
    respx.get(f"{BASE_URL}/opinions/").mock(
        return_value=httpx.Response(
            200,
            json={
                "results": [{"id": i, "case_name": f"Case {i}"} for i in range(50)],
                "next": None,
            },
        )
    )
    async with CourtListenerClient(api_token=None) as c:
        ids = [op["id"] async for op in c.list_opinions(limit=10, page_size=50)]
    assert ids == list(range(10))


@pytest.mark.asyncio
@respx.mock
async def test_api_token_attached_when_provided() -> None:
    route = respx.get(f"{BASE_URL}/opinions/1/").mock(
        return_value=httpx.Response(200, json={"id": 1})
    )
    async with CourtListenerClient(api_token="secret-token") as c:
        await c.fetch_opinion(1)
    assert route.calls.last.request.headers["Authorization"] == "Token secret-token"
