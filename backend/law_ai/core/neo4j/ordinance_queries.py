"""Cypher MERGE helpers for the ordinance tree (BL-20260509-05).

`Ordinance` and `OrdinanceSection` were declared by spec 015 and indexed by
migrations 005 (temporal) and 007 (fulltext), but no MERGE Cypher existed
anywhere — docs/data-model.md listed them under "declared only". This is the
write path, modelled on :mod:`law_ai.core.neo4j.statute_queries`.

The tree is shallower than the statute one: a municipal code has no `Code`
node between the jurisdiction and the chapter, so it is
``Jurisdiction ← Ordinance ← OrdinanceSection``. The `Jurisdiction` MERGE is
shared with the statute module rather than duplicated, so ``us-co-denver``
and ``us-co`` are the same kind of node.

NFR-SEC-1: every Cypher uses parameter binding only — no f-string
interpolation of payload data.
NFR-IDEMPOTENT-1: MERGE on the spec-015 unique-constraint properties, so
re-running against the same payload is a no-op.
"""

from __future__ import annotations

from neo4j import AsyncSession

from law_ai.core.neo4j.statute_queries import MERGE_JURISDICTION_CYPHER
from law_ai.core.schemas.ordinance_extraction import OrdinanceExtraction

MERGE_ORDINANCE_CYPHER = """
MERGE (o:Ordinance {id: $id})
ON CREATE SET
  o.title = $title,
  o.jurisdiction_code = $jurisdiction_code,
  o.citation = $citation,
  o.source = $source,
  o.source_url = $source_url,
  o.confidence = $confidence,
  o.ingest_timestamp = $ingest_timestamp,
  o.agent_version = $agent_version
ON MATCH SET
  o.title = coalesce($title, o.title),
  o.citation = coalesce($citation, o.citation),
  o.confidence = $confidence
WITH o
MATCH (j:Jurisdiction {code: $jurisdiction_code})
MERGE (o)-[r:IN_JURISDICTION]->(j)
RETURN o
"""

MERGE_ORDINANCE_SECTION_CYPHER = """
MERGE (sec:OrdinanceSection {id: $id})
ON CREATE SET
  sec.ordinance_id = $ordinance_id,
  sec.citation = $citation,
  sec.heading = $heading,
  sec.text = $text,
  sec.effective_from = $effective_from,
  sec.history_note = $history_note,
  sec.source = $source,
  sec.source_url = $source_url,
  sec.confidence = $confidence,
  sec.ingest_timestamp = $ingest_timestamp,
  sec.agent_version = $agent_version
ON MATCH SET
  sec.heading = coalesce($heading, sec.heading),
  sec.text = coalesce($text, sec.text),
  sec.effective_from = coalesce($effective_from, sec.effective_from),
  sec.history_note = coalesce($history_note, sec.history_note),
  sec.confidence = $confidence
WITH sec
MATCH (o:Ordinance {id: $ordinance_id})
MERGE (sec)-[r:PART_OF]->(o)
RETURN sec
"""


async def commit_ordinance_extraction(
    session: AsyncSession,
    extraction: OrdinanceExtraction,
    *,
    threshold: float = 0.7,
) -> int:
    """Persist an :class:`OrdinanceExtraction`; return the # of edges touched.

    The caller owns the HITL gate; this only commits sections that already
    cleared *threshold*. The `Jurisdiction` and `Ordinance` anchors are
    written only when there is at least one such section — a chapter of
    nothing but "Reserved." stubs must not leave an empty chapter node
    behind claiming the corpus covers it.
    """
    high = extraction.high_confidence_sections(threshold)
    if not high:
        return 0

    iso_ts = extraction.ingest_timestamp.isoformat()

    await session.run(
        MERGE_JURISDICTION_CYPHER,
        {
            "code": extraction.jurisdiction_code,
            "name": extraction.jurisdiction_name,
            "level": extraction.jurisdiction_level,
            "source": extraction.source,
            "source_url": extraction.source_url,
            "confidence": extraction.confidence,
            "ingest_timestamp": iso_ts,
            "agent_version": extraction.agent_version,
        },
    )
    await session.run(
        MERGE_ORDINANCE_CYPHER,
        {
            "id": extraction.ordinance_id,
            "title": extraction.ordinance_title,
            "jurisdiction_code": extraction.jurisdiction_code,
            "citation": extraction.ordinance_citation,
            "source": extraction.source,
            "source_url": extraction.source_url,
            "confidence": extraction.confidence,
            "ingest_timestamp": iso_ts,
            "agent_version": extraction.agent_version,
        },
    )

    edges = 1  # Ordinance -> Jurisdiction
    for sec in high:
        await session.run(
            MERGE_ORDINANCE_SECTION_CYPHER,
            {
                "id": sec.id,
                "ordinance_id": extraction.ordinance_id,
                "citation": sec.citation,
                "heading": sec.heading,
                "text": sec.text,
                "effective_from": (
                    sec.effective_from.isoformat() if sec.effective_from else None
                ),
                "history_note": sec.history_note or None,
                "source": extraction.source,
                "source_url": extraction.source_url,
                "confidence": sec.confidence,
                "ingest_timestamp": iso_ts,
                "agent_version": extraction.agent_version,
            },
        )
        edges += 1  # OrdinanceSection -> Ordinance
    return edges
