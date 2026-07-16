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
import time
from datetime import datetime, UTC
from pathlib import Path
from typing import Any

from law_ai.core.provenance import provenance
from law_ai.core.neo4j.driver import get_neo4j_driver
from law_ai.core.neo4j.queries import commit_extraction
from law_ai.core.neo4j.citation_resolver import densify_extraction
from law_ai.core.schemas.extraction import Citation, Entity, ExtractionResult

logger = logging.getLogger("law_ai.ingestion.scout")

# Confidence threshold below which extractions are quarantined for human review
# (specs/001 NFR-HITL-1).
CONFIDENCE_THRESHOLD = 0.7

# JSONL fallback used when Postgres is unreachable so the dev loop stays green.
PENDING_REVIEW_DIR = Path("backend/var/pending_review")


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
        """
        start = time.time()
        text = payload.get("plain_text") or payload.get("html_with_citations") or ""
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
        entities = _extract_entities(payload)
        confidence = _score(text=text, n_citations=len(citations), title=title)

        result = ExtractionResult(
            case_id=case_id,
            title=title,
            court=court,
            decided_at=decided_at,
            citations=citations,
            entities=entities,
            holding_summary=None,  # Reserved for future LLM pass.
            confidence=confidence,
            source="courtlistener",
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

    # ------------------------------------------------------------------
    # Commit
    # ------------------------------------------------------------------
    async def run_and_commit(
        self, payload: dict[str, Any], *, force_quarantine: bool = False
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

        Returns a small summary dict suitable for the CLI run report.
        """
        result = self.extract(payload)
        if force_quarantine or not result.is_high_confidence(self._threshold):
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
        """
        try:
            self._quarantine_via_celery(result, payload)
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


def _extract_citations(text: str) -> list[Citation]:
    """Run Eyecite over the body text, returning unique normalized citations."""
    if not text:
        return []
    try:
        from eyecite import get_citations  # type: ignore[import-untyped]
    except Exception:  # pragma: no cover — eyecite is a hard dep, but guard anyway
        return []

    seen: dict[str, Citation] = {}
    for cit in get_citations(text):
        raw = getattr(cit, "matched_text", None)
        if callable(raw):
            raw = raw()
        if not raw:
            raw = str(cit)
        normalized = " ".join(str(raw).split()).lower()
        if normalized in seen:
            continue
        seen[normalized] = Citation(text=str(raw), normalized=normalized)
    return list(seen.values())


def _extract_entities(payload: dict[str, Any]) -> list[Entity]:
    """Lightweight entity pull from structured fields. Blackstone NER is a follow-up."""
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
