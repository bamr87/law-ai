"""Pydantic v2 domain models for legal-corpus nodes (spec 015 FR-5).

These mirror the Neo4j labels declared in
``backend/law_ai/core/neo4j/migrations/003_statute_constraints.cypher`` ..
``007_fulltext_indexes.cypher``. Every model carries the constitution §4
provenance fields via :class:`LegalProvenance`, the same way ``ExtractionResult``
in :mod:`law_ai.core.schemas.extraction` does for opinions.

No write paths use these models yet — they exist so downstream specs
(016 ingestion, 018 retrieval, 019 derived corpus) can pass typed payloads.
"""

from __future__ import annotations

from datetime import date, datetime, UTC
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

JurisdictionLevel = Literal["federal", "state", "municipal", "tribal", "international"]
DerivedKind = Literal["analysis", "summary", "brief", "holding"]


class LegalProvenance(BaseModel):
    """Mandatory provenance fields per docs/constitution.md §4.

    Every node persisted to Neo4j must carry these so downstream retrieval
    can audit *where* a fact came from and *how confident* the producer was.
    """

    model_config = ConfigDict(extra="forbid")

    source: str = Field(..., description="Stable source identifier, e.g. 'crs'")
    source_url: str | None = Field(default=None, description="Canonical source URL")
    confidence: float = Field(
        ..., ge=0.0, le=1.0, description="Producer confidence 0..1"
    )
    ingest_timestamp: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="UTC moment the producer emitted this payload",
    )
    agent_version: str = Field(..., description="Producer/agent version, e.g. '0.1.0'")


class Jurisdiction(LegalProvenance):
    """A legal jurisdiction (federal, state, or municipal)."""

    code: str = Field(..., description="Stable code, e.g. 'us-co' or 'us-co-denver'")
    name: str
    level: JurisdictionLevel


class Court(LegalProvenance):
    """A court of record."""

    id: str
    name: str
    jurisdiction_code: str = Field(..., description="FK -> Jurisdiction.code")


class Code(LegalProvenance):
    """A statutory code (e.g. Colorado Revised Statutes)."""

    id: str = Field(..., description="e.g. 'us-co/crs'")
    title: str
    jurisdiction_code: str


class Statute(LegalProvenance):
    """A statute (a Title within a Code, or a standalone act)."""

    id: str = Field(..., description="e.g. 'us-co/crs/title-18'")
    code_id: str = Field(..., description="FK -> Code.id")
    title: str
    citation: str | None = None
    effective_from: date | None = None
    effective_to: date | None = None


class StatuteSection(LegalProvenance):
    """A single section of a statute — the unit of retrieval."""

    id: str = Field(..., description="e.g. 'us-co/crs/18-3-102'")
    statute_id: str = Field(..., description="FK -> Statute.id")
    citation: str = Field(
        ..., description="Bluebook-style citation, e.g. 'C.R.S. § 18-3-102'"
    )
    heading: str
    text: str
    effective_from: date | None = None
    effective_to: date | None = None


class Ordinance(LegalProvenance):
    """A municipal or county ordinance."""

    id: str
    jurisdiction_code: str
    title: str
    citation: str | None = None
    effective_from: date | None = None
    effective_to: date | None = None


class OrdinanceSection(LegalProvenance):
    """A single section of an ordinance."""

    id: str
    ordinance_id: str
    citation: str
    heading: str
    text: str
    effective_from: date | None = None
    effective_to: date | None = None


class Regulation(LegalProvenance):
    """An administrative regulation (federal CFR, state CCR, etc.)."""

    id: str
    jurisdiction_code: str
    citation: str
    text: str
    effective_from: date | None = None
    effective_to: date | None = None


class DerivedDocument(LegalProvenance):
    """An AI-generated document (analysis, summary, brief, holding).

    Stored as a first-class node so it can be filtered out of any query
    that must return only authoritative primary law (spec 019).
    """

    id: str
    kind: DerivedKind
    trace_id: str = Field(
        ..., description="audit.AuditEvent.trace_id of the producing run"
    )
    body: str
    is_hitl_approved: bool = Field(
        default=False,
        description="Set by the HITL flow once a reviewer has approved this output",
    )
    source_node_ids: list[str] = Field(
        default_factory=list,
        description="ids of the Case / StatuteSection / etc. this was derived from",
    )


__all__ = [
    "Code",
    "Court",
    "DerivedDocument",
    "DerivedKind",
    "Jurisdiction",
    "JurisdictionLevel",
    "LegalProvenance",
    "Ordinance",
    "OrdinanceSection",
    "Regulation",
    "Statute",
    "StatuteSection",
]
