"""Account endpoints — session login/logout/whoami (spec 036 FR-2, T-002).

Two credential families live here, and which one a client should use depends
on whether it is a browser.

**Session cookie** (spec 036 RQ-1) is what the first-party Next.js frontend
uses: same-origin, CSRF-enforced, and safer than parking a bearer token in
browser storage.

**OAuth2 bearer token** (BL-20260503-13) is what everything else uses. The
item asked for "JWT/OAuth on top of ``core.ApiToken``", and that is what
``POST token`` implements: an RFC 6749 §4.4 client-credentials grant that
exchanges an ``X-API-Key`` for a short-lived ``python-jose`` JWT plus a
rotating refresh token whose secret is stored as a ``passlib`` pbkdf2 digest.
The mechanics live in :mod:`law_ai.core.jwt_auth`; the two libraries come from
the ``[future-auth]`` extra, which the backend image now installs.

Routes (mounted at ``/api/auth/``):

* ``GET  csrf``   — issue the CSRF cookie a browser client needs before POSTing.
* ``POST login``  — ``{"username", "password"}`` → session cookie.
* ``POST logout`` — drop the session.
* ``GET  me``     — who the current caller is (session, owned key, or neither).
* ``POST token``  — ``grant_type=client_credentials`` (with ``X-API-Key``) or
  ``grant_type=refresh_token`` → ``{access_token, refresh_token, …}``.
* ``POST token/revoke`` — RFC 7009 revocation of a refresh token.

Every route is ``AllowAny``: they *establish* identity, so gating them on the
scope-key permission would be circular. Login attempts and grants are
provenance-logged (never the password, never the token) so a
credential-stuffing burst is visible in the audit trail.
"""

from __future__ import annotations

from typing import Any

from django.contrib.auth import (
    authenticate,
    login,
    logout,
)
from django.middleware.csrf import get_token
from django.urls import path
from django.views.decorators.debug import (
    sensitive_post_parameters,
)
from django.utils.decorators import method_decorator
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from law_ai.core.auth import is_signed_in
from law_ai.core.jwt_auth import (
    OAuthError,
    issue_token_pair,
    redeem_refresh_token,
    revoke_refresh_token,
)
from law_ai.core.models import ApiToken
from law_ai.core.provenance import provenance


def user_payload(request: Any) -> dict[str, Any]:
    """Serialise the caller's identity for ``me``/``login`` responses."""
    token = getattr(request, "auth", None)
    scopes = [token.scope] if isinstance(token, ApiToken) else []
    if not is_signed_in(request):
        return {
            "authenticated": False,
            "username": None,
            "id": None,
            "is_staff": False,
            "scopes": scopes,
        }
    user = request.user
    return {
        "authenticated": True,
        "username": user.get_username(),
        "id": user.pk,
        "is_staff": bool(getattr(user, "is_staff", False)),
        "email": getattr(user, "email", "") or "",
        "scopes": scopes,
    }


class CsrfView(APIView):
    """Hand a browser client the CSRF cookie + token before it POSTs."""

    permission_classes = [AllowAny]

    def get(self, request: Any, *args: Any, **kwargs: Any) -> Response:
        return Response({"csrf_token": get_token(request._request)})


@method_decorator(sensitive_post_parameters("password"), name="dispatch")
class LoginView(APIView):
    permission_classes = [AllowAny]

    def post(self, request: Any, *args: Any, **kwargs: Any) -> Response:
        data = request.data if isinstance(request.data, dict) else {}
        username = str(data.get("username") or "").strip()
        password = str(data.get("password") or "")
        if not username or not password:
            return Response(
                {"detail": "username and password are required"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        user = authenticate(request._request, username=username, password=password)
        if user is None or not user.is_active:
            provenance.log_event(
                "auth_login_failed",
                {"source": "api", "username": username[:150]},
            )
            return Response(
                {"detail": "invalid credentials"},
                status=status.HTTP_401_UNAUTHORIZED,
            )
        login(request._request, user)
        request.user = user
        provenance.log_event(
            "auth_login", {"source": "api", "username": user.get_username()}
        )
        return Response(user_payload(request))


class LogoutView(APIView):
    permission_classes = [AllowAny]

    def post(self, request: Any, *args: Any, **kwargs: Any) -> Response:
        was = is_signed_in(request)
        username = request.user.get_username() if was else None
        logout(request._request)
        if was:
            provenance.log_event("auth_logout", {"source": "api", "username": username})
        return Response({"authenticated": False, "was_authenticated": was})


class MeView(APIView):
    permission_classes = [AllowAny]

    def get(self, request: Any, *args: Any, **kwargs: Any) -> Response:
        return Response(user_payload(request))


@method_decorator(sensitive_post_parameters("refresh_token"), name="dispatch")
class TokenView(APIView):
    """RFC 6749 token endpoint (BL-20260503-13).

    ``client_credentials`` trades the caller's ``X-API-Key`` for a bearer pair;
    ``refresh_token`` rotates an existing pair without re-presenting the key.
    A grant never widens authority: the minted token carries the issuing
    ``ApiToken``'s scope and dies when that row is revoked.
    """

    permission_classes = [AllowAny]

    def post(self, request: Any, *args: Any, **kwargs: Any) -> Response:
        data = request.data if isinstance(request.data, dict) else {}
        grant = str(data.get("grant_type") or "").strip()
        try:
            if grant == "client_credentials":
                pair = issue_token_pair(self._token_from_key(request))
            elif grant == "refresh_token":
                raw = str(data.get("refresh_token") or "").strip()
                if not raw:
                    raise OAuthError(
                        "invalid_request", "refresh_token is required", status=400
                    )
                pair = redeem_refresh_token(raw)
            else:
                raise OAuthError(
                    "unsupported_grant_type",
                    "grant_type must be client_credentials or refresh_token",
                    status=400,
                )
        except OAuthError as exc:
            provenance.log_event(
                "auth_token_denied",
                {"source": "api", "grant_type": grant, "error": exc.code},
            )
            return Response(
                {"error": exc.code, "error_description": exc.description},
                status=exc.status,
            )
        provenance.log_event(
            "auth_token_issued",
            {"source": "api", "grant_type": grant, "scope": pair.scope},
        )
        return Response(pair.as_response())

    @staticmethod
    def _token_from_key(request: Any) -> ApiToken:
        raw = request.META.get("HTTP_X_API_KEY") or ""
        if not raw:
            raise OAuthError(
                "invalid_client", "X-API-Key header is required", status=401
            )
        try:
            return ApiToken.objects.select_related("user").get(
                key_hash=ApiToken.hash_key(raw), revoked_at__isnull=True
            )
        except ApiToken.DoesNotExist:
            # The env-key fallback deliberately does not grant here: an
            # env key has no ApiToken row, so there is nothing to scope a
            # bearer token to and nothing to revoke it by.
            raise OAuthError(
                "invalid_client", "no provisioned key matches", status=401
            ) from None


@method_decorator(sensitive_post_parameters("token"), name="dispatch")
class TokenRevokeView(APIView):
    """RFC 7009 revocation. Always 200 — an unknown token is a no-op."""

    permission_classes = [AllowAny]

    def post(self, request: Any, *args: Any, **kwargs: Any) -> Response:
        data = request.data if isinstance(request.data, dict) else {}
        raw = str(data.get("token") or "").strip()
        revoked = revoke_refresh_token(raw) if raw else False
        provenance.log_event(
            "auth_token_revoked", {"source": "api", "revoked": revoked}
        )
        return Response({"revoked": revoked})


urlpatterns = [
    path("csrf", CsrfView.as_view(), name="auth-csrf"),
    path("login", LoginView.as_view(), name="auth-login"),
    path("logout", LogoutView.as_view(), name="auth-logout"),
    path("me", MeView.as_view(), name="auth-me"),
    path("token", TokenView.as_view(), name="auth-token"),
    path("token/revoke", TokenRevokeView.as_view(), name="auth-token-revoke"),
]
