"""Server-persisted setting values (BL-20260830-07 / spec 040).

The authorisation half is the point: `user:<pk>` is an IDOR surface, and the
anonymous path must keep behaving exactly as it did when settings lived only
in localStorage.
"""

from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from law_ai.core.models import SettingValue

pytestmark = [pytest.mark.unit, pytest.mark.django_db]

INSTANCE = "instance:local"


@pytest.fixture
def client() -> APIClient:
    return APIClient()


@pytest.fixture
def user():
    return get_user_model().objects.create_user(username="ada", password="pw-123456")


@pytest.fixture
def admin():
    return get_user_model().objects.create_user(
        username="root", password="pw-123456", is_staff=True
    )


# --------------------------------------------------------------------------
# Reading
# --------------------------------------------------------------------------
def test_anonymous_callers_see_only_instance_rows(client: APIClient, user) -> None:
    SettingValue.objects.create(
        scope_type="instance", scope_id=INSTANCE, key="shell.density", value="cosy"
    )
    SettingValue.objects.create(
        scope_type="user", scope_id=f"user:{user.pk}", key="shell.rail", value=False
    )

    body = client.get("/api/settings/values").json()
    assert body["scopes"] == [INSTANCE]
    assert [row["key"] for row in body["values"]] == ["shell.density"]


def test_a_signed_in_user_sees_their_own_chain(client: APIClient, user) -> None:
    SettingValue.objects.create(
        scope_type="instance", scope_id=INSTANCE, key="shell.density", value="cosy"
    )
    SettingValue.objects.create(
        scope_type="user", scope_id=f"user:{user.pk}", key="shell.rail", value=False
    )
    other = get_user_model().objects.create_user(username="bob", password="pw-123456")
    SettingValue.objects.create(
        scope_type="user", scope_id=f"user:{other.pk}", key="shell.rail", value=True
    )

    client.force_login(user)
    body = client.get("/api/settings/values").json()
    assert body["scopes"] == [INSTANCE, f"user:{user.pk}"]
    keys = sorted(row["key"] for row in body["values"])
    assert keys == ["shell.density", "shell.rail"]
    # Someone else's row is not in the chain.
    assert all(row["scopeId"] != f"user:{other.pk}" for row in body["values"])


def test_the_wire_shape_matches_the_typescript_setting_value(
    client: APIClient,
) -> None:
    SettingValue.objects.create(
        scope_type="instance",
        scope_id=INSTANCE,
        key="shell.density",
        value="cosy",
        locked=True,
    )
    row = client.get("/api/settings/values").json()["values"][0]
    assert set(row) == {"scopeId", "key", "value", "locked"}
    assert row == {
        "scopeId": INSTANCE,
        "key": "shell.density",
        "value": "cosy",
        "locked": True,
    }


# --------------------------------------------------------------------------
# Writing
# --------------------------------------------------------------------------
def test_a_user_writes_their_own_scope(client: APIClient, user) -> None:
    client.force_login(user)
    res = client.put(
        f"/api/settings/values/user:{user.pk}/shell.rail",
        {"value": False},
        format="json",
    )
    assert res.status_code == 201
    row = SettingValue.objects.get(scope_id=f"user:{user.pk}", key="shell.rail")
    assert row.value is False
    assert row.updated_by == user
    assert row.scope_type == "user"


def test_the_me_alias_resolves_to_the_caller(client: APIClient, user) -> None:
    client.force_login(user)
    res = client.put(
        "/api/settings/values/user:me/shell.rail", {"value": True}, format="json"
    )
    assert res.status_code == 201
    assert res.json()["scopeId"] == f"user:{user.pk}"


def test_writing_someone_elses_scope_is_403(client: APIClient, user) -> None:
    victim = get_user_model().objects.create_user(username="bob", password="pw-123456")
    client.force_login(user)
    res = client.put(
        f"/api/settings/values/user:{victim.pk}/shell.rail",
        {"value": True},
        format="json",
    )
    assert res.status_code == 403
    assert "not your settings scope" in res.json()["detail"]
    assert not SettingValue.objects.exists()


def test_anonymous_writes_are_refused(client: APIClient) -> None:
    res = client.put(
        f"/api/settings/values/{INSTANCE}/shell.density",
        {"value": "cosy"},
        format="json",
    )
    assert res.status_code == 403
    assert not SettingValue.objects.exists()


def test_instance_scope_is_staff_only(client: APIClient, user, admin) -> None:
    client.force_login(user)
    assert (
        client.put(
            f"/api/settings/values/{INSTANCE}/shell.density",
            {"value": "cosy"},
            format="json",
        ).status_code
        == 403
    )

    staff = APIClient()
    staff.force_login(admin)
    res = staff.put(
        f"/api/settings/values/{INSTANCE}/shell.density",
        {"value": "cosy", "locked": True},
        format="json",
    )
    assert res.status_code == 201
    assert SettingValue.objects.get(scope_id=INSTANCE, key="shell.density").locked


def test_a_second_write_updates_rather_than_duplicating(
    client: APIClient, user
) -> None:
    client.force_login(user)
    scope = f"user:{user.pk}"
    client.put(f"/api/settings/values/{scope}/shell.rail", {"value": 1}, format="json")
    res = client.put(
        f"/api/settings/values/{scope}/shell.rail", {"value": 2}, format="json"
    )
    assert res.status_code == 200
    assert SettingValue.objects.filter(scope_id=scope, key="shell.rail").count() == 1
    assert SettingValue.objects.get(scope_id=scope, key="shell.rail").value == 2


def test_a_body_without_value_is_400(client: APIClient, user) -> None:
    client.force_login(user)
    res = client.put(
        f"/api/settings/values/user:{user.pk}/shell.rail", {}, format="json"
    )
    assert res.status_code == 400


def test_an_oversized_value_is_refused(client: APIClient, user) -> None:
    client.force_login(user)
    res = client.put(
        f"/api/settings/values/user:{user.pk}/shell.rail",
        {"value": "x" * 5000},
        format="json",
    )
    assert res.status_code == 413
    assert not SettingValue.objects.exists()


def test_an_unknown_scope_kind_is_refused(client: APIClient, user) -> None:
    client.force_login(user)
    res = client.put(
        "/api/settings/values/org:acme/shell.rail", {"value": True}, format="json"
    )
    assert res.status_code == 403
    assert "unknown scope" in res.json()["detail"]


# --------------------------------------------------------------------------
# Clearing
# --------------------------------------------------------------------------
def test_delete_clears_an_override(client: APIClient, user) -> None:
    client.force_login(user)
    scope = f"user:{user.pk}"
    client.put(f"/api/settings/values/{scope}/shell.rail", {"value": 1}, format="json")

    res = client.delete(f"/api/settings/values/{scope}/shell.rail")
    assert res.status_code == 200
    assert res.json()["deleted"] is True
    assert not SettingValue.objects.filter(scope_id=scope).exists()


def test_delete_of_a_missing_row_is_404(client: APIClient, user) -> None:
    client.force_login(user)
    res = client.delete(f"/api/settings/values/user:{user.pk}/nope")
    assert res.status_code == 404


def test_delete_cannot_reach_another_scope(client: APIClient, user, admin) -> None:
    SettingValue.objects.create(
        scope_type="instance", scope_id=INSTANCE, key="shell.density", value="cosy"
    )
    client.force_login(user)
    assert (
        client.delete(f"/api/settings/values/{INSTANCE}/shell.density").status_code
        == 403
    )
    assert SettingValue.objects.filter(scope_id=INSTANCE).exists()


def test_writes_are_provenance_logged(
    client: APIClient, user, monkeypatch: pytest.MonkeyPatch
) -> None:
    from law_ai.core import urls_settings

    seen: list[tuple[str, dict]] = []
    monkeypatch.setattr(
        urls_settings.provenance,
        "log_event",
        lambda kind, payload: seen.append((kind, payload)),
    )
    client.force_login(user)
    scope = f"user:{user.pk}"
    client.put(f"/api/settings/values/{scope}/shell.rail", {"value": 1}, format="json")
    client.delete(f"/api/settings/values/{scope}/shell.rail")

    assert [kind for kind, _ in seen] == [
        "setting_value.updated",
        "setting_value.deleted",
    ]
    assert all(payload["actor"] == "ada" for _, payload in seen)
