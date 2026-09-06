"""Account endpoints — session login/logout/whoami (spec 036 FR-2, T-002).

BL-20260503-13 asked for JWT/OAuth on top of ``core.ApiToken``. Spec 036 RQ-1
decided against it: the only client today is the first-party Next.js frontend
on the same origin, for which a Django session cookie plus CSRF is both
simpler and safer than a bearer token in browser storage; programmatic clients
keep using ``X-API-Key``, now optionally bound to a user
(:attr:`law_ai.core.models.ApiToken.user`). The JWT mechanism stays deferred
until a third-party client exists, so ``python-jose``/``passlib`` remain
unused under the ``[future-auth]`` extra.

Routes (mounted at ``/api/auth/``):

* ``GET  csrf``   — issue the CSRF cookie a browser client needs before POSTing.
* ``POST login``  — ``{"username", "password"}`` → session cookie.
* ``POST logout`` — drop the session.
* ``GET  me``     — who the current caller is (session, owned key, or neither).

Every route is ``AllowAny``: they *establish* identity, so gating them on the
scope-key permission would be circular. Login attempts are provenance-logged
(never the password) so a credential-stuffing burst is visible in the audit
trail.
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


urlpatterns = [
    path("csrf", CsrfView.as_view(), name="auth-csrf"),
    path("login", LoginView.as_view(), name="auth-login"),
    path("logout", LogoutView.as_view(), name="auth-logout"),
    path("me", MeView.as_view(), name="auth-me"),
]
