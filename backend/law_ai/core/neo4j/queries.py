"""Reusable Cypher snippets for ingestion + read paths.

All write queries use ``MERGE`` on stable IDs to satisfy NFR-IDEMPOTENT-1
in specs/001. Provenance fields (constitution §4) are set on every
created or matched node.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from neo4j import AsyncSession

from law_ai.core.schemas.extraction import ExtractionResult

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
  c.aliases = coalesce($aliases, []),
  c.holding_summary = $holding_summary,
  c.holding_summary_kind = $holding_summary_kind,
  c.disposition = $disposition,
  c.prevailing_party_type = $prevailing_party_type
ON MATCH SET
  c.title = coalesce($title, c.title),
  c.court = coalesce($court, c.court),
  c.decided_at = coalesce($decided_at, c.decided_at),
  c.confidence = $confidence,
  c.aliases = coalesce($aliases, c.aliases),
  c.holding_summary = coalesce($holding_summary, c.holding_summary),
  c.holding_summary_kind = coalesce(
    $holding_summary_kind, c.holding_summary_kind
  ),
  c.disposition = coalesce($disposition, c.disposition),
  c.prevailing_party_type = coalesce(
    $prevailing_party_type, c.prevailing_party_type
  )
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

# BL-20260509-07: the first writer of `CITES_STATUTE`. Declared in
# docs/data-model.md since spec 015 but never emitted, so the edge existed only
# on paper. MATCH-then-MERGE (never MERGE on the section) so an opinion can
# only be linked to a section that is really in the corpus; both provenance
# properties the constitution §4 requires are set on create.
MERGE_CITES_STATUTE_CYPHER = """
MATCH (c:Case {id: $case_id})
MATCH (sec:StatuteSection {id: $section_id})
MERGE (c)-[r:CITES_STATUTE]->(sec)
ON CREATE SET
  r.confidence = $confidence,
  r.source = $source,
  r.ingest_timestamp = $ingest_timestamp
ON MATCH SET
  r.confidence = $confidence
RETURN r
"""

LAST_INGEST_AT_CYPHER = """
MATCH (c:Case)
RETURN max(c.ingest_timestamp) AS last_ingest_at
"""

# Vector leg (BL-20260810-17). Written as a separate statement rather than
# folded into MERGE_CASE_CYPHER: the embedding is produced by a network call
# that is allowed to fail, and ingest must commit the node either way.
SET_CASE_EMBEDDING_CYPHER = """
MATCH (c:Case {id: $id})
SET c.embedding = $embedding,
    c.embedding_model = $model,
    c.embedding_at = $embedded_at
RETURN c.id AS id
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
        # BL-20260810-19: persist the snippet the retriever renders, plus the
        # label that says whether it is a verbatim excerpt or model prose.
        "holding_summary": result.holding_summary,
        "holding_summary_kind": result.holding_summary_kind,
        # BL-20260803-01: both stay None when the source record is silent, and
        # the MERGE coalesces on re-ingest so a later silent fetch never nulls
        # a disposition an earlier record did state.
        "disposition": result.disposition,
        "prevailing_party_type": result.prevailing_party_type,
    }
    await session.run(MERGE_CASE_CYPHER, case_params)
    await embed_case(
        session,
        result.case_id,
        title=result.title,
        holding_summary=result.holding_summary,
    )

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
        # BL-20260509-07. The resolver only fills this when the section really
        # is in the graph, so an unresolved statutory cite leaves a
        # :Citation node and no edge, exactly as an unresolved case cite does.
        if cit.target_statute_section_id:
            await session.run(
                MERGE_CITES_STATUTE_CYPHER,
                {
                    "case_id": result.case_id,
                    "section_id": cit.target_statute_section_id,
                    "confidence": result.confidence,
                    "source": result.source,
                    "ingest_timestamp": result.ingest_timestamp.isoformat(),
                },
            )

    return edges_created


async def embed_case(
    session: AsyncSession,
    case_id: str,
    *,
    title: str | None,
    holding_summary: str | None,
) -> bool:
    """Compute and store the ``:Case`` embedding; return whether one was written.

    Fail-open by construction (BL-20260810-17): a missing or unreachable local
    embedder returns ``None`` and ingest carries on without a vector, which the
    retriever handles by falling back to its lexical + expansion legs.
    """
    from law_ai.core.llm.embeddings import (
        case_embedding_text,
        embed_text,
        embedding_model,
    )

    text = case_embedding_text(title, holding_summary)
    if not text:
        return False
    vector = await embed_text(text, component="ingest_case")
    if vector is None:
        return False
    await session.run(
        SET_CASE_EMBEDDING_CYPHER,
        {
            "id": case_id,
            "embedding": vector,
            "model": embedding_model(),
            "embedded_at": datetime.now(UTC).isoformat(),
        },
    )
    return True


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


# ---------------------------------------------------------------------------
# Densify backfill helpers (BL-20260429-11)
# ---------------------------------------------------------------------------

# Cases carrying a :HAS_CITATION edge whose citation has no matching
# (:Case)-[:CITES]->(:Case) edge yet — i.e. work left over from ingests that
# ran before the target case (or its ``aliases``) existed. Same predicate
# shape as LIST_ORPHAN_CITATIONS_CYPHER, but grouped per source case and
# paginated so a large corpus is walked in batches instead of one
# transaction. Archived cases are skipped (constitution §4: soft delete).
#
# Pagination is a keyset cursor on ``Case.id`` rather than SKIP: a committing
# backfill removes rows from this result set as it goes, and a SKIP offset
# would step straight over the rows that shifted down.
LIST_CASES_WITH_UNLINKED_CITATIONS_CYPHER = """
MATCH (c:Case)-[h:HAS_CITATION]->(x:Citation)
WHERE c.archived_at IS NULL AND c.id > $after
OPTIONAL MATCH (c)-[:CITES]->(t:Case)
WHERE x.normalized IN coalesce(t.aliases, [])
WITH c, x, h, count(t) AS linked
WHERE linked = 0
WITH c.id AS case_id,
     collect(DISTINCT {
       normalized: x.normalized,
       confidence: coalesce(h.confidence, 0.0)
     }) AS pending
ORDER BY case_id
LIMIT $limit
RETURN case_id, pending
"""


async def list_cases_with_unlinked_citations(
    session: AsyncSession, *, after: str = "", limit: int = 100
) -> list[dict[str, Any]]:
    """Return one batch of ``{"case_id": str, "pending": [{normalized, confidence}]}``.

    Read-only. Rows come back ordered by ``case_id``; pass the last
    ``case_id`` of a batch back as ``after`` to get the next one. That keyset
    cursor is what makes ``densify_backfill`` safe to run in commit mode,
    where processed rows drop out of the predicate as the walk proceeds.
    """
    result = await session.run(
        LIST_CASES_WITH_UNLINKED_CITATIONS_CYPHER, {"after": after, "limit": limit}
    )
    batch: list[dict[str, Any]] = []
    async for record in result:
        pending = [
            {
                "normalized": str(entry["normalized"]),
                "confidence": float(entry.get("confidence") or 0.0),
            }
            for entry in (record["pending"] or [])
            if entry and entry.get("normalized")
        ]
        batch.append({"case_id": str(record["case_id"]), "pending": pending})
    return batch


# ---------------------------------------------------------------------------
# Statute-citation backfill helpers (BL-20260509-07)
# ---------------------------------------------------------------------------

# Cases whose stored citation strings look statutory (a CRS reporter spelling),
# so `resolve_statute_citations` can point them at :StatuteSection nodes.
#
# Keyed on the already-extracted `Citation.normalized` string rather than on
# opinion text, deliberately: `:Case` nodes do not persist the opinion body, so
# a text re-scan would mean re-fetching every opinion from upstream. The
# citation strings the original ingest wrote are enough, which makes the
# backfill offline, cheap and re-runnable. The candidate -> id mapping and the
# existence check both happen in Python
# (`citation_resolver.statute_section_id_from_normalized` and
# `resolve_statute_citations`), because the id format is not expressible in
# Cypher; this query only prunes the scan to plausible rows.
#
# Keyset cursor on Case.id, like LIST_CASES_WITH_UNLINKED_CITATIONS_CYPHER.
LIST_CASES_WITH_STATUTE_CITATIONS_CYPHER = """
MATCH (c:Case)-[h:HAS_CITATION]->(x:Citation)
WHERE c.archived_at IS NULL AND c.id > $after
  AND any(
    reporter IN $reporters
    WHERE toLower(coalesce(x.normalized, '')) CONTAINS reporter
  )
WITH c.id AS case_id,
     collect(DISTINCT {
       normalized: x.normalized,
       confidence: coalesce(h.confidence, coalesce(c.confidence, 0.0))
     }) AS pending
ORDER BY case_id
LIMIT $limit
RETURN case_id, pending
"""


async def list_cases_with_statute_citations(
    session: AsyncSession,
    *,
    reporters: list[str],
    after: str = "",
    limit: int = 100,
) -> list[dict[str, Any]]:
    """One batch of ``{"case_id", "pending": [{normalized, confidence}]}``.

    *reporters* are lowercased reporter spellings to prune on — the caller
    passes ``citation_resolver.STATUTE_REPORTERS`` — the union of every corpus
    in ``STATUTE_CORPORA`` (BL-20260906-02) — so the vocabulary lives in one
    place and follows the mapper when a second corpus lands. Read-only; same keyset-cursor contract as
    :func:`list_cases_with_unlinked_citations`.
    """
    result = await session.run(
        LIST_CASES_WITH_STATUTE_CITATIONS_CYPHER,
        {"after": after, "limit": limit, "reporters": reporters},
    )
    batch: list[dict[str, Any]] = []
    async for record in result:
        pending = [
            {
                "normalized": str(entry["normalized"]),
                "confidence": float(entry.get("confidence") or 0.0),
            }
            for entry in (record["pending"] or [])
            if entry and entry.get("normalized")
        ]
        batch.append({"case_id": str(record["case_id"]), "pending": pending})
    return batch


# ---------------------------------------------------------------------------
# Holding-summary backfill (BL-20260905-99)
# ---------------------------------------------------------------------------

#: Cases ingested before ``derive_holding_summary`` landed carry no
#: ``holding_summary``, so every GraphRAG passage built from them renders
#: "(no holding summary stored)". Keyset cursor on ``Case.id``, same contract
#: as :data:`LIST_CASES_WITH_STATUTE_CITATIONS_CYPHER`.
LIST_CASES_MISSING_HOLDING_SUMMARY_CYPHER = """
MATCH (c:Case)
WHERE c.archived_at IS NULL AND c.id > $after
  AND coalesce(c.holding_summary, '') = ''
RETURN c.id AS case_id,
       c.title AS title,
       c.source AS source,
       c.source_url AS source_url
ORDER BY case_id
LIMIT $limit
"""

#: Write-once: the ``WHERE`` clause means a re-run can never overwrite a
#: summary a later ingest (or a model pass) already wrote, so the backfill is
#: idempotent and cannot clobber better data.
SET_HOLDING_SUMMARY_CYPHER = """
MATCH (c:Case {id: $case_id})
WHERE c.archived_at IS NULL AND coalesce(c.holding_summary, '') = ''
SET c.holding_summary = $holding_summary,
    c.holding_summary_kind = $holding_summary_kind
RETURN c.id AS id
"""


async def list_cases_missing_holding_summary(
    session: AsyncSession, *, after: str = "", limit: int = 100
) -> list[dict[str, Any]]:
    """One batch of cases with no ``holding_summary`` (BL-20260905-99)."""
    result = await session.run(
        LIST_CASES_MISSING_HOLDING_SUMMARY_CYPHER, {"after": after, "limit": limit}
    )
    batch: list[dict[str, Any]] = []
    async for record in result:
        batch.append(
            {
                "case_id": str(record["case_id"]),
                "title": record["title"],
                "source": record["source"],
                "source_url": record["source_url"],
            }
        )
    return batch


async def set_holding_summary(
    session: AsyncSession, case_id: str, *, summary: str, kind: str = "excerpt"
) -> bool:
    """Fill an empty ``holding_summary``; True when a node was updated."""
    result = await session.run(
        SET_HOLDING_SUMMARY_CYPHER,
        {
            "case_id": case_id,
            "holding_summary": summary,
            "holding_summary_kind": kind,
        },
    )
    return bool([record async for record in result])


# ---------------------------------------------------------------------------
# Statute-citation recall (BL-20260906-88)
# ---------------------------------------------------------------------------

#: Cases that hold **no** statute-looking citation string at all. Opinions
#: ingested before ``scout._CRS_CITATION_RES`` landed were scanned by eyecite
#: alone, which misses the two C.R.S. forms Colorado courts write, so their
#: statutory cites were never stored and no offline pass can recover them.
#: ``source`` is bound so the caller only walks corpora it can actually
#: re-fetch by id.
LIST_CASES_WITHOUT_STATUTE_CITATIONS_CYPHER = """
MATCH (c:Case)
WHERE c.archived_at IS NULL AND c.id > $after AND c.source IN $sources
  AND NOT EXISTS {
    MATCH (c)-[:HAS_CITATION]->(x:Citation)
    WHERE any(
      reporter IN $reporters
      WHERE toLower(coalesce(x.normalized, '')) CONTAINS reporter
    )
  }
RETURN c.id AS case_id, c.source AS source
ORDER BY case_id
LIMIT $limit
"""


async def list_cases_without_statute_citations(
    session: AsyncSession,
    *,
    reporters: list[str],
    sources: list[str],
    after: str = "",
    limit: int = 100,
) -> list[dict[str, Any]]:
    """One batch of ``{"case_id", "source"}`` for cases with no statutory cite."""
    result = await session.run(
        LIST_CASES_WITHOUT_STATUTE_CITATIONS_CYPHER,
        {
            "after": after,
            "limit": limit,
            "reporters": reporters,
            "sources": sources,
        },
    )
    return [
        {"case_id": str(record["case_id"]), "source": record["source"]}
        async for record in result
    ]


# ---------------------------------------------------------------------------
# Authority verification (BL-20260906-16)
# ---------------------------------------------------------------------------

#: Does this graph node exist, and is it the kind of authority a matter may
#: cite? MATCH-only, archived nodes excluded (constitution §4), so a recorded
#: authority can never point at a node that is not in the corpus.
AUTHORITY_NODE_EXISTS_CYPHER = """
MATCH (n {id: $node_id})
WHERE n.archived_at IS NULL AND (n:Case OR n:StatuteSection OR n:OrdinanceSection)
RETURN labels(n) AS labels
LIMIT 1
"""


async def authority_node_labels(session: AsyncSession, node_id: str) -> list[str]:
    """Labels of the authority node with this id, or ``[]`` when there is none."""
    result = await session.run(AUTHORITY_NODE_EXISTS_CYPHER, {"node_id": node_id})
    record = await result.single()
    if record is None:
        return []
    return [str(label) for label in (record["labels"] or [])]
