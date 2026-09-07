"""Unit tests for the citation resolver (spec 002).

Uses a hand-rolled ``FakeAsyncSession`` so the tests stay hermetic \u2014 no
Docker / Neo4j required (BL-20260429-10 will add the integration variant).
"""

from __future__ import annotations

from typing import Any

import pytest

from law_ai.core.neo4j.citation_resolver import (
    RESOLVE_CITATIONS_CYPHER,
    densify_extraction,
    resolve_citations,
)
from law_ai.core.schemas.extraction import Citation, ExtractionResult


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


class FakeAsyncSession:
    """Records every ``run`` call and returns the next canned result."""

    def __init__(self, canned: list[list[dict[str, Any]]]) -> None:
        self._canned = list(canned)
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def run(self, cypher: str, params: dict[str, Any]) -> _FakeResult:
        self.calls.append((cypher, params))
        records = self._canned.pop(0) if self._canned else []
        return _FakeResult(records)


def _make_result(citations: list[Citation]) -> ExtractionResult:
    return ExtractionResult(
        case_id="case-b",
        title="B v. State",
        citations=citations,
        confidence=0.9,
    )


@pytest.mark.asyncio
async def test_resolve_citations_empty_input_does_no_io() -> None:
    session = FakeAsyncSession(canned=[])
    assert await resolve_citations(session, []) == {}
    assert session.calls == []


@pytest.mark.asyncio
async def test_resolve_citations_returns_mapping_for_known_alias() -> None:
    # AC-1: "410 us 113" resolves to case-a; "999 zz 999" stays None.
    session = FakeAsyncSession(
        canned=[
            [
                {"normalized": "410 us 113", "case_id": "case-a"},
                {"normalized": "999 zz 999", "case_id": None},
            ]
        ]
    )
    mapping = await resolve_citations(session, ["410 us 113", "999 zz 999"])
    assert mapping == {"410 us 113": "case-a", "999 zz 999": None}
    assert len(session.calls) == 1
    cypher, params = session.calls[0]
    assert cypher == RESOLVE_CITATIONS_CYPHER
    assert params == {"normalized": ["410 us 113", "999 zz 999"]}


@pytest.mark.asyncio
async def test_densify_extraction_populates_target_case_id() -> None:
    # AC-1 end-to-end via the higher-level helper.
    citations = [
        Citation(text="410 U.S. 113", normalized="410 us 113"),
        Citation(text="999 Z.Z. 999", normalized="999 zz 999"),
    ]
    session = FakeAsyncSession(
        canned=[
            [
                {"normalized": "410 us 113", "case_id": "case-a"},
                {"normalized": "999 zz 999", "case_id": None},
            ]
        ]
    )
    out = await densify_extraction(session, _make_result(citations))
    assert out.citations[0].target_case_id == "case-a"
    assert out.citations[1].target_case_id is None


@pytest.mark.asyncio
async def test_densify_is_idempotent_on_repeated_calls() -> None:
    # AC-2: calling densify twice yields identical state \u2014 the resolver is
    # read-only so the only way to violate this is to mutate something we
    # shouldn't. Each call still issues exactly one Cypher query (NFR-PERF-1).
    citations = [Citation(text="410 U.S. 113", normalized="410 us 113")]
    canned = [
        [{"normalized": "410 us 113", "case_id": "case-a"}],
        [{"normalized": "410 us 113", "case_id": "case-a"}],
    ]
    session = FakeAsyncSession(canned=canned)
    result = _make_result(citations)
    first = await densify_extraction(session, result)
    second = await densify_extraction(session, result)
    assert first.citations[0].target_case_id == "case-a"
    assert second.citations[0].target_case_id == "case-a"
    assert len(session.calls) == 2  # one per densify, no extras


@pytest.mark.asyncio
async def test_densify_no_match_issues_one_query_and_no_edges() -> None:
    # AC-3: zero matches \u2192 still exactly one Cypher query, all targets None.
    citations = [
        Citation(text="X", normalized="x"),
        Citation(text="Y", normalized="y"),
    ]
    session = FakeAsyncSession(
        canned=[
            [{"normalized": "x", "case_id": None}, {"normalized": "y", "case_id": None}]
        ]
    )
    out = await densify_extraction(session, _make_result(citations))
    assert all(c.target_case_id is None for c in out.citations)
    assert len(session.calls) == 1


@pytest.mark.asyncio
async def test_densify_extraction_no_citations_short_circuits() -> None:
    session = FakeAsyncSession(canned=[])
    out = await densify_extraction(session, _make_result([]))
    assert out.citations == []
    assert session.calls == []


def test_resolve_cypher_orders_before_collect_for_determinism() -> None:
    """BL-20260429-12: ``head(collect(c.id))`` must be fed a sorted stream.

    Without the ``ORDER BY`` two Cases sharing an alias resolve to whichever
    node Neo4j scanned first. The live-graph proof is the integration test
    ``test_resolve_citations_overlapping_alias_is_deterministic``.
    """
    assert "ORDER BY n, c.id" in RESOLVE_CITATIONS_CYPHER
    order_at = RESOLVE_CITATIONS_CYPHER.index("ORDER BY n, c.id")
    collect_at = RESOLVE_CITATIONS_CYPHER.index("head(collect(c.id))")
    assert order_at < collect_at
