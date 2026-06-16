"""Docker-backed integration tests for ``graph_queries.neighborhood`` (spec 006).

These require a live Neo4j spun up via Docker Compose. They are gated behind
``@pytest.mark.integration`` and excluded from the default ``pytest`` run (no
``-m integration`` selector) — mirroring ``test_citation_resolver_integration``.

Closes **BL-20260429-21** ("Docker-backed integration test for
``graph_queries.neighborhood`` against a real Neo4j; mirrors BL-20260429-10").
The hermetic unit test in ``test_graph_queries.py`` drives a ``FakeAsyncSession``
with canned records, so it can only prove the *Python* assembly of the Cytoscape
payload — it never evaluates ``NEIGHBORHOOD_CYPHER`` against the real schema.
These tests close that gap: they seed a tiny graph and assert the traversal,
de-duplication, edge direction, and the ``$limit`` slice all behave on live Neo4j.

AC-1: ``test_neighborhood_full_returns_cytoscape_graph`` — root + citation +
       outgoing + incoming edges all surface with correct ids/types/direction.
AC-2: ``test_neighborhood_missing_root_returns_empty`` — unknown id → empty graph.
AC-3: ``test_neighborhood_isolated_root_has_no_edges`` — lone node, no edges.
AC-4: ``test_neighborhood_respects_limit`` — the ``[0..$limit]`` slice bounds
       each relationship bucket (NFR-PERF-1), which the hermetic test can't prove.
AC-5: NOT collected by ``pytest -q`` (no ``-m integration``).
"""

from __future__ import annotations

import pytest

from lawgraph.core.neo4j.graph_queries import neighborhood

pytestmark = [
    pytest.mark.integration,
    pytest.mark.asyncio(loop_scope="session"),
]

# ---------------------------------------------------------------------------
# Seed helpers
# ---------------------------------------------------------------------------

_SEED_FULL_CYPHER = """
MERGE (root:Case {id: 'root'})
  SET root.title = 'Root v. State', root.court = 'SCOTUS',
      root.source = 'test', root.confidence = 1.0
MERGE (out:Case {id: 'out'})
  SET out.title = 'Outgoing v. State', out.court = '10th Cir.',
      out.source = 'test', out.confidence = 1.0
MERGE (inc:Case {id: 'inc'})
  SET inc.title = 'Incoming v. State', inc.court = 'Colo.',
      inc.source = 'test', inc.confidence = 1.0
MERGE (cit:Citation {normalized: '347 U.S. 483'})
  SET cit.text = '347 U.S. 483'
MERGE (root)-[:HAS_CITATION]->(cit)
MERGE (root)-[:CITES]->(out)
MERGE (inc)-[:CITES]->(root)
"""

_SEED_ISOLATED_CYPHER = """
MERGE (root:Case {id: 'lonely'})
  SET root.title = 'Lonely v. State', root.source = 'test', root.confidence = 1.0
"""

_SEED_FANOUT_CYPHER = """
MERGE (root:Case {id: 'root'})
  SET root.title = 'Root v. State', root.source = 'test', root.confidence = 1.0
WITH root
UNWIND ['a', 'b', 'c'] AS nid
MERGE (n:Case {id: nid})
  SET n.title = 'Case ' + nid, n.source = 'test', n.confidence = 1.0
MERGE (root)-[:CITES]->(n)
"""


def _edge_set(graph: dict) -> set[tuple[str, str, str]]:
    """``{(source, target, type)}`` for order-independent edge assertions."""
    return {
        (e["data"]["source"], e["data"]["target"], e["data"]["type"])
        for e in graph["edges"]
    }


def _nodes_by_id(graph: dict) -> dict[str, dict]:
    return {n["data"]["id"]: n["data"] for n in graph["nodes"]}


# ---------------------------------------------------------------------------
# AC-1: full 1-hop neighborhood
# ---------------------------------------------------------------------------


async def test_neighborhood_full_returns_cytoscape_graph(
    neo4j_integration_driver, clean_neo4j_db
) -> None:
    """Seed root + citation + outgoing + incoming, assert the live traversal.

    Proves NEIGHBORHOOD_CYPHER runs against the real schema and the Cytoscape
    assembly preserves edge direction and node typing.
    """
    async with neo4j_integration_driver.session() as session:
        await session.run(_SEED_FULL_CYPHER)

    async with neo4j_integration_driver.session() as session:
        graph = await neighborhood(session, "root")

    nodes = _nodes_by_id(graph)
    assert set(nodes) == {"root", "cit:347 U.S. 483", "out", "inc"}
    assert nodes["root"]["type"] == "Case"
    assert nodes["root"]["label"] == "Root v. State"
    assert nodes["root"]["court"] == "SCOTUS"
    assert nodes["cit:347 U.S. 483"]["type"] == "Citation"
    assert nodes["cit:347 U.S. 483"]["label"] == "347 U.S. 483"
    assert nodes["out"]["type"] == "Case"
    assert nodes["inc"]["type"] == "Case"

    # Direction matters: root→citation, root→out (outgoing), inc→root (incoming).
    assert _edge_set(graph) == {
        ("root", "cit:347 U.S. 483", "HAS_CITATION"),
        ("root", "out", "CITES"),
        ("inc", "root", "CITES"),
    }


# ---------------------------------------------------------------------------
# AC-2: unknown root → empty graph
# ---------------------------------------------------------------------------


async def test_neighborhood_missing_root_returns_empty(
    neo4j_integration_driver, clean_neo4j_db
) -> None:
    """An id with no matching Case returns ``{nodes: [], edges: []}``."""
    async with neo4j_integration_driver.session() as session:
        graph = await neighborhood(session, "does-not-exist")

    assert graph == {"nodes": [], "edges": []}


# ---------------------------------------------------------------------------
# AC-3: isolated root → the node, no edges
# ---------------------------------------------------------------------------


async def test_neighborhood_isolated_root_has_no_edges(
    neo4j_integration_driver, clean_neo4j_db
) -> None:
    """A Case with no relationships yields itself and an empty edge list.

    Exercises the ``OPTIONAL MATCH`` arms returning empty buckets.
    """
    async with neo4j_integration_driver.session() as session:
        await session.run(_SEED_ISOLATED_CYPHER)

    async with neo4j_integration_driver.session() as session:
        graph = await neighborhood(session, "lonely")

    assert [n["data"]["id"] for n in graph["nodes"]] == ["lonely"]
    assert graph["edges"] == []


# ---------------------------------------------------------------------------
# AC-4: $limit bounds each relationship bucket (NFR-PERF-1)
# ---------------------------------------------------------------------------


async def test_neighborhood_respects_limit(
    neo4j_integration_driver, clean_neo4j_db
) -> None:
    """With 3 outgoing CITES and ``limit=2``, only 2 outgoing edges return.

    The ``out_raw[0..$limit]`` slice in NEIGHBORHOOD_CYPHER can only be proven
    against a live graph — the hermetic FakeAsyncSession never runs the Cypher.
    """
    async with neo4j_integration_driver.session() as session:
        await session.run(_SEED_FANOUT_CYPHER)

    async with neo4j_integration_driver.session() as session:
        graph = await neighborhood(session, "root", limit=2)

    cites = [e for e in graph["edges"] if e["data"]["type"] == "CITES"]
    assert len(cites) == 2
    # Every surfaced edge points out of root to one of the seeded targets.
    for edge in cites:
        assert edge["data"]["source"] == "root"
        assert edge["data"]["target"] in {"a", "b", "c"}
