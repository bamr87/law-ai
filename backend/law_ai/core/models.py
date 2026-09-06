"""Core ORM models (spec 011 FR-6, FR-8).

* :class:`ApiToken` — replaces the env-only API-key auth from spec 008/009.
"""

from __future__ import annotations

import hashlib
import secrets

from django.conf import settings
from django.db import models


class ApiToken(models.Model):
    """An issued API key. ``key_hash`` is the only persisted form."""

    SCOPE_AGENT = "agent"
    SCOPE_ANALYSIS = "analysis"
    SCOPE_GRAPH = "graph"
    SCOPE_LSAT = "lsat"

    scope = models.CharField(max_length=32, db_index=True)
    name = models.CharField(max_length=128, default="")
    key_hash = models.CharField(max_length=128, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    revoked_at = models.DateTimeField(null=True, blank=True)
    # Spec 036 FR-2 / BL-20260503-13: an optional owner. Null keeps the
    # spec-008/009 key-only posture byte-identical (seeded dev keys, CI keys);
    # when set, the key authenticates *as* that Django user, so per-user
    # quotas and ownership checks work for programmatic clients too.
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="api_tokens",
    )

    # BL-20260503-12 / BL-20260811-06: an optional per-token quota as a DRF
    # rate string ("200/min"). Blank means "use the scope's configured rate",
    # so an ordinary key behaves exactly as before.
    rate_limit = models.CharField(max_length=32, default="", blank=True)

    class Meta:
        ordering = ["scope", "name"]

    def __str__(self) -> str:  # pragma: no cover
        return f"ApiToken({self.scope}/{self.name})"

    @staticmethod
    def hash_key(raw: str) -> str:
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    @classmethod
    def generate(
        cls, *, scope: str, name: str = "", user: object | None = None
    ) -> tuple[ApiToken, str]:
        raw = secrets.token_urlsafe(32)
        token = cls.objects.create(
            scope=scope, name=name, key_hash=cls.hash_key(raw), user=user
        )
        return token, raw


class SettingValue(models.Model):
    """A server-persisted setting override (BL-20260830-07 / spec 040).

    Settings were localStorage-only, so a preference did not survive a new
    browser and an admin could not set an instance-wide default at all. This
    is the storage layer for the *same* rows the frontend already resolves:
    the TypeScript ``resolveEffective`` engine (frontend/lib/scope/resolver.ts)
    stays the single implementation of precedence and locking — this table
    only decides which rows exist and who may write them.

    ``scope_id`` is the frontend's opaque scope identifier (``instance:local``
    today, ``user:<pk>`` once a caller signs in), so the two ends agree on
    identity without the backend having to model an org tree it does not have.

    ``value`` is JSON because a setting's type belongs to its definition, not
    to the store; an unparsable row is skipped by the resolver rather than
    crashing a render.
    """

    SCOPE_INSTANCE = "instance"
    SCOPE_USER = "user"

    scope_type = models.CharField(max_length=32, db_index=True)
    scope_id = models.CharField(max_length=128, db_index=True)
    key = models.CharField(max_length=128, db_index=True)
    value = models.JSONField(default=None, null=True, blank=True)
    locked = models.BooleanField(default=False)
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="setting_values",
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["scope_id", "key"]
        constraints = [
            models.UniqueConstraint(
                fields=["scope_type", "scope_id", "key"],
                name="uniq_setting_value_scope_key",
            )
        ]

    def __str__(self) -> str:  # pragma: no cover - admin/debug convenience
        return f"SettingValue({self.scope_id}/{self.key})"

    def as_row(self) -> dict[str, object]:
        """The wire shape, matching the TS ``SettingValue`` interface."""
        return {
            "scopeId": self.scope_id,
            "key": self.key,
            "value": self.value,
            "locked": self.locked,
        }
