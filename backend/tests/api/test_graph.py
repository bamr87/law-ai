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
                    "source": "courtlistener",
                    "source_url": "https://example.test/roe",
                    "confidence": 0.92,
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
    assert params == {
        "q": "roe",
        "limit": 3,
        "court": "",
        "decided_from": "",
        "decided_to": "",
    }


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


# --- BL-20260429-22: /api/graph/path ---


@pytest.mark.asyncio
async def test_path_returns_marked_chain(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    session = FakeAsyncSession(
        canned=[
            [
                {
                    "path_nodes": [
                        {"id": "a", "title": "A v. B", "court": "us"},
                        {"id": "z", "title": "Y v. Z", "court": "us"},
                    ],
                    "path_rels": [{"src": "a", "dst": "z"}],
                }
            ]
        ]
    )
    _patch_session(monkeypatch, session)
    res = await client.get("/api/graph/path?from=a&to=z")
    assert res.status_code == 200
    body = res.json()
    assert body["available"] is True
    assert body["found"] is True
    assert body["hops"] == 1
    assert [n["data"]["id"] for n in body["nodes"]] == ["a", "z"]
    assert body["edges"][0]["data"]["on_path"] is True
    # NFR-SEC-1: ids reach Cypher as bound parameters.
    assert session.calls[0][1] == {"from_id": "a", "to_id": "z"}


@pytest.mark.asyncio
async def test_path_no_chain_reports_not_found(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_session(monkeypatch, FakeAsyncSession(canned=[[]]))
    res = await client.get("/api/graph/path?from=a&to=z")
    assert res.status_code == 200
    assert res.json() == {
        "available": True,
        "nodes": [],
        "edges": [],
        "found": False,
        "hops": 0,
    }


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "qs", ["", "?from=a", "?to=z", "?from=&to=z", "?from=a&to=%20"]
)
async def test_path_requires_both_ids(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch, qs: str
) -> None:
    _patch_session(monkeypatch, FakeAsyncSession(canned=[[]]))
    res = await client.get(f"/api/graph/path{qs}")
    assert res.status_code == 422


@pytest.mark.asyncio
async def test_path_rejects_out_of_range_max_hops(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_session(monkeypatch, FakeAsyncSession(canned=[[]]))
    res = await client.get("/api/graph/path?from=a&to=z&max_hops=99")
    assert res.status_code == 422
    res = await client.get("/api/graph/path?from=a&to=z&max_hops=nope")
    assert res.status_code == 422


@pytest.mark.asyncio
async def test_path_bounds_hops_into_the_pattern(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    session = FakeAsyncSession(canned=[[]])
    _patch_session(monkeypatch, session)
    res = await client.get("/api/graph/path?from=a&to=z&max_hops=2")
    assert res.status_code == 200
    assert "[:CITES*..2]" in session.calls[0][0]


@pytest.mark.asyncio
async def test_path_degrades_when_neo4j_is_down(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_session_failure(monkeypatch, RuntimeError("neo4j down"))
    res = await client.get("/api/graph/path?from=a&to=z")
    assert res.status_code == 200
    assert res.json() == {
        "available": False,
        "nodes": [],
        "edges": [],
        "found": False,
        "hops": 0,
    }


# --- BL-20260429-23: case-picker filters ---


def _case_row(**over: Any) -> dict[str, Any]:
    row = {
        "id": "case-a",
        "title": "Roe v. Wade",
        "court": "Supreme Court",
        "decided_at": "1973-01-22",
        "source": "courtlistener",
        "source_url": "https://example.test/roe",
        "confidence": 0.92,
    }
    row.update(over)
    return row


@pytest.mark.asyncio
async def test_cases_forwards_court_and_date_filters(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    session = FakeAsyncSession(canned=[[_case_row()]])
    _patch_session(monkeypatch, session)
    res = await client.get(
        "/api/graph/cases",
        params={
            "court": " Supreme ",
            "decided_from": "1970-01-01",
            "decided_to": "1980-12-31",
        },
    )
    assert res.status_code == 200
    _, params = session.calls[0]
    assert params["court"] == "Supreme"
    assert params["decided_from"] == "1970-01-01"
    assert params["decided_to"] == "1980-12-31"


@pytest.mark.asyncio
async def test_cases_returns_source_url_for_the_inspector(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_session(monkeypatch, FakeAsyncSession(canned=[[_case_row()]]))
    res = await client.get("/api/graph/cases")
    case = res.json()["cases"][0]
    assert case["source_url"] == "https://example.test/roe"
    assert case["source"] == "courtlistener"
    assert case["confidence"] == 0.92


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "params",
    [
        {"decided_from": "not-a-date"},
        {"decided_to": "1973-13-45"},
        {"decided_from": "1980-01-01", "decided_to": "1970-01-01"},
    ],
)
async def test_cases_rejects_bad_date_filters(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch, params: dict[str, str]
) -> None:
    _patch_session(monkeypatch, FakeAsyncSession(canned=[[]]))
    res = await client.get("/api/graph/cases", params=params)
    assert res.status_code == 422


@pytest.mark.asyncio
async def test_neighborhood_nodes_carry_full_properties(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The inspector needs the source URL, so the node payload must carry it."""
    session = FakeAsyncSession(
        canned=[
            [
                {
                    "root": {
                        "id": "case-root",
                        "title": "Root v. State",
                        "court": "Supreme Court",
                        "decided_at": "1973-01-22",
                        "source": "courtlistener",
                        "source_url": "https://example.test/root",
                        "confidence": 0.9,
                        "ingest_timestamp": "2026-01-01T00:00:00Z",
                        "agent_version": "v1",
                    },
                    "citations": [
                        {
                            "node": {
                                "normalized": "410 us 113",
                                "text": "410 U.S. 113",
                            },
                            "edge": {},
                        }
                    ],
                    "outgoing": [],
                    "incoming": [],
                }
            ]
        ]
    )
    _patch_session(monkeypatch, session)
    res = await client.get("/api/graph/neighborhood/case-root")
    nodes = {n["data"]["id"]: n["data"] for n in res.json()["nodes"]}
    root = nodes["case-root"]
    assert root["source_url"] == "https://example.test/root"
    assert root["decided_at"] == "1973-01-22"
    assert root["confidence"] == 0.9
    assert root["agent_version"] == "v1"
    cit = nodes["cit:410 us 113"]
    assert cit["normalized"] == "410 us 113"
    assert cit["text"] == "410 U.S. 113"


@pytest.mark.asyncio
async def test_courts_lists_corpus_wide_vocabulary(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """BL-20260905-89: /api/graph/courts feeds the picker's court dropdown."""
    session = FakeAsyncSession(
        canned=[
            [
                {"court": "Supreme Court", "count": 12},
                {"court": "10th Cir.", "count": 3},
            ]
        ]
    )
    _patch_session(monkeypatch, session)
    res = await client.get("/api/graph/courts")
    assert res.status_code == 200
    assert res.json() == {
        "available": True,
        "count": 2,
        "courts": [
            {"court": "Supreme Court", "count": 12},
            {"court": "10th Cir.", "count": 3},
        ],
    }
    assert session.calls[0][1] == {"limit": 200}


@pytest.mark.asyncio
async def test_courts_rejects_out_of_range_limit(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    session = FakeAsyncSession(canned=[[]])
    _patch_session(monkeypatch, session)
    res = await client.get("/api/graph/courts", params={"limit": 5000})
    assert res.status_code == 422


@pytest.mark.asyncio
async def test_courts_degrades_when_graph_is_down(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_session_failure(monkeypatch, RuntimeError("neo4j down"))
    res = await client.get("/api/graph/courts")
    assert res.status_code == 200
    assert res.json() == {"available": False, "courts": [], "count": 0}
