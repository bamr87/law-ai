"""Reviewer identity is a real account, not free text (BL-20260811-04).

Two surfaces record HITL decisions: the quarantine queue (Django admin, CLI,
Celery sweep) and the LSAT proposal approve/reject endpoints. Both used to
attribute a decision to whatever string the caller supplied — unverifiable,
and unjoinable to anything. These lock in the replacement:

* a decision made by a signed-in account writes the FK *and* the audit id;
* the account's username beats a claimed body field (no impersonation);
* with no account the legacy free-text path is byte-identical.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
from django.conf import settings
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from law_ai.core.reviewer import (
    ANONYMOUS,
    attributed,
    current_reviewer,
    reviewer_from_request,
    reviewer_from_user,
)
from law_ai.ingestionapp.models import PendingReview
from law_ai.ingestionapp.services import approval as approval_mod
from law_ai.ingestionapp.services.approval import record_decision

pytestmark = [pytest.mark.unit]


def _make_review(**overrides: Any) -> PendingReview:
    defaults: dict[str, Any] = {
        "id": "case-rev-1",
        "source": "courtlistener",
        "kind": "case",
        "confidence": 0.42,
        "reason": "low_confidence",
        "payload": {"id": "case-rev-1", "case_name": "Doe v. Roe"},
    }
    defaults.update(overrides)
    return PendingReview.objects.create(**defaults)


@pytest.fixture
def user():
    return get_user_model().objects.create_user(
        username="ada", password="lovelace-1843"
    )


# ---------------------------------------------------------------------------
# The identity resolver itself
# ---------------------------------------------------------------------------
class TestReviewerIdentity:
    def test_no_user_is_anonymous(self) -> None:
        identity = reviewer_from_user(None)
        assert identity is ANONYMOUS
        assert identity.user_id is None
        assert identity.is_account is False

    @pytest.mark.django_db
    def test_user_yields_username_and_pk(self, user) -> None:
        identity = reviewer_from_user(user)
        assert identity.name == "ada"
        assert identity.user_id == user.pk
        assert identity.is_account is True
        assert identity.audit_fields() == {
            "reviewer": "ada",
            "reviewer_user_id": user.pk,
        }

    def test_anonymous_audit_fields_are_unattributed(self) -> None:
        assert ANONYMOUS.audit_fields() == {
            "reviewer": "(unattributed)",
            "reviewer_user_id": None,
        }

    @pytest.mark.django_db
    def test_request_user_beats_a_claimed_body_field(self, user) -> None:
        from django.test import RequestFactory

        request = RequestFactory().post("/x")
        request.user = user
        identity = reviewer_from_request(request, claimed="somebody-else")
        assert identity.name == "ada"
        assert identity.user_id == user.pk

    def test_unauthenticated_request_keeps_the_claimed_name(self) -> None:
        from django.contrib.auth.models import AnonymousUser
        from django.test import RequestFactory

        request = RequestFactory().post("/x")
        request.user = AnonymousUser()
        identity = reviewer_from_request(request, claimed="alice")
        assert identity.name == "alice"
        assert identity.user_id is None

    def test_blank_claim_falls_back_to_anonymous(self) -> None:
        identity = reviewer_from_request(None, claimed="   ")
        assert identity.name == "anonymous"
        assert identity.user_id is None

    def test_context_var_is_restored_after_the_block(self) -> None:
        assert current_reviewer().user_id is None
        with attributed(reviewer_from_user(None)):
            pass
        inner = None
        with attributed(
            reviewer_from_request(None, claimed="cli-operator"),
        ) as identity:
            inner = current_reviewer()
            assert inner.name == "cli-operator"
            assert identity.name == "cli-operator"
        assert current_reviewer() is not inner
        assert current_reviewer().name == "anonymous"


# ---------------------------------------------------------------------------
# Quarantine queue
# ---------------------------------------------------------------------------
@pytest.mark.django_db
class TestQuarantineAttribution:
    def _events(self) -> tuple[list[tuple[str, dict[str, Any]]], Any]:
        events: list[tuple[str, dict[str, Any]]] = []
        return events, patch.object(
            approval_mod.provenance,
            "log_event",
            lambda t, p: events.append((t, p)),
        )

    def test_decision_binds_the_django_user(self, user) -> None:
        review = _make_review()
        events, patcher = self._events()
        with patcher:
            record_decision(review, approved=True, reviewer_user=user, note="verified")

        review.refresh_from_db()
        assert review.reviewer_user_id == user.pk
        assert review.reviewer == "ada"
        kind, payload = events[0]
        assert kind == "quarantine_decision"
        assert payload["reviewer"] == "ada"
        assert payload["reviewer_user_id"] == user.pk

    def test_account_username_overrides_a_claimed_string(self, user) -> None:
        review = _make_review(id="case-rev-2")
        events, patcher = self._events()
        with patcher:
            record_decision(
                review, approved=False, reviewer="mallory", reviewer_user=user
            )

        review.refresh_from_db()
        assert review.reviewer == "ada"
        assert review.reviewer_user_id == user.pk
        assert events[0][1]["reviewer"] == "ada"

    def test_free_text_path_is_unchanged_without_an_account(self) -> None:
        review = _make_review(id="case-rev-3")
        events, patcher = self._events()
        with patcher:
            record_decision(review, approved=True, reviewer="alice", note="ok")

        review.refresh_from_db()
        assert review.reviewer == "alice"
        assert review.reviewer_user is None
        payload = events[0][1]
        assert payload["reviewer"] == "alice"
        assert payload["reviewer_user_id"] is None

    def test_deleting_the_reviewer_keeps_the_decision(self, user) -> None:
        """§4: an audit record is never erased by a user deletion (SET_NULL)."""
        review = _make_review(id="case-rev-4")
        with self._events()[1]:
            record_decision(review, approved=True, reviewer_user=user)
        user.delete()
        review.refresh_from_db()
        assert review.reviewer_user is None
        assert review.approved is True
        assert review.reviewer == "ada"  # the legacy string survives


# ---------------------------------------------------------------------------
# LSAT proposals
# ---------------------------------------------------------------------------
@pytest.fixture
def _lsat_sandbox(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Isolate the proposal log + bank files (mirrors tests/lsat/conftest)."""
    monkeypatch.setattr(settings, "AUDIT_PATH", str(tmp_path / "audit.jsonl"))
    monkeypatch.setattr(
        settings, "LSAT_PROPOSALS_DIR", str(tmp_path / "lsat_proposals"), raising=False
    )
    monkeypatch.setattr(settings, "LSAT_CROSS_CHECK_ON_APPROVE", False, raising=False)

    from law_ai.lsat.services import bank as bank_mod
    from law_ai.lsat.services import guides as guides_mod

    sandbox = tmp_path / "lsat_data"
    sandbox.mkdir()
    for name in (
        "lr_bank.json",
        "rc_bank.json",
        "lg_bank.json",
        "concepts.json",
        "passages.json",
        "sections.json",
        "guides.json",
    ):
        src = bank_mod.DATA_DIR / name
        if src.is_file():
            (sandbox / name).write_text(src.read_text(encoding="utf-8"), "utf-8")
    monkeypatch.setattr(bank_mod, "DATA_DIR", sandbox)

    def _clear() -> None:
        bank_mod.load_bank.cache_clear()
        bank_mod.load_concepts.cache_clear()
        bank_mod.load_passages.cache_clear()
        bank_mod.load_sections.cache_clear()
        guides_mod.reset_guide_cache()

    _clear()
    yield tmp_path
    _clear()


def _record_draft() -> str:
    from law_ai.lsat.services import proposals

    return proposals.record_proposal(
        {
            "section": "LR",
            "difficulty": "med",
            "stem": "Sample stem.",
            "choices": [
                {"label": "A", "text": "alpha"},
                {"label": "B", "text": "bravo"},
                {"label": "C", "text": "charlie"},
                {"label": "D", "text": "delta"},
                {"label": "E", "text": "echo"},
            ],
            "correct": "A",
            "explanation": "Because.",
            "concepts": ["parallel-reasoning"],
            "confidence": 0.8,
        },
        agent_trace_id="t1",
        model="m",
        confidence=0.8,
    )


def _decision_events(tmp_path: Path) -> list[dict[str, Any]]:
    path = Path(str(settings.AUDIT_PATH))
    if not path.is_file():
        return []
    rows = [json.loads(line) for line in path.read_text("utf-8").splitlines() if line]
    return [r for r in rows if r.get("type") == "lsat_proposal_decision"]


@pytest.mark.django_db
class TestLsatProposalAttribution:
    def test_reject_by_a_signed_in_user_records_the_account(
        self, _lsat_sandbox: Path, user
    ) -> None:
        pid = _record_draft()
        client = APIClient()
        client.force_authenticate(user=user)
        res = client.post(
            f"/api/lsat/proposals/{pid}/reject",
            {"note": "off-topic", "reviewer": "mallory"},
            format="json",
        )
        assert res.status_code == 200
        # The claimed body value is ignored in favour of the account.
        assert res.json()["reviewer"] == "ada"
        events = _decision_events(_lsat_sandbox)
        assert events and events[-1]["reviewer"] == "ada"
        assert events[-1]["reviewer_user_id"] == user.pk

    def test_approve_by_a_signed_in_user_records_the_account(
        self, _lsat_sandbox: Path, user
    ) -> None:
        pid = _record_draft()
        client = APIClient()
        client.force_authenticate(user=user)
        res = client.post(
            f"/api/lsat/proposals/{pid}/approve", {"note": "good"}, format="json"
        )
        assert res.status_code == 200
        assert res.json()["reviewer"] == "ada"
        events = _decision_events(_lsat_sandbox)
        assert events[-1]["reviewer_user_id"] == user.pk

    def test_anonymous_reject_keeps_the_free_text_path(
        self, _lsat_sandbox: Path
    ) -> None:
        pid = _record_draft()
        client = APIClient()
        res = client.post(
            f"/api/lsat/proposals/{pid}/reject",
            {"reviewer": "alice", "note": "dupe"},
            format="json",
        )
        assert res.status_code == 200
        assert res.json()["reviewer"] == "alice"
        events = _decision_events(_lsat_sandbox)
        assert events[-1]["reviewer"] == "alice"
        assert events[-1]["reviewer_user_id"] is None
