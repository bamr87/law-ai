"""Cypher MERGE helpers for the statute tree (spec 016 T-004).

Mirrors :mod:`law_ai.core.neo4j.queries` but for `Statute` / `StatuteSection`
/ `Code` / `Jurisdiction` (declared by spec 015). All writes use ``MERGE`` on
the spec-015 unique-constraint properties so re-running ingestion against the
same payload is a no-op (NFR-IDEMPOTENT-1).

NFR-SEC-1: every Cypher uses parameter binding only — no f-string
interpolation of payload data.
"""

from __future__ import annotations

from neo4j import AsyncSession

from law_ai.core.schemas.statute_extraction import StatuteExtraction

MERGE_JURISDICTION_CYPHER = """
MERGE (j:Jurisdiction {code: $code})
ON CREATE SET
  j.name = $name,
  j.level = $level,
  j.source = $source,
  j.source_url = $source_url,
  j.confidence = $confidence,
  j.ingest_timestamp = $ingest_timestamp,
  j.agent_version = $agent_version
ON MATCH SET
  j.name = coalesce($name, j.name),
  j.level = coalesce($level, j.level)
RETURN j
"""

MERGE_CODE_CYPHER = """
MERGE (c:Code {id: $id})
ON CREATE SET
  c.title = $title,
  c.jurisdiction_code = $jurisdiction_code,
  c.source = $source,
  c.source_url = $source_url,
  c.confidence = $confidence,
  c.ingest_timestamp = $ingest_timestamp,
  c.agent_version = $agent_version
ON MATCH SET
  c.title = coalesce($title, c.title)
WITH c
MATCH (j:Jurisdiction {code: $jurisdiction_code})
MERGE (c)-[r:IN_JURISDICTION]->(j)
RETURN c
"""

MERGE_STATUTE_CYPHER = """
MERGE (s:Statute {id: $id})
ON CREATE SET
  s.title = $title,
  s.code_id = $code_id,
  s.citation = $citation,
  s.source = $source,
  s.source_url = $source_url,
  s.confidence = $confidence,
  s.ingest_timestamp = $ingest_timestamp,
  s.agent_version = $agent_version
ON MATCH SET
  s.title = coalesce($title, s.title),
  s.citation = coalesce($citation, s.citation),
  s.confidence = $confidence
WITH s
MATCH (c:Code {id: $code_id})
MERGE (s)-[r:PART_OF]->(c)
WITH s
MATCH (j:Jurisdiction {code: $jurisdiction_code})
MERGE (s)-[r2:IN_JURISDICTION]->(j)
RETURN s
"""

MERGE_STATUTE_SECTION_CYPHER = """
MERGE (sec:StatuteSection {id: $id})
ON CREATE SET
  sec.statute_id = $statute_id,
  sec.citation = $citation,
  sec.heading = $heading,
  sec.text = $text,
  sec.effective_from = $effective_from,
  sec.source = $source,
  sec.source_url = $source_url,
  sec.confidence = $confidence,
  sec.ingest_timestamp = $ingest_timestamp,
  sec.agent_version = $agent_version
ON MATCH SET
  sec.heading = coalesce($heading, sec.heading),
  sec.text = coalesce($text, sec.text),
  sec.effective_from = coalesce($effective_from, sec.effective_from),
  sec.confidence = $confidence
WITH sec
MATCH (s:Statute {id: $statute_id})
MERGE (sec)-[r:PART_OF]->(s)
RETURN sec
"""

# Vector leg (BL-20260810-17); see the note on SET_CASE_EMBEDDING_CYPHER in
# queries.py for why this is a separate statement.
SET_SECTION_EMBEDDING_CYPHER = """
MATCH (sec:StatuteSection {id: $id})
SET sec.embedding = $embedding,
    sec.embedding_model = $model,
    sec.embedding_at = $embedded_at
RETURN sec.id AS id
"""


async def embed_statute_section(
    session: AsyncSession,
    section_id: str,
    *,
    citation: str | None,
    heading: str | None,
    text: str | None,
) -> bool:
    """Compute and store a ``:StatuteSection`` embedding; fail-open."""
    from datetime import UTC, datetime

    from law_ai.core.llm.embeddings import (
        embed_text,
        embedding_model,
        statute_embedding_text,
    )

    body = statute_embedding_text(citation, heading, text)
    if not body:
        return False
    vector = await embed_text(body, component="ingest_statute_section")
    if vector is None:
        return False
    await session.run(
        SET_SECTION_EMBEDDING_CYPHER,
        {
            "id": section_id,
            "embedding": vector,
            "model": embedding_model(),
            "embedded_at": datetime.now(UTC).isoformat(),
        },
    )
    return True


async def commit_statute_extraction(
    session: AsyncSession,
    extraction: StatuteExtraction,
    *,
    threshold: float = 0.7,
) -> int:
    """Persist a :class:`StatuteExtraction` and return the # of edges touched.

    Caller is responsible for the HITL gate on individual sections; this
    function only commits sections that already cleared ``threshold``.
    Statute / Code / Jurisdiction administrative metadata always commits
    when there is at least one high-confidence section to anchor.
    """
    high = extraction.high_confidence_sections(threshold)
    if not high:
        return 0

    iso_ts = extraction.ingest_timestamp.isoformat()

    # Jurisdiction
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

    # Code
    await session.run(
        MERGE_CODE_CYPHER,
        {
            "id": extraction.code_id,
            "title": extraction.code_title,
            "jurisdiction_code": extraction.jurisdiction_code,
            "source": extraction.source,
            "source_url": extraction.source_url,
            "confidence": extraction.confidence,
            "ingest_timestamp": iso_ts,
            "agent_version": extraction.agent_version,
        },
    )

    # Statute
    await session.run(
        MERGE_STATUTE_CYPHER,
        {
            "id": extraction.statute_id,
            "title": extraction.statute_title,
            "code_id": extraction.code_id,
            "jurisdiction_code": extraction.jurisdiction_code,
            "citation": extraction.statute_citation,
            "source": extraction.source,
            "source_url": extraction.source_url,
            "confidence": extraction.confidence,
            "ingest_timestamp": iso_ts,
            "agent_version": extraction.agent_version,
        },
    )

    edges = 2  # Code→Jurisdiction, Statute→Jurisdiction (Statute→Code counted below)
    for sec in high:
        await session.run(
            MERGE_STATUTE_SECTION_CYPHER,
            {
                "id": sec.id,
                "statute_id": extraction.statute_id,
                "citation": sec.citation,
                "heading": sec.heading,
                "text": sec.text,
                "effective_from": (
                    sec.effective_from.isoformat() if sec.effective_from else None
                ),
                "source": extraction.source,
                "source_url": extraction.source_url,
                "confidence": sec.confidence,
                "ingest_timestamp": iso_ts,
                "agent_version": extraction.agent_version,
            },
        )
        await embed_statute_section(
            session,
            sec.id,
            citation=sec.citation,
            heading=sec.heading,
            text=sec.text,
        )
        edges += 1  # Section→Statute :PART_OF

    edges += 1  # Statute→Code :PART_OF
    return edges
