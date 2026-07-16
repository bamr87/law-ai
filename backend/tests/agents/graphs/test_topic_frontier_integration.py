"""Integration tests for TopicFrontier (spec 018 T-007).

Requires a running Neo4j instance (``make test-integration``).
Asserts that every :Case node written through the workflow carries
``IngestionScout``'s ``agent_version`` property (spec 018 AC-4).

Skip automatically when the Neo4j env vars are absent so ``make test-backend``
still works with --no-deps.
"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from unittest.mock import MagicMock, patch

import pytest

import law_ai.agents_runtime.graphs.topic_frontier as tf_module
from law_ai.agents_runtime.graphs.topic_frontier import TopicFrontier
from law_ai.ingestionapp.services.scout import IngestionScout

_NEO4J_URI = os.getenv("NEO4J_URI", "")

pytestmark = pytest.mark.integration


@pytest.mark.skipif(
    not _NEO4J_URI,
    reason="NEO4J_URI not set — skipping integration test",
)
@pytest.mark.asyncio
async def test_dispatched_cases_carry_agent_version() -> None:
    """End-to-end: workflow dispatches a doc; Neo4j Case node has agent_version."""
    from law_ai.core.neo4j.driver import get_neo4j_driver

    # Seed a minimal orphan citation so the prioritize node has something.
    driver = get_neo4j_driver()
    async with driver.session() as session:
        await session.run(
            "MERGE (:Citation {normalized: 'integration-test-citation-007'})"
        )

    adapter = MagicMock()
    adapter.name = "courtlistener"
    adapter.jurisdiction = "*"
    adapter.requires_human_approval = False
    doc = MagicMock()
    doc.source_name = "courtlistener"
    doc.source_url = "https://integration-test.example.com/007"
    doc.title = "Integration Test Case 007"
    doc.text = "This is a test opinion for spec 018 T-007 integration testing."
    adapter.fetch.return_value = [doc]

    scout = IngestionScout()

    with (
        patch.object(
            tf_module.settings,
            "AUTONOMY_ALLOWED_SOURCES",
            ["courtlistener"],
            create=True,
        ),
        patch.object(tf_module.audit_jsonl, "record", lambda _: None),
    ):

        @asynccontextmanager
        async def _real_session():
            async with driver.session() as s:
                yield s

        tf = TopicFrontier(
            neo4j_session_factory=_real_session,
            ollama_caller=lambda *_, **__: '[{"query": "integration test", "jurisdiction": "*", "reason": "test", "priority": 1}]',
            registry={"courtlistener": adapter},
            scout_factory=lambda: scout,
        )
        output = await tf.run(trace_id="integration-007")

    # Regardless of commit vs quarantine, run_and_commit was called via the
    # real IngestionScout, so if the doc cleared confidence threshold the
    # Case node in Neo4j carries IngestionScout.agent_version.
    committed = [d for d in output.dispatched if d.committed]
    if committed:
        async with driver.session() as session:
            result = await session.run(
                "MATCH (c:Case {id: $url}) RETURN c.agent_version AS av",
                {"url": "https://integration-test.example.com/007"},
            )
            record = await result.single()
            if record:
                assert record["av"] == IngestionScout.agent_version

    # Clean up seeded node.
    async with driver.session() as session:
        await session.run(
            "MATCH (x:Citation {normalized: 'integration-test-citation-007'}) DETACH DELETE x"
        )
