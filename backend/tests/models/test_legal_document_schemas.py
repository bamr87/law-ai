"""Pydantic schema tests for spec 015 legal-corpus models (T-005, AC-2)."""

from __future__ import annotations

from datetime import date, datetime

import pytest
from pydantic import ValidationError

from law_ai.core.schemas.legal_documents import (
    Code,
    Court,
    DerivedDocument,
    Jurisdiction,
    Ordinance,
    OrdinanceSection,
    Regulation,
    Statute,
    StatuteSection,
)

PROV = {
    "source": "crs",
    "source_url": "https://leg.colorado.gov/crs/18-3-102",
    "confidence": 0.9,
    "agent_version": "0.1.0",
}


def test_jurisdiction_minimum_valid() -> None:
    j = Jurisdiction(code="us-co", name="Colorado", level="state", **PROV)
    assert j.code == "us-co"
    assert j.level == "state"
    assert isinstance(j.ingest_timestamp, datetime)


def test_court_requires_jurisdiction_code() -> None:
    Court(
        id="co-supreme",
        name="Colorado Supreme Court",
        jurisdiction_code="us-co",
        **PROV,
    )
    with pytest.raises(ValidationError):
        Court(id="x", name="x", **PROV)  # type: ignore[call-arg]


def test_code_and_statute_and_section_chain() -> None:
    Code(
        id="us-co/crs",
        title="Colorado Revised Statutes",
        jurisdiction_code="us-co",
        **PROV,
    )
    Statute(
        id="us-co/crs/title-18",
        code_id="us-co/crs",
        title="Criminal Code",
        effective_from=date(1971, 1, 1),
        **PROV,
    )
    s = StatuteSection(
        id="us-co/crs/18-3-102",
        statute_id="us-co/crs/title-18",
        citation="C.R.S. § 18-3-102",
        heading="Murder in the first degree",
        text="A person commits the crime of murder in the first degree if ...",
        **PROV,
    )
    assert s.citation.startswith("C.R.S.")


def test_ordinance_and_ordinance_section() -> None:
    Ordinance(
        id="us-co-denver/dmc/title-38",
        jurisdiction_code="us-co-denver",
        title="Offenses Against Public Order",
        **PROV,
    )
    OrdinanceSection(
        id="us-co-denver/dmc/38-32",
        ordinance_id="us-co-denver/dmc/title-38",
        citation="D.R.M.C. § 38-32",
        heading="Disturbing the peace",
        text="It is unlawful for any person ...",
        **PROV,
    )


def test_regulation_minimum_valid() -> None:
    Regulation(
        id="us-co/ccr/8-1-203",
        jurisdiction_code="us-co",
        citation="8 CCR 1206-1",
        text="Wage protection rules ...",
        **PROV,
    )


def test_derived_document_kind_and_provenance() -> None:
    d = DerivedDocument(
        id="analysis/abc-123",
        kind="analysis",
        trace_id="trace-xyz",
        body="The defendant's argument fails because ...",
        source_node_ids=["us-co/crs/18-3-102", "case-9001"],
        **PROV,
    )
    assert d.kind == "analysis"
    assert d.is_hitl_approved is False
    assert d.source_node_ids == ["us-co/crs/18-3-102", "case-9001"]


def test_confidence_bounds_are_enforced() -> None:
    bad = dict(PROV)
    bad["confidence"] = 1.5
    with pytest.raises(ValidationError):
        Jurisdiction(code="us-co", name="x", level="state", **bad)
    bad["confidence"] = -0.1
    with pytest.raises(ValidationError):
        Jurisdiction(code="us-co", name="x", level="state", **bad)


def test_jurisdiction_level_is_validated() -> None:
    with pytest.raises(ValidationError):
        Jurisdiction(code="us-co", name="x", level="planetary", **PROV)  # type: ignore[arg-type]


def test_derived_document_kind_is_validated() -> None:
    with pytest.raises(ValidationError):
        DerivedDocument(
            id="x",
            kind="rant",  # type: ignore[arg-type]
            trace_id="t",
            body="...",
            **PROV,
        )


def test_provenance_required_fields_missing_raises() -> None:
    with pytest.raises(ValidationError):
        Jurisdiction(code="us-co", name="Colorado", level="state")  # type: ignore[call-arg]
