"""HITL quarantine queue (spec 011 FR-6, AC-4).

Embeds the spec-004 `pending_review` schema verbatim via a `RunSQL` op
in the initial migration so existing rows are preserved on cutover.
"""

from __future__ import annotations

from django.conf import settings
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

    # --- Reviewer identity (spec 029; BL-20260810-08) --------------------
    # An audit-first platform cannot have anonymous, rationale-free review
    # decisions. Both are free-text so non-Django review surfaces (CLI,
    # future API) can record who decided and why.
    reviewer = models.TextField(blank=True, default="")
    review_note = models.TextField(blank=True, default="")

    # BL-20260811-04 / spec 036 T-003: the free-text column above cannot be
    # joined to anything, so "who approved this" was unverifiable. Now that
    # accounts exist, a decision made by a signed-in reviewer also records the
    # account. Nullable and SET_NULL: CLI/env-key decisions still have only the
    # string, and deleting a user must never erase the decision itself (§4).
    reviewer_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="quarantine_reviews",
    )

    # --- Commit tracking (spec 029; BL-20260810-03) ----------------------
    # `approved` alone cannot express "approved but the graph write failed".
    # These make the approval → commit handoff idempotent and auditable.
    committed_at = models.DateTimeField(null=True, blank=True, db_index=True)
    commit_error = models.TextField(blank=True, default="")

    class Meta:
        db_table = "pending_review"  # adopt the legacy table name
        ordering = ["-created_at"]

    def __str__(self) -> str:  # pragma: no cover
        return f"PendingReview({self.id}, {self.source}, conf={self.confidence:.2f})"

    @property
    def is_committed(self) -> bool:
        """True once the approved item has reached the knowledge graph."""
        return self.committed_at is not None

    @property
    def awaits_commit(self) -> bool:
        """Approved by a human but not yet written to the graph."""
        return self.approved is True and self.committed_at is None
