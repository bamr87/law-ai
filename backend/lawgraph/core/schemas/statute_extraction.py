"""Pydantic models for statute-tree extraction (spec 016 T-001).

`StatuteScout.extract` returns a `StatuteExtraction` carrying the full
Jurisdiction → Code → Statute → Section tree it parsed from a single
upstream document (e.g. one CRS title page on Justia).

Statute extractions are tree-shaped (one statute, many sections) so they
do **not** reuse `ExtractionResult` from spec 001 — that schema is
opinion-shaped. Both schemas independently satisfy constitution §4 by
embedding the provenance fields on every persisted node.
"""

from __future__ import annotations

from datetime import date, datetime, UTC

from pydantic import BaseModel, ConfigDict, Field

from .legal_documents import JurisdictionLevel


class StatuteSectionPayload(BaseModel):
    """One section parsed from a statute / title page.

    Mirrors the spec-015 `StatuteSection` Neo4j label one-for-one. Carries
    its own confidence score so the scout can route per-section to commit
    or quarantine.
    """

    model_config = ConfigDict(extra="forbid")

    id: str = Field(..., description="Stable id, e.g. us-co/crs/18-3-102")
    citation: str = Field(
        ..., description="Bluebook-style citation, e.g. C.R.S. § 18-3-102"
    )
    heading: str
    text: str
    effective_from: date | None = None
    confidence: float = Field(..., ge=0.0, le=1.0)


class StatuteExtraction(BaseModel):
    """Full extraction payload for one statute / title document.

    The `jurisdiction_*`, `code_*`, and `statute_*` fields are administrative
    metadata for the structural anchors that `commit_statute_extraction`
    MERGEs alongside the section list.
    """

    model_config = ConfigDict(extra="forbid")

    # Jurisdiction
    jurisdiction_code: str = Field(..., description="e.g. us-co")
    jurisdiction_name: str = Field(..., description="e.g. Colorado")
    jurisdiction_level: JurisdictionLevel = "state"

    # Code
    code_id: str = Field(..., description="e.g. us-co/crs")
    code_title: str = Field(..., description="e.g. Colorado Revised Statutes")

    # Statute (the title document we parsed)
    statute_id: str = Field(..., description="e.g. us-co/crs/title-18")
    statute_title: str = Field(..., description="e.g. Title 18 — Criminal Code")
    statute_citation: str | None = None

    # Sections
    sections: list[StatuteSectionPayload] = Field(default_factory=list)

    # Aggregate confidence (mean of section confidences) used for
    # provenance.log_agent_call summary.
    confidence: float = Field(..., ge=0.0, le=1.0)

    # Provenance (constitution §4) — applied to every MERGEd node.
    source: str = "colorado_statutes"
    source_url: str | None = None
    ingest_timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    agent_version: str = "0.1.0"

    def high_confidence_sections(
        self, threshold: float = 0.7
    ) -> list[StatuteSectionPayload]:
        """Return the sections at or above the HITL threshold (commit set)."""
        return [s for s in self.sections if s.confidence >= threshold]

    def low_confidence_sections(
        self, threshold: float = 0.7
    ) -> list[StatuteSectionPayload]:
        """Return the sections below the HITL threshold (quarantine set)."""
        return [s for s in self.sections if s.confidence < threshold]
