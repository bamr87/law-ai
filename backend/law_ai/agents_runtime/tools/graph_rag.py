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

Vector similarity joined the hybrid in BL-20260810-17: ``:Case`` and
``:StatuteSection`` now carry a local ``nomic-embed-text`` ``embedding``
(written at ingest by ``law_ai.core.llm.embeddings`` and backfilled by
``manage.py backfill_embeddings``), indexed by
``008_vector_indexes.cypher``. The lexical and vector rankings are combined by
reciprocal-rank fusion before citation expansion — separately per label, so a
statute cannot be crowded out by a case — and a passage that is strong on
either leg surfaces. When the index or the embedder is absent the vector
leg is simply skipped and ``coverage.vector_available`` says so — the
retriever degrades to exactly its pre-BL-20260810-17 behaviour.
"""

from __future__ import annotations

import logging
import re
import time
from collections.abc import Iterable, Mapping
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
#: BL-20260906-07: local law. `007_fulltext_indexes.cypher` has indexed
#: `:OrdinanceSection` since spec 015, but nothing queried it, so the sections
#: `ordinance_queries.commit_ordinance_extraction` writes were invisible to
#: every answer.
ORDINANCE_FULLTEXT_INDEX = "ordinance_section_text_fulltext"

#: Reciprocal-rank-fusion damping constant. 60 is the value from the original
#: RRF paper and the one every mainstream hybrid-search stack uses; it makes
#: the top few ranks matter without letting rank 1 dominate outright.
RRF_K = 60

# --- Cypher -----------------------------------------------------------------

CASE_FULLTEXT_CYPHER = """
CALL db.index.fulltext.queryNodes($index, $query, {limit: $limit})
YIELD node, score
WHERE node.archived_at IS NULL
  AND ($court_prefix = '' OR toLower(coalesce(node.court, '')) STARTS WITH $court_prefix)
RETURN node.id AS id,
       node.title AS title,
       node.holding_summary AS holding_summary,
       node.holding_summary_kind AS holding_summary_kind,
       node.court AS court,
       node.decided_at AS decided_at,
       node.disposition AS disposition,
       node.prevailing_party_type AS prevailing_party_type,
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
       c.holding_summary_kind AS holding_summary_kind,
       c.court AS court,
       c.decided_at AS decided_at,
       c.disposition AS disposition,
       c.prevailing_party_type AS prevailing_party_type,
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
# Vector leg (BL-20260810-17). `db.index.vector.queryNodes` needs the query
# embedded by the SAME model that produced the stored vectors, which is why
# `core.llm.embeddings` is pinned to Ollama regardless of LLM_PROVIDER_CHAIN.
CASE_VECTOR_CYPHER = """
CALL db.index.vector.queryNodes($index, $limit, $embedding)
YIELD node, score
WHERE node.archived_at IS NULL
  AND ($court_prefix = '' OR toLower(coalesce(node.court, '')) STARTS WITH $court_prefix)
RETURN node.id AS id,
       node.title AS title,
       node.holding_summary AS holding_summary,
       node.holding_summary_kind AS holding_summary_kind,
       node.court AS court,
       node.decided_at AS decided_at,
       node.disposition AS disposition,
       node.prevailing_party_type AS prevailing_party_type,
       node.source AS source,
       node.source_url AS source_url,
       node.confidence AS confidence,
       score
ORDER BY score DESC
"""

# The statute half of the vector leg. Same index shape, different label: the
# :StatuteSection embeddings written at ingest would otherwise be write-only.
STATUTE_VECTOR_CYPHER = """
CALL db.index.vector.queryNodes($index, $limit, $embedding)
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
       score
ORDER BY score DESC
"""

# The ordinance leg (BL-20260906-07). Unlike `:StatuteSection`, an
# `:OrdinanceSection` carries no `jurisdiction_code` of its own — jurisdiction
# hangs off the parent `:Ordinance` via `IN_JURISDICTION` — so the filter has
# to walk there. OPTIONAL, because a section whose ordinance anchor is missing
# should still be findable when no jurisdiction was asked for.
ORDINANCE_FULLTEXT_CYPHER = """
CALL db.index.fulltext.queryNodes($index, $query, {limit: $limit})
YIELD node, score
WHERE node.archived_at IS NULL
OPTIONAL MATCH (node)-[:PART_OF]->(:Ordinance)-[:IN_JURISDICTION]->(j:Jurisdiction)
WITH node, score, toLower(coalesce(j.code, '')) AS jurisdiction_code
WHERE $jurisdiction = '' OR jurisdiction_code = $jurisdiction
RETURN node.id AS id,
       node.citation AS citation,
       node.heading AS heading,
       node.text AS text,
       jurisdiction_code AS jurisdiction_code,
       node.source AS source,
       node.source_url AS source_url,
       node.confidence AS confidence,
       score AS score
ORDER BY score DESC
LIMIT $limit
"""

EXPAND_CITES_CYPHER = """
MATCH (seed:Case)-[r:CITES]->(neighbor:Case)
WHERE seed.id IN $seed_ids
  AND neighbor.archived_at IS NULL
  AND NOT neighbor.id IN $seed_ids
RETURN DISTINCT neighbor.id AS id,
       neighbor.title AS title,
       neighbor.holding_summary AS holding_summary,
       neighbor.holding_summary_kind AS holding_summary_kind,
       neighbor.court AS court,
       neighbor.decided_at AS decided_at,
       neighbor.disposition AS disposition,
       neighbor.prevailing_party_type AS prevailing_party_type,
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
    #: How many of the fused passages (:Case and :StatuteSection alike) came
    #: from the vector leg.
    vector_count: int = 0
    #: False when the vector index or the local embedder was unavailable, so
    #: this run was lexical + expansion only (BL-20260810-17).
    vector_available: bool = True
    #: Decision-date span of the retrieved passages (ISO strings), or None
    #: when nothing retrieved carries a date. A corpus that only reaches 1998
    #: cannot speak to a 2024 question, so the span is part of the envelope.
    date_earliest: str | None = None
    date_latest: str | None = None
    #: How many passages were promoted because a matter had already verified
    #: them (BL-20260817-05), and where that boost set came from. A boost is a
    #: deliberate bias in the ranking, so it is part of the envelope: a reader
    #: must be able to see that this order is not the corpus's own.
    boosted_count: int = 0
    boost_source: str = ""

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
            if not self.vector_available:
                base += (
                    " (The vector leg was unavailable — no embedding index or "
                    "no local embedder — so semantic matches were not searched.)"
                )
            return base
        parts = [
            f"{self.result_count} passage(s) retrieved "
            f"({self.lexical_count} lexical, {self.vector_count} semantic, "
            f"{self.expanded_count} via citation expansion); coverage is "
            "limited to the ingested corpus."
        ]
        if not self.vector_available:
            parts.append(
                "NOTE: the semantic (vector) leg was unavailable, so these "
                "results are lexical + citation expansion only."
            )
        if self.jurisdictions_present:
            parts.append(
                "Jurisdictions represented: "
                + ", ".join(sorted(self.jurisdictions_present))
                + "."
            )
        if self.date_earliest or self.date_latest:
            span = (
                f"{self.date_earliest} to {self.date_latest}"
                if self.date_earliest != self.date_latest
                else str(self.date_earliest or self.date_latest)
            )
            parts.append(
                f"Decision dates represented: {span}; nothing outside that "
                "span was retrieved."
            )
        if self.boosted_count:
            origin = f" ({self.boost_source})" if self.boost_source else ""
            parts.append(
                f"{self.boosted_count} passage(s) were ranked first because "
                f"this matter has already verified them{origin}; that is a "
                "deliberate bias toward known-good authority, not a fresh "
                "relevance judgement about them."
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
    # BL-20260810-19: the ingest extractor now stores a deterministic opinion
    # excerpt here, so the placeholder is the exception rather than the rule.
    # `snippet_kind` tells the downstream prompt what it is holding — a
    # verbatim excerpt (which may be a syllabus header, not the holding), a
    # model-written summary, or nothing at all.
    snippet_kind = record.get("holding_summary_kind") or (
        "excerpt" if summary else None
    )
    return {
        "id": record.get("id"),
        "type": "Case",
        "title": title,
        # `snippet` is what LegalWorkflow._analyze renders into the prompt.
        "snippet": summary or f"(no holding summary stored for {title})",
        "snippet_kind": snippet_kind,
        "source_url": record.get("source_url"),
        "court": record.get("court"),
        "decided_at": record.get("decided_at"),
        "source": record.get("source"),
        "confidence": record.get("confidence"),
        "score": record.get("score"),
        "retrieval_mode": retrieval_mode,
        # BL-20260803-01 / ADR 0004 P3 "surface who prevailed". Both are None
        # for records whose source was silent about the outcome; downstream
        # prompts must read None as "unknown", never as "nobody prevailed".
        "disposition": record.get("disposition"),
        "prevailing_party_type": record.get("prevailing_party_type"),
    }


def _statute_passage(record: Any, *, retrieval_mode: str = "lexical") -> dict[str, Any]:
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
        "retrieval_mode": retrieval_mode,
    }


def _ordinance_passage(
    record: Any, *, retrieval_mode: str = "lexical"
) -> dict[str, Any]:
    """Shape one ``:OrdinanceSection`` row (BL-20260906-07).

    Deliberately its own ``type`` rather than reusing ``StatuteSection``: a
    municipal code section and a state statute are different authorities, and
    a reader who cannot tell them apart cannot judge which one binds.
    """
    citation = record.get("citation") or "(uncited ordinance section)"
    heading = record.get("heading") or ""
    return {
        "id": record.get("id") or citation,
        "type": "OrdinanceSection",
        "title": f"{citation} {heading}".strip(),
        "snippet": (record.get("text") or "")[:1200],
        "source_url": record.get("source_url"),
        "court": None,
        "jurisdiction_code": record.get("jurisdiction_code") or None,
        "source": record.get("source"),
        "confidence": record.get("confidence"),
        "score": record.get("score"),
        "retrieval_mode": retrieval_mode,
    }


def reciprocal_rank_fusion(
    ranked_lists: list[list[dict[str, Any]]], *, k: int = RRF_K
) -> list[dict[str, Any]]:
    """Fuse ranked passage lists by reciprocal rank (BL-20260810-17).

    ``score = sum over lists of 1 / (k + rank)``, rank being 1-based. RRF is
    used rather than a weighted blend of the raw scores because a Lucene
    relevance score and a cosine similarity are not on the same scale and have
    no principled conversion — only their *orderings* are comparable.

    Ties break on the earliest rank achieved in any list, then on id, so the
    output is deterministic for a given input.

    A passage present in several lists keeps the dict from the first list that
    contained it, with ``retrieval_mode`` widened to ``"lexical+vector"`` when
    the legs disagree about how it was found.
    """
    merged: dict[str, dict[str, Any]] = {}
    scores: dict[str, float] = {}
    best_rank: dict[str, int] = {}
    modes: dict[str, set[str]] = {}

    for ranked in ranked_lists:
        for rank, passage in enumerate(ranked, start=1):
            pid = str(passage.get("id"))
            if not pid or pid == "None":
                continue
            scores[pid] = scores.get(pid, 0.0) + 1.0 / (k + rank)
            best_rank[pid] = min(best_rank.get(pid, rank), rank)
            modes.setdefault(pid, set()).add(str(passage.get("retrieval_mode") or ""))
            merged.setdefault(pid, passage)

    for pid, passage in merged.items():
        found = {m for m in modes[pid] if m}
        if len(found) > 1:
            passage["retrieval_mode"] = "+".join(sorted(found))
        passage["fusion_score"] = round(scores[pid], 6)

    return sorted(
        merged.values(),
        key=lambda p: (
            -scores[str(p["id"])],
            best_rank[str(p["id"])],
            str(p["id"]),
        ),
    )


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
        include_ordinances: bool = True,
        boost_ids: Iterable[str] | None = None,
        boost_source: str = "",
    ) -> None:
        self._session_factory = session_factory
        self._limit = limit
        self._expand_limit = expand_limit
        self._include_statutes = include_statutes
        # BL-20260906-07: local law is on by default — an ordinance that was
        # ingested but never retrievable is worse than not ingesting it, since
        # the coverage note would count it as corpus the answer had seen.
        self._include_ordinances = include_ordinances
        # BL-20260817-05: node ids a human has already verified on this
        # matter. Opt-in and never inferred — an unverified candidate must not
        # get a ranking advantage from having been guessed once before.
        self._boost_ids = {str(i) for i in (boost_ids or ())}
        self._boost_source = boost_source
        self.last_coverage = RetrievalCoverage()

    def _resolve_boost(self, state: Mapping[str, Any]) -> tuple[set[str], str]:
        """Boost set for this run: constructor set plus anything the state names.

        A ``matter_id`` in the state is resolved through the matters app; the
        import is local and guarded so ``agents_runtime`` keeps working (and
        keeps its tests hermetic) on an install where matters are absent.
        """
        ids = set(self._boost_ids)
        source = self._boost_source
        explicit = state.get("boost_case_ids")
        if explicit:
            ids.update(str(i) for i in explicit)
            source = source or "explicit"
        matter_id = state.get("matter_id")
        if matter_id:
            try:
                from law_ai.matters.services.authorities import boost_set_for_matter

                matter_ids, label = boost_set_for_matter(int(matter_id))
            except Exception as exc:  # pragma: no cover - matters app absent
                logger.debug("matter boost set unavailable: %s", exc)
            else:
                ids.update(matter_ids)
                source = label or source
        return ids, source

    @staticmethod
    def _apply_boost(
        passages: list[dict[str, Any]],
        boost_ids: set[str],
        source: str,
        coverage: RetrievalCoverage,
    ) -> list[dict[str, Any]]:
        """Stable-promote verified passages to the front, and label them.

        Stable: within the boosted group and within the rest, the retriever's
        own ranking is preserved, so the boost reorders *between* the two
        groups only and cannot scramble relevance inside either.
        """
        if not boost_ids:
            return passages
        boosted: list[dict[str, Any]] = []
        rest: list[dict[str, Any]] = []
        for passage in passages:
            if str(passage.get("id")) in boost_ids:
                passage["boosted"] = True
                passage["boost_source"] = source
                boosted.append(passage)
            else:
                rest.append(passage)
        coverage.boosted_count = len(boosted)
        coverage.boost_source = source if boosted else ""
        return boosted + rest

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

        boost_ids, boost_source = self._resolve_boost(state)

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

        passages = self._apply_boost(passages, boost_ids, boost_source, coverage)
        coverage.result_count = len(passages)
        present = {
            str(p.get("court") or p.get("jurisdiction_code") or "").strip()
            for p in passages
        }
        coverage.jurisdictions_present = sorted(p for p in present if p)
        dates = sorted(
            str(p.get("decided_at")).strip()
            for p in passages
            if str(p.get("decided_at") or "").strip()
        )
        if dates:
            coverage.date_earliest = dates[0]
            coverage.date_latest = dates[-1]
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
            vector_ids: set[str] = set()
            for query in queries[:3]:
                # One embedding per query, shared by both label legs: the
                # vectors live in the same space, so embedding twice would
                # only pay Ollama twice for the identical float list.
                embedding = await self._embed_query(query, coverage)
                lexical = await self._lexical_cases(
                    session, query, jurisdiction, coverage
                )
                vector = await self._vector_cases(
                    session, embedding, jurisdiction, coverage
                )
                vector_ids.update(str(p["id"]) for p in vector)
                # Fuse the two rankings for this query before merging into the
                # cross-query set, so neither leg can crowd the other out.
                for passage in reciprocal_rank_fusion([lexical, vector])[: self._limit]:
                    seen.setdefault(str(passage["id"]), passage)
                if self._include_statutes:
                    lex_sections = await self._lexical_statutes(
                        session, query, jurisdiction
                    )
                    vec_sections = await self._vector_statutes(
                        session, embedding, jurisdiction, coverage
                    )
                    vector_ids.update(str(p["id"]) for p in vec_sections)
                    fused_sections = reciprocal_rank_fusion(
                        [lex_sections, vec_sections]
                    )
                    for passage in fused_sections[: self._limit]:
                        seen.setdefault(str(passage["id"]), passage)
                if self._include_ordinances:
                    # Lexical only: no ordinance embeddings are written yet,
                    # so there is no vector half to fuse with.
                    ordinances = await self._lexical_ordinances(
                        session, query, jurisdiction
                    )
                    for passage in ordinances[: self._limit]:
                        seen.setdefault(str(passage["id"]), passage)

            coverage.lexical_count = len(seen)
            coverage.vector_count = sum(1 for pid in seen if pid in vector_ids)

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

    async def _embed_query(
        self, query: str, coverage: RetrievalCoverage
    ) -> list[float] | None:
        """Embed one query locally, or ``None`` when the embedder is absent.

        ``None`` is not an error: no Ollama (or the model not pulled) means
        the run is lexical + expansion only, and ``vector_available`` carries
        that caveat to the reviewer rather than silently narrowing recall.
        """
        from law_ai.core.llm.embeddings import embed_text

        embedding = await embed_text(query, component="graph_rag")
        if embedding is None:
            coverage.vector_available = False
        return embedding

    async def _vector_cases(
        self,
        session: Any,
        embedding: list[float] | None,
        jurisdiction: str | None,
        coverage: RetrievalCoverage,
    ) -> list[dict[str, Any]]:
        """Semantic top-K over ``:Case``, or ``[]`` when the leg is unavailable.

        Two things can be missing and both are non-fatal: the local embedder
        (no Ollama, model not pulled) and the vector index (migration 008 not
        applied). Either sets ``coverage.vector_available = False`` so the
        caveat reaches the reviewer rather than silently narrowing recall.
        """
        from law_ai.core.llm.embeddings import CASE_VECTOR_INDEX

        if embedding is None:
            return []
        court_prefix = str(jurisdiction).lower() if jurisdiction else ""
        try:
            records = await _run_logged(
                session,
                CASE_VECTOR_CYPHER,
                {
                    "index": CASE_VECTOR_INDEX,
                    "embedding": embedding,
                    "limit": self._limit,
                    "court_prefix": court_prefix,
                },
            )
        except Exception as exc:
            logger.info("vector case search unavailable (%s); skipping leg", exc)
            coverage.vector_available = False
            return []
        return [_case_passage(r, retrieval_mode="vector") for r in records]

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

    async def _lexical_ordinances(
        self, session: Any, query: str, jurisdiction: str | None
    ) -> list[dict[str, Any]]:
        """Fulltext top-K over ``:OrdinanceSection`` (BL-20260906-07).

        Degrades like the statute leg: a missing index logs and yields
        nothing rather than failing the run.
        """
        try:
            records = await _run_logged(
                session,
                ORDINANCE_FULLTEXT_CYPHER,
                {
                    "index": ORDINANCE_FULLTEXT_INDEX,
                    "query": escape_lucene(query),
                    "limit": self._limit,
                    "jurisdiction": str(jurisdiction).lower() if jurisdiction else "",
                },
            )
        except Exception as exc:
            logger.info("fulltext ordinance search unavailable (%s); skipping", exc)
            return []
        return [_ordinance_passage(r) for r in records]

    async def _vector_statutes(
        self,
        session: Any,
        embedding: list[float] | None,
        jurisdiction: str | None,
        coverage: RetrievalCoverage,
    ) -> list[dict[str, Any]]:
        """Semantic top-K over ``:StatuteSection`` (the second half of the leg).

        Statutes are the label most likely to be *asked about* in words the
        drafters never used ("can my landlord keep the deposit?"), so the
        lexical leg alone under-recalls them. Degrades exactly like the case
        leg: a missing embedder or index marks ``vector_available`` False and
        the run continues on fulltext.
        """
        from law_ai.core.llm.embeddings import STATUTE_VECTOR_INDEX

        if embedding is None:
            return []
        try:
            records = await _run_logged(
                session,
                STATUTE_VECTOR_CYPHER,
                {
                    "index": STATUTE_VECTOR_INDEX,
                    "embedding": embedding,
                    "limit": self._limit,
                    "jurisdiction": str(jurisdiction).lower() if jurisdiction else "",
                },
            )
        except Exception as exc:
            logger.info("vector statute search unavailable (%s); skipping leg", exc)
            coverage.vector_available = False
            return []
        return [_statute_passage(r, retrieval_mode="vector") for r in records]


def build_default_retriever() -> GraphRAGRetriever:
    """Factory used by ``LegalWorkflow`` when no retriever is injected."""
    return GraphRAGRetriever()


__all__ = [
    "CASE_FULLTEXT_INDEX",
    "ORDINANCE_FULLTEXT_CYPHER",
    "ORDINANCE_FULLTEXT_INDEX",
    "RRF_K",
    "STATUTE_FULLTEXT_INDEX",
    "STATUTE_VECTOR_CYPHER",
    "GraphRAGRetriever",
    "RetrievalCoverage",
    "build_default_retriever",
    "escape_lucene",
    "reciprocal_rank_fusion",
]
