"""Pydantic models for ingestion extraction results.

T-001 from specs/001-ingest-courtlistener-opinions.

Used by `IngestionScout` to return structured, audited output from any
data-source ingestion pass. All confidence values are 0..1.
"""

from __future__ import annotations

from datetime import datetime, UTC
from typing import Literal

from pydantic import BaseModel, Field


class Citation(BaseModel):
    """A single citation extracted from an opinion's text."""

    text: str = Field(..., description="Raw citation string as it appeared in source")
    normalized: str = Field(
        ..., description="Stable, deduplicatable form (used as Neo4j key)"
    )
    target_case_id: str | None = Field(
        default=None,
        description="CourtListener (or other source) ID of the cited case if known",
    )


class Entity(BaseModel):
    """A named entity (party, judge, statute) extracted from the text."""

    text: str
    label: Literal["PARTY", "JUDGE", "STATUTE", "COURT", "OTHER"] = "OTHER"


class ExtractionResult(BaseModel):
    """Structured output of `IngestionScout.extract`.

    Carries provenance fields required by docs/constitution.md §4 so the
    caller can persist them on the resulting Neo4j node.
    """

    case_id: str = Field(
        ..., description="Stable source id, e.g. CourtListener opinion id"
    )
    title: str
    court: str | None = None
    decided_at: datetime | None = None

    citations: list[Citation] = Field(default_factory=list)
    entities: list[Entity] = Field(default_factory=list)
    holding_summary: str | None = None

    aliases: list[str] = Field(
        default_factory=list,
        description="Canonical normalized citation forms this case is known by",
    )

    confidence: float = Field(..., ge=0.0, le=1.0)

    # Provenance (constitution §4)
    source: str = Field(default="courtlistener")
    source_url: str | None = None
    ingest_timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    agent_version: str = "0.1.0"

    def is_high_confidence(self, threshold: float = 0.7) -> bool:
        """Return True when this result clears the HITL threshold (NFR-HITL-1)."""
        return self.confidence >= threshold
