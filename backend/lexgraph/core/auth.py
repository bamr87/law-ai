"""DRF authentication + permissions (spec 011 FR-8, AC-2)."""

from __future__ import annotations

import secrets

from django.conf import settings
from rest_framework import authentication, exceptions, permissions
from rest_framework.request import Request

from lawgraph.core.models import ApiToken


class _AnonymousActor:
    """Lightweight stand-in for an authenticated principal."""

    is_authenticated = True

    def __init__(self, scope: str | None) -> None:
        self.scope = scope

    def __str__(self) -> str:
        return f"api-key:{self.scope or 'open'}"


class ApiKeyAuthentication(authentication.BaseAuthentication):
    """Read ``X-API-Key`` header, look up via ``ApiToken.key_hash``.

    No header → no authentication (downstream permission decides).
    """

    keyword = "X-API-Key"

    def authenticate(self, request: Request):
        raw = request.META.get("HTTP_X_API_KEY")
        if not raw:
            return None
        digest = ApiToken.hash_key(raw)
        try:
            token = ApiToken.objects.get(key_hash=digest, revoked_at__isnull=True)
        except ApiToken.DoesNotExist:
            # Defer to the env-key fallback path in HasScope before failing.
            return None
        return (_AnonymousActor(token.scope), token)

    def authenticate_header(self, request: Request) -> str:
        return self.keyword


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

    return type(  # type: ignore[return-value]
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
    "RequireAgent",
    "RequireAnalysis",
    "RequireGraph",
    "RequireLsat",
    "has_scope",
]
