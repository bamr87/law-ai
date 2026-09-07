"""Docker-backed integration tests for the two graph backfill commands.

BL-20260906-88. ``densify_backfill`` and ``backfill_embeddings`` were covered
only by unit tests driving a fake session with canned records, so they proved
the Python around the Cypher and never that the Cypher itself does anything to
a real graph. These tests seed live Neo4j and assert the two things an operator
actually cares about:

* the write **lands** — a ``(:Case)-[:CITES]->(:Case)`` edge appears where only
  a ``HAS_CITATION`` pair and a resolvable ``aliases`` entry existed, and an
  ``embedding`` property appears on a vector-less ``:Case``;
* the second ``--commit`` run is a **no-op** — both commands claim idempotence,
  which only holds if their pending-work predicates stop matching the rows they
  just fixed.

Gated behind ``@pytest.mark.integration``, like the rest of ``tests/db/``, so
the default unit run never needs Neo4j.
"""

from __future__ import annotations

from typing import Any

import pytest

from law_ai.core.management.commands import backfill_embeddings as embed_cmd
from law_ai.ingestionapp.management.commands import densify_backfill as densify_cmd

pytestmark = [
    pytest.mark.integration,
    pytest.mark.asyncio(loop_scope="session"),
]


# ---------------------------------------------------------------------------
# Seeds
# ---------------------------------------------------------------------------

#: A citing case whose Citation matches the cited case's ``aliases`` entry, and
#: no ``CITES`` edge between them — exactly the shape an ingest leaves behind
#: when the cited case landed after the citing one.
_SEED_UNLINKED_CYPHER = """
MERGE (src:Case {id: 'case-src'})
  SET src.title = 'Src v. State', src.source = 'test', src.confidence = 1.0,
      src.aliases = ['100 F.3d 1']
MERGE (dst:Case {id: 'case-dst'})
  SET dst.title = 'Dst v. State', dst.source = 'test', dst.confidence = 1.0,
      dst.aliases = ['347 U.S. 483']
MERGE (cit:Citation {normalized: '347 U.S. 483'})
  SET cit.text = '347 U.S. 483'
MERGE (src)-[h:HAS_CITATION]->(cit)
  SET h.confidence = 0.9
"""

#: One embeddable case (title + holding) with no vector at all.
_SEED_VECTORLESS_CYPHER = """
MERGE (c:Case {id: 'case-novec'})
  SET c.title = 'Novec v. State', c.holding_summary = 'A holding worth indexing.',
      c.source = 'test', c.confidence = 1.0
REMOVE c.embedding, c.embedding_model
"""

_VECTOR = [0.25, -0.5, 0.75]


async def _cites_edges(driver: Any) -> list[tuple[str, str, float]]:
    async with driver.session() as session:
        result = await session.run(
            "MATCH (a:Case)-[r:CITES]->(b:Case) "
            "RETURN a.id AS src, b.id AS dst, r.confidence AS confidence "
            "ORDER BY src, dst"
        )
        return [
            (record["src"], record["dst"], record["confidence"])
            async for record in result
        ]


async def _case_row(driver: Any, case_id: str) -> dict[str, Any]:
    async with driver.session() as session:
        result = await session.run(
            "MATCH (c:Case {id: $id}) "
            "RETURN c.embedding AS embedding, c.embedding_model AS model, "
            "c.embedding_at IS NOT NULL AS stamped",
            {"id": case_id},
        )
        return dict(await anext(record async for record in result))


# ---------------------------------------------------------------------------
# densify_backfill
# ---------------------------------------------------------------------------


async def test_densify_backfill_commit_writes_the_missing_cites_edge(
    neo4j_integration_driver, clean_neo4j_db
) -> None:
    """The edge the unit test could only assert against a fake session."""
    async with neo4j_integration_driver.session() as session:
        await session.run(_SEED_UNLINKED_CYPHER)

    stats, _report = await densify_cmd.run_backfill(
        commit=True, batch_size=10, limit=None
    )

    assert stats.scanned == 1
    assert stats.resolved == 1
    assert stats.edges_created == 1
    assert await _cites_edges(neo4j_integration_driver) == [
        ("case-src", "case-dst", pytest.approx(0.9))
    ]


async def test_densify_backfill_dry_run_writes_nothing(
    neo4j_integration_driver, clean_neo4j_db
) -> None:
    """The default mode resolves the pair and still leaves the graph alone."""
    async with neo4j_integration_driver.session() as session:
        await session.run(_SEED_UNLINKED_CYPHER)

    stats, _report = await densify_cmd.run_backfill(
        commit=False, batch_size=10, limit=None
    )

    assert stats.resolved == 1
    assert stats.edges_created == 0
    assert await _cites_edges(neo4j_integration_driver) == []


async def test_densify_backfill_second_commit_is_a_no_op(
    neo4j_integration_driver, clean_neo4j_db
) -> None:
    """Idempotence: the fixed pair drops out of the pending predicate."""
    async with neo4j_integration_driver.session() as session:
        await session.run(_SEED_UNLINKED_CYPHER)

    await densify_cmd.run_backfill(commit=True, batch_size=10, limit=None)
    again, _report = await densify_cmd.run_backfill(
        commit=True, batch_size=10, limit=None
    )

    assert again.as_dict() == {
        "scanned": 0,
        "resolved": 0,
        "edges_created": 0,
        "self_citations": 0,
    }
    # And no duplicate edge was merged on top of the first one.
    assert len(await _cites_edges(neo4j_integration_driver)) == 1


# ---------------------------------------------------------------------------
# backfill_embeddings
# ---------------------------------------------------------------------------


@pytest.fixture
def stub_embedder(monkeypatch: pytest.MonkeyPatch) -> list[list[str]]:
    """Deterministic vectors in place of the local embedder.

    The claim under test is the Cypher, not Ollama: these tests must assert
    that the vector reaches the node, and must not depend on a pulled model.
    """
    calls: list[list[str]] = []

    async def fake_embed_texts(
        texts: list[str], *, component: str = ""
    ) -> list[list[float] | None]:
        calls.append(list(texts))
        return [_VECTOR if text else None for text in texts]

    monkeypatch.setattr(embed_cmd, "embed_texts", fake_embed_texts)
    return calls


async def test_backfill_embeddings_commit_writes_the_vector(
    neo4j_integration_driver, clean_neo4j_db, stub_embedder
) -> None:
    """A vector-less :Case comes back carrying the embedding and its model."""
    async with neo4j_integration_driver.session() as session:
        await session.run(_SEED_VECTORLESS_CYPHER)

    stats = await embed_cmd.run_backfill(
        labels=("Case",), batch_size=10, limit=None, commit=True
    )

    assert stats["Case"]["pending"] == 1
    assert stats["Case"]["embedded"] == 1
    row = await _case_row(neo4j_integration_driver, "case-novec")
    assert row["embedding"] == pytest.approx(_VECTOR)
    assert row["model"] == embed_cmd.embedding_model()
    assert row["stamped"] is True


async def test_backfill_embeddings_dry_run_writes_nothing(
    neo4j_integration_driver, clean_neo4j_db, stub_embedder
) -> None:
    async with neo4j_integration_driver.session() as session:
        await session.run(_SEED_VECTORLESS_CYPHER)

    stats = await embed_cmd.run_backfill(
        labels=("Case",), batch_size=10, limit=None, commit=False
    )

    assert stats["Case"]["pending"] == 1
    assert stats["Case"]["embedded"] == 0
    assert stub_embedder == []
    row = await _case_row(neo4j_integration_driver, "case-novec")
    assert row["embedding"] is None


async def test_backfill_embeddings_second_commit_is_a_no_op(
    neo4j_integration_driver, clean_neo4j_db, stub_embedder
) -> None:
    """A node already carrying this model's vector is no longer pending."""
    async with neo4j_integration_driver.session() as session:
        await session.run(_SEED_VECTORLESS_CYPHER)

    await embed_cmd.run_backfill(
        labels=("Case",), batch_size=10, limit=None, commit=True
    )
    again = await embed_cmd.run_backfill(
        labels=("Case",), batch_size=10, limit=None, commit=True
    )

    assert again["Case"] == {"pending": 0, "embedded": 0, "skipped_empty": 0}
    assert len(stub_embedder) == 1, "the second pass re-embedded a settled node"
