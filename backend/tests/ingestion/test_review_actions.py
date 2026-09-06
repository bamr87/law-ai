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


def _make_statute_review(**overrides: Any) -> PendingReview:
    """A ``kind="statute_section"`` row carrying the quarantine envelope.

    Mirrors ``StatuteScout._quarantine_via_celery``: the row stores the parsed
    section, not the title HTML (BL-20260905-96). The heading and body are
    substantial enough that today's scorer lifts it over the 0.7 threshold.
    """
    section = {
        "id": "us-co/crs/18-3-102",
        "citation": "C.R.S. § 18-3-102",
        "heading": "18-3-102. Murder in the first degree",
        "text": (
            "A person commits the crime of murder in the first degree if, "
            "after deliberation and with the intent to cause the death of a "
            "person other than himself, he causes the death of that person "
            "or of another person."
        ),
        "effective_from": None,
        "confidence": 0.42,
    }
    defaults: dict[str, Any] = {
        "id": "us-co/crs/18-3-102",
        "source": "colorado_statutes",
        "kind": "statute_section",
        "confidence": 0.42,
        "reason": "low_confidence",
        "payload": {
            "id": "us-co/crs/18-3-102",
            "source": "colorado_statutes",
            "confidence": 0.42,
            "reason": "low_confidence",
            "payload": {
                "section": section,
                "statute_id": "us-co/crs/title-18",
                "statute_title": "Criminal Code",
                "statute_citation": "C.R.S. tit. 18",
                "jurisdiction_code": "us-co",
                "jurisdiction_name": "Colorado",
                "jurisdiction_level": "state",
                "code_id": "us-co/crs",
                "code_title": "Colorado Revised Statutes",
                "source": "colorado_statutes",
                "source_url": "https://example.test/title-18",
                "agent_version": "0.1.0",
            },
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

    def test_rejects_a_kind_with_no_reextraction_path(self) -> None:
        # Ordinance rows have no re-extraction path yet (BL-20260905-96 added
        # the statute one), so they still fail loudly.
        review = _make_review(kind="ordinance_section")
        with pytest.raises(ApprovalError, match="ordinance_section"):
            reextract_review(review)

    def test_rescores_a_statute_row_from_its_stored_section(self) -> None:
        """BL-20260905-96: statute rows re-score instead of re-parsing HTML."""
        review = _make_statute_review()
        with patch.object(approval_mod.provenance, "log_event", lambda t, p: None):
            outcome = reextract_review(review, reviewer="alice")

        review.refresh_from_db()
        assert outcome["reextracted"] is True
        assert outcome["clears_threshold"] is True
        assert outcome["n_citations"] == 0
        assert outcome["previous_confidence"] == 0.42
        assert review.confidence > 0.42
        # §5: a fresh score still only informs the reviewer.
        assert review.committed_at is None

    def test_statute_row_without_a_section_records_the_failure(self) -> None:
        review = _make_review(kind="statute_section")
        with patch.object(approval_mod.provenance, "log_event", lambda t, p: None):
            outcome = reextract_review(review)

        review.refresh_from_db()
        assert outcome["reextracted"] is False
        assert "no 'section'" in outcome["error"]
        assert "no 'section'" in review.commit_error


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
        _make_review(kind="ordinance_section")
        messages_seen: list[tuple[str, int | None]] = []
        with patch.object(
            PendingReviewAdmin,
            "message_user",
            lambda self, req, msg, level=None: messages_seen.append((msg, level)),
        ):
            _admin().reextract_selected(_request(), PendingReview.objects.all())
        assert any("ordinance_section" in m for m, _ in messages_seen)
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
        _make_review(kind="ordinance_section")
        with pytest.raises(CommandError, match="ordinance_section"):
            call_command("review_queue", "re-extract", "case-1")


# ---------------------------------------------------------------------------
# review_queue: account attribution + scoped bulk approval
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestReviewQueueAttribution:
    """BL-20260906-20: the CLI can name a real Django account."""

    def test_reviewer_user_records_the_fk(self) -> None:
        from django.contrib.auth import get_user_model

        user = get_user_model().objects.create_user(
            username="ada", password="lovelace-1843"
        )
        review = _make_review()

        async def _fake_commit(row: Any) -> dict[str, Any]:
            return {"id": row.pk, "committed": True, "edges": 0}

        with (
            patch.object(approval_mod, "commit_approved_review", _fake_commit),
            patch.object(approval_mod.provenance, "log_event", lambda t, p: None),
        ):
            call_command(
                "review_queue",
                "approve",
                "case-1",
                "--reviewer-user",
                "ada",
                stdout=StringIO(),
            )

        review.refresh_from_db()
        assert review.reviewer_user_id == user.pk
        # The account's username wins over the (absent) free-text claim.
        assert review.reviewer == "ada"

    def test_unknown_reviewer_user_is_an_error(self) -> None:
        _make_review()
        with pytest.raises(CommandError, match="no user account named 'nobody'"):
            call_command(
                "review_queue", "approve", "case-1", "--reviewer-user", "nobody"
            )


@pytest.mark.django_db
class TestReviewQueueApproveAll:
    """BL-20260905-98: one decision across a scoped batch."""

    def _rows(self) -> None:
        _make_statute_review(id="us-co/crs/18-3-101")
        _make_statute_review(id="us-co/crs/18-3-102")
        _make_statute_review(id="us-co/crs/24-4-101")

    def test_approves_only_the_scoped_rows(self) -> None:
        self._rows()
        committed: list[str] = []

        async def _fake_commit(row: Any) -> dict[str, Any]:
            committed.append(row.pk)
            return {"id": row.pk, "committed": True, "edges": 1}

        out = StringIO()
        with (
            patch.object(approval_mod, "commit_approved_review", _fake_commit),
            patch.object(approval_mod.provenance, "log_event", lambda t, p: None),
        ):
            call_command(
                "review_queue",
                "approve-all",
                "--id-prefix",
                "us-co/crs/18-",
                "--reviewer",
                "alice",
                stdout=out,
            )

        assert sorted(committed) == ["us-co/crs/18-3-101", "us-co/crs/18-3-102"]
        assert "approved 2 row(s), committed 2" in out.getvalue()
        untouched = PendingReview.objects.get(pk="us-co/crs/24-4-101")
        assert untouched.approved is None

    def test_refuses_to_approve_the_whole_queue(self) -> None:
        self._rows()
        with pytest.raises(CommandError, match="needs a scope"):
            call_command("review_queue", "approve-all", "--reviewer", "alice")
        assert PendingReview.objects.filter(approved=True).count() == 0

    def test_reports_a_commit_failure_per_row(self) -> None:
        self._rows()

        async def _fake_commit(row: Any) -> dict[str, Any]:
            return {"id": row.pk, "committed": False, "error": "neo4j down"}

        out = StringIO()
        with (
            patch.object(approval_mod, "commit_approved_review", _fake_commit),
            patch.object(approval_mod.provenance, "log_event", lambda t, p: None),
        ):
            call_command(
                "review_queue",
                "approve-all",
                "--kind",
                "statute_section",
                "--reviewer",
                "alice",
                stdout=out,
            )
        text = out.getvalue()
        assert "approved 3 row(s), committed 0" in text
        assert text.count("neo4j down") == 3

    def test_empty_scope_says_so(self) -> None:
        self._rows()
        out = StringIO()
        call_command("review_queue", "approve-all", "--source", "nowhere", stdout=out)
        assert "no pending rows match that scope" in out.getvalue()
