"""Data portability and account deletion (BL-20260817-01).

The pair is one obligation with two halves: a user can take everything with
them, and a user can leave — without the audit trail being rewritten and
without the ``PROTECT`` FK on matter ownership blocking the door.
"""

from __future__ import annotations

from typing import Any

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APIClient

from law_ai.core.accounts.deletion import TOMBSTONE_USERNAME, delete_account
from law_ai.matters.models import Matter, MatterArtifact, MatterAuthority, MatterTask
from law_ai.matters.services.export import export_matter

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


@pytest.fixture
def owner():
    return get_user_model().objects.create_user(
        username="ada", password="pw-12345678", email="ada@example.test"
    )


@pytest.fixture
def matter(owner) -> Matter:
    row = Matter.objects.create(
        owner=owner,
        slug="lease",
        name="Smith lease",
        issue_tags=["landlord-tenant"],
    )
    MatterArtifact.objects.create(
        matter=row,
        kind="analysis",
        title="IRAC",
        trace_id="tr-42",
        analysis_id="an-1",
        created_by=owner,
    )
    MatterArtifact.objects.create(
        matter=row, kind="note", title="old note", archived_at=timezone.now()
    )
    MatterAuthority.objects.create(
        matter=row, node_id="case:1", citation="1 U.S. 1", verified_at=timezone.now()
    )
    MatterTask.objects.create(matter=row, title="File answer", due_at=timezone.now())
    return row


class TestExport:
    def test_the_bundle_holds_every_part_of_the_matter(self, matter: Matter) -> None:
        bundle = export_matter(matter, log=False)
        assert bundle["matter"]["slug"] == "lease"
        assert len(bundle["artifacts"]) == 2
        assert len(bundle["authorities"]) == 1
        assert len(bundle["tasks"]) == 1
        assert bundle["bundle_version"] >= 1

    def test_provenance_ids_travel_with_the_data(self, matter: Matter) -> None:
        bundle = export_matter(matter, log=False)
        traces = {a["trace_id"] for a in bundle["artifacts"]}
        assert "tr-42" in traces

    def test_archived_rows_are_included_and_marked(self, matter: Matter) -> None:
        bundle = export_matter(matter, log=False)
        archived = [a for a in bundle["artifacts"] if a["archived"]]
        assert [a["title"] for a in archived] == ["old note"]

    def test_the_timeline_is_ordered_and_covers_everything(
        self, matter: Matter
    ) -> None:
        timeline = export_matter(matter, log=False)["timeline"]
        kinds = [e["kind"] for e in timeline]
        assert kinds[0] == "matter.created"
        assert "authority.recorded" in kinds
        assert "task.created" in kinds
        stamps = [e["at"] or "" for e in timeline]
        assert stamps == sorted(stamps)

    def test_the_bundle_carries_the_disclaimer(self, matter: Matter) -> None:
        assert "not legal advice" in export_matter(matter, log=False)["disclaimer"]

    def test_the_endpoint_is_owner_scoped_and_downloadable(
        self, matter: Matter, owner
    ) -> None:
        client = APIClient()
        client.force_authenticate(user=owner)
        res = client.get("/api/matters/lease/export")
        assert res.status_code == 200
        assert "attachment" in res["Content-Disposition"]
        assert res.json()["matter"]["slug"] == "lease"

        intruder = get_user_model().objects.create_user(
            username="mallory", password="pw-12345678"
        )
        client.force_authenticate(user=intruder)
        assert client.get("/api/matters/lease/export").status_code == 404

    def test_the_account_export_gathers_every_matter(self, matter: Matter, owner):
        Matter.objects.create(owner=owner, slug="second", name="Second")
        client = APIClient()
        client.force_authenticate(user=owner)
        body = client.get("/api/account/export").json()
        assert {m["matter"]["slug"] for m in body["matters"]} == {"lease", "second"}


class TestDeletion:
    def _events(self) -> tuple[list[Any], Any]:
        from unittest.mock import patch

        from law_ai.core import provenance as provenance_mod

        events: list[Any] = []
        return events, patch.object(
            provenance_mod.provenance,
            "log_event",
            lambda t, p: events.append((t, p)),
        )

    def test_matters_are_archived_and_reassigned_not_deleted(
        self, matter: Matter, owner
    ) -> None:
        summary = delete_account(owner)
        assert summary["matters_archived"] == 1
        matter.refresh_from_db()
        assert matter.archived_at is not None
        assert matter.owner.username == TOMBSTONE_USERNAME
        # Nothing inside the matter was hard-deleted (§5).
        assert MatterArtifact.objects.filter(matter=matter).count() == 2

    def test_the_protect_fk_would_have_blocked_a_naive_delete(
        self, matter: Matter, owner
    ) -> None:
        from django.db.models import ProtectedError

        with pytest.raises(ProtectedError):
            owner.delete()

    def test_the_account_is_de_identified_rather_than_removed(self, owner) -> None:
        pk = owner.pk
        delete_account(owner)
        row = get_user_model().objects.get(pk=pk)
        assert row.username == f"deleted-user-{pk}"
        assert row.email == ""
        assert row.is_active is False
        assert row.has_usable_password() is False

    def test_audit_attribution_survives_deletion(self, owner) -> None:
        """§4: a decision the account made is still attributable afterwards."""
        from law_ai.ingestionapp.models import PendingReview
        from law_ai.ingestionapp.services.approval import record_decision

        review = PendingReview.objects.create(
            id="case-1", source="courtlistener", payload={}, confidence=0.1
        )
        record_decision(review, approved=True, reviewer_user=owner)
        delete_account(owner)
        review.refresh_from_db()
        assert review.reviewer_user_id == owner.pk
        assert review.reviewer == "ada"

    def test_personal_learning_history_is_actually_removed(self, owner) -> None:
        from law_ai.lsat.models import LsatAttempt
        from law_ai.lsat.services.attempts import record_attempt

        record_attempt(owner, question_id="q1", section="LR", correct=True)
        summary = delete_account(owner)
        assert summary["lsat_attempts"] == 1
        assert LsatAttempt.objects.filter(user=owner).count() == 0

    def test_tokens_are_revoked_and_shares_killed(self, owner) -> None:
        from law_ai.analysis.models import AnalysisRun, ShareLink
        from law_ai.core.models import ApiToken

        token, _ = ApiToken.generate(scope="agent", name="cli", user=owner)
        run = AnalysisRun.objects.create(analysis_id="an-1", created_by=owner)
        link = ShareLink.objects.create(slug="abc123xyz", analysis=run)

        summary = delete_account(owner)
        token.refresh_from_db()
        run.refresh_from_db()
        link.refresh_from_db()
        assert summary["tokens_revoked"] == 1
        assert token.revoked_at is not None
        assert run.archived_at is not None
        assert link.revoked_at is not None

    def test_two_accounts_with_the_same_matter_slug_can_both_delete(
        self, matter: Matter, owner
    ) -> None:
        """The collision that used to roll the whole de-identification back.

        ``Matter`` is unique on ``(owner, slug)`` and slugs are auto-derived
        from the matter's name, so "lease" belonging to two accounts is
        ordinary. Reassigning both to the single ``deleted-user`` tombstone
        without touching the slug raised ``IntegrityError`` on the second
        deletion, and because ``delete_account`` is one atomic block the
        second account came out undeleted: tokens live, history intact,
        endpoint 500.
        """
        second = get_user_model().objects.create_user(
            username="bob", password="pw-12345678"
        )
        theirs = Matter.objects.create(owner=second, slug="lease", name="Other lease")

        delete_account(owner)
        summary = delete_account(second)

        assert summary["matters_archived"] == 1
        second.refresh_from_db()
        assert second.username == f"deleted-user-{second.pk}"
        assert second.is_active is False

        matter.refresh_from_db()
        theirs.refresh_from_db()
        assert matter.owner.username == TOMBSTONE_USERNAME
        assert theirs.owner.username == TOMBSTONE_USERNAME
        assert matter.archived_at is not None and theirs.archived_at is not None
        # Both survive, under slugs that stay unique on the shared tombstone
        # and still name the matter they came from.
        assert matter.slug != theirs.slug
        assert matter.slug == f"lease-{matter.pk}"
        assert theirs.slug == f"lease-{theirs.pk}"

    def test_a_third_account_with_the_same_slug_still_deletes(self, owner) -> None:
        """Not just two: the tombstone accumulates for the life of the deployment."""
        for name in ("bob", "cyd", "dee"):
            user = get_user_model().objects.create_user(
                username=name, password="pw-12345678"
            )
            Matter.objects.create(owner=user, slug="eviction", name="Eviction")
            assert delete_account(user)["matters_archived"] == 1
        assert Matter.objects.filter(slug__startswith="eviction-").count() == 3

    def test_a_rewritten_slug_stays_inside_the_column(self, owner) -> None:
        long_slug = "x" * 64
        row = Matter.objects.create(owner=owner, slug=long_slug, name="Long")
        delete_account(owner)
        row.refresh_from_db()
        assert len(row.slug) <= 64
        assert row.slug.endswith(f"-{row.pk}")

    def test_the_tokens_of_a_colliding_second_account_are_really_revoked(
        self, matter: Matter, owner
    ) -> None:
        """The rollback's real damage: an account that looked deleted was not."""
        from law_ai.core.models import ApiToken

        second = get_user_model().objects.create_user(
            username="bob", password="pw-12345678"
        )
        Matter.objects.create(owner=second, slug="lease", name="Other lease")
        token, _raw = ApiToken.generate(scope="agent", name="cli", user=second)

        delete_account(owner)
        delete_account(second)

        token.refresh_from_db()
        assert token.revoked_at is not None

    def test_deletion_is_idempotent(self, owner) -> None:
        delete_account(owner)
        again = delete_account(owner)
        assert again["already_deleted"] is True

    def test_it_logs_one_provenance_event(self, matter: Matter, owner) -> None:
        events, patcher = self._events()
        with patcher:
            delete_account(owner, reason="user request")
        kinds = [k for k, _ in events]
        assert "account.deleted" in kinds
        payload = dict(events[kinds.index("account.deleted")][1])
        assert payload["matters_archived"] == 1
        assert payload["reason"] == "user request"


class TestDeleteEndpoint:
    def test_it_demands_the_username_back(self, owner) -> None:
        client = APIClient()
        client.force_authenticate(user=owner)
        assert (
            client.post(
                "/api/account/delete", {"confirm_username": "nope"}, format="json"
            ).status_code
            == 400
        )
        res = client.post(
            "/api/account/delete", {"confirm_username": "ada"}, format="json"
        )
        assert res.status_code == 200
        owner.refresh_from_db()
        assert owner.is_active is False

    def test_anonymous_callers_cannot_delete_anything(self) -> None:
        assert (
            APIClient().post("/api/account/delete", {}, format="json").status_code
            == 401
        )
