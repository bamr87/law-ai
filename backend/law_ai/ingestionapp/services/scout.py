"""IngestionScout — first concrete Law AI ingestion crew (T-003 in specs/001).

Responsibilities:

* Parse a raw CourtListener opinion payload into an ``ExtractionResult``.
* Route high-confidence results into Neo4j; route low-confidence ones to
  the ``pending_review`` Postgres table (or a JSONL fallback).
* Log every step through ``app.core.provenance`` for legal auditability.
"""

from __future__ import annotations

import json
import logging
import re
import time
from datetime import datetime, UTC
from pathlib import Path
from typing import Any

from law_ai.core.provenance import provenance
from law_ai.core.neo4j.driver import get_neo4j_driver
from law_ai.core.neo4j.queries import commit_extraction
from law_ai.core.neo4j.citation_resolver import (
    densify_extraction,
    densify_statute_extraction,
)
from law_ai.core.schemas.extraction import (
    Citation,
    Disposition,
    Entity,
    ExtractionResult,
    HoldingSummaryKind,
    PrevailingPartyType,
)

logger = logging.getLogger("law_ai.ingestion.scout")

# Confidence threshold below which extractions are quarantined for human review
# (specs/001 NFR-HITL-1).
CONFIDENCE_THRESHOLD = 0.7

# JSONL fallback used when Postgres is unreachable so the dev loop stays green.
PENDING_REVIEW_DIR = Path("backend/var/pending_review")


def _llm_summary_enabled() -> bool:
    """Whether the optional audited LLM holding-summary pass is on.

    ``INGEST_LLM_SUMMARY`` (BL-20260906-01) is off by default: the excerpt is
    deterministic and free, and a per-document model call is neither. Read at
    call time so an operator can flip it per run, and defaulting to *False* —
    the cheap, offline reading — when settings are unavailable.
    """
    try:
        from django.conf import settings

        return bool(getattr(settings, "INGEST_LLM_SUMMARY", False))
    except Exception:  # pragma: no cover - settings always configured in app
        return False


def _hitl_gates_enabled() -> bool:
    """Whether the ingestion HITL gate is armed (constitution §5).

    Reads ``ENABLE_HUMAN_APPROVAL_GATES`` at call time (not import time) so
    tests and operators can flip it per-run. Defaults to *True* — the safe
    reading — when settings are unavailable.
    """
    try:
        from django.conf import settings

        return bool(getattr(settings, "ENABLE_HUMAN_APPROVAL_GATES", True))
    except Exception:  # pragma: no cover - settings always configured in app
        return True


class IngestionScout:
    """Concrete agent for ingesting US court opinions."""

    name = "IngestionScout"
    description = "Parses opinion payloads into audited Neo4j graph nodes"
    requires_human_approval = False  # Per-item HITL via confidence threshold.
    agent_version = "0.1.1"

    def __init__(self, *, threshold: float = CONFIDENCE_THRESHOLD) -> None:
        self._threshold = threshold

    # ------------------------------------------------------------------
    # Extraction
    # ------------------------------------------------------------------
    def extract(self, payload: dict[str, Any]) -> ExtractionResult:
        """Convert a raw opinion payload into a structured ``ExtractionResult``.

        ``payload`` mirrors the CourtListener v4 ``/opinions/{id}/`` shape
        but only a small subset of fields is required:

        * ``id`` (int|str) — stable opinion identifier (becomes ``Case.id``).
        * ``case_name`` or ``cluster.case_name`` — title.
        * ``plain_text`` or ``html_with_citations`` — body for citation parsing.
        * ``absolute_url`` — populated on full opinion responses.
        * ``source_name`` — optional registry key of the originating adapter
          (BL-20260602-07); defaults to ``"courtlistener"``.
        """
        start = time.time()
        plain_text = payload.get("plain_text") or ""
        # BL-20260810-19: remember which body we fell back to so the excerpt
        # deriver knows whether it has to strip markup.
        body_is_html = not plain_text and bool(payload.get("html_with_citations"))
        text = plain_text or payload.get("html_with_citations") or ""
        case_id = str(payload.get("id") or payload.get("opinion_id") or "")
        if not case_id:
            raise ValueError("opinion payload missing 'id'")

        title = (
            payload.get("case_name")
            or (payload.get("cluster") or {}).get("case_name")
            or "Untitled opinion"
        )
        court = (payload.get("cluster") or {}).get("court") or payload.get("court")
        decided_at = _parse_date(
            (payload.get("cluster") or {}).get("date_filed")
            or payload.get("date_filed")
        )
        source_url = payload.get("absolute_url")
        if source_url and source_url.startswith("/"):
            source_url = f"https://www.courtlistener.com{source_url}"

        citations = _extract_citations(text)
        entities = _extract_entities(payload, text=text)
        confidence = _score(text=text, n_citations=len(citations), title=title)

        # BL-20260803-01 / ADR 0004 P3. Read only what the record states: the
        # cluster's own disposition + posture text. Nothing here is inferred
        # from the opinion prose, and no LLM is consulted, so a silent record
        # stays silent (both fields None) instead of acquiring a made-up
        # outcome.
        cluster = payload.get("cluster") or {}
        disposition: Disposition | None = map_disposition(
            cluster.get("disposition") or payload.get("disposition")
        )
        posture = cluster.get("posture") or payload.get("posture")
        prevailing_party_type: PrevailingPartyType | None = (
            derive_prevailing_party_type(disposition, posture)
        )

        # BL-20260810-19: `:Case.holding_summary` is fulltext-indexed and is
        # what GraphRAG renders as the passage snippet, so leaving it null made
        # every retrieved passage read "(no holding summary stored)". Derive a
        # deterministic opinion excerpt and label it as such.
        holding_summary = derive_holding_summary(text, is_html=body_is_html)
        holding_summary_kind: HoldingSummaryKind | None = (
            "excerpt" if holding_summary else None
        )

        result = ExtractionResult(
            case_id=case_id,
            title=title,
            court=court,
            decided_at=decided_at,
            citations=citations,
            entities=entities,
            holding_summary=holding_summary,
            holding_summary_kind=holding_summary_kind,
            disposition=disposition,
            prevailing_party_type=prevailing_party_type,
            confidence=confidence,
            # BL-20260602-07: dispatch routes every adapter's document through
            # this extractor, so a hardcoded "courtlistener" made
            # ``PendingReview.source`` a lie for the other adapters and left
            # HITL rows addressable only by primary key. Callers that know
            # their originating adapter pass ``source_name``.
            source=str(payload.get("source_name") or "courtlistener"),
            source_url=source_url,
            ingest_timestamp=datetime.now(UTC),
            agent_version=self.agent_version,
        )

        provenance.log_agent_call(
            agent_name=self.name,
            input_data={"case_id": case_id, "title": title},
            output_data={
                "confidence": result.confidence,
                "n_citations": len(result.citations),
            },
            model="rule-based+eyecite",
            latency_ms=(time.time() - start) * 1000,
            confidence=result.confidence,
            sources=[{"url": source_url}] if source_url else [],
        )
        return result

    async def aextract(self, payload: dict[str, Any]) -> ExtractionResult:
        """:meth:`extract`, plus the optional audited LLM summary pass.

        BL-20260906-01. ``ExtractionResult.holding_summary_kind`` reserved
        ``"summary"`` for prose written by a model, but ``extract`` is sync
        and had no way to make the call, so only the rule-based ``"excerpt"``
        was ever produced. This is the async variant that can: gated behind
        ``INGEST_LLM_SUMMARY``, routed through :mod:`law_ai.core.llm` so the
        ``llm_call`` provenance event is written (constitution §4), and
        fail-open — a provider outage leaves the excerpt in place rather than
        failing the ingest.
        """
        result = self.extract(payload)
        if not _llm_summary_enabled():
            return result
        text = payload.get("plain_text") or payload.get("html_with_citations") or ""
        if not str(text).strip():
            return result

        summary = await self._llm_holding_summary(str(text), result.case_id)
        if summary:
            result.holding_summary = summary
            result.holding_summary_kind = "summary"
        return result

    async def _llm_holding_summary(self, text: str, case_id: str) -> str | None:
        """One audited model call for a holding summary, or ``None``.

        Never raises: the summary is an enrichment, so a refusal, an outage or
        an empty answer degrades to the excerpt the extractor already wrote.
        """
        from law_ai.core import llm

        try:
            result = await llm.agenerate(
                HOLDING_SUMMARY_PROMPT.format(text=text[:LLM_SUMMARY_INPUT_CHARS]),
                system=HOLDING_SUMMARY_SYSTEM,
                max_tokens=300,
                agent=self.name,
            )
        except Exception as exc:
            logger.warning("holding-summary pass failed for %s: %s", case_id, exc)
            return None
        summary = " ".join((result.text or "").split()).strip()
        if not summary:
            return None
        return summary[:HOLDING_EXCERPT_MAX_CHARS]

    # ------------------------------------------------------------------
    # Commit
    # ------------------------------------------------------------------
    async def run_and_commit(
        self,
        payload: dict[str, Any],
        *,
        force_quarantine: bool = False,
        force_commit: bool = False,
    ) -> dict[str, Any]:
        """Extract then either commit to Neo4j or quarantine.

        Parameters
        ----------
        payload:
            Raw document dict passed to :meth:`extract`.
        force_quarantine:
            When *True*, always route to the HITL queue regardless of
            confidence score.  Set this when the source adapter's
            ``requires_human_approval`` flag is True (spec 018 NFR-HITL-1).
        force_commit:
            When *True*, bypass the confidence gate and commit. Reserved for
            the human-approval path (spec 029): the item was quarantined,
            a person reviewed it, and that approval **is** the HITL gate.
            ``force_quarantine`` wins if both are set, so an
            approval-required source can never be auto-committed.

        Returns a small summary dict suitable for the CLI run report.

        This method remains the single writer of ``:Case`` nodes
        (constitution §12 invariant I1) — the approval path routes through
        here rather than writing to the graph itself.
        """
        result = await self.aextract(payload)
        gates_enabled = _hitl_gates_enabled()
        below_threshold = not result.is_high_confidence(self._threshold)
        should_quarantine = force_quarantine or (
            not force_commit and gates_enabled and below_threshold
        )
        if (
            not gates_enabled
            and not force_quarantine
            and not force_commit
            and below_threshold
        ):
            # Constitution §5 requires HITL on ingestion; running with the gate
            # off is an operator override that must leave a trace. Only a
            # sub-threshold extraction is an override, though: a high-confidence
            # one commits with the gate armed too, so logging it here would
            # over-report overrides and mislabel them (BL-20260906-92).
            provenance.log_event(
                "hitl_gate_disabled",
                {
                    "agent": self.name,
                    "case_id": result.case_id,
                    "confidence": result.confidence,
                    "detail": (
                        "ENABLE_HUMAN_APPROVAL_GATES=False — extraction scoring "
                        f"{result.confidence:.3f} (below the "
                        f"{self._threshold:.2f} threshold) committed without "
                        "human review"
                    ),
                },
            )
        if should_quarantine:
            await self._quarantine(result, payload)
            return {
                "case_id": result.case_id,
                "committed": False,
                "pending": True,
                "confidence": result.confidence,
                "edges": 0,
            }

        driver = get_neo4j_driver()
        async with driver.session() as session:
            await densify_extraction(session, result)
            # BL-20260509-07: statutory citations get the same treatment, so
            # an opinion that cites the CRS gains a real CITES_STATUTE edge.
            # Costs no round-trip when the opinion cites no statutes.
            await densify_statute_extraction(session, result)
            edges = await commit_extraction(session, result)

        provenance.log_graph_query(
            cypher="ingestion.commit",
            params={"case_id": result.case_id},
            result_count=1 + edges,
            latency_ms=0.0,
        )
        return {
            "case_id": result.case_id,
            "committed": True,
            "pending": False,
            "confidence": result.confidence,
            "edges": edges,
        }

    # ------------------------------------------------------------------
    # HITL quarantine
    # ------------------------------------------------------------------
    async def _quarantine(
        self, result: ExtractionResult, payload: dict[str, Any]
    ) -> None:
        """Send a low-confidence result to the HITL queue (or JSONL fallback).

        Canonical path (specs/004 FR-3, spec 011 FR-11): enqueue the
        ``quarantine_extraction`` Celery task which atomically writes a
        ``PendingReview`` row + matching ``AuditEvent`` via the Django ORM.
        Under ``CELERY_TASK_ALWAYS_EAGER=True`` (test/dev) this runs in-line;
        in production it is dispatched to a worker via Redis.

        JSONL is a true *failure* fallback — only used when the dispatch
        path or the task itself raises (e.g. broker unreachable, Postgres
        down, ORM constraint failure). Closes BL-20260503-20.

        The dispatch runs through ``sync_to_async`` (BL-20260510-01): under
        ``CELERY_TASK_ALWAYS_EAGER`` the task body executes inline, and its
        Django ORM writes raise ``SynchronousOnlyOperation`` when called
        straight from this coroutine — which silently demoted every eager
        quarantine to the JSONL fallback, so no ``PendingReview`` row was
        ever written from the async ingestion path.
        """
        from asgiref.sync import sync_to_async

        try:
            await sync_to_async(self._quarantine_via_celery)(result, payload)
        except Exception as exc:
            logger.warning(
                "pending_review celery dispatch failed (%s); using JSONL",
                type(exc).__name__,
            )
            self._quarantine_jsonl(result, payload)
            provenance.log_agent_call(
                agent_name=self.name,
                input_data={"case_id": result.case_id},
                output_data={"pending": True, "store": "jsonl"},
                model="n/a",
                latency_ms=0.0,
                confidence=result.confidence,
            )
            return

        provenance.log_agent_call(
            agent_name=self.name,
            input_data={"case_id": result.case_id},
            output_data={"pending": True, "store": "celery"},
            model="n/a",
            latency_ms=0.0,
            confidence=result.confidence,
        )

    def _quarantine_jsonl(
        self, result: ExtractionResult, payload: dict[str, Any]
    ) -> None:
        """Append a low-confidence record to a daily JSONL file (fallback only)."""
        PENDING_REVIEW_DIR.mkdir(parents=True, exist_ok=True)
        path = PENDING_REVIEW_DIR / f"{datetime.now(UTC):%Y-%m-%d}.jsonl"
        with path.open("a", encoding="utf-8") as fh:
            fh.write(
                json.dumps(
                    {
                        "id": result.case_id,
                        "source": result.source,
                        "confidence": result.confidence,
                        "payload": payload,
                        "reason": "low_confidence",
                    },
                    default=str,
                )
                + "\n"
            )

    def _quarantine_via_celery(
        self, result: ExtractionResult, payload: dict[str, Any]
    ) -> None:
        """Dispatch the extraction to the ``quarantine_extraction`` Celery task.

        The task is the single writer for the ``PendingReview`` table and the
        matching ``AuditEvent`` row (spec 011 FR-11). Imported lazily so this
        module stays importable in environments where Celery is not yet
        configured (e.g. unit tests that only exercise ``extract``).

        Any exception (broker unreachable, ORM error in eager mode, …) is
        allowed to propagate so ``_quarantine`` can fall back to JSONL.
        """
        from law_ai.ingestionapp.tasks import quarantine_extraction

        task_payload: dict[str, Any] = {
            "id": result.case_id,
            "source": result.source,
            "confidence": result.confidence,
            "reason": "low_confidence",
            "payload": json.loads(json.dumps(payload, default=str)),
        }
        quarantine_extraction.delay(task_payload)


# ---------------------------------------------------------------------------
# Helpers (small, deterministic, unit-tested)
# ---------------------------------------------------------------------------
def _parse_date(raw: Any) -> datetime | None:
    if not raw:
        return None
    if isinstance(raw, datetime):
        return raw if raw.tzinfo else raw.replace(tzinfo=UTC)
    try:
        # CourtListener returns ISO date or datetime strings.
        return datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except ValueError:
        return None


#: CRS citations eyecite does not recognise (BL-20260509-07). eyecite knows
#: the reporter "Colo. Rev. Stat." but not the abbreviation Colorado courts
#: actually write — "C.R.S." yields a bare ``UnknownCitation('§')`` — and it
#: never matches the trailing-reporter form "§ 13-80-102, C.R.S." at all. Both
#: orders are picked up here so a statutory cite becomes a real ``:Citation``
#: node that ``densify_statute_extraction`` can point at a ``:StatuteSection``.
#: Decimal articles ("18-1.3-401") are ordinary in the CRS, so each dotted
#: part carries its own optional decimal (BL-20260906-89).
_CRS_SECTION_NUMBER = r"\d{1,2}(?:\.\d+)?-\d{1,3}(?:\.\d+)?-\d{1,4}(?:\.\d+)?"
_CRS_REPORTER_PATTERN = (
    r"C\.\s?R\.\s?S\.(?:\s?A\.)?|Colo\.\s?Rev\.\s?Stat\.(?:\s?Ann\.)?"
)
_CRS_CITATION_RES = (
    # Reporter first: "C.R.S. § 18-3-102", "Colo. Rev. Stat. Ann. 18-3-102".
    re.compile(
        rf"(?:{_CRS_REPORTER_PATTERN})\s*(?:§+\s*)?{_CRS_SECTION_NUMBER}",
        re.IGNORECASE,
    ),
    # Reporter last: "§ 13-80-102, C.R.S.", "section 13-80-102, C.R.S. (2020)",
    # "18-3-102(1)(a), C.R.S." The trailing reporter is the anchor, so the
    # leading "§"/"section" is optional; a bare number with no reporter after
    # it still matches nothing.
    re.compile(
        rf"(?:§+\s*|sections?\s+)?{_CRS_SECTION_NUMBER}"
        rf"(?:\([^)]{{1,8}}\))*,?\s*(?:{_CRS_REPORTER_PATTERN})",
        re.IGNORECASE,
    ),
)


def _extract_citations(text: str) -> list[Citation]:
    """Run Eyecite over the body text, returning unique normalized citations."""
    if not text:
        return []
    try:
        from eyecite import get_citations
    except Exception:  # pragma: no cover — eyecite is a hard dep, but guard anyway
        return []

    seen: dict[str, Citation] = {}

    def _add(raw_text: str) -> None:
        normalized = " ".join(str(raw_text).split()).lower()
        if not normalized or normalized in seen:
            return
        seen[normalized] = Citation(text=str(raw_text), normalized=normalized)

    for cit in get_citations(text):
        raw = getattr(cit, "matched_text", None)
        if callable(raw):
            raw = raw()
        if not raw:
            raw = str(cit)
        _add(str(raw))

    for pattern in _CRS_CITATION_RES:
        for match in pattern.finditer(text):
            _add(match.group(0))
    return list(seen.values())


def _extract_entities(payload: dict[str, Any], *, text: str = "") -> list[Entity]:
    """Entity pull from structured fields, plus an optional NER pass.

    Structured fields (judges, court) are always trusted. The NER pass over
    *text* is off unless ``ENABLE_NER`` is set (BL-20260429-03) — see
    :mod:`law_ai.ingestionapp.services.ner` for why Blackstone itself could
    not be reintroduced. NER output only ever *adds* entities: it never
    overrides a structured field and never feeds ``_score``, so it cannot
    move a document across the HITL threshold.
    """
    entities: list[Entity] = []
    cluster = payload.get("cluster") or {}
    judges = cluster.get("judges") or payload.get("judges")
    if judges:
        for judge in str(judges).split(","):
            j = judge.strip()
            if j:
                entities.append(Entity(text=j, label="JUDGE"))
    court = cluster.get("court") or payload.get("court")
    if isinstance(court, str) and court:
        entities.append(Entity(text=court, label="COURT"))

    if text:
        from law_ai.ingestionapp.services.ner import extract_ner_entities

        seen = {(e.text, e.label) for e in entities}
        for entity in extract_ner_entities(text):
            key = (entity.text, entity.label)
            if key in seen or any(entity.text == e.text for e in entities):
                continue
            seen.add(key)
            entities.append(entity)
    return entities


def _score(*, text: str, n_citations: int, title: str) -> float:
    """Rule-based confidence in 0..1.

    Conservative on purpose: items below 0.7 are quarantined for human
    review, so we'd rather under-score than silently corrupt the graph.
    """
    score = 0.0
    if title and title != "Untitled opinion":
        score += 0.4
    if len(text) > 500:
        score += 0.3
    if n_citations >= 1:
        score += 0.2
    if n_citations >= 5:
        score += 0.1
    return round(min(score, 1.0), 3)


# ---------------------------------------------------------------------------
# Disposition + prevailing party (BL-20260803-01, ADR 0004 P3)
# ---------------------------------------------------------------------------
#: Ordered keyword table for the disposition mapper. Order matters: the first
#: matching keyword wins, so the stronger outcome ("reversed and remanded" is
#: a reversal) is listed ahead of the weaker one. Deliberately narrow — an
#: unrecognised disposition string yields ``None`` (see ``map_disposition``),
#: never a guess.
_DISPOSITION_KEYWORDS: tuple[tuple[str, Disposition], ...] = (
    ("vacated", "vacated"),
    ("reversed", "reversed"),
    ("dismissed", "dismissed"),
    ("remanded", "remanded"),
    ("affirmed", "affirmed"),
)

#: Phrases that mark a split outcome. A split appeal has no single coarse
#: disposition in our vocabulary, so it maps to ``"other"`` and yields no
#: prevailing party type at all.
_SPLIT_PHRASES = (
    "in part",
    "in-part",
)


def map_disposition(raw: Any) -> Disposition | None:
    """Map a source record's free-text disposition onto our coarse vocabulary.

    Deterministic and conservative (BL-20260803-01): CourtListener's
    ``cluster.disposition`` is free text written by the court, so anything we
    do not recognise returns ``None`` and is logged rather than guessed. No
    LLM is consulted — constitution §13 forbids inventing an outcome the
    record does not state.

    >>> map_disposition("Affirmed.")
    'affirmed'
    >>> map_disposition("Judgment of the district court is REVERSED and REMANDED")
    'reversed'
    >>> map_disposition("") is None
    True
    """
    if not raw:
        return None
    text = str(raw).strip().lower()
    if not text:
        return None
    if any(phrase in text for phrase in _SPLIT_PHRASES):
        return "other"
    for keyword, mapped in _DISPOSITION_KEYWORDS:
        if keyword in text:
            return mapped
    logger.info("scout.map_disposition: unmapped disposition text %r", text[:120])
    return None


#: Dispositions whose winner is structurally unambiguous on a direct appeal.
#: Everything else (remanded / dismissed / vacated / other) is left ``None``:
#: a remand or a vacatur does not by itself say who ultimately prevails.
_PREVAILING_BY_DISPOSITION: dict[str, PrevailingPartyType] = {
    "affirmed": "appellee",
    "reversed": "appellant",
}


def derive_prevailing_party_type(
    disposition: Disposition | None, posture: Any = None
) -> PrevailingPartyType | None:
    """Derive the coarse prevailing party, or ``None`` when ambiguous.

    Only ``affirmed`` (the appellee keeps the judgment) and ``reversed`` (the
    appellant upsets it) are unambiguous, and only on a record whose posture
    is an appeal. *posture* is the source record's own posture text; when it
    is present and does not read as an appeal, we decline rather than assume.
    Never inferred by an LLM.

    >>> derive_prevailing_party_type("affirmed")
    'appellee'
    >>> derive_prevailing_party_type("remanded") is None
    True
    """
    if disposition is None:
        return None
    mapped = _PREVAILING_BY_DISPOSITION.get(disposition)
    if mapped is None:
        return None
    if posture:
        posture_text = str(posture).strip().lower()
        if posture_text and not any(
            token in posture_text for token in ("appeal", "certiorari", "review")
        ):
            return None
    return mapped


# ---------------------------------------------------------------------------
# Holding summary (BL-20260810-19)
# ---------------------------------------------------------------------------
#: Maximum characters kept in a derived excerpt. Long enough to carry a real
#: holding, short enough that a fulltext hit's snippet stays readable in a
#: prompt without crowding out the other retrieved passages.
HOLDING_EXCERPT_MAX_CHARS = 600

#: A paragraph shorter than this is almost always a caption, docket line or
#: section heading rather than reasoning, so the excerpt skips past it.
_MIN_PARAGRAPH_CHARS = 120

#: How much opinion text the optional LLM summary pass reads (BL-20260906-01).
#: Bounded so one long opinion cannot blow a context window or a budget; the
#: holding is in the opening reasoning far more often than in the tail.
LLM_SUMMARY_INPUT_CHARS = 12_000

#: The summary pass says what the court *held*, in the court's own terms, and
#: refuses rather than guessing — a fabricated holding is worse than none, and
#: the caller falls back to the verbatim excerpt when this returns nothing
#: (ADR 0004 P3: the graph never acquires an outcome the record does not state).
HOLDING_SUMMARY_SYSTEM = (
    "You summarise judicial opinions for a legal knowledge graph. Report only "
    "what the opinion itself states. Never infer an outcome the text does not "
    "state, never add citations, and answer with the summary alone. If the "
    "text does not state a holding, answer with an empty string."
)

HOLDING_SUMMARY_PROMPT = (
    "Summarise the holding of this opinion in at most three sentences.\n\n"
    "OPINION:\n{text}"
)

_WHITESPACE_RE = re.compile(r"\s+")


def _html_to_text(html: str) -> str:
    """Best-effort tag strip for the ``html_with_citations`` fallback body."""
    try:
        from lxml import html as lxml_html

        return str(lxml_html.fromstring(html).text_content())
    except Exception:  # pragma: no cover - malformed markup only
        return re.sub(r"<[^>]+>", " ", html)


def derive_holding_summary(text: str, *, is_html: bool = False) -> str | None:
    """Return a deterministic opinion excerpt for ``:Case.holding_summary``.

    BL-20260810-19: the field is indexed for fulltext and rendered as the
    retrieval snippet, but nothing populated it, so every passage degraded to
    "(no holding summary stored)". This is the excerpt half of the item's
    "populate it (or fall back to a stored opinion excerpt)" — purely
    rule-based, so the extractor stays deterministic and free of a per-document
    vendor call. Callers label it ``holding_summary_kind="excerpt"`` so a
    downstream prompt can tell an excerpt from a real holding summary and not
    read a syllabus header as the court's holding.

    >>> derive_holding_summary("")  is None
    True
    """
    if not text or not text.strip():
        return None
    body = _html_to_text(text) if is_html else text
    paragraphs = [
        _WHITESPACE_RE.sub(" ", para).strip()
        for para in re.split(r"\n\s*\n", body)
        if para.strip()
    ]
    paragraphs = [p for p in paragraphs if p]
    if not paragraphs:
        return None
    chosen = next(
        (p for p in paragraphs if len(p) >= _MIN_PARAGRAPH_CHARS), paragraphs[0]
    )
    if len(chosen) <= HOLDING_EXCERPT_MAX_CHARS:
        return chosen
    cut = chosen[:HOLDING_EXCERPT_MAX_CHARS]
    if " " in cut:
        cut = cut[: cut.rindex(" ")]
    return f"{cut.rstrip()}…"
