"""Operator levers that used to need a shell (BL-20260906-12).

``SettingValue``, ``AnalysisRun`` and ``ShareLink`` had no Django admin, so
clearing a locked instance-wide setting, archiving a run, or revoking a share
link meant `manage.py shell`. These tests pin the registrations *and* the two
properties that make them safe to hand an operator: an analysis run and a
share link can only be soft-changed (archive / revoke), never deleted, because
freeing a slug would let an old share URL be re-minted.

``admin.site.check()`` runs Django's own admin system checks, so a
``list_editable`` or ``readonly_fields`` mistake fails here rather than at the
first page load.
"""

from __future__ import annotations

import pytest
from django.contrib import admin
from django.contrib.messages.storage.fallback import FallbackStorage
from django.test import RequestFactory

from law_ai.analysis.models import AnalysisRun, ShareLink
from law_ai.core.models import SettingValue

pytestmark = pytest.mark.unit


def _request() -> object:
    """A real HttpRequest with message storage, so ``message_user`` works."""
    request = RequestFactory().post("/admin/")
    request.session = {}
    request._messages = FallbackStorage(request)
    return request


@pytest.mark.parametrize("model", [SettingValue, AnalysisRun, ShareLink])
def test_model_is_registered_in_the_admin(model: type) -> None:
    assert model in admin.site._registry, f"{model.__name__} has no ModelAdmin"


def test_admin_configuration_passes_djangos_own_checks() -> None:
    errors = admin.site.check(None)
    assert not errors, [str(e) for e in errors]


class TestSoftOnlyWrites:
    """Archive and revoke are timestamps; delete is not offered at all."""

    @pytest.mark.parametrize("model", [AnalysisRun, ShareLink])
    def test_rows_cannot_be_added_or_deleted_from_the_admin(self, model: type) -> None:
        model_admin = admin.site._registry[model]
        assert model_admin.has_add_permission(None) is False  # type: ignore[arg-type]
        assert model_admin.has_delete_permission(None) is False  # type: ignore[arg-type]

    def test_the_soft_actions_are_the_ones_offered(self) -> None:
        run_admin = admin.site._registry[AnalysisRun]
        share_admin = admin.site._registry[ShareLink]
        assert "archive_runs" in run_admin.actions
        assert "unarchive_runs" in run_admin.actions
        assert "revoke_links" in share_admin.actions


@pytest.mark.django_db
class TestActionsDoTheSoftThing:
    def test_archive_and_unarchive_flip_archived_at(self) -> None:
        run = AnalysisRun.objects.create(analysis_id="an-1")
        run_admin = admin.site._registry[AnalysisRun]
        qs = AnalysisRun.objects.filter(pk=run.pk)

        run_admin.archive_runs(_request(), qs)  # type: ignore[attr-defined]
        run.refresh_from_db()
        assert run.archived_at is not None

        run_admin.unarchive_runs(_request(), qs)  # type: ignore[attr-defined]
        run.refresh_from_db()
        assert run.archived_at is None

    def test_revoking_a_share_link_keeps_the_slug_row(self) -> None:
        run = AnalysisRun.objects.create(analysis_id="an-2")
        link = ShareLink.objects.create(slug="keep-me", analysis=run)
        share_admin = admin.site._registry[ShareLink]

        share_admin.revoke_links(  # type: ignore[attr-defined]
            _request(), ShareLink.objects.filter(pk=link.pk)
        )
        link.refresh_from_db()
        assert link.revoked_at is not None
        # The slug must stay taken so it cannot be re-minted (models.ShareLink).
        assert ShareLink.objects.filter(slug="keep-me").exists()


class TestSettingValueAdmin:
    def test_the_identity_columns_lock_once_a_row_exists(self) -> None:
        """Editing scope/key in place would re-target the override."""
        model_admin = admin.site._registry[SettingValue]
        fresh = model_admin.get_readonly_fields(None)  # type: ignore[arg-type]
        existing = model_admin.get_readonly_fields(  # type: ignore[arg-type]
            None, SettingValue(scope_type="instance", scope_id="i", key="k")
        )
        assert "key" not in fresh
        assert {"scope_type", "scope_id", "key"} <= set(existing)

    def test_locked_is_editable_from_the_changelist(self) -> None:
        """Taking a lock off is the whole point of the registration."""
        model_admin = admin.site._registry[SettingValue]
        assert "locked" in model_admin.list_editable
