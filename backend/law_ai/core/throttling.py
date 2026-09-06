"""Per-principal rate limiting (BL-20260811-06, BL-20260503-12).

DRF's ``ScopedRateThrottle`` buckets on ``request.user.pk`` when the request
is authenticated and otherwise on the client IP. Neither is right here:

* **IP is wrong behind a shared proxy.** Everyone in one office, or every user
  of one deployment's reverse proxy, shares a bucket and starves each other —
  the complaint in BL-20260811-06.
* **``user.pk`` was a latent 500.** ``ApiKeyAuthentication`` returns a
  lightweight ``_AnonymousActor`` for an unowned key. It sets
  ``is_authenticated = True`` but had no ``pk``, so DRF's
  ``request.user.pk`` raised ``AttributeError`` — on *every* throttled view a
  provisioned key touched. No test sent a key at a throttled route, so nothing
  caught it (BL-20260503-12's evidence).

:class:`ScopedActorRateThrottle` picks the narrowest principal it can prove
and buckets on that:

1. a provisioned ``ApiToken`` → its ``key_hash`` (per-token quota, which is
   what BL-20260503-12 asked for; ``django-ratelimit`` is not needed for it);
2. a signed-in Django user → their pk (per-user quota, spec 036 FR-2);
3. neither → the client IP, exactly as before.

An identified principal is also *trusted more*: it gets the ``<scope>_keyed``
rate when one is configured, so a signed-in user behind a shared proxy is not
held to the anonymous limit. A single ``ApiToken`` may carry its own
``rate_limit`` (a DRF rate string like ``"200/min"``) which overrides both.
"""

from __future__ import annotations

from typing import Any

from rest_framework.throttling import (
    ScopedRateThrottle,
)

from law_ai.core.models import ApiToken

#: ``(kind, ident, token)`` — the resolved principal for one request.
Principal = tuple[str, str, "ApiToken | None"]


def resolve_principal(request: Any, fallback_ident: str) -> Principal:
    """Narrowest provable identity for *request*.

    ``fallback_ident`` is the caller's IP-derived identity, used only when
    nothing better is known.
    """
    token = getattr(request, "auth", None)
    if isinstance(token, ApiToken):
        return "key", token.key_hash, token
    user = getattr(request, "user", None)
    pk = getattr(user, "pk", None)
    if pk is not None and getattr(user, "is_authenticated", False):
        return "user", str(pk), None
    return "ip", fallback_ident, None


class ScopedActorRateThrottle(ScopedRateThrottle):
    """``ScopedRateThrottle`` that buckets per token / per user / per IP."""

    #: Set in :meth:`allow_request` before the base class reads the rate.
    _principal: Principal = ("ip", "", None)

    def allow_request(self, request: Any, view: Any) -> bool:
        self._principal = resolve_principal(request, self.get_ident(request))
        return bool(super().allow_request(request, view))

    def get_rate(self) -> str | None:
        """Per-token override, then the keyed rate, then the anonymous rate."""
        _kind, _ident, token = self._principal
        if token is not None and token.rate_limit:
            return str(token.rate_limit)
        if _kind != "ip":
            keyed = self.THROTTLE_RATES.get(f"{self.scope}_keyed")
            if keyed:
                return str(keyed)
        rate: str | None = super().get_rate()
        return rate

    def get_cache_key(self, request: Any, view: Any) -> str | None:
        if not getattr(self, "scope", None):
            return None
        kind, ident, _token = self._principal
        # e.g. "throttle_llm_key:<sha256>", "throttle_llm_user:7",
        # "throttle_llm_ip:203.0.113.4" — distinct namespaces, so changing
        # principal can never collide with someone else's bucket.
        return str(
            self.cache_format % {"scope": self.scope, "ident": f"{kind}:{ident}"}
        )


__all__ = ["Principal", "ScopedActorRateThrottle", "resolve_principal"]
