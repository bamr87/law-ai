"""Session accounts + user-bound API tokens (spec 036 FR-2 / BL-20260503-13).

Two halves matter here: the new session leg works, and the old key-only leg
is byte-identical. The second half is why ``test_scope_key_path_unchanged*``
exist — the DRF auth class is on the request path of every API test, so a
regression there is silent until something 500s in production.
"""

from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from law_ai.core.models import ApiToken

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


@pytest.fixture
def client() -> APIClient:
    return APIClient()


@pytest.fixture
def user():
    return get_user_model().objects.create_user(
        username="ada", password="lovelace-1843", email="ada@example.test"
    )


# --------------------------------------------------------------------------
# /api/auth/*
# --------------------------------------------------------------------------
def test_me_is_anonymous_without_credentials(client: APIClient) -> None:
    res = client.get("/api/auth/me")
    assert res.status_code == 200
    assert res.json() == {
        "authenticated": False,
        "username": None,
        "id": None,
        "is_staff": False,
        "scopes": [],
    }


def test_csrf_route_issues_a_token_and_cookie(client: APIClient) -> None:
    res = client.get("/api/auth/csrf")
    assert res.status_code == 200
    assert res.json()["csrf_token"]
    assert "csrftoken" in res.cookies


def test_login_then_me_then_logout(client: APIClient, user) -> None:
    res = client.post(
        "/api/auth/login",
        {"username": "ada", "password": "lovelace-1843"},
        format="json",
    )
    assert res.status_code == 200
    body = res.json()
    assert body["authenticated"] is True
    assert body["username"] == "ada"
    assert body["id"] == user.pk
    assert body["email"] == "ada@example.test"

    me = client.get("/api/auth/me").json()
    assert me["authenticated"] is True and me["username"] == "ada"

    out = client.post("/api/auth/logout", {}, format="json")
    assert out.status_code == 200
    assert out.json() == {"authenticated": False, "was_authenticated": True}
    assert client.get("/api/auth/me").json()["authenticated"] is False


def test_login_rejects_bad_password(client: APIClient, user) -> None:
    res = client.post(
        "/api/auth/login", {"username": "ada", "password": "wrong"}, format="json"
    )
    assert res.status_code == 401
    assert res.json()["detail"] == "invalid credentials"
    assert client.get("/api/auth/me").json()["authenticated"] is False


def test_login_rejects_inactive_user(client: APIClient, user) -> None:
    user.is_active = False
    user.save()
    res = client.post(
        "/api/auth/login",
        {"username": "ada", "password": "lovelace-1843"},
        format="json",
    )
    assert res.status_code == 401


def test_login_requires_both_fields(client: APIClient) -> None:
    res = client.post("/api/auth/login", {"username": "ada"}, format="json")
    assert res.status_code == 400


def test_logout_without_a_session_is_a_noop(client: APIClient) -> None:
    res = client.post("/api/auth/logout", {}, format="json")
    assert res.status_code == 200
    assert res.json()["was_authenticated"] is False


# --------------------------------------------------------------------------
# Session as a credential on a scope-gated route
# --------------------------------------------------------------------------
def test_session_satisfies_a_scope_gate_when_an_env_key_is_set(
    client: APIClient, user, settings
) -> None:
    settings.GRAPH_API_KEY = "env-secret"
    # Anonymous: env key configured, no header → rejected as before.
    assert client.get("/api/graph/stats").status_code in (401, 403)

    client.force_login(user)
    assert client.get("/api/graph/stats").status_code == 200


def test_signed_in_user_does_not_bypass_scope_for_anonymous_callers(
    client: APIClient, settings
) -> None:
    """No session → the env-key gate behaves exactly as it did pre-036."""
    settings.GRAPH_API_KEY = "env-secret"
    assert client.get("/api/graph/stats").status_code in (401, 403)
    res = client.get("/api/graph/stats", HTTP_X_API_KEY="env-secret")
    assert res.status_code == 200


# --------------------------------------------------------------------------
# ApiToken.user
# --------------------------------------------------------------------------
def test_api_token_user_is_optional(client: APIClient) -> None:
    token, raw = ApiToken.generate(scope="graph", name="ci")
    assert token.user is None
    assert client.get("/api/graph/stats", HTTP_X_API_KEY=raw).status_code == 200
    # An unowned key is still an anonymous actor — no account is implied.
    me = client.get("/api/auth/me", HTTP_X_API_KEY=raw).json()
    assert me["authenticated"] is False and me["scopes"] == ["graph"]


def test_owned_token_authenticates_as_its_user(client: APIClient, user) -> None:
    _token, raw = ApiToken.generate(scope="agent", name="ada-cli", user=user)
    me = client.get("/api/auth/me", HTTP_X_API_KEY=raw).json()
    assert me["authenticated"] is True
    assert me["username"] == "ada"
    assert me["scopes"] == ["agent"]


def test_revoked_owned_token_does_not_authenticate(
    client: APIClient, user, settings
) -> None:
    from django.utils import timezone

    token, raw = ApiToken.generate(scope="graph", name="ada-cli", user=user)
    token.revoked_at = timezone.now()
    token.save()
    settings.GRAPH_API_KEY = "env-secret"
    assert client.get("/api/graph/stats", HTTP_X_API_KEY=raw).status_code in (401, 403)


def test_scope_key_path_unchanged_for_unowned_tokens(
    client: APIClient, settings
) -> None:
    """A DB token still wins over a mismatched env key, as in spec 011."""
    settings.GRAPH_API_KEY = "env-secret"
    _token, raw = ApiToken.generate(scope="graph", name="ops")
    assert client.get("/api/graph/stats", HTTP_X_API_KEY=raw).status_code == 200
