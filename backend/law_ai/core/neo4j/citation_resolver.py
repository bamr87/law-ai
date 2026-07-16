"""Citation \u2192 Case resolver (spec 002).

Densifies the knowledge graph by mapping ``Citation.normalized`` strings to
existing ``Case`` nodes (via ``Case.aliases``) so that the ingestion pipeline
can create real ``(:Case)-[:CITES]->(:Case)`` edges via ``MERGE_CITES_CYPHER``.

NFR-PERF-1: exactly one Cypher round-trip per ``ExtractionResult``.
NFR-IDEMPOTENT-1: read-only resolver \u2192 idempotent by construction.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

from law_ai.core.provenance import provenance
from law_ai.core.schemas.extraction import ExtractionResult

if TYPE_CHECKING:  # pragma: no cover - typing only
    from neo4j import AsyncSession

RESOLVE_CITATIONS_CYPHER = """
UNWIND $normalized AS n
OPTIONAL MATCH (c:Case)
WHERE n IN coalesce(c.aliases, [])
RETURN n AS normalized, head(collect(c.id)) AS case_id
"""


async def resolve_citations(
    session: AsyncSession, normalized: list[str]
) -> dict[str, str | None]:
    """Return ``{normalized: case_id_or_None}`` for the given citation strings.

    Empty input returns an empty dict and issues no Cypher (NFR-PERF-1 still
    holds: one round-trip *at most*, zero when nothing to resolve).
    """
    if not normalized:
        return {}

    started = time.perf_counter()
    result = await session.run(RESOLVE_CITATIONS_CYPHER, {"normalized": normalized})
    records = [record async for record in result]
    latency_ms = (time.perf_counter() - started) * 1000.0

    mapping: dict[str, str | None] = {n: None for n in normalized}
    for record in records:
        mapping[record["normalized"]] = record["case_id"]

    provenance.log_graph_query(
        cypher="citation_resolver.resolve_citations",
        params={"normalized_count": len(normalized)},
        result_count=sum(1 for v in mapping.values() if v is not None),
        latency_ms=latency_ms,
    )
    return mapping


async def densify_extraction(
    session: AsyncSession, result: ExtractionResult
) -> ExtractionResult:
    """Populate ``target_case_id`` on every citation that resolves to a known Case.

    Mutates ``result`` in place and returns it for chaining.
    """
    if not result.citations:
        return result

    normalized = [c.normalized for c in result.citations]
    mapping = await resolve_citations(session, normalized)

    resolved = 0
    for cit in result.citations:
        target = mapping.get(cit.normalized)
        if target is not None:
            cit.target_case_id = target
            resolved += 1

    if resolved:
        provenance.log_graph_query(
            cypher="citation_resolver.densify_extraction",
            params={
                "case_id": result.case_id,
                "resolved": resolved,
                "agent_version": result.agent_version,
            },
            result_count=resolved,
            latency_ms=0.0,
        )
    return result
