"""OrdinanceScout — municipal-code ingestion crew (BL-20260509-05).

The third scout, alongside :class:`~law_ai.ingestionapp.services.scout.IngestionScout`
(opinions) and :class:`~law_ai.ingestionapp.services.statute_scout.StatuteScout`
(state statutes). It parses one municipal-code chapter, commits the sections
that clear the confidence threshold, and quarantines the rest with
``kind="ordinance_section"`` — the spec-015 discriminator that had been
declared for two specs without a producer.

Constitution §12 I1 holds: the scout is the only writer of `:Ordinance` /
`:OrdinanceSection` nodes, and the adapter that feeds it never touches Neo4j.

Approval path
-------------
:meth:`commit_section` is the counterpart of ``StatuteScout.commit_section``
and is what ``approval._commit_by_kind`` calls for an approved
``ordinance_section`` row. Without it an approved ordinance could never reach
the graph, which is exactly the trap BL-20260811-03 found for statutes.
"""

from __future__ import annotations

import json
import logging
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from law_ai.core.neo4j.driver import get_neo4j_driver
from law_ai.core.neo4j.ordinance_queries import commit_ordinance_extraction
from law_ai.core.provenance import provenance
from law_ai.core.schemas.ordinance_extraction import (
    OrdinanceExtraction,
    OrdinanceSectionPayload,
)
from law_ai.ingestionapp.quarantine_kinds import KIND_ORDINANCE_SECTION
from law_ai.ingestionapp.services.denver_municipal_code import parse_chapter_html

logger = logging.getLogger("law_ai.ingestion.ordinance_scout")

CONFIDENCE_THRESHOLD = 0.7
PENDING_REVIEW_DIR = Path("backend/var/pending_review")

#: Administrative metadata a quarantined section needs before it can be
#: rehydrated into a committable extraction. Learned from BL-20260811-03:
#: statute rows shipped without it and became permanently uncommittable, so
#: the ordinance envelope carries it from the first line of code.
REQUIRED_COMMIT_METADATA = (
    "jurisdiction_code",
    "jurisdiction_name",
    "ordinance_id",
    "ordinance_title",
)


def section_envelope(
    extraction: OrdinanceExtraction, section: OrdinanceSectionPayload
) -> dict[str, Any]:
    """Self-contained quarantine payload for one ordinance section."""
    return {
        "section": json.loads(section.model_dump_json()),
        "ordinance_id": extraction.ordinance_id,
        "ordinance_title": extraction.ordinance_title,
        "ordinance_citation": extraction.ordinance_citation,
        "jurisdiction_code": extraction.jurisdiction_code,
        "jurisdiction_name": extraction.jurisdiction_name,
        "jurisdiction_level": extraction.jurisdiction_level,
        "source": extraction.source,
        "source_url": extraction.source_url,
        "agent_version": extraction.agent_version,
    }


class OrdinanceScout:
    """Concrete agent for ingesting municipal-code chapter HTML."""

    name = "OrdinanceScout"
    description = "Parses municipal-code HTML into audited Neo4j ordinance nodes"
    #: The upstream host's terms are restrictive and its markup is
    #: JS-rendered, so a person looks at everything this scout produces
    #: (constitution §5). ``run_and_commit`` honours this by default.
    requires_human_approval = True
    agent_version = "0.1.0"

    def __init__(self, *, threshold: float = CONFIDENCE_THRESHOLD) -> None:
        self._threshold = threshold

    # ------------------------------------------------------------------
    # Extraction
    # ------------------------------------------------------------------
    def extract(self, payload: dict[str, Any]) -> OrdinanceExtraction:
        """Parse a ``{"chapter", "html", "source_url"?}`` payload."""
        start = time.time()
        chapter = payload.get("chapter")
        html = payload.get("html")
        if not chapter or not html:
            raise ValueError("ordinance payload requires 'chapter' and 'html'")

        extraction = parse_chapter_html(
            str(chapter), str(html), source_url=payload.get("source_url")
        )
        extraction.agent_version = self.agent_version

        provenance.log_agent_call(
            agent_name=self.name,
            input_data={"chapter": str(chapter)},
            output_data={
                "n_sections": len(extraction.sections),
                "confidence": extraction.confidence,
            },
            model="rule-based+lxml",
            latency_ms=(time.time() - start) * 1000,
            confidence=extraction.confidence,
            sources=([{"url": extraction.source_url}] if extraction.source_url else []),
        )
        return extraction

    # ------------------------------------------------------------------
    # Commit
    # ------------------------------------------------------------------
    async def run_and_commit(
        self, payload: dict[str, Any], *, force_quarantine: bool | None = None
    ) -> dict[str, Any]:
        """Extract, then commit or quarantine every section.

        *force_quarantine* defaults to this scout's ``requires_human_approval``,
        so the safe posture is the one you get by not thinking about it. An
        operator working from a source they are licensed to bulk-ingest can
        pass ``False`` explicitly, and the per-section confidence gate then
        applies as it does for statutes.
        """
        extraction = self.extract(payload)
        return await self.commit(extraction, force_quarantine=force_quarantine)

    async def commit(
        self,
        extraction: OrdinanceExtraction,
        *,
        force_quarantine: bool | None = None,
    ) -> dict[str, Any]:
        """Commit a (possibly pre-trimmed) extraction."""
        quarantine_all = (
            self.requires_human_approval
            if force_quarantine is None
            else force_quarantine
        )
        if quarantine_all:
            committed: list[OrdinanceSectionPayload] = []
            pending = list(extraction.sections)
        else:
            committed = extraction.high_confidence_sections(self._threshold)
            pending = extraction.low_confidence_sections(self._threshold)

        edges = 0
        if committed:
            driver = get_neo4j_driver()
            async with driver.session() as session:
                edges = await commit_ordinance_extraction(
                    session, extraction, threshold=self._threshold
                )
            provenance.log_graph_query(
                cypher="ingestion.commit_ordinance",
                params={
                    "ordinance_id": extraction.ordinance_id,
                    "sections": len(committed),
                },
                result_count=len(committed) + edges,
                latency_ms=0.0,
            )

        for section in pending:
            await self._quarantine(extraction, section)

        return {
            "ordinance_id": extraction.ordinance_id,
            "committed": len(committed),
            "pending": len(pending),
            "sections_total": len(extraction.sections),
            "edges": edges,
        }

    async def commit_section(
        self, payload: dict[str, Any], *, force_commit: bool = True
    ) -> dict[str, Any]:
        """Commit ONE quarantined ordinance section after human approval.

        Rehydrates a single-section extraction from the envelope
        :func:`section_envelope` wrote and commits it with ``threshold=0.0``:
        the human approval *is* the gate, so the confidence score that
        quarantined the row must not re-fire.
        """
        section_data = payload.get("section")
        if not isinstance(section_data, dict):
            raise ValueError("ordinance quarantine payload has no 'section'")
        missing = [key for key in REQUIRED_COMMIT_METADATA if not payload.get(key)]
        if missing:
            raise ValueError(
                "ordinance row lacks jurisdiction/chapter metadata "
                f"({', '.join(missing)}); re-ingest the chapter to commit it"
            )

        section = OrdinanceSectionPayload.model_validate(section_data)
        extraction = OrdinanceExtraction(
            jurisdiction_code=str(payload["jurisdiction_code"]),
            jurisdiction_name=str(payload["jurisdiction_name"]),
            jurisdiction_level=payload.get("jurisdiction_level") or "municipal",
            ordinance_id=str(payload["ordinance_id"]),
            ordinance_title=str(payload["ordinance_title"]),
            ordinance_citation=payload.get("ordinance_citation"),
            sections=[section],
            confidence=section.confidence,
            source=str(payload.get("source") or "denver_municipal_code"),
            source_url=payload.get("source_url"),
            agent_version=str(payload.get("agent_version") or self.agent_version),
        )

        threshold = 0.0 if force_commit else self._threshold
        driver = get_neo4j_driver()
        async with driver.session() as session:
            edges = await commit_ordinance_extraction(
                session, extraction, threshold=threshold
            )
        provenance.log_graph_query(
            cypher="ingestion.commit_ordinance_section",
            params={
                "section_id": section.id,
                "ordinance_id": extraction.ordinance_id,
            },
            result_count=1 + edges,
            latency_ms=0.0,
        )
        return {
            "section_id": section.id,
            "case_id": section.id,  # keyed the same way as the other paths
            "committed": True,
            "pending": False,
            "confidence": section.confidence,
            "edges": edges,
        }

    # ------------------------------------------------------------------
    # HITL quarantine
    # ------------------------------------------------------------------
    async def _quarantine(
        self, extraction: OrdinanceExtraction, section: OrdinanceSectionPayload
    ) -> None:
        """Send a section to the HITL queue (Celery, JSONL as the fallback)."""
        try:
            self._quarantine_via_celery(extraction, section)
        except Exception as exc:
            logger.warning(
                "ordinance pending_review celery dispatch failed (%s); using JSONL",
                type(exc).__name__,
            )
            self._quarantine_jsonl(extraction, section)

        provenance.log_agent_call(
            agent_name=self.name,
            input_data={"section_id": section.id},
            output_data={"pending": True, "kind": KIND_ORDINANCE_SECTION},
            model="n/a",
            latency_ms=0.0,
            confidence=section.confidence,
        )

    def _quarantine_via_celery(
        self, extraction: OrdinanceExtraction, section: OrdinanceSectionPayload
    ) -> None:
        """Dispatch with ``kind=ordinance_section``; imported lazily."""
        from law_ai.ingestionapp.tasks import quarantine_extraction

        task_payload: dict[str, Any] = {
            "id": section.id,
            "source": extraction.source,
            "kind": KIND_ORDINANCE_SECTION,
            "confidence": section.confidence,
            "reason": (
                "source_requires_human_approval"
                if self.requires_human_approval
                else "low_confidence"
            ),
            "payload": section_envelope(extraction, section),
        }
        quarantine_extraction.delay(task_payload)

    def _quarantine_jsonl(
        self, extraction: OrdinanceExtraction, section: OrdinanceSectionPayload
    ) -> None:
        """Append the section to a daily JSONL file (fallback only)."""
        PENDING_REVIEW_DIR.mkdir(parents=True, exist_ok=True)
        path = PENDING_REVIEW_DIR / f"{datetime.now(UTC):%Y-%m-%d}.jsonl"
        with path.open("a", encoding="utf-8") as fh:
            fh.write(
                json.dumps(
                    {
                        "id": section.id,
                        "source": extraction.source,
                        "kind": KIND_ORDINANCE_SECTION,
                        "confidence": section.confidence,
                        "payload": section_envelope(extraction, section),
                    },
                    default=str,
                )
                + "\n"
            )
