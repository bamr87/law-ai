"""Hybrid GraphRAG retrieval over the Neo4j knowledge graph (BL-20260810-01).

Replaces the stub retriever that returned ``[]`` — which made every
production ``LegalWorkflow`` run take the insufficient-sources refusal path.

Strategy (lexical → graph expansion):

1. **Lexical top-K** via the native fulltext indexes created by
   ``007_fulltext_indexes.cypher`` (``case_text_fulltext``,
   ``statute_section_text_fulltext``). Falls back to a bounded substring
   scan when the index is absent (fresh DB, migrations not yet applied).
2. **Graph expansion** — the step that makes this GraphRAG rather than
   search: pull ``CITES`` neighbours of the top lexical hits, so
   authorities that the seed cases rely on surface even when their text
   does not match the query wording.

Every passage carries constitution §13 attribution (court, decided date,
source, source_url, confidence) so downstream agents can name the issuing
authority, and every Cypher round-trip is logged via
``provenance.log_graph_query`` (constitution §4).

Vector similarity is deliberately NOT part of this pass — embeddings are a
separate spec (no embedding column exists on ``:Case`` yet). The lexical +
graph hybrid is what the current schema can honestly support.
"""

from __future__ import annotations

import logging
import re
import time
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from law_ai.core.provenance import provenance

logger = logging.getLogger("law_ai.agents_runtime.tools.graph_rag")

#: Lucene query-syntax metacharacters. User questions routinely contain
#: ``?``, ``:`` and ``"`` — unescaped they either throw or silently change
#: the query semantics, so every term is escaped before it reaches the index.
_LUCENE_SPECIALS = re.compile(r'([+\-!(){}\[\]^"~*?:\\/]|&&|\|\|)')

CASE_FULLTEXT_INDEX = "case_text_fulltext"
STATUTE_FULLTEXT_INDEX = "statute_section_text_fulltext"

# --- Cypher -----------------------------------------------------------------

CASE_FULLTEXT_CYPHER = """
CALL db.index.fulltext.queryNodes($index, $query, {limit: $limit})
YIELD node, score
WHERE node.archived_at IS NULL
  AND ($court_prefix = '' OR toLower(coalesce(node.court, '')) STARTS WITH $court_prefix)
RETURN node.id AS id,
       node.title AS title,
       node.holding_summary AS holding_summary,
       node.court AS court,
       node.decided_at AS decided_at,
       node.source AS source,
       node.source_url AS source_url,
       node.confidence AS confidence,
       score AS score
ORDER BY score DESC
LIMIT $limit
"""

# Fallback when the fulltext index has not been created yet. Bounded scan;
# `CONTAINS` on a lowercased title is enough to keep a fresh dev DB useful.
CASE_SUBSTRING_CYPHER = """
MATCH (c:Case)
WHERE c.archived_at IS NULL
  AND ($q = '' OR toLower(coalesce(c.title, '')) CONTAINS $q
       OR toLower(coalesce(c.holding_summary, '')) CONTAINS $q)
  AND ($court_prefix = '' OR toLower(coalesce(c.court, '')) STARTS WITH $court_prefix)
RETURN c.id AS id,
       c.title AS title,
       c.holding_summary AS holding_summary,
       c.court AS court,
       c.decided_at AS decided_at,
       c.source AS source,
       c.source_url AS source_url,
       c.confidence AS confidence,
       0.0 AS score
ORDER BY c.title
LIMIT $limit
"""

STATUTE_FULLTEXT_CYPHER = """
CALL db.index.fulltext.queryNodes($index, $query, {limit: $limit})
YIELD node, score
WHERE node.archived_at IS NULL
  AND ($jurisdiction = '' OR toLower(coalesce(node.jurisdiction_code, '')) = $jurisdiction)
RETURN node.citation AS citation,
       node.heading AS heading,
       node.text AS text,
       node.jurisdiction_code AS jurisdiction_code,
       node.source AS source,
       node.source_url AS source_url,
       node.confidence AS confidence,
       score AS score
ORDER BY score DESC
LIMIT $limit
"""

# GraphRAG expansion: authorities the seed cases CITE (one hop out).
EXPAND_CITES_CYPHER = """
MATCH (seed:Case)-[r:CITES]->(neighbor:Case)
WHERE seed.id IN $seed_ids
  AND neighbor.archived_at IS NULL
  AND NOT neighbor.id IN $seed_ids
RETURN DISTINCT neighbor.id AS id,
       neighbor.title AS title,
       neighbor.holding_summary AS holding_summary,
       neighbor.court AS court,
       neighbor.decided_at AS decided_at,
       neighbor.source AS source,
       neighbor.source_url AS source_url,
       neighbor.confidence AS confidence,
       count(r) AS cited_by_seeds
ORDER BY cited_by_seeds DESC
LIMIT $limit
"""


@dataclass
class RetrievalCoverage:
    """What the corpus could and could not answer for one retrieval run.

    Constitution §13 "absence is reported": a thin or jurisdictionally
    lopsided result set must say so rather than reading as "no such law".
    """

    queries: list[str] = field(default_factory=list)
    result_count: int = 0
    lexical_count: int = 0
    expanded_count: int = 0
    jurisdiction_requested: str | None = None
    jurisdictions_present: list[str] = field(default_factory=list)
    jurisdiction_absent: bool = False
    index_available: bool = True

    def note(self) -> str:
        """Human-readable coverage caveat for reviewers."""
        if self.result_count == 0:
            base = (
                "No passages were retrieved from the knowledge graph. Absence "
                "of results in this corpus does NOT mean no such law exists."
            )
            if not self.index_available:
                base += (
                    " (The fulltext index is missing — run the Neo4j "
                    "migrations; results here are substring-matched only.)"
                )
            return base
        parts = [
            f"{self.result_count} passage(s) retrieved "
            f"({self.lexical_count} lexical, {self.expanded_count} via citation "
            "expansion); coverage is limited to the ingested corpus."
        ]
        if self.jurisdictions_present:
            parts.append(
                "Jurisdictions represented: "
                + ", ".join(sorted(self.jurisdictions_present))
                + "."
            )
        if self.jurisdiction_absent and self.jurisdiction_requested:
            parts.append(
                f"NOTE: no results from the requested jurisdiction "
                f"'{self.jurisdiction_requested}' — the passages below are "
                "from other jurisdictions and may be persuasive at best."
            )
        return " ".join(parts)


def escape_lucene(text: str) -> str:
    """Escape Lucene metacharacters so user prose is a safe fulltext query."""
    return _LUCENE_SPECIALS.sub(r"\\\1", text)


def _case_passage(record: Any, *, retrieval_mode: str) -> dict[str, Any]:
    """Shape one ``:Case`` row into a passage with §13 attribution."""
    title = record.get("title") or record.get("id") or "Untitled case"
    summary = record.get("holding_summary") or ""
    return {
        "id": record.get("id"),
        "type": "Case",
        "title": title,
        # `snippet` is what LegalWorkflow._analyze renders into the prompt.
        "snippet": summary or f"(no holding summary stored for {title})",
        "source_url": record.get("source_url"),
        "court": record.get("court"),
        "decided_at": record.get("decided_at"),
        "source": record.get("source"),
        "confidence": record.get("confidence"),
        "score": record.get("score"),
        "retrieval_mode": retrieval_mode,
    }


def _statute_passage(record: Any) -> dict[str, Any]:
    citation = record.get("citation") or "(uncited section)"
    heading = record.get("heading") or ""
    return {
        "id": citation,
        "type": "StatuteSection",
        "title": f"{citation} {heading}".strip(),
        "snippet": (record.get("text") or "")[:1200],
        "source_url": record.get("source_url"),
        "court": None,
        "jurisdiction_code": record.get("jurisdiction_code"),
        "source": record.get("source"),
        "confidence": record.get("confidence"),
        "score": record.get("score"),
        "retrieval_mode": "lexical",
    }


async def _run_logged(session: Any, cypher: str, params: dict[str, Any]) -> list[Any]:
    """Run Cypher, log it via provenance (§4), return records as dicts."""
    started = time.perf_counter()
    result = await session.run(cypher, params)
    records = [dict(record) async for record in result]
    latency_ms = (time.perf_counter() - started) * 1000.0
    provenance.log_graph_query(cypher, params, len(records), round(latency_ms, 2))
    return records


class GraphRAGRetriever:
    """Hybrid lexical + citation-graph retriever for ``LegalWorkflow``.

    Usable directly as the workflow's ``retriever`` callable::

        workflow = LegalWorkflow(retriever=GraphRAGRetriever())

    The last run's coverage is exposed on :attr:`last_coverage` so callers
    can surface it without re-querying.
    """

    def __init__(
        self,
        *,
        session_factory: Any = None,
        limit: int = 8,
        expand_limit: int = 4,
        include_statutes: bool = True,
    ) -> None:
        self._session_factory = session_factory
        self._limit = limit
        self._expand_limit = expand_limit
        self._include_statutes = include_statutes
        self.last_coverage = RetrievalCoverage()

    async def __call__(self, state: Mapping[str, Any]) -> list[dict[str, Any]]:
        """Retrieve passages for the workflow ``state`` (Retriever protocol).

        Takes a ``Mapping`` rather than the concrete ``LegalWorkflowState``
        TypedDict so it satisfies the workflow's ``Retriever`` callable type
        (parameters are contravariant) while staying usable standalone.
        """
        queries = [q for q in (state.get("queries") or []) if str(q).strip()]
        if not queries:
            question = str(state.get("question") or "").strip()
            queries = [question] if question else []
        jurisdiction = state.get("jurisdiction") or None

        coverage = RetrievalCoverage(
            queries=[str(q) for q in queries],
            jurisdiction_requested=str(jurisdiction) if jurisdiction else None,
        )
        if not queries:
            self.last_coverage = coverage
            return []

        try:
            passages = await self._retrieve(queries, jurisdiction, coverage)
        except Exception as exc:  # never break the workflow on a graph fault
            logger.warning("graph_rag retrieval failed: %s", exc)
            coverage.result_count = 0
            self.last_coverage = coverage
            return []

        coverage.result_count = len(passages)
        present = {
            str(p.get("court") or p.get("jurisdiction_code") or "").strip()
            for p in passages
        }
        coverage.jurisdictions_present = sorted(p for p in present if p)
        if jurisdiction:
            wanted = str(jurisdiction).lower()
            coverage.jurisdiction_absent = not any(
                wanted in j.lower() for j in coverage.jurisdictions_present
            )
        self.last_coverage = coverage
        return passages

    async def _retrieve(
        self,
        queries: list[str],
        jurisdiction: str | None,
        coverage: RetrievalCoverage,
    ) -> list[dict[str, Any]]:
        session_cm = self._open_session()
        async with session_cm as session:
            seen: dict[str, dict[str, Any]] = {}
            for query in queries[:3]:
                for passage in await self._lexical_cases(
                    session, query, jurisdiction, coverage
                ):
                    seen.setdefault(str(passage["id"]), passage)
                if self._include_statutes:
                    for passage in await self._lexical_statutes(
                        session, query, jurisdiction
                    ):
                        seen.setdefault(str(passage["id"]), passage)

            coverage.lexical_count = len(seen)

            seed_ids = [str(p["id"]) for p in seen.values() if p.get("type") == "Case"]
            if seed_ids:
                expanded = await _run_logged(
                    session,
                    EXPAND_CITES_CYPHER,
                    {"seed_ids": seed_ids, "limit": self._expand_limit},
                )
                for record in expanded:
                    passage = _case_passage(record, retrieval_mode="cites_expansion")
                    if str(passage["id"]) not in seen:
                        seen[str(passage["id"])] = passage
                        coverage.expanded_count += 1

            return list(seen.values())

    def _open_session(self) -> Any:
        if self._session_factory is not None:
            return self._session_factory()
        from law_ai.core.neo4j.driver import get_neo4j_driver

        return get_neo4j_driver().session()

    async def _lexical_cases(
        self,
        session: Any,
        query: str,
        jurisdiction: str | None,
        coverage: RetrievalCoverage,
    ) -> list[dict[str, Any]]:
        court_prefix = str(jurisdiction).lower() if jurisdiction else ""
        try:
            records = await _run_logged(
                session,
                CASE_FULLTEXT_CYPHER,
                {
                    "index": CASE_FULLTEXT_INDEX,
                    "query": escape_lucene(query),
                    "limit": self._limit,
                    "court_prefix": court_prefix,
                },
            )
        except Exception as exc:
            # Missing index (migrations not applied) or malformed query —
            # degrade to substring matching rather than returning nothing.
            logger.info("fulltext case search unavailable (%s); using substring", exc)
            coverage.index_available = False
            records = await _run_logged(
                session,
                CASE_SUBSTRING_CYPHER,
                {
                    "q": query.lower(),
                    "limit": self._limit,
                    "court_prefix": court_prefix,
                },
            )
        return [_case_passage(r, retrieval_mode="lexical") for r in records]

    async def _lexical_statutes(
        self, session: Any, query: str, jurisdiction: str | None
    ) -> list[dict[str, Any]]:
        try:
            records = await _run_logged(
                session,
                STATUTE_FULLTEXT_CYPHER,
                {
                    "index": STATUTE_FULLTEXT_INDEX,
                    "query": escape_lucene(query),
                    "limit": self._limit,
                    "jurisdiction": str(jurisdiction).lower() if jurisdiction else "",
                },
            )
        except Exception as exc:
            logger.info("fulltext statute search unavailable (%s); skipping", exc)
            return []
        return [_statute_passage(r) for r in records]


def build_default_retriever() -> GraphRAGRetriever:
    """Factory used by ``LegalWorkflow`` when no retriever is injected."""
    return GraphRAGRetriever()


__all__ = [
    "CASE_FULLTEXT_INDEX",
    "STATUTE_FULLTEXT_INDEX",
    "GraphRAGRetriever",
    "RetrievalCoverage",
    "build_default_retriever",
    "escape_lucene",
]
