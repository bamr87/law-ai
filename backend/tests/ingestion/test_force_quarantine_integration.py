"""Live-stack integration test for the full ``force_quarantine`` path.

BL-20260602-01: adapter with ``requires_human_approval=True`` → TopicFrontier
dispatch → ``IngestionScout.run_and_commit(force_quarantine=True)`` → Celery
``quarantine_extraction`` → a real ``PendingReview`` row in Postgres, with
**nothing** in Neo4j.

Until BL-20260510-01 was fixed, that chain could not be asserted at all: the
eager Celery task's ORM write raised ``SynchronousOnlyOperation`` inside the
async scout and every quarantine silently fell back to the JSONL spool. The
scout now dispatches through ``sync_to_async``, so the row really is written —
which is exactly what this test pins.

Run with ``make test-integration`` (real Postgres + Redis + Neo4j).
"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from asgiref.sync import sync_to_async

import law_ai.agents_runtime.graphs.topic_frontier as tf_module
from law_ai.agents_runtime.graphs.topic_frontier import TopicFrontier
from law_ai.ingestionapp.models import PendingReview
from law_ai.ingestionapp.quarantine_kinds import KIND_CASE
from law_ai.ingestionapp.services.scout import IngestionScout

_NEO4J_URI = os.getenv("NEO4J_URI", "")

pytestmark = [pytest.mark.integration, pytest.mark.django_db(transaction=True)]

DOC_URL = "https://integration-test.example.com/force-quarantine-01"

# Scores 0.9 under ``scout._score`` — it would be committed straight to Neo4j
# were it not for the adapter's HITL flag.
HIGH_CONF_TEXT = (
    "The judgment of the district court is affirmed. See Marbury v. Madison, "
    "5 U.S. 137 (1803); Brown v. Board of Education, 347 U.S. 483 (1954); "
    "Roe v. Wade, 410 U.S. 113 (1973); Miranda v. Arizona, 384 U.S. 436 "
    "(1966); Gideon v. Wainwright, 372 U.S. 335 (1963). Appellant's remaining "
    "contentions are without merit and warrant no extended discussion. The "
    "findings below are supported by substantial evidence in the record as a "
    "whole, and the legal conclusions drawn from them comport with our "
    "precedent, so we decline to disturb the judgment. It is so ordered."
)


async def _get_row(pk: str) -> Any:
    """Read a row from the async test body (Django forbids sync ORM there)."""
    return await sync_to_async(PendingReview.objects.get)(pk=pk)


def _new_driver() -> Any:
    """A driver bound to *this* test's event loop.

    The module-level driver singleton binds to whichever loop first touched
    it, and neo4j's async driver refuses reuse from another loop ("Future
    attached to a different loop").
    """
    from django.conf import settings
    from neo4j import AsyncGraphDatabase

    return AsyncGraphDatabase.driver(
        settings.NEO4J_URI, auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD)
    )


async def _case_count(driver: Any, case_id: str) -> int:
    async with driver.session() as session:
        result = await session.run(
            "MATCH (c:Case {id: $id}) RETURN count(c) AS n", {"id": case_id}
        )
        record = await result.single()
    return int(record["n"]) if record else 0


@pytest.fixture(autouse=True)
def _clean_rows() -> Any:
    PendingReview.objects.filter(id__startswith=DOC_URL).delete()
    yield
    PendingReview.objects.filter(id__startswith=DOC_URL).delete()


@pytest.mark.skipif(not _NEO4J_URI, reason="NEO4J_URI not set")
@pytest.mark.asyncio
async def test_force_quarantine_writes_a_pending_review_row(
    docker_services: Any,
) -> None:
    """A forced quarantine reaches Postgres, not the JSONL fallback."""
    driver = _new_driver()
    scout = IngestionScout()
    summary = await scout.run_and_commit(
        {
            "id": DOC_URL,
            "case_name": "Integration v. Quarantine",
            "plain_text": HIGH_CONF_TEXT,
            "absolute_url": DOC_URL,
        },
        force_quarantine=True,
    )

    assert summary["committed"] is False
    assert summary["pending"] is True
    assert summary["confidence"] >= 0.7  # would have been auto-committed

    row = await _get_row(DOC_URL)
    assert row.source == "courtlistener"
    assert row.kind == KIND_CASE
    assert row.approved is None
    assert row.committed_at is None
    assert row.payload["payload"]["case_name"] == "Integration v. Quarantine"
    try:
        assert await _case_count(driver, DOC_URL) == 0
    finally:
        await driver.close()


@pytest.mark.skipif(not _NEO4J_URI, reason="NEO4J_URI not set")
@pytest.mark.asyncio
async def test_hitl_adapter_dispatch_quarantines_end_to_end(
    docker_services: Any,
) -> None:
    """The whole chain: HITL adapter → dispatch → Celery → PendingReview."""
    driver = _new_driver()

    adapter = MagicMock()
    adapter.name = "courtlistener"
    adapter.jurisdiction = "*"
    adapter.requires_human_approval = True  # the flag under test
    doc = MagicMock()
    doc.source_name = "courtlistener"
    doc.source_url = DOC_URL
    doc.title = "Integration v. Quarantine"
    doc.text = HIGH_CONF_TEXT
    adapter.fetch.return_value = [doc]

    @asynccontextmanager
    async def _real_session() -> Any:
        async with driver.session() as session:
            yield session

    with (
        patch.object(
            tf_module.settings,
            "AUTONOMY_ALLOWED_SOURCES",
            ["courtlistener"],
            create=True,
        ),
        patch.object(tf_module.audit_jsonl, "record", lambda _: None),
    ):
        frontier = TopicFrontier(
            neo4j_session_factory=_real_session,
            llm_caller=lambda *_, **__: (
                '[{"query": "force quarantine", "jurisdiction": "*", '
                '"reason": "test", "priority": 1}]'
            ),
            registry={"courtlistener": adapter},
            scout_factory=IngestionScout,
        )
        output = await frontier.run(trace_id="integration-force-quarantine-01")

    assert output.human_approval_required is True
    assert all(not d.committed for d in output.dispatched)

    row = await _get_row(DOC_URL)
    assert row.approved is None
    assert row.confidence >= 0.7
    try:
        assert await _case_count(driver, DOC_URL) == 0
    finally:
        await driver.close()
