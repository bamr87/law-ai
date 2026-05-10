"""Unit tests for `quarantine_extraction` Celery task (spec 011 FR-11, AC-5)."""

from __future__ import annotations

import pytest

from lawgraph.audit.models import AuditEvent
from lawgraph.ingestionapp.models import PendingReview
from lawgraph.ingestionapp.tasks import quarantine_extraction


@pytest.mark.django_db
def test_quarantine_extraction_creates_pending_review_and_audit_event() -> None:
    payload = {
        "id": "case-42",
        "source": "courtlistener",
        "confidence": 0.31,
        "reason": "low ocr quality",
    }
    pid = quarantine_extraction(payload)
    assert pid == "case-42"

    pr = PendingReview.objects.get(pk="case-42")
    assert pr.source == "courtlistener"
    assert pr.confidence == pytest.approx(0.31)
    assert pr.reason == "low ocr quality"

    events = list(AuditEvent.objects.filter(kind="ingestion_quarantine"))
    assert len(events) == 1
    assert events[0].payload == {
        "id": "case-42",
        "source": "courtlistener",
        "kind": "case",
    }


@pytest.mark.django_db
def test_quarantine_extraction_is_idempotent_per_id() -> None:
    payload = {"id": "dup", "source": "cap", "confidence": 0.2, "reason": "noisy"}
    quarantine_extraction(payload)
    payload["confidence"] = 0.5
    payload["reason"] = "rerun"
    quarantine_extraction(payload)

    rows = PendingReview.objects.filter(pk="dup")
    assert rows.count() == 1
    assert rows[0].confidence == pytest.approx(0.5)
    assert rows[0].reason == "rerun"
    # Two audit rows is correct: each call records one quarantine event.
    assert AuditEvent.objects.filter(kind="ingestion_quarantine").count() == 2


@pytest.mark.django_db
def test_quarantine_extraction_falls_back_to_source_or_unknown() -> None:
    pid = quarantine_extraction({"source": "cap", "confidence": 0.0})
    assert pid == "cap"
    assert PendingReview.objects.filter(pk="cap").exists()


@pytest.mark.django_db
def test_quarantine_extraction_persists_kind_field() -> None:
    """Spec 016 FR-6 — payload['kind'] flows into PendingReview.kind."""
    pid = quarantine_extraction(
        {
            "id": "us-co/crs/18-3-106",
            "source": "colorado_statutes",
            "kind": "statute_section",
            "confidence": 0.4,
            "reason": "low_confidence",
            "payload": {"section": {"id": "us-co/crs/18-3-106"}},
        }
    )
    assert pid == "us-co/crs/18-3-106"
    pr = PendingReview.objects.get(pk=pid)
    assert pr.kind == "statute_section"
    assert pr.source == "colorado_statutes"

    event = AuditEvent.objects.filter(kind="ingestion_quarantine").latest("timestamp")
    assert event.payload["kind"] == "statute_section"


@pytest.mark.django_db
def test_quarantine_extraction_defaults_kind_to_case() -> None:
    """Spec 016 FR-6 backwards-compat — legacy CourtListener payloads default to 'case'."""
    pid = quarantine_extraction(
        {"id": "case-99", "source": "courtlistener", "confidence": 0.1}
    )
    pr = PendingReview.objects.get(pk=pid)
    assert pr.kind == "case"
