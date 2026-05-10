"""Integration tests for IngestionScout against real Neo4j + Postgres (spec 013).

These tests run with `pytest -m integration` and require:
* Docker Compose stack (neo4j, postgres, redis) running
* Health checks passing (T-001)
* Integration fixtures from conftest.py (T-002)

AC-1: All three tests pass with zero failures.
AC-3: test_idempotency_no_duplicate_nodes asserts count(c) = 1.
AC-4: test_commit_high_confidence_creates_case_and_edges asserts edges >= 1.
AC-5: test_low_confidence_routes_to_postgres_pending_review confirms Postgres row exists, Neo4j node does not.
NFR-IDEMPOTENT-1: Verified by test_idempotency_no_duplicate_nodes.
"""

from __future__ import annotations

import pytest
from asgiref.sync import sync_to_async

from lawgraph.ingestionapp.models import PendingReview
from lawgraph.ingestionapp.services.scout import IngestionScout

# All tests in this module need the same event loop as the session-scoped
# async fixtures (``neo4j_integration_driver``, ``postgres_integration_pool``)
# in ``backend/tests/conftest.py``. Without ``loop_scope="session"`` on the
# asyncio marker, pytest-asyncio creates a fresh per-test loop and the
# driver's pending futures end up "attached to a different loop".
pytestmark = [
    pytest.mark.integration,
    pytest.mark.asyncio(loop_scope="session"),
]

# ---------------------------------------------------------------------------
# Fixture opinions (spec 013 plan.md §8)
# ---------------------------------------------------------------------------

HIGH_CONF_FIXTURE = {
    "id": 10001,
    "case_name": "Brown v. Board of Education",
    "absolute_url": "/opinion/10001/brown-v-board-of-education/",
    "plain_text": (
        "This landmark decision by the Supreme Court in Brown v. Board of Education, "
        "347 U.S. 483 (1954), declared state laws establishing separate public schools "
        "for black and white students to be unconstitutional. The decision effectively "
        "overturned the Plessy v. Ferguson decision of 1896, which allowed state-sponsored "
        "segregation. Chief Justice Earl Warren wrote the unanimous opinion, stating that "
        "'separate educational facilities are inherently unequal.' The Court cited social "
        "science evidence showing that segregation had a detrimental effect on minority "
        "children. This decision was a major victory for the civil rights movement and "
        "paved the way for integration and the Civil Rights Act of 1964. The case relied "
        "heavily on the Equal Protection Clause of the Fourteenth Amendment. Multiple lower "
        "court cases were consolidated, including Briggs v. Elliott, 342 U.S. 350 (1952), "
        "and Davis v. County School Board, 103 F. Supp. 337 (E.D. Va. 1952). The decision "
        "was followed by Brown II, 349 U.S. 294 (1955), which addressed implementation. "
        "See also Cooper v. Aaron, 358 U.S. 1 (1958); Green v. County School Board, "
        "391 U.S. 430 (1968); Swann v. Charlotte-Mecklenburg Board of Education, "
        "402 U.S. 1 (1971). The opinion is frequently cited in subsequent civil rights cases."
    ),
    "cluster": {
        "case_name": "Brown v. Board of Education",
        "court": "Supreme Court",
        "date_filed": "1954-05-17",
        "judges": "Warren, Black, Reed, Frankfurter, Douglas, Jackson, Burton, Clark, Minton",
    },
}

# Target case to pre-seed in Neo4j for citation resolution testing.
# spec 002: resolve_citations matches against `Case.aliases` using the
# lowercased/whitespace-collapsed form produced by `_extract_citations`
# in scout.py (" ".join(raw.split()).lower()). "342 U.S. 350" appears
# verbatim in HIGH_CONF_FIXTURE.plain_text below; we seed it lowercased
# so the resolver's exact-match Cypher hits.
TARGET_CASE = {
    "id": "briggs-v-elliott-1952",
    "title": "Briggs v. Elliott",
    "citation": "342 U.S. 350",
    "aliases": ["342 u.s. 350"],
    "court": "Supreme Court",
    "decided_at": "1952-01-28",
}

IDEMPOTENT_FIXTURE = {
    "id": 10002,
    "case_name": "Miranda v. Arizona",
    "absolute_url": "/opinion/10002/miranda-v-arizona/",
    "plain_text": (
        "In Miranda v. Arizona, 384 U.S. 436 (1966), the Supreme Court held that "
        "the prosecution may not use statements stemming from custodial interrogation "
        "of the defendant unless it demonstrates the use of procedural safeguards effective "
        "to secure the Fifth Amendment privilege against self-incrimination. The Court "
        "established the famous 'Miranda warnings' that police must read to suspects: "
        "the right to remain silent, that anything said can be used against them, the right "
        "to an attorney, and the right to a court-appointed attorney if indigent. This "
        "decision builds on earlier cases like Escobedo v. Illinois, 378 U.S. 478 (1964), "
        "and Gideon v. Wainwright, 372 U.S. 335 (1963). Chief Justice Warren again wrote "
        "for the majority. The case consolidated four separate cases, each presenting "
        "similar issues of custodial interrogation. The decision has been widely debated "
        "and refined in subsequent cases like Dickerson v. United States, 530 U.S. 428 (2000), "
        "and Berghuis v. Thompkins, 560 U.S. 370 (2010). The warnings must be given prior "
        "to any questioning when a person has been taken into custody or otherwise deprived "
        "of freedom. See also Rhode Island v. Innis, 446 U.S. 291 (1980); Edwards v. Arizona, "
        "451 U.S. 477 (1981); Arizona v. Roberson, 486 U.S. 675 (1988)."
    ),
    "cluster": {
        "case_name": "Miranda v. Arizona",
        "court": "Supreme Court",
        "date_filed": "1966-06-13",
        "judges": "Warren, Black, Douglas, Clark, Harlan, Brennan, Stewart, White, Fortas",
    },
}

LOW_CONF_FIXTURE = {
    "id": 10003,
    "case_name": "Untitled opinion",
    "plain_text": "",  # Empty text → confidence < 0.7
    "cluster": {},
}


# ---------------------------------------------------------------------------
# Integration tests (FR-1, AC-3, AC-4, AC-5)
# ---------------------------------------------------------------------------


async def test_commit_high_confidence_creates_case_and_edges(
    neo4j_integration_driver, clean_neo4j_db
):
    """AC-4: Commit a fixture opinion with citations and assert CITES edges exist.

    Steps:
    1. Pre-seed a target case (Plessy v. Ferguson) in Neo4j
    2. Run IngestionScout.run_and_commit with HIGH_CONF_FIXTURE
    3. Query for (source)-[:CITES]->(target) edges
    4. Assert edges >= 1
    """
    # Pre-seed target case (with aliases — spec 002 resolves against Case.aliases)
    async with neo4j_integration_driver.session() as session:
        await session.run(
            """
            CREATE (:Case {
                id: $id,
                title: $title,
                citation: $citation,
                aliases: $aliases,
                court: $court,
                decided_at: date($decided_at)
            })
            """,
            TARGET_CASE,
        )

    # Commit the high-confidence fixture
    scout = IngestionScout()
    summary = await scout.run_and_commit(HIGH_CONF_FIXTURE)

    # Verify summary indicates commit
    assert summary["committed"] is True
    assert summary["pending"] is False
    assert summary["confidence"] >= 0.7

    # Query for Case node
    async with neo4j_integration_driver.session() as session:
        result = await session.run(
            "MATCH (c:Case {id: $id}) RETURN c",
            {"id": "10001"},
        )
        record = await result.single()
        assert record is not None, "Case node should exist in Neo4j"

        # Query for CITES edges (AC-4)
        result = await session.run(
            """
            MATCH (source:Case {id: $id})-[:CITES]->(target:Case)
            RETURN count(target) AS edges
            """,
            {"id": "10001"},
        )
        record = await result.single()
        assert record is not None
        edges = record["edges"]
        assert edges >= 1, f"Expected at least 1 CITES edge, got {edges}"


async def test_idempotency_no_duplicate_nodes(neo4j_integration_driver, clean_neo4j_db):
    """AC-3, NFR-IDEMPOTENT-1: Run ingestion twice, assert count(Case) = 1.

    Steps:
    1. Run IngestionScout.run_and_commit with IDEMPOTENT_FIXTURE
    2. Run IngestionScout.run_and_commit with IDEMPOTENT_FIXTURE again (same payload)
    3. Query MATCH (c:Case {id: '10002'}) RETURN count(c)
    4. Assert count = 1
    """
    scout = IngestionScout()

    # First commit
    summary1 = await scout.run_and_commit(IDEMPOTENT_FIXTURE)
    assert summary1["committed"] is True

    # Second commit (idempotent)
    summary2 = await scout.run_and_commit(IDEMPOTENT_FIXTURE)
    assert summary2["committed"] is True

    # Query for count (AC-3)
    async with neo4j_integration_driver.session() as session:
        result = await session.run(
            "MATCH (c:Case {id: $id}) RETURN count(c) AS n",
            {"id": "10002"},
        )
        record = await result.single()
        assert record is not None
        count = record["n"]
        assert (
            count == 1
        ), f"Expected exactly 1 Case node, got {count} (NFR-IDEMPOTENT-1)"


async def test_low_confidence_routes_to_postgres_pending_review(
    neo4j_integration_driver, postgres_integration_pool, clean_neo4j_db, db
):
    """AC-5: Commit a low-confidence opinion and assert it goes to Postgres, not Neo4j.

    The ``db`` fixture (from pytest-django) is required so the in-process
    Celery eager task (``quarantine_extraction``) is allowed to use the
    Django ORM to write the PendingReview row. Without it, pytest-django
    blocks ORM access and the write silently fails.
    """
    scout = IngestionScout()
    summary = await scout.run_and_commit(LOW_CONF_FIXTURE)

    # Verify summary indicates quarantine
    assert summary["committed"] is False
    assert summary["pending"] is True
    assert summary["confidence"] < 0.7
    assert summary["edges"] == 0

    # Query Postgres via the Django ORM, wrapped in sync_to_async so it can
    # run from this async test (avoids SynchronousOnlyOperation). Going
    # through the ORM ensures we read from the same database/connection
    # that pytest-django + Celery eager mode just wrote into.
    pending_row = await sync_to_async(
        lambda: PendingReview.objects.filter(id="10003").first()
    )()
    assert pending_row is not None, "PendingReview row should exist in Postgres"
    assert pending_row.confidence < 0.7
    assert pending_row.source == "courtlistener"

    # Query Neo4j to confirm case is NOT there (AC-5)
    async with neo4j_integration_driver.session() as session:
        result = await session.run(
            "MATCH (c:Case {id: $id}) RETURN count(c) AS n",
            {"id": "10003"},
        )
        record = await result.single()
        assert record is not None
        count = record["n"]
        assert count == 0, f"Expected 0 Case nodes in Neo4j, got {count}"
