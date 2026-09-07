"""Persisted Analysis Studio runs (spec 007 → BL-20260429-25).

Before this, an analysis existed only as a JSONL provenance trail plus the
HTTP response the caller happened to still have open: refreshing the page lost
it, and ``/api/agents/runs/{trace_id}`` could be reached only by copying a
trace id out of the network tab. :class:`AnalysisRun` stores the request, the
finished response and the trace ids under the ``analysis_id`` the API already
mints, so a run is addressable at ``GET /api/analysis/<analysis_id>``.

The JSONL audit log stays the record of *what happened*; this table is the
user-facing artefact. Losing a row must never fail a run, so every write is
best-effort (see ``analysis/urls.py``).

Soft-delete only (constitution §5): ``archived_at`` hides a run from the API,
nothing deletes the row.
"""

from __future__ import annotations

import re
import secrets
from typing import Any

from django.conf import settings
from django.db import models

#: A user-chosen slug: lowercase words and digits joined by - or _, so a
#: shared URL stays readable and cannot smuggle a path segment.
SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{2,63}$")


class AnalysisRun(models.Model):
    """One completed Analysis Studio run, keyed by its ``analysis_id``."""

    ENGINE_LANGGRAPH = "langgraph"
    ENGINE_DIRECT = "direct"

    analysis_id = models.CharField(primary_key=True, max_length=64)
    # The validated AnalysisRequest, minus nothing: the text is what makes a
    # revisited run intelligible. Confidential work belongs in a local-only
    # deployment (LOCAL_ONLY_MODE), not in a redacted copy of itself.
    request = models.JSONField(default=dict)
    response = models.JSONField(default=dict)
    # Parent provenance trace of the AnalysisStudio agent_call, and the child
    # agent traces it fanned out to — the join the /agents/runs drill-down
    # needs (BL-20260429-14).
    trace_id = models.CharField(max_length=64, default="", db_index=True)
    child_trace_ids = models.JSONField(default=list)
    engine = models.CharField(max_length=32, default="")
    confidence = models.FloatField(default=0.0)
    requires_human_review = models.BooleanField(default=False)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="analysis_runs",
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    archived_at = models.DateTimeField(null=True, blank=True)
    # BL-20260429-26 / spec 036 NFR-PRIV-1: sharing is a per-run property, so
    # a run that must not leave the deployment can be marked unshareable and
    # no slug can ever be minted for it. Confidential-by-deployment installs
    # flip the default with ANALYSIS_SHAREABLE_DEFAULT=false.
    shareable = models.BooleanField(default=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:  # pragma: no cover - admin/debug convenience
        return f"AnalysisRun({self.analysis_id})"

    @property
    def is_archived(self) -> bool:
        return self.archived_at is not None

    def as_payload(self) -> dict[str, Any]:
        """The revisit payload: the original response plus its provenance."""
        payload = dict(self.response)
        payload["persisted"] = True
        payload["created_at"] = self.created_at.isoformat() if self.created_at else None
        payload["trace_id"] = self.trace_id or None
        payload["child_trace_ids"] = list(self.child_trace_ids or [])
        payload["request"] = dict(self.request)
        return payload


class ShareLink(models.Model):
    """A "save & share" bookmark: one slug that resolves to one analysis.

    Slugs are the whole security boundary for an unauthenticated read, so a
    minted one is 32 random bytes unless the owner picks a readable slug
    explicitly. Revocation is a timestamp, never a delete — a revoked slug
    must stay taken so it cannot be re-minted by someone else and quietly
    resurrect an old link.
    """

    slug = models.CharField(primary_key=True, max_length=64)
    analysis = models.ForeignKey(
        AnalysisRun, on_delete=models.CASCADE, related_name="share_links"
    )
    label = models.CharField(max_length=200, default="")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="share_links",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    revoked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:  # pragma: no cover - admin/debug convenience
        return f"ShareLink({self.slug})"

    @property
    def is_active(self) -> bool:
        return self.revoked_at is None

    @staticmethod
    def mint_slug() -> str:
        """An unguessable slug: 32 bytes, ~256 bits of entropy."""
        return secrets.token_urlsafe(32)

    def as_payload(self, *, url_prefix: str = "/shared/") -> dict[str, Any]:
        return {
            "slug": self.slug,
            "url": f"{url_prefix}{self.slug}",
            "analysis_id": self.analysis_id,
            "label": self.label,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "revoked": not self.is_active,
        }


__all__ = ["SLUG_RE", "AnalysisRun", "ShareLink"]
