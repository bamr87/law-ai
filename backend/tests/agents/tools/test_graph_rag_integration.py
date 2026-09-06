"""Docker-backed integration tests for ``GraphRAGRetriever`` (BL-20260810-18).

The unit tests in ``test_graph_rag.py`` drive a fake Neo4j session, so nothing
there proves the Cypher is valid, that the fulltext index is actually used, or
that ``CITES`` expansion traverses a real relationship. These do, against the
Neo4j the compose stack runs.

Gated behind ``@pytest.mark.integration`` (excluded from the default run).
Run with::

    make test-integration
    docker compose run --rm backend pytest -m integration -k graph_rag -q

Covers: fulltext hits, citation expansion, jurisdiction filtering,
``log_graph_query`` provenance rows, and the substring fallback when the
index is missing.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any

import pytest

from law_ai.agents_runtime.tools import graph_rag as gr

pytestmark = [
    pytest.mark.integration,
    pytest.mark.asyncio(loop_scope="session"),
]


_SEED_CYPHER = """
MERGE (c:Case {id: $id})
SET c.title = $title,
    c.holding_summary = $summary,
    c.court = $court,
    c.decided_at = $decided_at,
    c.source = 'test',
    c.source_url = $url,
    c.confidence = 1.0,
    c.archived_at = null
"""

_CITES_CYPHER = """
MATCH (a:Case {id: $from_id}), (b:Case {id: $to_id})
MERGE (a)-[:CITES]->(b)
"""


async def _seed_corpus(session: Any) -> None:
    """Two `us-supreme` cases and one `us-ca-9`; the first cites the third.

    Only the first mentions "estoppel", so the expansion leg is the only way
    the cited case can surface — which is what makes this GraphRAG rather
    than search.
    """
    rows = [
        {
            "id": "case:seed-a",
            "title": "Alpha v. Beta",
            "summary": "Equitable estoppel bars the inconsistent position.",
            "court": "us-supreme",
            "decided_at": "1994-06-13",
            "url": "https://example.test/alpha",
        },
        {
            "id": "case:seed-b",
            "title": "Gamma v. Delta",
            "summary": "Laches is distinct from the statute of limitations.",
            "court": "us-supreme",
            "decided_at": "2001-01-09",
            "url": "https://example.test/gamma",
        },
        {
            "id": "case:seed-c",
            "title": "Epsilon v. Zeta",
            "summary": "Reliance must be reasonable and detrimental.",
            "court": "us-ca-9",
            "decided_at": "1988-11-02",
            "url": "https://example.test/epsilon",
        },
    ]
    for row in rows:
        await session.run(_SEED_CYPHER, row)
    await session.run(_CITES_CYPHER, {"from_id": "case:seed-a", "to_id": "case:seed-c"})


async def _ensure_fulltext_index(session: Any) -> None:
    """Create the index from migration 007 and wait for it to come online.

    ``make test-integration`` never runs ``init-db.sh``, so the index the
    retriever prefers may be absent; creation is async in Neo4j, hence the
    explicit ``awaitIndexes``.
    """
    await session.run(
        f"CREATE FULLTEXT INDEX {gr.CASE_FULLTEXT_INDEX} IF NOT EXISTS "
        "FOR (c:Case) ON EACH [c.title, c.holding_summary]"
    )
    await session.run(
        f"CREATE FULLTEXT INDEX {gr.STATUTE_FULLTEXT_INDEX} IF NOT EXISTS "
        "FOR (s:StatuteSection) ON EACH [s.heading, s.text, s.citation]"
    )
    await session.run("CALL db.awaitIndexes(60)")


def _factory(driver: Any) -> Any:
    @asynccontextmanager
    async def factory() -> Any:
        async with driver.session() as session:
            yield session

    return factory


@pytest.fixture()
def graph_queries(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, int]]:
    """Capture every ``log_graph_query`` call (constitution §4)."""
    captured: list[tuple[str, int]] = []

    def _capture(cypher: str, params: dict, result_count: int, latency_ms: float):
        captured.append((cypher, result_count))

    monkeypatch.setattr(gr.provenance, "log_graph_query", _capture)
    return captured


class TestGraphRAGAgainstNeo4j:
    async def test_fulltext_hit_and_citation_expansion(
        self, neo4j_integration_driver, clean_neo4j_db, graph_queries
    ) -> None:
        async with neo4j_integration_driver.session() as session:
            await _ensure_fulltext_index(session)
            await _seed_corpus(session)

        retriever = gr.GraphRAGRetriever(
            session_factory=_factory(neo4j_integration_driver),
            include_statutes=False,
        )
        passages = await retriever({"question": "estoppel", "queries": ["estoppel"]})
        by_id = {p["id"]: p for p in passages}

        # Lexical leg found the case whose holding_summary mentions estoppel…
        assert "case:seed-a" in by_id
        assert by_id["case:seed-a"]["retrieval_mode"] == "lexical"
        # …and graph expansion pulled in the case it CITES, which the query
        # text alone would never have matched.
        assert "case:seed-c" in by_id
        assert by_id["case:seed-c"]["retrieval_mode"] == "cites_expansion"
        # Unrelated case stays out.
        assert "case:seed-b" not in by_id

        # §13 attribution survives the round-trip.
        assert by_id["case:seed-a"]["court"] == "us-supreme"
        assert by_id["case:seed-a"]["source_url"] == "https://example.test/alpha"
        assert by_id["case:seed-a"]["source"] == "test"

        coverage = retriever.last_coverage
        assert coverage.index_available is True
        assert coverage.result_count == 2
        assert coverage.expanded_count == 1
        assert coverage.date_earliest == "1988-11-02"
        assert coverage.date_latest == "1994-06-13"

        # Every Cypher round-trip is logged: the fulltext query and the
        # expansion at minimum.
        assert len(graph_queries) >= 2

    async def test_jurisdiction_filter_drops_other_courts(
        self, neo4j_integration_driver, clean_neo4j_db, graph_queries
    ) -> None:
        async with neo4j_integration_driver.session() as session:
            await _ensure_fulltext_index(session)
            await _seed_corpus(session)

        retriever = gr.GraphRAGRetriever(
            session_factory=_factory(neo4j_integration_driver),
            include_statutes=False,
        )
        passages = await retriever(
            {
                "question": "reliance",
                "queries": ["reliance"],
                "jurisdiction": "us-ca-9",
            }
        )
        assert {p["id"] for p in passages} == {"case:seed-c"}
        assert retriever.last_coverage.jurisdiction_absent is False

    async def test_absent_jurisdiction_is_reported_not_hidden(
        self, neo4j_integration_driver, clean_neo4j_db, graph_queries
    ) -> None:
        async with neo4j_integration_driver.session() as session:
            await _ensure_fulltext_index(session)
            await _seed_corpus(session)

        retriever = gr.GraphRAGRetriever(
            session_factory=_factory(neo4j_integration_driver),
            include_statutes=False,
        )
        await retriever(
            {
                "question": "estoppel",
                "queries": ["estoppel"],
                "jurisdiction": "us-tx",
            }
        )
        coverage = retriever.last_coverage
        assert coverage.result_count == 0
        assert "does NOT mean no such law exists" in coverage.note()

    async def test_substring_fallback_when_the_index_is_missing(
        self, neo4j_integration_driver, clean_neo4j_db, graph_queries
    ) -> None:
        """A fresh DB without migration 007 must still return the hit."""
        async with neo4j_integration_driver.session() as session:
            await _seed_corpus(session)
            await session.run(f"DROP INDEX {gr.CASE_FULLTEXT_INDEX} IF EXISTS")
            await session.run("CALL db.awaitIndexes(60)")

        retriever = gr.GraphRAGRetriever(
            session_factory=_factory(neo4j_integration_driver),
            include_statutes=False,
        )
        try:
            passages = await retriever(
                {"question": "estoppel", "queries": ["estoppel"]}
            )
            assert "case:seed-a" in {p["id"] for p in passages}
            assert retriever.last_coverage.index_available is False
        finally:
            # Index state is shared across the DB; put it back for later tests.
            async with neo4j_integration_driver.session() as session:
                await _ensure_fulltext_index(session)
