"""Tests for the approval → commit path (spec 029, BL-20260810-03).

The regression these lock in: ``PendingReview.approved`` used to have no
consumer at all, so approving a quarantined document never reached Neo4j.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from law_ai.ingestionapp.models import PendingReview
from law_ai.ingestionapp.services import approval as approval_mod
from law_ai.ingestionapp.services.approval import (
    ApprovalError,
    commit_approved_reviews,
    record_decision,
)


def _make_review(**overrides: Any) -> PendingReview:
    defaults: dict[str, Any] = {
        "id": "case-1",
        "source": "courtlistener",
        "kind": "case",
        "confidence": 0.42,
        "reason": "low_confidence",
        "payload": {
            "id": "case-1",
            "source": "courtlistener",
            "confidence": 0.42,
            "reason": "low_confidence",
            "payload": {"id": "case-1", "case_name": "Doe v. Roe"},
        },
    }
    defaults.update(overrides)
    return PendingReview.objects.create(**defaults)


@pytest.mark.django_db
class TestRecordDecision:
    def test_records_reviewer_and_rationale(self) -> None:
        review = _make_review()
        events: list[tuple[str, dict[str, Any]]] = []
        with patch.object(
            approval_mod.provenance,
            "log_event",
            lambda t, p: events.append((t, p)),
        ):
            record_decision(
                review, approved=True, reviewer="alice", note="verified against source"
            )

        review.refresh_from_db()
        assert review.approved is True
        assert review.reviewer == "alice"
        assert review.review_note == "verified against source"
        assert review.reviewed_at is not None
        # Decision is auditable, with its author (§4).
        assert events[0][0] == "quarantine_decision"
        assert events[0][1]["reviewer"] == "alice"
        assert events[0][1]["approved"] is True

    def test_rejection_is_recorded_without_committing(self) -> None:
        review = _make_review(id="case-rej")
        with patch.object(approval_mod.provenance, "log_event", lambda *a: None):
            record_decision(review, approved=False, reviewer="bob", note="duplicate")
        review.refresh_from_db()
        assert review.approved is False
        assert review.committed_at is None


@pytest.mark.django_db
class TestCommitApprovedReviews:
    def test_approved_row_reaches_the_graph(self) -> None:
        review = _make_review()
        with patch.object(approval_mod.provenance, "log_event", lambda *a: None):
            record_decision(review, approved=True, reviewer="alice")

        fake_commit = AsyncMock(return_value={"committed": True, "edges": 3})
        with (
            patch(
                "law_ai.ingestionapp.services.scout.IngestionScout.run_and_commit",
                new=fake_commit,
            ),
            patch.object(approval_mod.provenance, "log_event", lambda *a: None),
        ):
            results = commit_approved_reviews()

        assert results == [{"id": "case-1", "committed": True, "edges": 3}]
        review.refresh_from_db()
        assert review.committed_at is not None
        assert review.commit_error == ""
        # §12 I1: the commit goes through IngestionScout, with the human
        # approval standing in for the confidence gate.
        assert fake_commit.await_args.kwargs["force_commit"] is True
        # The unwrapped document payload is what gets committed.
        assert fake_commit.await_args.args[0] == {
            "id": "case-1",
            "case_name": "Doe v. Roe",
        }

    def test_unapproved_rows_are_never_committed(self) -> None:
        _make_review(id="pending-1")  # approved is None
        _make_review(id="rejected-1", approved=False)

        fake_commit = AsyncMock(return_value={"committed": True, "edges": 1})
        with patch(
            "law_ai.ingestionapp.services.scout.IngestionScout.run_and_commit",
            new=fake_commit,
        ):
            assert commit_approved_reviews() == []
        assert fake_commit.await_count == 0

    def test_sweep_is_idempotent(self) -> None:
        review = _make_review()
        with patch.object(approval_mod.provenance, "log_event", lambda *a: None):
            record_decision(review, approved=True, reviewer="alice")

        fake_commit = AsyncMock(return_value={"committed": True, "edges": 1})
        with (
            patch(
                "law_ai.ingestionapp.services.scout.IngestionScout.run_and_commit",
                new=fake_commit,
            ),
            patch.object(approval_mod.provenance, "log_event", lambda *a: None),
        ):
            commit_approved_reviews()
            second = commit_approved_reviews()

        # Second sweep finds nothing: committed rows are filtered out.
        assert second == []
        assert fake_commit.await_count == 1

    def test_graph_failure_is_recorded_not_swallowed(self) -> None:
        review = _make_review()
        with patch.object(approval_mod.provenance, "log_event", lambda *a: None):
            record_decision(review, approved=True, reviewer="alice")

        boom = AsyncMock(side_effect=RuntimeError("neo4j down"))
        events: list[tuple[str, dict[str, Any]]] = []
        with (
            patch(
                "law_ai.ingestionapp.services.scout.IngestionScout.run_and_commit",
                new=boom,
            ),
            patch.object(
                approval_mod.provenance,
                "log_event",
                lambda t, p: events.append((t, p)),
            ),
        ):
            results = commit_approved_reviews()

        assert results[0]["committed"] is False
        review.refresh_from_db()
        # Still approved, still uncommitted, with the reason visible — so the
        # next sweep retries instead of the failure being lost.
        assert review.committed_at is None
        assert "neo4j down" in review.commit_error
        assert review.approved is True
        assert any(t == "quarantine_commit_failed" for t, _ in events)

    def test_rejects_committing_an_unapproved_review(self) -> None:
        from asgiref.sync import async_to_sync

        review = _make_review(id="not-approved")
        with pytest.raises(ApprovalError, match="not approved"):
            async_to_sync(approval_mod.commit_approved_review)(review)

    def test_legacy_flat_payload_is_accepted(self) -> None:
        """Spec-004 rows stored the document directly, not an envelope."""
        review = _make_review(
            id="legacy-1", payload={"id": "legacy-1", "case_name": "Old v. Form"}
        )
        with patch.object(approval_mod.provenance, "log_event", lambda *a: None):
            record_decision(review, approved=True, reviewer="alice")

        fake_commit = AsyncMock(return_value={"committed": True, "edges": 0})
        with (
            patch(
                "law_ai.ingestionapp.services.scout.IngestionScout.run_and_commit",
                new=fake_commit,
            ),
            patch.object(approval_mod.provenance, "log_event", lambda *a: None),
        ):
            commit_approved_reviews()

        assert fake_commit.await_args.args[0] == {
            "id": "legacy-1",
            "case_name": "Old v. Form",
        }


@pytest.mark.django_db
def test_celery_task_reports_counts() -> None:
    from law_ai.ingestionapp.tasks import commit_approved_reviews_task

    review = _make_review()
    with patch.object(approval_mod.provenance, "log_event", lambda *a: None):
        record_decision(review, approved=True, reviewer="alice")

    fake_commit = AsyncMock(return_value={"committed": True, "edges": 2})
    with (
        patch(
            "law_ai.ingestionapp.services.scout.IngestionScout.run_and_commit",
            new=fake_commit,
        ),
        patch.object(approval_mod.provenance, "log_event", lambda *a: None),
    ):
        summary = commit_approved_reviews_task()

    assert summary == {"processed": 1, "committed": 1, "failed": 0}
