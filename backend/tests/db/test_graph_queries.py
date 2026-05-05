"""Unit tests for app.db.graph_queries (spec 006).

Hermetic — uses ``FakeAsyncSession`` modelled after
``tests/db/test_citation_resolver.py``.
"""

from __future__ import annotations

from typing import Any

import pytest

from lawgraph.core.neo4j import graph_queries


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


@pytest.mark.asyncio
async def test_list_cases_passes_q_and_limit() -> None:
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
    out = await graph_queries.list_cases(session, q="roe", limit=5)
    assert out == [
        {
            "id": "case-a",
            "title": "Roe v. Wade",
            "court": "Supreme Court",
            "decided_at": "1973-01-22",
        }
    ]
    _cypher, params = session.calls[0]
    assert params == {"q": "roe", "limit": 5}


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
