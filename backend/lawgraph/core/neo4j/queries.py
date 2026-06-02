"""Reusable Cypher snippets for ingestion + read paths.

All write queries use ``MERGE`` on stable IDs to satisfy NFR-IDEMPOTENT-1
in specs/001. Provenance fields (constitution §4) are set on every
created or matched node.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from neo4j import AsyncSession

from lawgraph.core.schemas.extraction import ExtractionResult

MERGE_CASE_CYPHER = """
MERGE (c:Case {id: $id})
ON CREATE SET
  c.title = $title,
  c.court = $court,
  c.decided_at = $decided_at,
  c.source = $source,
  c.source_url = $source_url,
  c.ingest_timestamp = $ingest_timestamp,
  c.agent_version = $agent_version,
  c.confidence = $confidence,
  c.aliases = coalesce($aliases, [])
ON MATCH SET
  c.title = coalesce($title, c.title),
  c.court = coalesce($court, c.court),
  c.decided_at = coalesce($decided_at, c.decided_at),
  c.confidence = $confidence,
  c.aliases = coalesce($aliases, c.aliases)
RETURN c
"""

MERGE_CITATION_CYPHER = """
MERGE (x:Citation {normalized: $normalized})
ON CREATE SET x.text = $text
WITH x
MATCH (c:Case {id: $case_id})
MERGE (c)-[r:HAS_CITATION]->(x)
ON CREATE SET
  r.ingest_timestamp = $ingest_timestamp,
  r.confidence = $confidence
RETURN r
"""

MERGE_CITES_CYPHER = """
MATCH (src:Case {id: $src_id})
MATCH (dst:Case {id: $dst_id})
MERGE (src)-[r:CITES]->(dst)
ON CREATE SET
  r.confidence = $confidence,
  r.ingest_timestamp = $ingest_timestamp
RETURN r
"""

LAST_INGEST_AT_CYPHER = """
MATCH (c:Case)
RETURN max(c.ingest_timestamp) AS last_ingest_at
"""


async def commit_extraction(session: AsyncSession, result: ExtractionResult) -> int:
    """Persist a high-confidence ``ExtractionResult`` and return # of CITES edges created.

    Caller is responsible for the HITL gate; this function does no
    confidence check itself so it can also be used from backfill scripts.
    """
    case_params: dict[str, Any] = {
        "id": result.case_id,
        "title": result.title,
        "court": result.court,
        "decided_at": result.decided_at.isoformat() if result.decided_at else None,
        "source": result.source,
        "source_url": result.source_url,
        "ingest_timestamp": result.ingest_timestamp.isoformat(),
        "agent_version": result.agent_version,
        "confidence": result.confidence,
        "aliases": result.aliases or None,
    }
    await session.run(MERGE_CASE_CYPHER, case_params)

    edges_created = 0
    for cit in result.citations:
        await session.run(
            MERGE_CITATION_CYPHER,
            {
                "normalized": cit.normalized,
                "text": cit.text,
                "case_id": result.case_id,
                "ingest_timestamp": result.ingest_timestamp.isoformat(),
                "confidence": result.confidence,
            },
        )
        if cit.target_case_id:
            cites_result = await session.run(
                MERGE_CITES_CYPHER,
                {
                    "src_id": result.case_id,
                    "dst_id": cit.target_case_id,
                    "confidence": result.confidence,
                    "ingest_timestamp": result.ingest_timestamp.isoformat(),
                },
            )
            # Count only edges whose dst exists; missing dst -> empty result.
            records = [r async for r in cites_result]
            if records:
                edges_created += 1

    return edges_created


async def get_last_ingest_at(session: AsyncSession) -> datetime | None:
    """Return the most recent ``Case.ingest_timestamp`` or None."""
    result = await session.run(LAST_INGEST_AT_CYPHER)
    record = await result.single()
    if not record or record["last_ingest_at"] is None:
        return None
    raw = record["last_ingest_at"]
    if isinstance(raw, datetime):
        return raw
    return datetime.fromisoformat(str(raw))


# ---------------------------------------------------------------------------
# TopicFrontier gap-detection helpers (spec 018 T-007)
# ---------------------------------------------------------------------------

LIST_ORPHAN_CITATIONS_CYPHER = """
MATCH (x:Citation)
WHERE NOT (x)<-[:RESOLVES_TO]-(:Case)
  AND NOT (x)<-[:HAS_CITATION]-(:Case)-[:CITES]->(:Case)
RETURN x.normalized AS citation
ORDER BY x.normalized
LIMIT $limit
"""

LIST_UNDER_CITED_JURISDICTIONS_CYPHER = """
MATCH (c:Case)
WITH c.court AS court, count(*) AS cnt
WHERE cnt < 5 AND court IS NOT NULL
WITH split(court, '-')[0] AS jurisdiction, sum(cnt) AS total
RETURN jurisdiction
ORDER BY total ASC
LIMIT $limit
"""


async def list_orphan_citations(session: AsyncSession, *, limit: int = 20) -> list[str]:
    """Return normalized citation strings that have no resolved :Case target.

    These are :Citation nodes that exist in the graph but have never been
    linked to a :Case via a CITES or RESOLVES_TO relationship.  Used by
    TopicFrontier to prioritise what to fetch next.

    Returns an empty list when Neo4j is not reachable; callers should
    handle the empty-list case gracefully (TopicFrontier will still run
    the prioritize node with an empty input and return an empty array).
    """
    result = await session.run(LIST_ORPHAN_CITATIONS_CYPHER, {"limit": limit})
    records = [r async for r in result]
    return [str(r["citation"]) for r in records if r["citation"]]


async def list_under_cited_jurisdictions(
    session: AsyncSession, *, limit: int = 10
) -> list[str]:
    """Return jurisdiction tags that have fewer than 5 :Case nodes.

    Groups by the first segment of ``Case.court`` (e.g. ``"us"`` from
    ``"us-9th-circuit"``).  Returns at most *limit* tags sorted by
    ascending case count so the TopicFrontier prioritizes truly empty
    jurisdictions first.
    """
    result = await session.run(LIST_UNDER_CITED_JURISDICTIONS_CYPHER, {"limit": limit})
    records = [r async for r in result]
    return [str(r["jurisdiction"]) for r in records if r["jurisdiction"]]
