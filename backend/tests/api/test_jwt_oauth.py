"""OAuth2 bearer tokens over ``core.ApiToken`` (BL-20260503-13).

The item asked for "JWT/OAuth on top of ``core.ApiToken``" plus the revival of
``python-jose`` and ``passlib`` from the ``[future-auth]`` extra. Each test
below pins one half of that: the grant, the bearer leg on a gated route, the
revocation semantics, and the fact that the two libraries are genuinely
installed and genuinely used (a bcrypt digest on disk, a jose-verifiable JWT
on the wire) rather than merely declared.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from law_ai.core import jwt_auth
from law_ai.core.models import ApiToken, OAuthRefreshToken

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


@pytest.fixture
def client() -> APIClient:
    return APIClient()


@pytest.fixture
def graph_key() -> tuple[ApiToken, str]:
    return ApiToken.generate(scope="graph", name="cli")


def _grant(client: APIClient, raw_key: str):
    return client.post(
        "/api/auth/token",
        {"grant_type": "client_credentials"},
        format="json",
        HTTP_X_API_KEY=raw_key,
    )


# --------------------------------------------------------------------------
# The extra itself
# --------------------------------------------------------------------------
def test_future_auth_extra_is_installed() -> None:
    """`python-jose` + `passlib` must actually be importable, not just declared.

    This is the clause the backlog item states literally. It fails the moment
    backend/Dockerfile stops installing the ``[future-auth]`` extra.
    """
    import jose  # noqa: F401
    import passlib  # noqa: F401

    assert jwt_auth.DEPENDENCIES_AVAILABLE is True


def test_access_token_is_a_jose_verifiable_jwt(graph_key) -> None:
    from jose import jwt as jose_jwt

    token, _raw = graph_key
    signed = jwt_auth.mint_access_token(token)
    assert signed.count(".") == 2
    claims = jose_jwt.get_unverified_claims(signed)
    assert claims["kh"] == token.key_hash
    assert claims["scope"] == "graph"
    assert claims["typ"] == "access"


def test_refresh_secret_is_a_passlib_digest(graph_key) -> None:
    token, _raw = graph_key
    plaintext = jwt_auth.issue_refresh_token(token)
    handle, _, secret = plaintext.partition(".")
    row = OAuthRefreshToken.objects.get(handle=handle)
    # passlib's modular-crypt prefix — nothing else in this repo hashes so.
    assert row.secret_hash.startswith("$pbkdf2-sha256$")
    assert secret not in row.secret_hash
    from passlib.context import CryptContext

    assert CryptContext(schemes=[jwt_auth.HASH_SCHEME]).verify(secret, row.secret_hash)


# --------------------------------------------------------------------------
# The grant
# --------------------------------------------------------------------------
def test_client_credentials_grant_returns_a_bearer_pair(client, graph_key) -> None:
    _token, raw = graph_key
    res = _grant(client, raw)
    assert res.status_code == 200
    body = res.json()
    assert body["token_type"] == "Bearer"
    assert body["scope"] == "graph"
    assert body["expires_in"] == 900
    assert body["access_token"].count(".") == 2
    assert "." in body["refresh_token"]


def test_grant_without_a_key_is_invalid_client(client) -> None:
    res = client.post(
        "/api/auth/token", {"grant_type": "client_credentials"}, format="json"
    )
    assert res.status_code == 401
    assert res.json()["error"] == "invalid_client"


def test_grant_with_an_unknown_key_is_invalid_client(client) -> None:
    res = _grant(client, "not-a-provisioned-key")
    assert res.status_code == 401
    assert res.json()["error"] == "invalid_client"


def test_unsupported_grant_type_is_rejected(client, graph_key) -> None:
    _token, raw = graph_key
    res = client.post(
        "/api/auth/token", {"grant_type": "password"}, format="json", HTTP_X_API_KEY=raw
    )
    assert res.status_code == 400
    assert res.json()["error"] == "unsupported_grant_type"


# --------------------------------------------------------------------------
# The bearer leg on a scope-gated route
# --------------------------------------------------------------------------
def test_bearer_token_satisfies_a_scope_gate(client, graph_key, settings) -> None:
    settings.GRAPH_API_KEY = "env-secret"
    _token, raw = graph_key
    assert client.get("/api/graph/stats").status_code in (401, 403)

    access = _grant(client, raw).json()["access_token"]
    res = client.get("/api/graph/stats", HTTP_AUTHORIZATION=f"Bearer {access}")
    assert res.status_code == 200


def test_bearer_token_carries_its_owner(client, graph_key, django_user_model) -> None:
    user = django_user_model.objects.create_user(username="ada", password="x-1843")
    token, raw = ApiToken.generate(scope="graph", name="ada-cli", user=user)
    assert token.user == user
    access = _grant(client, raw).json()["access_token"]
    me = client.get("/api/auth/me", HTTP_AUTHORIZATION=f"Bearer {access}").json()
    assert me["authenticated"] is True
    assert me["username"] == "ada"
    assert me["scopes"] == ["graph"]


def test_revoking_the_api_token_kills_its_bearer_tokens(
    client, graph_key, settings
) -> None:
    settings.GRAPH_API_KEY = "env-secret"
    token, raw = graph_key
    access = _grant(client, raw).json()["access_token"]
    assert (
        client.get(
            "/api/graph/stats", HTTP_AUTHORIZATION=f"Bearer {access}"
        ).status_code
        == 200
    )

    token.revoked_at = timezone.now()
    token.save(update_fields=["revoked_at"])
    res = client.get("/api/graph/stats", HTTP_AUTHORIZATION=f"Bearer {access}")
    assert res.status_code in (401, 403)


def test_expired_access_token_is_rejected(client, graph_key, settings) -> None:
    settings.GRAPH_API_KEY = "env-secret"
    # A negative TTL mints a token whose `exp` is already in the past — the
    # same rejection path as waiting the real 15 minutes out.
    settings.JWT_ACCESS_TTL_SECONDS = -10
    token, _raw = graph_key
    access = jwt_auth.mint_access_token(token)
    assert jwt_auth.decode_access_token(access) is None
    assert client.get(
        "/api/graph/stats", HTTP_AUTHORIZATION=f"Bearer {access}"
    ).status_code in (401, 403)


def test_tampered_access_token_is_rejected(graph_key) -> None:
    token, _raw = graph_key
    access = jwt_auth.mint_access_token(token)
    head, payload, sig = access.split(".")
    forged = f"{head}.{payload}.{sig[:-2]}xx"
    assert jwt_auth.resolve_access_token(forged) is None


def test_token_signed_by_another_key_is_rejected(graph_key, settings) -> None:
    token, _raw = graph_key
    access = jwt_auth.mint_access_token(token)
    settings.SECRET_KEY = "a-different-signing-key"
    assert jwt_auth.decode_access_token(access) is None


def test_an_unrelated_bearer_header_falls_through(client) -> None:
    """A foreign ``Authorization`` header must not 401 an otherwise-open call."""
    assert (
        client.get(
            "/api/graph/stats", HTTP_AUTHORIZATION="Bearer somebody-elses-token"
        ).status_code
        == 200
    )


def test_key_header_still_wins_over_a_bearer_header(
    client, graph_key, settings
) -> None:
    settings.GRAPH_API_KEY = "env-secret"
    _token, raw = graph_key
    res = client.get(
        "/api/graph/stats",
        HTTP_X_API_KEY=raw,
        HTTP_AUTHORIZATION="Bearer garbage",
    )
    assert res.status_code == 200


# --------------------------------------------------------------------------
# Refresh + revocation
# --------------------------------------------------------------------------
def test_refresh_rotates_and_retires_the_presented_token(client, graph_key) -> None:
    _token, raw = graph_key
    first = _grant(client, raw).json()
    res = client.post(
        "/api/auth/token",
        {"grant_type": "refresh_token", "refresh_token": first["refresh_token"]},
        format="json",
    )
    assert res.status_code == 200
    second = res.json()
    assert second["refresh_token"] != first["refresh_token"]

    old_handle = first["refresh_token"].split(".")[0]
    old = OAuthRefreshToken.objects.get(handle=old_handle)
    assert old.revoked_at is not None
    assert old.rotated_to == second["refresh_token"].split(".")[0]

    replay = client.post(
        "/api/auth/token",
        {"grant_type": "refresh_token", "refresh_token": first["refresh_token"]},
        format="json",
    )
    assert replay.status_code == 400
    assert replay.json()["error"] == "invalid_grant"


def test_refresh_requires_the_secret_half(client, graph_key) -> None:
    _token, raw = graph_key
    refresh = _grant(client, raw).json()["refresh_token"]
    handle = refresh.split(".")[0]
    res = client.post(
        "/api/auth/token",
        {"grant_type": "refresh_token", "refresh_token": f"{handle}.wrong-secret"},
        format="json",
    )
    assert res.status_code == 400
    assert res.json()["error"] == "invalid_grant"


def test_expired_refresh_token_is_rejected(client, graph_key) -> None:
    _token, raw = graph_key
    refresh = _grant(client, raw).json()["refresh_token"]
    row = OAuthRefreshToken.objects.get(handle=refresh.split(".")[0])
    row.expires_at = timezone.now() - timedelta(seconds=1)
    row.save(update_fields=["expires_at"])
    with pytest.raises(jwt_auth.OAuthError, match="expired"):
        jwt_auth.redeem_refresh_token(refresh)


def test_refresh_dies_with_the_underlying_key(client, graph_key) -> None:
    token, raw = graph_key
    refresh = _grant(client, raw).json()["refresh_token"]
    token.revoked_at = timezone.now()
    token.save(update_fields=["revoked_at"])
    res = client.post(
        "/api/auth/token",
        {"grant_type": "refresh_token", "refresh_token": refresh},
        format="json",
    )
    assert res.status_code == 400


def test_revoke_endpoint_kills_a_refresh_token(client, graph_key) -> None:
    _token, raw = graph_key
    refresh = _grant(client, raw).json()["refresh_token"]
    res = client.post("/api/auth/token/revoke", {"token": refresh}, format="json")
    assert res.status_code == 200
    assert res.json()["revoked"] is True
    row = OAuthRefreshToken.objects.get(handle=refresh.split(".")[0])
    assert row.revoked_at is not None
    # RFC 7009 §2.2: revoking an already-dead token is still a 200.
    again = client.post("/api/auth/token/revoke", {"token": refresh}, format="json")
    assert again.status_code == 200
    assert again.json()["revoked"] is False


def test_revoking_an_unknown_token_is_a_noop(client) -> None:
    res = client.post("/api/auth/token/revoke", {"token": "nope.nope"}, format="json")
    assert res.status_code == 200
    assert res.json()["revoked"] is False


# --------------------------------------------------------------------------
# The degraded path — the extra absent (BL-20260906-96)
# --------------------------------------------------------------------------
# `[future-auth]` is installed by backend/Dockerfile and every CI job, so every
# test above exercises the *installed* path. `jwt_auth` also has a whole second
# behaviour for when the two libraries are missing, and nothing covered it —
# which is the worse half to get wrong: an unimportable dependency must degrade
# to "key + session only", never to a 500 or, far worse, to an unsigned token.
class TestDegradesWithoutTheExtra:
    """`DEPENDENCIES_AVAILABLE = False`: the bearer leg disappears cleanly."""

    @pytest.fixture(autouse=True)
    def _no_extra(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(jwt_auth, "DEPENDENCIES_AVAILABLE", False)

    def test_minting_refuses_with_a_503_rather_than_an_import_error(
        self, graph_key
    ) -> None:
        token, _raw = graph_key
        with pytest.raises(jwt_auth.OAuthError) as excinfo:
            jwt_auth.mint_access_token(token)
        assert excinfo.value.status == 503
        assert excinfo.value.code == "temporarily_unavailable"

    def test_the_grant_endpoint_answers_503(self, client, graph_key) -> None:
        _token, raw = graph_key
        res = _grant(client, raw)
        assert res.status_code == 503
        assert res.json()["error"] == "temporarily_unavailable"

    def test_decoding_returns_none_instead_of_raising(self) -> None:
        """A bearer header must not 500 the request that carries it."""
        assert jwt_auth.decode_access_token("anything.at.all") is None
        assert jwt_auth.resolve_access_token("anything.at.all") is None

    def test_a_bearer_header_falls_through_to_the_other_credentials(
        self, client, graph_key, settings
    ) -> None:
        """The whole promise of the degradation: key + session still work."""
        settings.GRAPH_API_KEY = "env-secret"
        _token, raw = graph_key

        refused = client.get(
            "/api/graph/stats", HTTP_AUTHORIZATION="Bearer not-a-real-token"
        )
        assert refused.status_code in (401, 403)

        allowed = client.get("/api/graph/stats", HTTP_X_API_KEY=raw)
        assert allowed.status_code not in (401, 403)
