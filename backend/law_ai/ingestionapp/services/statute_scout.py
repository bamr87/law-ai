"""StatuteScout — concrete Law AI crew for CRS section ingestion (spec 016 T-003).

Mirrors :class:`law_ai.ingestionapp.services.scout.IngestionScout` but operates
on statute/title HTML payloads rather than CourtListener opinions:

* Parse a payload via :func:`law_ai.ingestionapp.services.colorado_statutes.parse_title_html`
  into a :class:`StatuteExtraction`.
* Commit high-confidence sections to Neo4j via
  :func:`law_ai.core.neo4j.statute_queries.commit_statute_extraction`.
* Send low-confidence sections to the spec-015 ``PendingReview`` quarantine
  with ``kind="statute_section"`` (FR-3, FR-4).
* Log every step through ``law_ai.core.provenance`` (NFR-AUDIT-1).
"""

from __future__ import annotations

import json
import logging
import time
from datetime import datetime, UTC
from pathlib import Path
from typing import Any

from law_ai.core.neo4j.driver import get_neo4j_driver
from law_ai.core.neo4j.statute_queries import commit_statute_extraction
from law_ai.core.provenance import provenance
from law_ai.core.schemas.statute_extraction import (
    StatuteExtraction,
    StatuteSectionPayload,
)
from law_ai.ingestionapp.quarantine_kinds import KIND_STATUTE_SECTION
from law_ai.ingestionapp.services.colorado_statutes import parse_title_html

logger = logging.getLogger("law_ai.ingestion.statute_scout")

CONFIDENCE_THRESHOLD = 0.7
PENDING_REVIEW_DIR = Path("backend/var/pending_review")


class StatuteScout:
    """Concrete agent for ingesting U.S. state-statute HTML pages.

    Currently bound to the Colorado Justia HTML structure via
    :func:`parse_title_html`; the surrounding commit / quarantine plumbing
    is source-agnostic and can host additional state parsers later.
    """

    name = "StatuteScout"
    description = "Parses statute HTML into audited Neo4j statute-tree nodes"
    requires_human_approval = False
    agent_version = "0.1.0"

    def __init__(self, *, threshold: float = CONFIDENCE_THRESHOLD) -> None:
        self._threshold = threshold

    # ------------------------------------------------------------------
    # Extraction
    # ------------------------------------------------------------------
    def extract(self, payload: dict[str, Any]) -> StatuteExtraction:
        """Parse a ``{"title_id", "html", "source_url"?}`` payload.

        Stamps the extraction's ``agent_version`` and any caller-provided
        ``source_url`` and emits one ``provenance.log_agent_call``.
        """
        start = time.time()
        title_id = payload.get("title_id")
        html = payload.get("html")
        if not title_id or not html:
            raise ValueError("statute payload requires 'title_id' and 'html'")

        extraction = parse_title_html(
            title_id=str(title_id),
            html=str(html),
            source_url=payload.get("source_url"),
        )
        # Ensure our agent_version stamps the extraction (parser default
        # could drift from the scout).
        extraction.agent_version = self.agent_version
        extraction.ingest_timestamp = extraction.ingest_timestamp or datetime.now(UTC)

        provenance.log_agent_call(
            agent_name=self.name,
            input_data={"title_id": title_id},
            output_data={
                "n_sections": len(extraction.sections),
                "confidence": extraction.confidence,
            },
            model="rule-based+bs4",
            latency_ms=(time.time() - start) * 1000,
            confidence=extraction.confidence,
            sources=([{"url": extraction.source_url}] if extraction.source_url else []),
        )
        return extraction

    # ------------------------------------------------------------------
    # Commit
    # ------------------------------------------------------------------
    async def run_and_commit(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Extract then commit high-confidence sections, quarantining the rest."""
        extraction = self.extract(payload)
        return await self.commit(extraction)

    async def commit(self, extraction: StatuteExtraction) -> dict[str, Any]:
        """Commit a (possibly pre-trimmed) ``StatuteExtraction``.

        Split out from :meth:`run_and_commit` so callers (e.g. the CLI in
        ``backend/scripts/ingest_sample.py``) can extract once, slice
        ``extraction.sections`` to honour ``--limit``, then commit.
        """
        committed = extraction.high_confidence_sections(self._threshold)
        pending = extraction.low_confidence_sections(self._threshold)

        edges = 0
        if committed:
            driver = get_neo4j_driver()
            async with driver.session() as session:
                edges = await commit_statute_extraction(
                    session, extraction, threshold=self._threshold
                )
            provenance.log_graph_query(
                cypher="ingestion.commit_statute",
                params={
                    "statute_id": extraction.statute_id,
                    "sections": len(committed),
                },
                result_count=len(committed) + edges,
                latency_ms=0.0,
            )

        for section in pending:
            await self._quarantine(extraction, section)

        return {
            "title_id": extraction.statute_id,
            "committed": len(committed),
            "pending": len(pending),
            "sections_total": len(extraction.sections),
            "edges": edges,
        }

    # ------------------------------------------------------------------
    # HITL quarantine
    # ------------------------------------------------------------------
    async def _quarantine(
        self, extraction: StatuteExtraction, section: StatuteSectionPayload
    ) -> None:
        """Send a low-confidence section to the HITL queue (Celery + JSONL fallback)."""
        try:
            self._quarantine_via_celery(extraction, section)
        except Exception as exc:
            logger.warning(
                "statute pending_review celery dispatch failed (%s); using JSONL",
                type(exc).__name__,
            )
            self._quarantine_jsonl(extraction, section)

        provenance.log_agent_call(
            agent_name=self.name,
            input_data={"section_id": section.id},
            output_data={"pending": True, "kind": KIND_STATUTE_SECTION},
            model="n/a",
            latency_ms=0.0,
            confidence=section.confidence,
        )

    def _quarantine_via_celery(
        self, extraction: StatuteExtraction, section: StatuteSectionPayload
    ) -> None:
        """Dispatch one section to ``quarantine_extraction`` with ``kind=statute_section``.

        Imported lazily so this module stays importable in environments
        where Celery is not yet configured (mirrors ``IngestionScout``).
        """
        from law_ai.ingestionapp.tasks import quarantine_extraction

        task_payload: dict[str, Any] = {
            "id": section.id,
            "source": extraction.source,
            "kind": KIND_STATUTE_SECTION,
            "confidence": section.confidence,
            "reason": "low_confidence",
            "payload": {
                "section": json.loads(section.model_dump_json()),
                "statute_id": extraction.statute_id,
                "source_url": extraction.source_url,
            },
        }
        quarantine_extraction.delay(task_payload)

    def _quarantine_jsonl(
        self, extraction: StatuteExtraction, section: StatuteSectionPayload
    ) -> None:
        """Append a low-confidence section to a daily JSONL file (fallback only)."""
        PENDING_REVIEW_DIR.mkdir(parents=True, exist_ok=True)
        path = PENDING_REVIEW_DIR / f"{datetime.now(UTC):%Y-%m-%d}.jsonl"
        with path.open("a", encoding="utf-8") as fh:
            fh.write(
                json.dumps(
                    {
                        "id": section.id,
                        "source": extraction.source,
                        "kind": KIND_STATUTE_SECTION,
                        "confidence": section.confidence,
                        "reason": "low_confidence",
                        "payload": {
                            "section": json.loads(section.model_dump_json()),
                            "statute_id": extraction.statute_id,
                            "source_url": extraction.source_url,
                        },
                    },
                    default=str,
                )
                + "\n"
            )
