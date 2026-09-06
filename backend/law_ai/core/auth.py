"""DRF authentication + permissions (spec 011 FR-8, AC-2)."""

from __future__ import annotations

import secrets

from django.conf import settings
from rest_framework import authentication, exceptions, permissions
from rest_framework.request import Request

from law_ai.core.jwt_auth import JwtBearerAuthentication
from law_ai.core.models import ApiToken


class _AnonymousActor:
    """Lightweight stand-in for an authenticated principal.

    ``pk`` exists because DRF reads ``request.user.pk`` on any throttled view
    once ``is_authenticated`` is True; without it a provisioned key raised
    ``AttributeError`` there (BL-20260503-12). It carries the token's
    ``key_hash`` so even a default DRF throttle buckets per key rather than
    lumping every key together.
    """

    is_authenticated = True

    def __init__(self, scope: str | None, pk: str | None = None) -> None:
        self.scope = scope
        self.pk = pk

    def __str__(self) -> str:
        return f"api-key:{self.scope or 'open'}"


class ApiKeyAuthentication(authentication.BaseAuthentication):
    """Read ``X-API-Key`` header, look up via ``ApiToken.key_hash``.

    Spec 036 FR-2 / BL-20260503-13 adds a second, additive leg: when no
    ``X-API-Key`` header is present, an authenticated Django **session** is
    accepted (CSRF-enforced, exactly as DRF's ``SessionAuthentication`` does).
    Key-only callers are unaffected — with no session cookie the session leg
    returns ``None`` and the behaviour is byte-identical to spec 011.

    BL-20260503-13 adds the third leg the item named: an
    ``Authorization: Bearer <jwt>`` access token minted from an ``ApiToken``
    by the OAuth2 grant in :mod:`law_ai.core.jwt_auth`. It resolves to the
    *same* ``(actor, ApiToken)`` pair the header path produces, so ``HasScope``
    and the throttles need no bearer-specific branch. Order is
    header → bearer → session: a request that carries a key means it, and an
    unrelated ``Authorization`` header falls through instead of 401-ing.

    No credential at all → no authentication (downstream permission decides,
    so the local-first open gate still works).
    """

    keyword = "X-API-Key"

    def __init__(self) -> None:
        # Delegate the cookie/CSRF half to DRF rather than re-deriving it.
        self._session = authentication.SessionAuthentication()
        self._bearer = JwtBearerAuthentication()

    def authenticate(self, request: Request):
        raw = request.META.get("HTTP_X_API_KEY")
        if not raw:
            bearer = self._bearer.authenticate(request)
            if bearer is not None:
                return bearer
            return self._session.authenticate(request)
        digest = ApiToken.hash_key(raw)
        try:
            token = ApiToken.objects.select_related("user").get(
                key_hash=digest, revoked_at__isnull=True
            )
        except ApiToken.DoesNotExist:
            # Defer to the env-key fallback path in HasScope before failing.
            return None
        # A token bound to an owner authenticates *as* that user, so ownership
        # checks and per-user quotas see the same principal as a session login.
        actor: object = token.user or _AnonymousActor(token.scope, token.key_hash)
        return (actor, token)

    def authenticate_header(self, request: Request) -> str:
        return self.keyword


def is_signed_in(request: Request) -> bool:
    """True when the caller is a real Django user (session or owned token)."""
    user = getattr(request, "user", None)
    if user is None or isinstance(user, _AnonymousActor):
        return False
    return bool(getattr(user, "is_authenticated", False))


def _resolve_env_key(*setting_names: str) -> str | None:
    for name in setting_names:
        value = getattr(settings, name, None)
        if value:
            return value
    return None


class HasScope(permissions.BasePermission):
    """Permission factory for per-router scope gating.

    Falls back to env-driven keys when no ``ApiToken`` is provisioned for the
    requested scope, preserving the spec-008/009 local-first dev posture.
    """

    setting_names: tuple[str, ...] = ()
    scope: str = ""

    def has_permission(self, request: Request, view) -> bool:
        scopes = (self.scope, *self.setting_names)
        env_expected = _resolve_env_key(*self.setting_names)
        token = getattr(request, "auth", None)

        # 1. ApiToken-driven path: any provisioned token with matching scope wins.
        if token is not None and isinstance(token, ApiToken):
            return token.scope in {self.scope, "agent"} or token.scope in scopes

        # 1b. Signed-in Django session (spec 036 FR-2): a real user account is
        # an accepted credential alongside a scope key. Anonymous key-only
        # callers never reach this branch.
        if is_signed_in(request):
            return True

        # 2. No DB token + no env key configured → open (local-first dev).
        if env_expected is None:
            return True

        # 3. Env key configured → require X-API-Key header to match.
        raw = request.META.get("HTTP_X_API_KEY")
        if raw is None:
            raise exceptions.AuthenticationFailed("missing api key")
        if not secrets.compare_digest(raw, env_expected):
            raise exceptions.AuthenticationFailed("invalid api key")
        return True


def has_scope(scope: str, *fallback_envs: str) -> type[HasScope]:
    """Build a parameterised :class:`HasScope` subclass for view ``permission_classes``."""

    cls_name = f"HasScope_{scope}"

    return type(
        cls_name,
        (HasScope,),
        {"scope": scope, "setting_names": tuple(fallback_envs)},
    )


# Convenience factories matching the legacy ``make_api_key_dep`` helpers.
RequireAgent: type[HasScope] = has_scope("agent", "AGENT_API_KEY")
RequireAnalysis: type[HasScope] = has_scope(
    "analysis", "ANALYSIS_API_KEY", "AGENT_API_KEY"
)
RequireGraph: type[HasScope] = has_scope("graph", "GRAPH_API_KEY", "AGENT_API_KEY")
RequireLsat: type[HasScope] = has_scope("lsat", "LSAT_API_KEY", "AGENT_API_KEY")


__all__ = [
    "ApiKeyAuthentication",
    "HasScope",
    "JwtBearerAuthentication",
    "RequireAgent",
    "RequireAnalysis",
    "RequireGraph",
    "RequireLsat",
    "has_scope",
    "is_signed_in",
]
