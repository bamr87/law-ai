"""Pydantic models for municipal-ordinance extraction (BL-20260509-05).

The `Ordinance` / `OrdinanceSection` labels were declared by spec 015 and
indexed by migrations 005 and 007, but nothing ever produced one: spec 016
scoped Denver ordinance ingestion out of the Colorado-statutes MVP ("spec
016.b"), and no spec ever picked it up. This is the payload half of that work.

Deliberately a sibling of `statute_extraction`, not a reuse of it. The trees
are the same shape (one document, many sections) but the vocabulary is not —
an ordinance belongs to a *municipality*, hangs off a chapter rather than a
title, and cites as `D.R.M.C. § 38-31`. Collapsing the two would mean a
`StatuteExtraction` whose "statute" is a chapter of a city code, which reads
as a legal claim the data does not support.

Both schemas independently satisfy constitution §4 by embedding the
provenance fields carried onto every persisted node.
"""

from __future__ import annotations

from datetime import UTC, date, datetime

from pydantic import BaseModel, ConfigDict, Field

from .legal_documents import JurisdictionLevel


class OrdinanceSectionPayload(BaseModel):
    """One section parsed from a municipal code chapter.

    Mirrors the spec-015 `OrdinanceSection` Neo4j label one-for-one, and
    carries its own confidence so the scout can route per-section.
    """

    model_config = ConfigDict(extra="forbid")

    id: str = Field(..., description="Stable id, e.g. us-co-denver/dmc/38-31")
    citation: str = Field(
        ..., description="Bluebook-style citation, e.g. D.R.M.C. § 38-31"
    )
    heading: str
    text: str
    effective_from: date | None = None
    #: The "(Ord. No. 342-05, § 1, 5-31-05)" trailer municipal codes print
    #: under each section. Kept verbatim: it is the amendment history, and
    #: paraphrasing it would destroy the only pointer back to the enacting
    #: ordinance.
    history_note: str = ""
    confidence: float = Field(..., ge=0.0, le=1.0)


class OrdinanceExtraction(BaseModel):
    """Full extraction payload for one municipal-code chapter.

    The `jurisdiction_*` and `ordinance_*` fields are administrative metadata
    for the structural anchors `commit_ordinance_extraction` MERGEs alongside
    the section list.
    """

    model_config = ConfigDict(extra="forbid")

    # Jurisdiction (a municipality, hence level="municipal")
    jurisdiction_code: str = Field(..., description="e.g. us-co-denver")
    jurisdiction_name: str = Field(..., description="e.g. Denver, Colorado")
    jurisdiction_level: JurisdictionLevel = "municipal"

    # Ordinance (the chapter document we parsed)
    ordinance_id: str = Field(..., description="e.g. us-co-denver/dmc/chapter-38")
    ordinance_title: str = Field(
        ..., description="e.g. Chapter 38 — Law Enforcement, Fire Protection"
    )
    ordinance_citation: str | None = Field(
        default=None, description="e.g. D.R.M.C. ch. 38"
    )

    sections: list[OrdinanceSectionPayload] = Field(default_factory=list)

    #: Mean of the section confidences; used for the agent-call summary.
    confidence: float = Field(..., ge=0.0, le=1.0)

    # Provenance (constitution §4) — applied to every MERGEd node.
    source: str = "denver_municipal_code"
    source_url: str | None = None
    ingest_timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    agent_version: str = "0.1.0"

    def high_confidence_sections(
        self, threshold: float = 0.7
    ) -> list[OrdinanceSectionPayload]:
        """Sections at or above the HITL threshold (the commit set)."""
        return [s for s in self.sections if s.confidence >= threshold]

    def low_confidence_sections(
        self, threshold: float = 0.7
    ) -> list[OrdinanceSectionPayload]:
        """Sections below the HITL threshold (the quarantine set)."""
        return [s for s in self.sections if s.confidence < threshold]
