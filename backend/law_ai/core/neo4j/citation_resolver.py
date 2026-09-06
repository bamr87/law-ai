"""Citation \u2192 Case resolver (spec 002).

Densifies the knowledge graph by mapping ``Citation.normalized`` strings to
existing ``Case`` nodes (via ``Case.aliases``) so that the ingestion pipeline
can create real ``(:Case)-[:CITES]->(:Case)`` edges via ``MERGE_CITES_CYPHER``.

NFR-PERF-1: exactly one Cypher round-trip per ``ExtractionResult``.
NFR-IDEMPOTENT-1: read-only resolver \u2192 idempotent by construction.
"""

from __future__ import annotations

import re
import time
from typing import TYPE_CHECKING

from law_ai.core.provenance import provenance
from law_ai.core.schemas.extraction import ExtractionResult

if TYPE_CHECKING:  # pragma: no cover - typing only
    from neo4j import AsyncSession

# Determinism (BL-20260429-12): when two :Case nodes share an alias, the
# ``ORDER BY n, c.id`` on the WITH feeds collect() in sorted order, so
# ``head(collect(c.id))`` is always the lexicographically smallest Case.id
# rather than whichever node Neo4j happened to scan first. A non-matching n
# still yields c = null, collect() drops it, and head([]) is null — preserving
# the "unresolved -> None" contract and the single round-trip of NFR-PERF-1.
RESOLVE_CITATIONS_CYPHER = """
UNWIND $normalized AS n
OPTIONAL MATCH (c:Case)
WHERE n IN coalesce(c.aliases, [])
WITH n, c ORDER BY n, c.id
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


async def resolve_with_default_driver(names: list[str]) -> dict[str, str | None]:
    """Resolve citation strings against the process-wide Neo4j driver.

    The driver-owning half of :func:`resolve_citations`, lifted out of
    ``LegalWorkflow._default_cite_resolver`` so every caller that needs
    grounding (``LegalWorkflow``, ``LegalAnalyst``) shares one implementation
    (BL-20260615-03).

    Returns an empty mapping — never raises — when there is nothing to
    resolve; a graph fault propagates so callers can decide whether to
    degrade, which both current callers do.
    """
    if not names:
        return {}
    from law_ai.core.neo4j.driver import get_neo4j_driver

    driver = get_neo4j_driver()
    async with driver.session() as session:
        return await resolve_citations(session, names)


# ---------------------------------------------------------------------------
# Citation -> StatuteSection resolver (BL-20260509-07)
# ---------------------------------------------------------------------------
# The CRS corpus landed with spec 016, so opinion text that cites
# "Colo. Rev. Stat. § 18-3-102" or "C.R.S. § 18-3-102" can now be pointed at a
# real :StatuteSection node. Same shape as the Case resolver above: a pure
# normalization step maps a citation string onto a *candidate* node id, and one
# Cypher round-trip decides whether that node actually exists. Nothing is ever
# written on the strength of the string alone.

#: Reporter spellings that mean "Colorado Revised Statutes". Matched as
#: substrings of a lowercased, whitespace-collapsed citation, so both eyecite's
#: canonical "colo. rev. stat." and the abbreviation courts actually type
#: ("c.r.s.") hit. Every entry keeps its periods: a bare "crs" would match
#: inside unrelated words, and a false statutory link is worse than a miss.
#: `queries.list_cases_with_statute_citations` prunes its scan with this same
#: tuple, so the vocabulary lives in exactly one place.
CRS_REPORTERS = (
    "colo. rev. stat. ann.",
    "colo. rev. stat.",
    "colo.rev.stat.",
    "c.r.s.a.",
    "c.r.s.",
)

#: A CRS section number: title-article-section, e.g. ``18-3-102``. Trailing
#: subsection pin-cites (``(1)(a)``) are deliberately dropped — the graph's
#: unit of law is the section, and spec 015 ids stop there.
_CRS_SECTION_RE = re.compile(r"\b(\d{1,2})-(\d{1,3})-(\d{1,4}(?:\.\d+)?)\b")


def statute_section_id_from_normalized(normalized: str) -> str | None:
    """Map a normalized citation string onto a candidate ``StatuteSection.id``.

    Pure, deterministic, and deliberately narrow: it recognises only the
    Colorado Revised Statutes, because CRS is the only statutory corpus in the
    graph (spec 016). Anything else — a case reporter, a federal code cite, a
    CRS-looking string with no recognised reporter — returns ``None`` rather
    than a guessed id.

    The id format matches ``colorado_statutes._section_id`` exactly, since that
    is what wrote the nodes.

    >>> statute_section_id_from_normalized("colo. rev. stat. § 18-3-102")
    'us-co/crs/18-3-102'
    >>> statute_section_id_from_normalized("c.r.s. § 18-3-102(1)(a)")
    'us-co/crs/18-3-102'
    >>> statute_section_id_from_normalized("410 u.s. 113") is None
    True
    """
    if not normalized:
        return None
    text = " ".join(str(normalized).split()).lower()
    if not any(reporter in text for reporter in CRS_REPORTERS):
        return None
    match = _CRS_SECTION_RE.search(text)
    if match is None:
        return None
    return f"us-co/crs/{match.group(1)}-{match.group(2)}-{match.group(3)}"


# Verification only: MATCH (never MERGE) the candidate ids, so an unresolved
# citation stays unresolved instead of conjuring an empty section node.
RESOLVE_STATUTE_CITATIONS_CYPHER = """
UNWIND $section_ids AS sid
OPTIONAL MATCH (sec:StatuteSection {id: sid})
WHERE sec.archived_at IS NULL
RETURN sid AS section_id, sec.id AS resolved
"""


async def resolve_statute_citations(
    session: AsyncSession, section_ids: list[str]
) -> dict[str, str | None]:
    """Return ``{candidate_id: id_or_None}`` for candidate section ids.

    One Cypher round-trip, or zero when there is nothing to resolve — the same
    budget the Case resolver keeps (NFR-PERF-1).
    """
    if not section_ids:
        return {}

    started = time.perf_counter()
    result = await session.run(
        RESOLVE_STATUTE_CITATIONS_CYPHER, {"section_ids": section_ids}
    )
    records = [record async for record in result]
    latency_ms = (time.perf_counter() - started) * 1000.0

    mapping: dict[str, str | None] = {sid: None for sid in section_ids}
    for record in records:
        mapping[record["section_id"]] = record["resolved"]

    provenance.log_graph_query(
        cypher="citation_resolver.resolve_statute_citations",
        params={"section_id_count": len(section_ids)},
        result_count=sum(1 for v in mapping.values() if v is not None),
        latency_ms=latency_ms,
    )
    return mapping


async def densify_statute_extraction(
    session: AsyncSession, result: ExtractionResult
) -> ExtractionResult:
    """Fill ``target_statute_section_id`` on every citation that resolves.

    Costs one extra round-trip only for extractions that actually contain a
    statutory citation; an opinion that cites no statutes issues no query at
    all. Mutates *result* in place and returns it for chaining.
    """
    candidates: dict[str, str] = {}
    for cit in result.citations:
        candidate = statute_section_id_from_normalized(cit.normalized)
        if candidate:
            candidates[cit.normalized] = candidate
    if not candidates:
        return result

    mapping = await resolve_statute_citations(session, sorted(set(candidates.values())))

    resolved = 0
    for cit in result.citations:
        candidate = candidates.get(cit.normalized)
        if candidate and mapping.get(candidate):
            cit.target_statute_section_id = candidate
            resolved += 1

    if resolved:
        provenance.log_graph_query(
            cypher="citation_resolver.densify_statute_extraction",
            params={
                "case_id": result.case_id,
                "resolved": resolved,
                "agent_version": result.agent_version,
            },
            result_count=resolved,
            latency_ms=0.0,
        )
    return result
