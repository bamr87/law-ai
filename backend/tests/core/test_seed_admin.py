"""``manage.py seed_admin`` (spec 051 / BL-20260503-17)."""

from __future__ import annotations

from io import StringIO

import pytest
from django.contrib.auth import get_user_model
from django.core.management import call_command

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


def test_seed_admin_is_a_noop_without_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DJANGO_SUPERUSER_USERNAME", raising=False)
    monkeypatch.delenv("DJANGO_SUPERUSER_PASSWORD", raising=False)

    out = StringIO()
    call_command("seed_admin", stdout=out)

    assert "skipped" in out.getvalue()
    assert get_user_model().objects.count() == 0


def test_seed_admin_creates_a_superuser(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DJANGO_SUPERUSER_USERNAME", "e2e-admin")
    monkeypatch.setenv("DJANGO_SUPERUSER_PASSWORD", "hunter2!")
    monkeypatch.setenv("DJANGO_SUPERUSER_EMAIL", "e2e@example.test")

    out = StringIO()
    call_command("seed_admin", stdout=out)

    user = get_user_model().objects.get(username="e2e-admin")
    assert user.is_superuser and user.is_staff and user.is_active
    assert user.email == "e2e@example.test"
    assert user.check_password("hunter2!")
    assert "created 'e2e-admin'" in out.getvalue()


def test_seed_admin_is_idempotent_and_rotates_password(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DJANGO_SUPERUSER_USERNAME", "e2e-admin")
    monkeypatch.setenv("DJANGO_SUPERUSER_PASSWORD", "first")
    call_command("seed_admin")

    monkeypatch.setenv("DJANGO_SUPERUSER_PASSWORD", "second")
    out = StringIO()
    call_command("seed_admin", stdout=out)

    users = get_user_model().objects.filter(username="e2e-admin")
    assert users.count() == 1
    assert users.get().check_password("second")
    assert "updated 'e2e-admin'" in out.getvalue()
