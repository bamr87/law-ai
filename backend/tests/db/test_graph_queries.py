"""Unit tests for app.db.graph_queries (spec 006).

Hermetic — uses ``FakeAsyncSession`` modelled after
``tests/db/test_citation_resolver.py``.
"""

from __future__ import annotations

from typing import Any

import pytest

from law_ai.core.neo4j import graph_queries


class _FakeResult:
    def __init__(self, records: list[dict[str, Any]]) -> None:
        self._records = records

    def __aiter__(self) -> _FakeResult:
        self._iter = iter(self._records)
        return self

    async def __anext__(self) -> dict[str, Any]:
        try:
            return next(self._iter)
        except StopIteration as exc:  # pragma: no cover - protocol boilerplate
            raise StopAsyncIteration from exc

    async def single(self) -> dict[str, Any] | None:
        return self._records[0] if self._records else None


class FakeAsyncSession:
    def __init__(self, canned: list[list[dict[str, Any]]]) -> None:
        self._canned = list(canned)
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def run(self, cypher: str, params: dict[str, Any]) -> _FakeResult:
        self.calls.append((cypher, params))
        records = self._canned.pop(0) if self._canned else []
        return _FakeResult(records)


@pytest.mark.asyncio
async def test_stats_returns_int_counts() -> None:
    session = FakeAsyncSession(
        canned=[[{"cases": 12, "citations": 30, "cites_edges": 7}]]
    )
    out = await graph_queries.stats(session)
    assert out == {"cases": 12, "citations": 30, "cites_edges": 7}


@pytest.mark.asyncio
async def test_stats_handles_empty_db() -> None:
    session = FakeAsyncSession(canned=[[]])
    assert await graph_queries.stats(session) == {
        "cases": 0,
        "citations": 0,
        "cites_edges": 0,
    }


_CASE_ROW = {
    "id": "case-a",
    "title": "Roe v. Wade",
    "court": "Supreme Court",
    "decided_at": "1973-01-22",
    "source": "courtlistener",
    "source_url": "https://example.test/roe",
    "confidence": 0.92,
}


@pytest.mark.asyncio
async def test_list_cases_passes_q_and_limit() -> None:
    session = FakeAsyncSession(canned=[[dict(_CASE_ROW)]])
    out = await graph_queries.list_cases(session, q="roe", limit=5)
    # The picker row now carries provenance so the sidebar inspector
    # (BL-20260429-23) has something to show without a second round-trip.
    assert out == [dict(_CASE_ROW)]
    _cypher, params = session.calls[0]
    assert params == {
        "q": "roe",
        "limit": 5,
        "court": "",
        "decided_from": "",
        "decided_to": "",
    }


@pytest.mark.asyncio
async def test_list_cases_binds_the_court_and_date_filters() -> None:
    # BL-20260429-23: every filter is parameter-bound (NFR-SEC-1) and
    # empty-string-disabled.
    session = FakeAsyncSession(canned=[[dict(_CASE_ROW)]])
    await graph_queries.list_cases(
        session,
        q="",
        limit=10,
        court="Supreme",
        decided_from="1970-01-01",
        decided_to="1980-01-01",
    )
    cypher, params = session.calls[0]
    assert params == {
        "q": "",
        "limit": 10,
        "court": "Supreme",
        "decided_from": "1970-01-01",
        "decided_to": "1980-01-01",
    }
    assert "$court" in cypher and "$decided_from" in cypher and "$decided_to" in cypher
    assert "Supreme" not in cypher
    # Court matching is case-insensitive substring, not equality.
    assert "toLower(coalesce(c.court, '')) CONTAINS toLower($court)" in cypher
    # Archived cases never reach the picker (constitution §4).
    assert "c.archived_at IS NULL" in cypher


@pytest.mark.asyncio
async def test_neighborhood_builds_cytoscape_payload() -> None:
    session = FakeAsyncSession(
        canned=[
            [
                {
                    "root": {
                        "id": "case-root",
                        "title": "Root v. State",
                        "court": "Supreme Court",
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
                    "incoming": [
                        {
                            "node": {
                                "id": "case-in",
                                "title": "In v. State",
                                "court": "Supreme Court",
                            },
                            "edge": {},
                        }
                    ],
                }
            ]
        ]
    )
    out = await graph_queries.neighborhood(session, "case-root", limit=10)
    node_ids = {n["data"]["id"] for n in out["nodes"]}
    edge_types = sorted(e["data"]["type"] for e in out["edges"])
    assert node_ids == {"case-root", "cit:410 us 113", "case-out", "case-in"}
    assert edge_types == ["CITES", "CITES", "HAS_CITATION"]
    _cypher, params = session.calls[0]
    assert params == {"case_id": "case-root", "limit": 10}


@pytest.mark.asyncio
async def test_neighborhood_missing_root_returns_empty() -> None:
    session = FakeAsyncSession(canned=[[{"root": None}]])
    assert await graph_queries.neighborhood(session, "missing") == {
        "nodes": [],
        "edges": [],
    }


# ---------------------------------------------------------------------------
# shortest_path (BL-20260429-22)
# ---------------------------------------------------------------------------


def _node(case_id: str, title: str, court: str = "us") -> dict[str, Any]:
    return {"id": case_id, "title": title, "court": court}


@pytest.mark.asyncio
async def test_shortest_path_returns_chain_marked_on_path() -> None:
    session = FakeAsyncSession(
        canned=[
            [
                {
                    "path_nodes": [
                        _node("a", "A v. B"),
                        _node("m", "M v. N"),
                        _node("z", "Y v. Z"),
                    ],
                    "path_rels": [
                        {"src": "a", "dst": "m"},
                        {"src": "m", "dst": "z"},
                    ],
                }
            ]
        ]
    )
    out = await graph_queries.shortest_path(session, "a", "z")
    assert out["found"] is True
    assert out["hops"] == 2
    assert [n["data"]["id"] for n in out["nodes"]] == ["a", "m", "z"]
    assert all(n["data"]["on_path"] is True for n in out["nodes"])
    assert [e["data"]["id"] for e in out["edges"]] == ["cites:a->m", "cites:m->z"]
    assert all(e["data"]["type"] == "CITES" for e in out["edges"])
    assert all(e["data"]["on_path"] is True for e in out["edges"])


@pytest.mark.asyncio
async def test_shortest_path_binds_ids_as_parameters() -> None:
    """NFR-SEC-1: only the validated hop bound is interpolated."""
    session = FakeAsyncSession(canned=[[]])
    await graph_queries.shortest_path(session, "a'--", "z", max_hops=3)
    cypher, params = session.calls[0]
    assert params == {"from_id": "a'--", "to_id": "z"}
    assert "$from_id" in cypher and "$to_id" in cypher
    assert "[:CITES*..3]" in cypher
    assert "a'--" not in cypher


@pytest.mark.asyncio
async def test_shortest_path_clamps_max_hops() -> None:
    session = FakeAsyncSession(canned=[[], []])
    await graph_queries.shortest_path(session, "a", "z", max_hops=999)
    assert f"[:CITES*..{graph_queries.MAX_PATH_HOPS}]" in session.calls[0][0]
    await graph_queries.shortest_path(session, "a", "z", max_hops=0)
    assert "[:CITES*..1]" in session.calls[1][0]


@pytest.mark.asyncio
async def test_shortest_path_no_chain_returns_not_found() -> None:
    session = FakeAsyncSession(canned=[[]])
    out = await graph_queries.shortest_path(session, "a", "z")
    assert out == {"nodes": [], "edges": [], "found": False, "hops": 0}


@pytest.mark.asyncio
async def test_shortest_path_same_case_is_a_zero_hop_chain() -> None:
    session = FakeAsyncSession(canned=[[{"c": _node("a", "A v. B")}]])
    out = await graph_queries.shortest_path(session, "a", "a")
    assert out["found"] is True
    assert out["hops"] == 0
    assert out["edges"] == []
    assert out["nodes"][0]["data"]["id"] == "a"
    # No shortestPath traversal is issued for the trivial case.
    assert "shortestPath" not in session.calls[0][0]


@pytest.mark.asyncio
async def test_shortest_path_same_case_missing_returns_not_found() -> None:
    session = FakeAsyncSession(canned=[[]])
    out = await graph_queries.shortest_path(session, "ghost", "ghost")
    assert out == {"nodes": [], "edges": [], "found": False, "hops": 0}


@pytest.mark.asyncio
async def test_shortest_path_excludes_archived_endpoints() -> None:
    """Constitution §4: soft-deleted cases must not appear in a chain."""
    session = FakeAsyncSession(canned=[[]])
    await graph_queries.shortest_path(session, "a", "z")
    assert "a.archived_at IS NULL" in session.calls[0][0]
    assert "b.archived_at IS NULL" in session.calls[0][0]


@pytest.mark.asyncio
async def test_list_courts_returns_distinct_courts_with_counts() -> None:
    """BL-20260905-89: the picker needs the corpus-wide court vocabulary."""
    session = FakeAsyncSession(
        canned=[
            [
                {"court": "Supreme Court", "count": 12},
                {"court": "10th Cir.", "count": 3},
            ]
        ]
    )
    out = await graph_queries.list_courts(session, limit=50)
    assert out == [
        {"court": "Supreme Court", "count": 12},
        {"court": "10th Cir.", "count": 3},
    ]
    cypher, params = session.calls[0]
    assert params == {"limit": 50}
    # Archived and court-less cases never reach the dropdown.
    assert "c.archived_at IS NULL" in cypher
    assert "coalesce(c.court, '') <> ''" in cypher


@pytest.mark.asyncio
async def test_list_courts_handles_empty_graph() -> None:
    session = FakeAsyncSession(canned=[[]])
    assert await graph_queries.list_courts(session) == []
    assert session.calls[0][1] == {"limit": 200}
