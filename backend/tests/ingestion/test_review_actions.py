"""Review-queue verbs: approve / reject / re-extract (BL-20260503-10).

Spec 011 T-354 asked for three admin actions on ``ingestionapp.PendingReview``
plus tasks that apply the decision back to Neo4j. Approve/reject/commit shipped
with spec 029 but were never covered by a test, and ``re-extract`` did not
exist. This module locks all three verbs across the admin, the service layer
and the ``review_queue`` management command.
"""

from __future__ import annotations

from datetime import UTC, datetime
from io import StringIO
from typing import Any
from unittest.mock import patch

import pytest
from django.contrib.admin.sites import AdminSite
from django.contrib.messages import constants as message_levels
from django.core.management import CommandError, call_command
from django.test import RequestFactory

from law_ai.ingestionapp.admin import PendingReviewAdmin
from law_ai.ingestionapp.models import PendingReview
from law_ai.ingestionapp.services import approval as approval_mod
from law_ai.ingestionapp.services.approval import ApprovalError, reextract_review

# Long, well-cited body: scores 0.9 under ``scout._score`` so a re-extraction
# of a row quarantined at 0.42 now clears the 0.7 threshold.
RICH_TEXT = (
    "The judgment below is affirmed. See Marbury v. Madison, 5 U.S. 137 "
    "(1803); Brown v. Board of Education, 347 U.S. 483 (1954); Roe v. Wade, "
    "410 U.S. 113 (1973). Appellant's remaining contentions are without "
    "merit. Because the findings are supported by substantial evidence in "
    "the record as a whole, and because the legal conclusions drawn from "
    "those findings comport with our precedent, we decline to disturb the "
    "judgment. The mandate shall issue forthwith. It is so ordered, and the "
    "clerk is directed to enter judgment accordingly without further delay."
)


def _make_review(**overrides: Any) -> PendingReview:
    doc: dict[str, Any] = {
        "id": "case-1",
        "case_name": "Doe v. Roe",
        "plain_text": RICH_TEXT,
        "cluster": {"court": "Supreme Court of Colorado"},
    }
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
            "payload": doc,
        },
    }
    defaults.update(overrides)
    return PendingReview.objects.create(**defaults)


def _admin() -> PendingReviewAdmin:
    return PendingReviewAdmin(PendingReview, AdminSite())


def _request(username: str = "alice") -> Any:
    request = RequestFactory().post("/admin/ingestionapp/pendingreview/")
    request.user = type("U", (), {"username": username})()  # type: ignore[attr-defined]
    return request


# ---------------------------------------------------------------------------
# Service layer: re-extract
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestReextractReview:
    def test_refreshes_confidence_from_the_stored_raw_document(self) -> None:
        review = _make_review()
        events: list[tuple[str, dict[str, Any]]] = []
        with patch.object(
            approval_mod.provenance, "log_event", lambda t, p: events.append((t, p))
        ):
            outcome = reextract_review(review, reviewer="alice")

        review.refresh_from_db()
        assert outcome["reextracted"] is True
        assert outcome["previous_confidence"] == 0.42
        assert outcome["confidence"] > 0.42
        assert outcome["clears_threshold"] is True
        assert outcome["n_citations"] >= 1
        assert review.confidence == outcome["confidence"]
        assert "re-extracted" in review.reason
        # §4: the re-extraction is audited with its author and both scores.
        kinds = [k for k, _ in events]
        assert "quarantine_reextracted" in kinds
        payload = dict(events[0][1])
        assert payload["reviewer"] == "alice"
        assert payload["previous_confidence"] == 0.42

    def test_never_commits_even_when_it_clears_the_threshold(self) -> None:
        """Constitution §5: approval stays the gate, re-extraction only informs."""
        review = _make_review()
        with patch.object(approval_mod.provenance, "log_event", lambda t, p: None):
            outcome = reextract_review(review)

        review.refresh_from_db()
        assert outcome["clears_threshold"] is True
        assert review.committed_at is None
        assert review.approved is None

    def test_low_quality_document_stays_low_confidence(self) -> None:
        review = _make_review(
            payload={"payload": {"id": "case-1", "plain_text": "Affirmed."}}
        )
        with patch.object(approval_mod.provenance, "log_event", lambda t, p: None):
            outcome = reextract_review(review)

        review.refresh_from_db()
        assert outcome["clears_threshold"] is False
        assert review.reason.startswith("low_confidence (re-extracted")

    def test_records_error_when_the_payload_cannot_be_extracted(self) -> None:
        review = _make_review(payload={"payload": {"case_name": "no id here"}})
        with patch.object(approval_mod.provenance, "log_event", lambda t, p: None):
            outcome = reextract_review(review)

        review.refresh_from_db()
        assert outcome["reextracted"] is False
        assert "ValueError" in outcome["error"]
        assert "ValueError" in review.commit_error

    def test_skips_an_already_committed_row(self) -> None:
        review = _make_review(committed_at=datetime.now(UTC))
        outcome = reextract_review(review)
        assert outcome == {
            "id": "case-1",
            "reextracted": False,
            "skipped": "already-committed",
        }

    def test_rejects_a_non_case_kind(self) -> None:
        review = _make_review(kind="statute_section")
        with pytest.raises(ApprovalError, match="statute_section"):
            reextract_review(review)


# ---------------------------------------------------------------------------
# Django admin actions
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestAdminActions:
    def test_all_three_verbs_are_registered(self) -> None:
        assert _admin().actions == (
            "approve_and_commit",
            "reject_selected",
            "reextract_selected",
        )

    def test_approve_and_commit_records_decision_and_commits(self) -> None:
        review = _make_review()
        messages_seen: list[tuple[str, int]] = []

        committed_rows: list[str] = []

        async def _fake_commit(row: Any) -> dict[str, Any]:
            # The real service writes committed_at through sync_to_async; here
            # we only need to know the admin action reached the commit path.
            committed_rows.append(row.pk)
            return {"id": row.pk, "committed": True, "edges": 3}

        with (
            patch.object(approval_mod, "commit_approved_review", _fake_commit),
            patch.object(approval_mod.provenance, "log_event", lambda t, p: None),
            patch.object(
                PendingReviewAdmin,
                "message_user",
                lambda self, req, msg, level=None: messages_seen.append((msg, level)),
            ),
        ):
            _admin().approve_and_commit(
                _request(), PendingReview.objects.filter(pk=review.pk)
            )

        review.refresh_from_db()
        assert review.approved is True
        assert review.reviewer == "alice"
        assert committed_rows == [review.pk]
        assert any("1 committed" in m for m, _ in messages_seen)

    def test_approve_and_commit_skips_already_committed_rows(self) -> None:
        _make_review(committed_at=datetime.now(UTC))
        messages_seen: list[tuple[str, int]] = []
        with patch.object(
            PendingReviewAdmin,
            "message_user",
            lambda self, req, msg, level=None: messages_seen.append((msg, level)),
        ):
            _admin().approve_and_commit(_request(), PendingReview.objects.all())
        assert any("already committed" in m for m, _ in messages_seen)

    def test_reject_selected_records_the_reviewer(self) -> None:
        review = _make_review()
        with (
            patch.object(approval_mod.provenance, "log_event", lambda t, p: None),
            patch.object(
                PendingReviewAdmin,
                "message_user",
                lambda self, req, msg, level=None: None,
            ),
        ):
            _admin().reject_selected(
                _request("bob"), PendingReview.objects.filter(pk=review.pk)
            )

        review.refresh_from_db()
        assert review.approved is False
        assert review.reviewer == "bob"
        assert review.committed_at is None

    def test_reextract_selected_refreshes_and_reports(self) -> None:
        review = _make_review()
        messages_seen: list[tuple[str, int | None]] = []
        with (
            patch.object(approval_mod.provenance, "log_event", lambda t, p: None),
            patch.object(
                PendingReviewAdmin,
                "message_user",
                lambda self, req, msg, level=None: messages_seen.append((msg, level)),
            ),
        ):
            _admin().reextract_selected(
                _request(), PendingReview.objects.filter(pk=review.pk)
            )

        review.refresh_from_db()
        assert review.confidence > 0.42
        assert review.committed_at is None
        assert any("1 re-extracted" in m for m, _ in messages_seen)
        assert any(
            "clear the confidence threshold" in m and level == message_levels.INFO
            for m, level in messages_seen
        )

    def test_reextract_selected_warns_on_unsupported_kind(self) -> None:
        _make_review(kind="statute_section")
        messages_seen: list[tuple[str, int | None]] = []
        with patch.object(
            PendingReviewAdmin,
            "message_user",
            lambda self, req, msg, level=None: messages_seen.append((msg, level)),
        ):
            _admin().reextract_selected(_request(), PendingReview.objects.all())
        assert any("statute_section" in m for m, _ in messages_seen)
        assert any("could not be re-extracted" in m for m, _ in messages_seen)


# ---------------------------------------------------------------------------
# review_queue management command
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestReviewQueueReextractVerb:
    def test_re_extract_verb_refreshes_the_row(self) -> None:
        review = _make_review()
        out = StringIO()
        with patch.object(approval_mod.provenance, "log_event", lambda t, p: None):
            call_command(
                "review_queue",
                "re-extract",
                "case-1",
                "--reviewer",
                "alice",
                stdout=out,
            )

        review.refresh_from_db()
        text = out.getvalue()
        assert "re-extracted case-1" in text
        assert "0.420 ->" in text
        assert "clears the confidence threshold" in text
        assert review.confidence > 0.42
        assert review.committed_at is None

    def test_re_extract_verb_errors_on_unsupported_kind(self) -> None:
        _make_review(kind="statute_section")
        with pytest.raises(CommandError, match="statute_section"):
            call_command("review_queue", "re-extract", "case-1")
