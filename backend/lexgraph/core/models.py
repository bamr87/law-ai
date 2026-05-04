"""Core ORM models (spec 011 FR-6, FR-8).

* :class:`ApiToken` — replaces the env-only API-key auth from spec 008/009.
"""
from __future__ import annotations

import hashlib
import secrets

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

    class Meta:
        ordering = ["scope", "name"]

    def __str__(self) -> str:  # pragma: no cover
        return f"ApiToken({self.scope}/{self.name})"

    @staticmethod
    def hash_key(raw: str) -> str:
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    @classmethod
    def generate(cls, *, scope: str, name: str = "") -> tuple["ApiToken", str]:
        raw = secrets.token_urlsafe(32)
        token = cls.objects.create(
            scope=scope, name=name, key_hash=cls.hash_key(raw)
        )
        return token, raw
