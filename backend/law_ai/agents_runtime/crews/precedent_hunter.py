"""
Precedent Hunter Agent

Hybrid GraphRAG retrieval (Neo4j lexical fulltext + one hop of ``CITES``
expansion) over the ingested corpus, surfaced as ranked precedents with the
coverage envelope the retriever publishes (BL-20260511-06).

Honesty rules this agent must keep (constitution §4 provenance, §13
attribution):

* Every precedent is a row that came back from the graph. Nothing is
  model-generated, so nothing here can be a hallucinated case.
* An empty result set stays ``degraded=True`` at confidence 0.0 with a
  summary that says "no results in *this corpus*" — never "no such
  precedent exists".
* ``confidence`` is derived from what the graph returned, never raised on an
  empty set.
"""

from typing import Any

from pydantic import BaseModel, Field
import logging
import time
from law_ai.agents_runtime.attribution import (
    attribution_from_passage,
    check_attribution,
)
from law_ai.core.provenance import provenance

logger = logging.getLogger("law_ai.agents.precedent_hunter")

#: Provenance label for a real retrieval run. Not a model name — no LLM is
#: called on this path; the "model" that produced the output is the retriever.
RETRIEVAL_MODEL_LABEL = "graph_rag/lexical+cites"

#: Label used when no retrieval could run at all (graph down, no query).
DEGRADED_MODEL_LABEL = "degraded/no-retrieval"


class Precedent(BaseModel):
    case_id: str
    title: str
    court: str
    year: int
    relevance_score: float
    distinguishing_factors: list[str] = Field(default_factory=list)
    url: str
    retrieval_mode: str = Field(
        default="lexical",
        description="`lexical` (fulltext hit) or `citation_expansion` (CITES hop).",
    )
    source: str = Field(
        default="", description="Ingestion source recorded on the graph node."
    )
    graph_confidence: float | None = Field(
        default=None, description="`confidence` stored on the :Case node."
    )
    attribution: dict[str, Any] = Field(
        default_factory=dict,
        description=(
            "Constitution §13 issuing authority (court, jurisdiction, "
            "decided_at, binding/persuasive) read off the graph node — "
            "BL-20260803-04."
        ),
    )


class PrecedentList(BaseModel):
    precedents: list[Precedent]
    summary: str
    confidence: float
    degraded: bool = Field(
        default=False,
        description=(
            "True when no real retrieval ran (unimplemented/offline path). "
            "Degraded output must never be presented as genuine search results."
        ),
    )
    coverage_note: str = Field(
        default="",
        description=(
            "Verbatim coverage envelope from the retriever — what the corpus "
            "could and could not answer (constitution §13)."
        ),
    )
    requires_review: bool = Field(
        default=False,
        description=(
            "Structured HITL flag: True when at least one retrieved precedent "
            "is emitted without a complete issuing authority (court + "
            "jurisdiction + decided_at). Carrying attribution is not the same "
            "as having it — an under-attributed precedent must be looked at "
            "before it is relied on (constitution §13, BL-20260803-04)."
        ),
    )
    trace_id: str | None = Field(
        default=None, description="Provenance trace_id from log_agent_call"
    )


def _year_of(decided_at: Any) -> int:
    """Best-effort year from an ISO date; 0 when the node stores none.

    0 reads as "the graph does not record a date" — better than guessing a
    year onto a legal authority (§13).
    """
    text = str(decided_at or "").strip()
    if len(text) >= 4 and text[:4].isdigit():
        return int(text[:4])
    return 0


def _to_precedent(
    passage: dict[str, Any], requested_jurisdiction: str | None = None
) -> Precedent | None:
    """Map one retriever passage onto :class:`Precedent`.

    Statute sections are dropped: this agent hunts *precedent*, and a statute
    has no court or decision year to attribute.
    """
    if passage.get("type") != "Case":
        return None
    case_id = str(passage.get("id") or "").strip()
    if not case_id:
        return None
    score = passage.get("score")
    try:
        relevance = float(score) if score is not None else 0.0
    except (TypeError, ValueError):
        relevance = 0.0
    graph_conf = passage.get("confidence")
    try:
        graph_confidence = float(graph_conf) if graph_conf is not None else None
    except (TypeError, ValueError):
        graph_confidence = None
    return Precedent(
        case_id=case_id,
        title=str(passage.get("title") or case_id),
        # "" (not a guess) when the graph does not record the court.
        court=str(passage.get("court") or ""),
        year=_year_of(passage.get("decided_at")),
        relevance_score=relevance,
        url=str(passage.get("source_url") or ""),
        retrieval_mode=str(passage.get("retrieval_mode") or "lexical"),
        source=str(passage.get("source") or ""),
        graph_confidence=graph_confidence,
        attribution=attribution_from_passage(
            passage, requested_jurisdiction
        ).model_dump(),
    )


def _confidence_from(precedents: list[Precedent], coverage: Any) -> float:
    """Confidence grounded in what the graph returned, capped well below 1.

    An empty set is 0.0, always. A non-empty set scales with how many
    passages came back (saturating at 5) and is halved when the requested
    jurisdiction is absent entirely — precedent from elsewhere is persuasive
    at best.
    """
    if not precedents:
        return 0.0
    base = min(len(precedents), 5) / 5.0 * 0.8
    if getattr(coverage, "jurisdiction_absent", False):
        base *= 0.5
    if not getattr(coverage, "index_available", True):
        base *= 0.75
    return round(min(base, 0.8), 3)


class PrecedentHunter:
    """Retrieve on-point precedent from the citation graph.

    :param retriever: async callable taking a retrieval state mapping and
        returning passage dicts, exposing ``last_coverage``. Defaults to the
        shared :class:`~law_ai.agents_runtime.tools.graph_rag.GraphRAGRetriever`.
        Injected in tests so no Neo4j is required.
    """

    name = "PrecedentHunter"

    def __init__(self, *, retriever: Any = None) -> None:
        self._retriever = retriever

    def _get_retriever(self) -> Any:
        if self._retriever is None:
            from law_ai.agents_runtime.tools.graph_rag import build_default_retriever

            self._retriever = build_default_retriever()
        return self._retriever

    async def run(self, input_data: dict[str, Any]) -> PrecedentList:
        start = time.time()
        question = str(
            input_data.get("text") or input_data.get("question") or ""
        ).strip()
        jurisdiction = input_data.get("jurisdiction") or None

        passages: list[dict[str, Any]] = []
        coverage: Any = None
        retrieval_ran = False
        if question:
            retriever = self._get_retriever()
            try:
                passages = await retriever(
                    {
                        "question": question,
                        "queries": [question],
                        "jurisdiction": jurisdiction,
                    }
                )
                retrieval_ran = True
            except Exception as exc:
                # A graph fault must degrade honestly, never 500 a caller and
                # never look like "we searched and found nothing".
                logger.warning("precedent retrieval failed: %s", exc, exc_info=True)
            coverage = getattr(retriever, "last_coverage", None)

        precedents = [
            p
            for p in (
                _to_precedent(x, str(jurisdiction) if jurisdiction else None)
                for x in passages
            )
            if p is not None
        ]
        precedents.sort(key=lambda p: p.relevance_score, reverse=True)

        coverage_note = ""
        if coverage is not None and hasattr(coverage, "note"):
            coverage_note = str(coverage.note())

        if not question:
            summary = (
                "No question was supplied, so no precedent search was "
                "performed. 0 precedents retrieved."
            )
        elif not retrieval_ran:
            summary = (
                "Precedent search could not run: the knowledge graph was "
                "unreachable. 0 precedents retrieved. Absence of results here "
                "does NOT mean no relevant precedent exists."
            )
        elif not precedents:
            summary = (
                "0 precedents retrieved from the ingested corpus. Absence of "
                "results here does NOT mean no relevant precedent exists — it "
                "means this corpus holds none matching the query. " + coverage_note
            ).strip()
        else:
            summary = (
                f"{len(precedents)} precedent(s) retrieved from the citation "
                f"graph for {question[:120]!r}. " + coverage_note
            ).strip()

        # §13: a precedent whose :Case node records no court or no decision
        # date is an unattributed statement of law the moment it is shown, so
        # it pins the output for review even though retrieval "worked".
        unattributed = check_attribution(
            [
                {"text": p.title or p.case_id, "attribution": p.attribution}
                for p in precedents
            ]
        )
        if unattributed:
            summary = (
                f"{summary} Attribution incomplete (constitution §13): "
                + "; ".join(unattributed[:5])
                + " — human review required."
            ).strip()

        output = PrecedentList(
            precedents=precedents,
            summary=summary,
            confidence=_confidence_from(precedents, coverage),
            # Degraded whenever nothing real came back: callers must keep
            # forcing human review rather than reading an empty set as an
            # authoritative "no precedent".
            degraded=not precedents,
            requires_review=bool(unattributed),
            coverage_note=coverage_note,
        )

        latency = (time.time() - start) * 1000
        trace_id = provenance.log_agent_call(
            self.name,
            input_data,
            output.model_dump(),
            RETRIEVAL_MODEL_LABEL if retrieval_ran else DEGRADED_MODEL_LABEL,
            latency,
            confidence=output.confidence,
            sources=[
                {"title": p.title, "source_url": p.url, "case_id": p.case_id}
                for p in precedents
            ],
        )
        output.trace_id = trace_id
        return output
