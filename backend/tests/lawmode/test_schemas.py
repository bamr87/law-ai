"""lawmode finding and report schemas (spec 057 FR-1).

Rewritten from ``lawmode/tests/test_models.py`` against
``law_ai.lawmode.schemas``. The blocking-verdict tests of the original are
replaced by the human-review ones: the port has no pass/fail.
"""

from __future__ import annotations

import json
from datetime import UTC

import pytest

from law_ai.lawmode.schemas import (
    DISCLAIMER_NOTICE,
    ReviewResult,
    ReviewStatus,
    Risk,
    Severity,
)

pytestmark = pytest.mark.unit


def _risk(severity: Severity = Severity.CRITICAL, **overrides: object) -> Risk:
    fields: dict[str, object] = {
        "severity": severity,
        "title": "Test Risk",
        "law": "Test Law",
        "description": "Test description",
        "mitigation": "Test mitigation",
    }
    fields.update(overrides)
    return Risk.model_validate(fields)


def test_severity_values_are_the_ones_the_lawmode_report_always_used() -> None:
    assert [s.value for s in Severity] == ["Critical", "High", "Medium", "Low"]


def test_risk_creation() -> None:
    risk = _risk()

    assert risk.severity == Severity.CRITICAL
    assert risk.title == "Test Risk"
    assert risk.id.startswith("R")
    assert risk.jurisdiction is None and risk.citation is None


def test_risk_ids_do_not_collide() -> None:
    assert len({_risk().id for _ in range(200)}) == 200


def test_a_risk_nobody_ran_through_the_policy_is_not_treated_as_cleared() -> None:
    assert _risk(Severity.LOW).review_status == ReviewStatus.UNREVIEWED


def test_citation_must_be_a_url() -> None:
    with pytest.raises(ValueError):
        _risk(citation="GDPR Art. 32")


def test_review_result() -> None:
    review = ReviewResult(jurisdictions=["US", "EU"], domain="fintech")

    assert len(review.jurisdictions) == 2
    assert review.domain == "fintech"
    assert not review.has_critical_risks()
    assert review.timestamp.tzinfo is UTC


def test_review_result_with_risks() -> None:
    review = ReviewResult(risks=[_risk(Severity.CRITICAL)])

    assert review.has_critical_risks()


def test_a_high_risk_is_not_a_critical_one() -> None:
    assert not ReviewResult(risks=[_risk(Severity.HIGH)]).has_critical_risks()


def test_human_approval_follows_the_findings_that_need_review() -> None:
    advisory = _risk(Severity.LOW, review_status=ReviewStatus.NOT_REQUIRED)
    gated = _risk(Severity.HIGH, review_status=ReviewStatus.UNREVIEWED)
    queued = _risk(Severity.CRITICAL, review_status=ReviewStatus.AWAITING_REVIEW)

    assert ReviewResult(risks=[advisory]).human_approval_required is False
    review = ReviewResult(risks=[advisory, gated, queued])
    assert review.risks_requiring_review() == [gated, queued]
    assert review.human_approval_required is True


def test_a_report_has_no_pass_or_fail() -> None:
    """The old ``has_blocking_risks`` let a model's severity fail a merge."""
    review = ReviewResult(risks=[_risk(Severity.CRITICAL)])

    assert not hasattr(review, "has_blocking_risks")
    assert set(review.model_dump(mode="json")) == {
        "review_id",
        "commit_sha",
        "timestamp",
        "jurisdictions",
        "domain",
        "risks",
        "history",
        "signature",
        "metadata",
        "unparsed_findings",
        "disclaimer",
        "human_approval_required",
    }


def test_findings_that_could_not_be_read_ask_for_a_human() -> None:
    """An incomplete report is not a clean one, even with nothing listed."""
    review = ReviewResult(unparsed_findings=1)

    assert review.risks == []
    assert review.human_approval_required is True
    assert review.model_dump(mode="json")["human_approval_required"] is True


def test_the_outcome_is_serialised_with_the_report() -> None:
    gated = _risk(Severity.HIGH, review_status=ReviewStatus.UNREVIEWED)

    assert ReviewResult().model_dump(mode="json")["human_approval_required"] is False
    assert (
        json.loads(ReviewResult(risks=[gated]).model_dump_json())[
            "human_approval_required"
        ]
        is True
    )


def test_no_auto_fix_patch_is_carried() -> None:
    assert "auto_fix_patch" not in Risk.model_fields


def test_every_serialised_report_carries_the_disclaimer() -> None:
    dumped = ReviewResult().model_dump(mode="json")

    assert dumped["disclaimer"] == DISCLAIMER_NOTICE
    assert "Not legal advice" in dumped["disclaimer"]
    assert "not a statement that the code is compliant" in dumped["disclaimer"]


def test_report_round_trips_through_json() -> None:
    review = ReviewResult(
        commit_sha="abc123",
        jurisdictions=["EU"],
        risks=[
            _risk(
                Severity.HIGH,
                jurisdiction="EU",
                citation="https://eur-lex.europa.eu/eli/reg/2016/679/oj",
                line_start=3,
                line_end=5,
                file_path="app.py",
            )
        ],
    )

    restored = ReviewResult.model_validate_json(review.model_dump_json())

    assert restored == review
    assert restored.risks[0].severity is Severity.HIGH
