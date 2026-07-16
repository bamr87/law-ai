"""Tests for /api/graph/* (spec 006)."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from law_ai.graph import urls as graph_api
from law_ai.asgi import application as app
from tests.db.test_graph_queries import FakeAsyncSession


def _patch_session(monkeypatch: pytest.MonkeyPatch, session: Any) -> None:
    @asynccontextmanager
    async def fake_open() -> AsyncIterator[Any]:
        yield session

    monkeypatch.setattr(graph_api, "_open_session", fake_open)


def _patch_session_failure(monkeypatch: pytest.MonkeyPatch, exc: Exception) -> None:
    @asynccontextmanager
    async def fake_open() -> AsyncIterator[Any]:
        raise exc
        yield  # pragma: no cover

    monkeypatch.setattr(graph_api, "_open_session", fake_open)


@pytest_asyncio.fixture
async def client() -> AsyncIterator[AsyncClient]:
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac


@pytest.mark.asyncio
async def test_stats_returns_counts(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    # AC-1 + AC-5
    session = FakeAsyncSession(
        canned=[[{"cases": 5, "citations": 10, "cites_edges": 3}]]
    )
    _patch_session(monkeypatch, session)
    res = await client.get("/api/graph/stats")
    assert res.status_code == 200
    body = res.json()
    assert body == {
        "available": True,
        "cases": 5,
        "citations": 10,
        "cites_edges": 3,
    }


@pytest.mark.asyncio
async def test_cases_passes_query_via_parameter_binding(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    # AC-2 + NFR-SEC-1
    session = FakeAsyncSession(
        canned=[
            [
                {
                    "id": "case-a",
                    "title": "Roe v. Wade",
                    "court": "Supreme Court",
                    "decided_at": "1973-01-22",
                }
            ]
        ]
    )
    _patch_session(monkeypatch, session)
    res = await client.get("/api/graph/cases", params={"q": "roe", "limit": 3})
    assert res.status_code == 200
    body = res.json()
    assert body["available"] is True
    assert body["count"] == 1
    assert body["cases"][0]["id"] == "case-a"
    # parameter binding, not interpolation
    _, params = session.calls[0]
    assert params == {"q": "roe", "limit": 3}


@pytest.mark.asyncio
async def test_cases_validates_limit(client: AsyncClient) -> None:
    res = await client.get("/api/graph/cases", params={"limit": 0})
    assert res.status_code == 422
    res = await client.get("/api/graph/cases", params={"limit": 9999})
    assert res.status_code == 422


@pytest.mark.asyncio
async def test_neighborhood_returns_cytoscape_shape(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    # AC-3
    session = FakeAsyncSession(
        canned=[
            [
                {
                    "root": {
                        "id": "case-root",
                        "title": "Root v. State",
                        "court": "Supreme Court",
                    },
                    "citations": [],
                    "outgoing": [
                        {
                            "node": {
                                "id": "case-out",
                                "title": "Out v. State",
                                "court": "Supreme Court",
                            },
                            "edge": {},
                        }
                    ],
                    "incoming": [],
                }
            ]
        ]
    )
    _patch_session(monkeypatch, session)
    res = await client.get("/api/graph/neighborhood/case-root")
    assert res.status_code == 200
    body = res.json()
    assert body["available"] is True
    assert {n["data"]["id"] for n in body["nodes"]} == {"case-root", "case-out"}
    assert body["edges"][0]["data"]["type"] == "CITES"


@pytest.mark.asyncio
async def test_endpoints_degrade_when_neo4j_unavailable(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    # AC-4 + NFR-DEGRADE-1
    _patch_session_failure(monkeypatch, RuntimeError("connection refused"))
    res = await client.get("/api/graph/stats")
    assert res.status_code == 200
    assert res.json() == {
        "available": False,
        "cases": 0,
        "citations": 0,
        "cites_edges": 0,
    }
    res = await client.get("/api/graph/cases")
    assert res.status_code == 200
    assert res.json() == {"available": False, "cases": [], "count": 0}
    res = await client.get("/api/graph/neighborhood/anything")
    assert res.status_code == 200
    assert res.json() == {"available": False, "nodes": [], "edges": []}


# --- Spec 009: per-router auth gating ---


@pytest.mark.asyncio
async def test_graph_auth_unset_open(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC-1 — default-open posture preserved on /api/graph."""
    _patch_session(monkeypatch, FakeAsyncSession([{"value": 0}]))
    res = await client.get("/api/graph/stats")
    assert res.status_code == 200


@pytest.mark.asyncio
async def test_graph_auth_falls_back_to_agent_key(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC-2/AC-3/AC-4 — fallback to AGENT_API_KEY when GRAPH_API_KEY unset."""
    from django.conf import settings

    monkeypatch.setattr(settings, "AGENT_API_KEY", "shared")
    _patch_session(monkeypatch, FakeAsyncSession([{"value": 0}]))

    res = await client.get("/api/graph/stats")
    assert res.status_code == 401
    assert res.json()["detail"] == "missing api key"

    res = await client.get("/api/graph/stats", headers={"X-API-Key": "wrong"})
    assert res.status_code == 401
    assert res.json()["detail"] == "invalid api key"

    res = await client.get("/api/graph/stats", headers={"X-API-Key": "shared"})
    assert res.status_code == 200


@pytest.mark.asyncio
async def test_graph_per_router_override(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """GRAPH_API_KEY override wins over fallback."""
    from django.conf import settings

    monkeypatch.setattr(settings, "AGENT_API_KEY", "shared")
    monkeypatch.setattr(settings, "GRAPH_API_KEY", "graph-key")
    _patch_session(monkeypatch, FakeAsyncSession([{"value": 0}]))

    res = await client.get("/api/graph/stats", headers={"X-API-Key": "shared"})
    assert res.status_code == 401
    res = await client.get("/api/graph/stats", headers={"X-API-Key": "graph-key"})
    assert res.status_code == 200
