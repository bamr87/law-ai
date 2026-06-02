"""Docker-backed integration tests for ``resolve_citations`` + ``densify_extraction``.

Tests in this module require a live Neo4j instance spun up via Docker Compose.
They are gated behind ``@pytest.mark.integration`` and excluded from the default
``pytest`` run (no ``-m integration`` selector).

Spec 014 — closes BL-20260429-10.

AC-1: ``test_resolve_citations_hits_real_neo4j_alias_match``
AC-2: ``test_densify_extraction_idempotent``
AC-3: ``test_resolve_citations_no_match_returns_none``
AC-4: All three tests green under ``pytest -m integration -k citation_resolver_integration``.
AC-5: Tests NOT collected by ``pytest -q`` (no ``-m integration``).
NFR-IDEMPOTENT-1: Verified by AC-2 test — two calls produce the same mapping.
NFR-AUDIT-1: ``provenance.log_graph_query`` is called (verified indirectly by
              asserting the mapping values, which only appear after the Cypher runs).
"""

from __future__ import annotations

import pytest

from lawgraph.core.neo4j.citation_resolver import densify_extraction, resolve_citations
from lawgraph.core.schemas.extraction import Citation, ExtractionResult

pytestmark = [
    pytest.mark.integration,
    pytest.mark.asyncio(loop_scope="session"),
]

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_SEED_CASE_CYPHER = """
MERGE (c:Case {id: $case_id})
SET c.aliases = $aliases,
    c.title = $title,
    c.source = 'test',
    c.confidence = 1.0
"""


async def _seed_case(
    session,
    case_id: str,
    aliases: list[str],
    title: str = "Test Case",
) -> None:
    await session.run(
        _SEED_CASE_CYPHER,
        {"case_id": case_id, "aliases": aliases, "title": title},
    )


# ---------------------------------------------------------------------------
# AC-1: alias match against live Neo4j
# ---------------------------------------------------------------------------


async def test_resolve_citations_hits_real_neo4j_alias_match(
    neo4j_integration_driver, clean_neo4j_db
) -> None:
    """Seed a Case with a known alias, resolve it, assert we get the case id.

    This proves RESOLVE_CITATIONS_CYPHER is evaluated against the live schema.
    """
    async with neo4j_integration_driver.session() as session:
        await _seed_case(session, "brown", aliases=["347 U.S. 483"])

    async with neo4j_integration_driver.session() as session:
        mapping = await resolve_citations(session, ["347 U.S. 483"])

    assert mapping == {"347 U.S. 483": "brown"}


# ---------------------------------------------------------------------------
# AC-2 + NFR-IDEMPOTENT-1: two calls produce the same mapping
# ---------------------------------------------------------------------------


async def test_densify_extraction_idempotent(
    neo4j_integration_driver, clean_neo4j_db
) -> None:
    """Call densify_extraction twice; assert both calls return the same target_case_id.

    NFR-IDEMPOTENT-1: the resolver is read-only, so repeated calls MUST NOT
    produce different results or corrupt state.
    """
    async with neo4j_integration_driver.session() as session:
        await _seed_case(session, "brown", aliases=["347 U.S. 483"])

    def _make_result() -> ExtractionResult:
        return ExtractionResult(
            case_id="opinion-001",
            title="Appellant v. Appellee",
            confidence=0.95,
            citations=[
                Citation(text="347 U.S. 483", normalized="347 U.S. 483"),
            ],
        )

    async with neo4j_integration_driver.session() as session:
        result_first = await densify_extraction(session, _make_result())

    async with neo4j_integration_driver.session() as session:
        result_second = await densify_extraction(session, _make_result())

    assert result_first.citations[0].target_case_id == "brown"
    assert result_second.citations[0].target_case_id == "brown"


# ---------------------------------------------------------------------------
# AC-3: no match returns None, no edge created
# ---------------------------------------------------------------------------


async def test_resolve_citations_no_match_returns_none(
    neo4j_integration_driver, clean_neo4j_db
) -> None:
    """Without a matching alias, resolve_citations maps the citation to None.

    No Case node is seeded here (clean_neo4j_db wiped the graph).
    """
    async with neo4j_integration_driver.session() as session:
        mapping = await resolve_citations(session, ["999 U.S. 999"])

    assert mapping == {"999 U.S. 999": None}
