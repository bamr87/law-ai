"""Unit tests for ExtractionResult / Citation / Entity (T-001)."""

from datetime import datetime, UTC

import pytest

from law_ai.core.schemas.extraction import Citation, Entity, ExtractionResult


def test_extraction_result_defaults_provenance() -> None:
    result = ExtractionResult(
        case_id="abc-1",
        title="Foo v. Bar",
        confidence=0.81,
    )
    assert result.source == "courtlistener"
    assert result.agent_version == "0.1.0"
    assert isinstance(result.ingest_timestamp, datetime)
    assert result.ingest_timestamp.tzinfo == UTC
    assert result.is_high_confidence()


def test_extraction_result_low_confidence_flag() -> None:
    result = ExtractionResult(case_id="x", title="t", confidence=0.55)
    assert not result.is_high_confidence()
    assert result.is_high_confidence(threshold=0.5)


def test_confidence_bounds_enforced() -> None:
    with pytest.raises(ValueError):
        ExtractionResult(case_id="x", title="t", confidence=1.2)
    with pytest.raises(ValueError):
        ExtractionResult(case_id="x", title="t", confidence=-0.1)


def test_citation_and_entity_models_minimal() -> None:
    c = Citation(text="410 U.S. 113", normalized="410 u.s. 113")
    e = Entity(text="Justice Blackmun", label="JUDGE")
    assert c.target_case_id is None
    assert e.label == "JUDGE"
