"""OAuth2 bearer tokens on top of ``core.ApiToken`` (BL-20260503-13).

Spec 011 planned "JWT/OAuth on top of ``core.ApiToken``" and parked the two
libraries it needs (``python-jose``, ``passlib``) in the ``[future-auth]``
extra. This module is that plan, wired: it does **not** replace the
``X-API-Key`` header or the session cookie, it adds a third, additive leg for
the case those two do not cover — a programmatic client that must hold a
credential with a short life and a revocable renewal path.

The grant is RFC 6749 §4.4 *client credentials* with RFC 6749 §6 *refresh*:

* ``POST /api/auth/token`` with ``grant_type=client_credentials`` and an
  ``X-API-Key`` header exchanges the long-lived key for a short-lived access
  token plus a refresh token. The key itself then stays out of every
  subsequent request.
* ``POST /api/auth/token`` with ``grant_type=refresh_token`` rotates: the
  presented refresh token is retired and a fresh pair is issued.
* ``POST /api/auth/token/revoke`` (RFC 7009) kills a refresh token.

**Access token** — a ``python-jose`` HS256 JWT signed with ``SECRET_KEY``,
carrying the issuing token's ``key_hash`` in the private ``kh`` claim. It is
stateless by design (no DB write per request), which is exactly why its TTL is
minutes: nothing can recall one early. Authorisation is unchanged —
:class:`JwtBearerAuthentication` resolves ``kh`` back to the ``ApiToken`` row
and hands DRF the same ``(actor, token)`` pair the header path produces, so
``HasScope``, the throttles and the ownership checks all see one principal
model rather than two.

**Refresh token** — an opaque ``<handle>.<secret>`` string whose secret half is
stored as a ``passlib`` digest on :class:`~law_ai.core.models.OAuthRefreshToken`.
A deliberately slow, salted scheme rather than the plain SHA-256
``ApiToken.hash_key`` uses, because a refresh token is presented rarely (so the
work factor costs nothing) and lives long (so an offline attack on a leaked
table is the realistic threat). The scheme is ``pbkdf2_sha256``, which passlib
implements itself: passlib 1.7.4's bcrypt backend probes with a 73-byte
password and modern ``bcrypt`` releases raise on it, so ``[bcrypt]`` would
break on import in this image.

Every issue, refresh, rejection and revocation is provenance-logged, so a
credential-stuffing burst against this endpoint is visible in the audit trail.
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from django.conf import settings
from django.utils import timezone
from rest_framework import authentication
from rest_framework.request import Request

from law_ai.core.models import ApiToken, OAuthRefreshToken

try:  # pragma: no cover - exercised by test_jwt_extra_is_installed
    from jose import jwt as _jose_jwt
    from passlib.context import CryptContext as _CryptContext

    DEPENDENCIES_AVAILABLE = True
except ModuleNotFoundError:  # pragma: no cover - only on a host without the extra
    _jose_jwt = None
    _CryptContext = None
    DEPENDENCIES_AVAILABLE = False


ALGORITHM = "HS256"
TOKEN_TYPE = "Bearer"

#: Marks our own tokens so an unrelated ``Authorization: Bearer`` header
#: (another gateway's, say) is ignored rather than rejected outright.
ACCESS_TOKEN_TYPE = "access"


class OAuthError(Exception):
    """An RFC 6749 §5.2 error response, raised by the grant helpers."""

    def __init__(self, code: str, description: str, status: int = 400) -> None:
        super().__init__(description)
        self.code = code
        self.description = description
        self.status = status


@dataclass(frozen=True)
class TokenPair:
    """What a successful grant returns; ``refresh_token`` is shown once."""

    access_token: str
    refresh_token: str
    expires_in: int
    scope: str

    def as_response(self) -> dict[str, Any]:
        return {
            "access_token": self.access_token,
            "token_type": TOKEN_TYPE,
            "expires_in": self.expires_in,
            "refresh_token": self.refresh_token,
            "scope": self.scope,
        }


def _require_dependencies() -> None:
    if not DEPENDENCIES_AVAILABLE:  # pragma: no cover - guarded install path
        raise OAuthError(
            "temporarily_unavailable",
            "the [future-auth] extra (python-jose, passlib) is not installed",
            status=503,
        )


#: passlib's own PBKDF2 implementation — no compiled backend, so no exposure
#: to the passlib-1.7.4 / bcrypt-4.1 backend-probe incompatibility.
HASH_SCHEME = "pbkdf2_sha256"


def _crypt_context() -> Any:
    _require_dependencies()
    return _CryptContext(schemes=[HASH_SCHEME], deprecated="auto")


def _signing_key() -> str:
    return str(settings.SECRET_KEY)


def _issuer() -> str:
    return str(getattr(settings, "JWT_ISSUER", "law-ai"))


def access_ttl() -> int:
    return int(getattr(settings, "JWT_ACCESS_TTL_SECONDS", 900))


def refresh_ttl() -> int:
    return int(getattr(settings, "JWT_REFRESH_TTL_SECONDS", 1_209_600))


def mint_access_token(token: ApiToken) -> str:
    """Sign a short-lived JWT that stands in for ``token``."""
    _require_dependencies()
    now = datetime.now(UTC)
    ttl = access_ttl()
    owner = token.user
    claims: dict[str, Any] = {
        "iss": _issuer(),
        "sub": owner.get_username() if owner is not None else f"api-key:{token.scope}",
        "scope": token.scope,
        # Private claim: the ApiToken this bearer stands for. Storing the
        # hash (not the pk) means a dumped JWT reveals nothing a stolen key
        # would not already reveal, and the lookup stays a unique-index hit.
        "kh": token.key_hash,
        "typ": ACCESS_TOKEN_TYPE,
        "jti": secrets.token_urlsafe(12),
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(seconds=ttl)).timestamp()),
    }
    signed: str = _jose_jwt.encode(claims, _signing_key(), algorithm=ALGORITHM)
    return signed


def decode_access_token(raw: str) -> dict[str, Any] | None:
    """Verify a JWT and return its claims, or ``None`` if it is not ours."""
    if not DEPENDENCIES_AVAILABLE:
        return None
    try:
        claims: dict[str, Any] = _jose_jwt.decode(
            raw,
            _signing_key(),
            algorithms=[ALGORITHM],
            issuer=_issuer(),
            options={"require_exp": True},
        )
    except Exception:
        # jose raises a family of JWTError subclasses (expired, bad
        # signature, wrong issuer). None of them are distinguishable to a
        # caller without leaking which check failed, so all are one answer.
        return None
    if claims.get("typ") != ACCESS_TOKEN_TYPE:
        return None
    return claims


def resolve_access_token(raw: str) -> ApiToken | None:
    """Map a bearer JWT back to a live, non-revoked ``ApiToken`` row."""
    claims = decode_access_token(raw)
    if claims is None:
        return None
    key_hash = str(claims.get("kh") or "")
    if not key_hash:
        return None
    try:
        return ApiToken.objects.select_related("user").get(
            key_hash=key_hash, revoked_at__isnull=True
        )
    except ApiToken.DoesNotExist:
        # Revoking the ApiToken invalidates every JWT minted from it, which
        # is the only kill switch a stateless access token has.
        return None


def issue_refresh_token(token: ApiToken) -> str:
    """Create a refresh row for ``token`` and return the one-time plaintext."""
    _require_dependencies()
    handle = secrets.token_urlsafe(9)
    secret = secrets.token_urlsafe(32)
    OAuthRefreshToken.objects.create(
        handle=handle,
        secret_hash=_crypt_context().hash(secret),
        api_token=token,
        expires_at=timezone.now() + timedelta(seconds=refresh_ttl()),
    )
    return f"{handle}.{secret}"


def _lookup_refresh(raw: str) -> OAuthRefreshToken:
    handle, _, secret = raw.partition(".")
    if not handle or not secret:
        raise OAuthError("invalid_grant", "malformed refresh token", status=400)
    try:
        row = OAuthRefreshToken.objects.select_related("api_token__user").get(
            handle=handle
        )
    except OAuthRefreshToken.DoesNotExist:
        raise OAuthError("invalid_grant", "unknown refresh token", status=400) from None
    if not _crypt_context().verify(secret, row.secret_hash):
        raise OAuthError("invalid_grant", "unknown refresh token", status=400)
    return row


def redeem_refresh_token(raw: str) -> TokenPair:
    """Rotate ``raw``: retire it and issue a fresh pair for the same key."""
    row = _lookup_refresh(raw)
    now = timezone.now()
    if row.revoked_at is not None:
        raise OAuthError("invalid_grant", "refresh token was revoked", status=400)
    if row.expires_at <= now:
        raise OAuthError("invalid_grant", "refresh token expired", status=400)
    token = row.api_token
    if token.revoked_at is not None:
        raise OAuthError("invalid_grant", "the underlying key was revoked", status=400)
    pair = issue_token_pair(token)
    new_handle, _, _ = pair.refresh_token.partition(".")
    row.revoked_at = now
    row.rotated_to = new_handle
    row.save(update_fields=["revoked_at", "rotated_to"])
    return pair


def revoke_refresh_token(raw: str) -> bool:
    """RFC 7009 revocation. Returns whether a live row was actually killed."""
    try:
        row = _lookup_refresh(raw)
    except OAuthError:
        # RFC 7009 §2.2: an unknown token is a successful revocation.
        return False
    if row.revoked_at is not None:
        return False
    row.revoked_at = timezone.now()
    row.save(update_fields=["revoked_at"])
    return True


def issue_token_pair(token: ApiToken) -> TokenPair:
    """The whole grant: an access JWT plus a rotating refresh token."""
    _require_dependencies()
    return TokenPair(
        access_token=mint_access_token(token),
        refresh_token=issue_refresh_token(token),
        expires_in=access_ttl(),
        scope=token.scope,
    )


def bearer_from(request: Request | Any) -> str | None:
    """Extract the raw bearer credential, if this request carries one."""
    header = request.META.get("HTTP_AUTHORIZATION") or ""
    prefix, _, value = header.partition(" ")
    if prefix.lower() != "bearer" or not value.strip():
        return None
    return value.strip()


class JwtBearerAuthentication(authentication.BaseAuthentication):
    """``Authorization: Bearer <jwt>`` → the same principal the key produces.

    Registered as a standalone DRF class as well as being chained inside
    :class:`law_ai.core.auth.ApiKeyAuthentication`, so a view that overrides
    ``authentication_classes`` can still opt into the bearer path alone.
    """

    def authenticate(self, request: Request) -> tuple[Any, ApiToken] | None:
        raw = bearer_from(request)
        if raw is None:
            return None
        token = resolve_access_token(raw)
        if token is None:
            # Not our token (or no longer valid): fall through to the other
            # credentials rather than 401-ing a request that may carry one.
            return None
        from law_ai.core.auth import _AnonymousActor

        actor: object = token.user or _AnonymousActor(token.scope, token.key_hash)
        return actor, token

    def authenticate_header(self, request: Request) -> str:
        return f'{TOKEN_TYPE} realm="api"'


__all__ = [
    "ACCESS_TOKEN_TYPE",
    "ALGORITHM",
    "DEPENDENCIES_AVAILABLE",
    "HASH_SCHEME",
    "TOKEN_TYPE",
    "JwtBearerAuthentication",
    "OAuthError",
    "TokenPair",
    "access_ttl",
    "bearer_from",
    "decode_access_token",
    "issue_refresh_token",
    "issue_token_pair",
    "mint_access_token",
    "redeem_refresh_token",
    "refresh_ttl",
    "resolve_access_token",
    "revoke_refresh_token",
]
