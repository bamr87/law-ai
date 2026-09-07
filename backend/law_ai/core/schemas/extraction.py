"""Pydantic models for ingestion extraction results.

T-001 from specs/001-ingest-courtlistener-opinions.

Used by `IngestionScout` to return structured, audited output from any
data-source ingestion pass. All confidence values are 0..1.
"""

from __future__ import annotations

from datetime import datetime, UTC
from typing import Literal

from pydantic import BaseModel, Field

#: How ``:Case.holding_summary`` came to exist (BL-20260810-19). An excerpt is
#: verbatim opinion text chosen by rule; a summary is prose written by an
#: audited model pass. The distinction is load-bearing: an excerpt may be a
#: syllabus header rather than the holding, and a prompt must be able to say so.
HoldingSummaryKind = Literal["excerpt", "summary"]

#: Coarse appellate outcomes recorded on a ``:Case`` (BL-20260803-01).
Disposition = Literal[
    "affirmed",
    "reversed",
    "remanded",
    "dismissed",
    "vacated",
    "other",
]

#: Coarse party role that prevailed. Deliberately a *type*, not a name: the
#: graph records who won structurally, never a natural-person identification.
PrevailingPartyType = Literal[
    "appellant",
    "appellee",
    "plaintiff",
    "defendant",
    "government",
    "mixed",
]


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
    target_statute_section_id: str | None = Field(
        default=None,
        description=(
            "`StatuteSection.id` this citation resolves to, when the citation "
            "is statutory and that section is already in the graph "
            "(BL-20260509-07). Like `target_case_id` this is written by the "
            "resolver, never by the extractor: an id here means the node "
            "exists, so a `CITES_STATUTE` edge can be merged."
        ),
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
    holding_summary_kind: HoldingSummaryKind | None = Field(
        default=None,
        description=(
            "Provenance of `holding_summary`: 'excerpt' when it is a "
            "deterministic slice of the opinion body, 'summary' when an "
            "audited LLM pass wrote it. None when no summary is stored. "
            "Downstream prompts must not read an excerpt as the court's "
            "holding (BL-20260810-19)."
        ),
    )

    # Outcome metadata (constitution §13 / ADR 0004 P3 "surface who prevailed").
    # Both are nullable and MUST stay null when the source record is silent —
    # a disposition is never inferred by an LLM or guessed from prose.
    disposition: Disposition | None = Field(
        default=None,
        description=(
            "Coarse outcome of the appeal, mapped deterministically from the "
            "source record's own disposition text; None when the record is "
            "silent or the text does not map cleanly."
        ),
    )
    prevailing_party_type: PrevailingPartyType | None = Field(
        default=None,
        description=(
            "Coarse party role that prevailed, derived only when the "
            "disposition makes it unambiguous; None otherwise."
        ),
    )

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
