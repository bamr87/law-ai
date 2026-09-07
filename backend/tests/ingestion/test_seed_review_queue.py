"""``manage.py seed_review_queue`` (spec 051 / BL-20260503-17).

The e2e admin spec approves this row and asserts the case reaches the graph, so
the seed has to be deterministic *and* re-runnable: a second nightly run must
find the row pending again, not already committed.
"""

from __future__ import annotations

from datetime import UTC, datetime
from io import StringIO

import pytest
from django.core.management import call_command

from law_ai.ingestionapp.management.commands.seed_review_queue import (
    CASE_ID,
    PAYLOAD,
    REVIEW_ID,
)
from law_ai.ingestionapp.models import PendingReview

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


def _seed(*args: str) -> str:
    out = StringIO()
    call_command("seed_review_queue", *args, stdout=out)
    return out.getvalue()


def test_creates_one_pending_row() -> None:
    assert "created" in _seed()

    review = PendingReview.objects.get(id=REVIEW_ID)
    assert review.approved is None
    assert review.committed_at is None
    assert review.source == "e2e"
    assert review.kind == "case"
    # Below the auto-commit threshold — the reason it is in the queue at all.
    assert review.confidence < 0.85


def test_is_idempotent_without_reset() -> None:
    _seed()
    review = PendingReview.objects.get(id=REVIEW_ID)
    review.approved = True
    review.committed_at = datetime.now(UTC)
    review.save()

    assert "exists (committed)" in _seed()
    review.refresh_from_db()
    assert review.committed_at is not None, "a plain run must not undo a commit"
    assert PendingReview.objects.filter(id=REVIEW_ID).count() == 1


def test_reset_returns_a_committed_row_to_pending() -> None:
    _seed()
    review = PendingReview.objects.get(id=REVIEW_ID)
    review.approved = True
    review.reviewer = "someone"
    review.review_note = "looked fine"
    review.committed_at = datetime.now(UTC)
    review.commit_error = "stale error"
    review.save()

    assert "reset" in _seed("--reset")

    review.refresh_from_db()
    assert review.approved is None
    assert review.reviewed_at is None
    assert review.reviewer == ""
    assert review.review_note == ""
    assert review.committed_at is None
    assert review.commit_error == ""


def test_the_payload_extracts_without_a_model_call() -> None:
    """The approval path is rule-based, so the seed must parse deterministically."""
    from law_ai.ingestionapp.services.scout import IngestionScout

    result = IngestionScout().extract(PAYLOAD)
    assert result.case_id == CASE_ID
    assert result.title.startswith("E2E Harness")
    # eyecite finds the two reporter citations planted in the opinion text.
    assert len(result.citations) >= 2
