"""Docker-backed parity check for the Cypher migration set (BL-20260509-03).

``tests/core/test_neo4j_migrations.py`` reads the ``.cypher`` files and
asserts what they *declare*. This module applies the whole set to the live
compose Neo4j through the BL-20260509-02 runner and asserts that
``SHOW CONSTRAINTS`` / ``SHOW INDEXES`` agree with those declarations — the
half a file-content test cannot reach.

Gated behind ``@pytest.mark.integration``; run with ``make test-integration``.

Two live-schema realities this test pins down:

* The compose image is ``neo4j:5-community``, which rejects the
  property-existence constraints in ``006_derived_document``. The runner
  reports them as ``unsupported`` and leaves that file pending rather than
  failing the run, so this test asserts parity *minus* those two names and
  asserts the deferral explicitly.
* Schema objects outlive ``clean_neo4j_db`` (which only deletes nodes), so
  everything created here is dropped on teardown. Otherwise a later
  integration test would inherit constraints that reject its fixtures.
"""

from __future__ import annotations

from typing import Any

import pytest
import pytest_asyncio

from law_ai.core.neo4j import migrator
from tests.core.test_neo4j_migrations import expected_schema_names

pytestmark = [
    pytest.mark.integration,
    pytest.mark.asyncio(loop_scope="session"),
]

# Enterprise-only: property-existence constraints (006). Community refuses them.
ENTERPRISE_ONLY_CONSTRAINTS = {
    "derived_document_agent_version_exists",
    "derived_document_kind_exists",
}


async def _show(driver: Any, statement: str) -> list[dict[str, Any]]:
    async with driver.session() as session:
        result = await session.run(statement)
        return [dict(record) async for record in result]


async def _drop_all(driver: Any, names: dict[str, set[str]]) -> None:
    async with driver.session() as session:
        for name in sorted(names["constraints"] | {"migration_id_unique"}):
            await session.run(f"DROP CONSTRAINT {name} IF EXISTS")
        for name in sorted(names["indexes"] | names["fulltext"] | names["vector"]):
            await session.run(f"DROP INDEX {name} IF EXISTS")
        await session.run("MATCH (m:_Migration) DETACH DELETE m")


@pytest_asyncio.fixture(loop_scope="session")
async def migrated_graph(neo4j_integration_driver):
    """Apply every migration, yield ``(driver, plan)``, then drop what it made.

    Teardown matters: ``clean_neo4j_db`` only deletes nodes, so without this
    the uniqueness constraints would persist into other integration tests.
    """
    names = expected_schema_names()
    await _drop_all(neo4j_integration_driver, names)
    plan = await migrator.apply_migrations(neo4j_integration_driver)
    try:
        yield neo4j_integration_driver, plan
    finally:
        await _drop_all(neo4j_integration_driver, names)


async def test_constraints_match_the_declared_set(migrated_graph) -> None:
    """AC: SHOW CONSTRAINTS parity with the file-content declarations."""
    driver, _plan = migrated_graph
    live = {row["name"] for row in await _show(driver, "SHOW CONSTRAINTS YIELD name")}
    declared = expected_schema_names()["constraints"]
    supported = declared - ENTERPRISE_ONLY_CONSTRAINTS

    missing = supported - live
    assert not missing, f"declared but not created: {sorted(missing)}"
    # The runner's own bookkeeping constraint is expected on top of the set.
    assert "migration_id_unique" in live
    # Enterprise-only constraints genuinely are not there on this image.
    assert not (ENTERPRISE_ONLY_CONSTRAINTS & live)


async def test_indexes_match_the_declared_set_with_the_right_types(
    migrated_graph,
) -> None:
    """AC: SHOW INDEXES parity, including RANGE / FULLTEXT / VECTOR."""
    driver, _plan = migrated_graph
    rows = await _show(driver, "SHOW INDEXES YIELD name, type")
    live = {row["name"]: row["type"] for row in rows}
    declared = expected_schema_names()

    for name in sorted(declared["indexes"]):
        assert name in live, f"range index {name} was declared but not created"
        assert live[name] == "RANGE", f"{name} is {live[name]}, expected RANGE"
    for name in sorted(declared["fulltext"]):
        assert name in live, f"fulltext index {name} was declared but not created"
        assert live[name] == "FULLTEXT", f"{name} is {live[name]}, expected FULLTEXT"
    # BL-20260810-17: the GraphRAG vector leg is dead without these.
    for name in sorted(declared["vector"]):
        assert name in live, f"vector index {name} was declared but not created"
        assert live[name] == "VECTOR", f"{name} is {live[name]}, expected VECTOR"


async def test_community_edition_defers_the_existence_constraints(
    migrated_graph,
) -> None:
    """006 is reported, not fatal, and stays pending on Community."""
    _driver, plan = migrated_graph
    assert "006_derived_document" in plan.deferred
    # Both existence constraints in 006 are rejected, and both are reported.
    assert {mid for mid, _ in plan.unsupported} == {"006_derived_document"}
    assert len(plan.unsupported) == 2
    assert all("IS NOT NULL" in stmt for _, stmt in plan.unsupported)
    assert "006_derived_document" not in plan.applied


async def test_applied_migrations_are_recorded_and_the_rerun_is_a_no_op(
    migrated_graph,
) -> None:
    """The bookkeeping node is what makes a non-idempotent migration safe."""
    driver, plan = migrated_graph
    assert "001_case_constraints" in plan.applied
    assert "007_fulltext_indexes" in plan.applied
    assert "008_vector_indexes" in plan.applied

    recorded = await migrator.applied_migrations(driver)
    assert set(plan.applied) <= set(recorded)

    second = await migrator.apply_migrations(driver)
    assert second.applied == []
    assert set(plan.applied) <= set(second.skipped)
    assert second.checksum_mismatches == []
    # 006 is still pending, and retrying it is still non-fatal. Only its
    # supported statement re-runs, and IF NOT EXISTS makes that free.
    assert second.deferred == ["006_derived_document"]
    assert second.statements_run == 1


async def test_the_migration_node_carries_its_checksum(migrated_graph) -> None:
    driver, _plan = migrated_graph
    rows = await _show(
        driver,
        "MATCH (m:_Migration {id: '001_case_constraints'}) "
        "RETURN m.checksum AS checksum, m.statement_count AS n, "
        "m.applied_at AS applied_at",
    )
    assert len(rows) == 1
    path = next(
        p
        for p in migrator.discover()
        if migrator.migration_id(p) == "001_case_constraints"
    )
    assert rows[0]["checksum"] == migrator.checksum(path.read_text())
    assert rows[0]["n"] == len(migrator.split_statements(path.read_text()))
    assert rows[0]["applied_at"] is not None
