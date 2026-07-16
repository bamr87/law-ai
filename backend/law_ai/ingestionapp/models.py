"""HITL quarantine queue (spec 011 FR-6, AC-4).

Embeds the spec-004 `pending_review` schema verbatim via a `RunSQL` op
in the initial migration so existing rows are preserved on cutover.
"""

from __future__ import annotations

from django.db import models


class PendingReview(models.Model):
    """An extraction quarantined for human approval.

    ``kind`` is the spec-015 discriminator that lets one queue serve cases,
    statutes, ordinances, regulations, and derived documents. Constants live
    in :mod:`law_ai.ingestionapp.quarantine_kinds`.
    """

    id = models.TextField(primary_key=True)
    source = models.TextField(db_index=True)
    kind = models.CharField(max_length=32, default="case", db_index=True)
    payload = models.JSONField()
    confidence = models.FloatField()
    reason = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    approved = models.BooleanField(null=True, default=None)

    class Meta:
        db_table = "pending_review"  # adopt the legacy table name
        ordering = ["-created_at"]

    def __str__(self) -> str:  # pragma: no cover
        return f"PendingReview({self.id}, {self.source}, conf={self.confidence:.2f})"
