"""Matters — the spine the legal journey hangs off (spec 036, BL-2026081x).

Everything in this platform used to be a one-shot: an analysis, a research
round, a quarantine decision. Nothing said *what they were about*, so the
journey stages the product promises (intake → research → analysis → action)
had no object to attach to, and five BACKLOG items were blocked on the same
missing noun.

A :class:`Matter` is that noun: a user-owned container carrying the issue tags
that describe the legal question, the artifacts produced while working it, the
authorities verified along the way, and the tasks it generated.

Design rules the rest of the app leans on:

* **Ownership is server-side.** A matter is addressed by ``slug`` in URLs but
  every lookup is filtered by ``owner``; the slug is unique *per owner*, never
  globally, so one user's slug says nothing about another's (the IDOR trap
  BL-20260830-08 names).
* **PROTECT on the owner.** Deleting a user must not silently take their
  matters — and with them, the audit context of everything inside — with it.
  ``PROTECT`` forces account deletion through the deliberate service in
  ``law_ai.matters.services.deletion`` (BL-20260817-01).
* **Soft delete only** (constitution §5): ``archived_at`` hides a row; nothing
  here is ever hard-deleted.
"""

from __future__ import annotations

import re
from typing import Any

from django.conf import settings
from django.db import models

#: A matter slug: lowercase words and digits joined by - or _. Short enough to
#: type, constrained so it cannot smuggle a path segment into a URL.
SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{2,63}$")


class Matter(models.Model):
    """One legal question a user is working, with its journey stage."""

    STAGE_INTAKE = "intake"
    STAGE_RESEARCH = "research"
    STAGE_ANALYSIS = "analysis"
    STAGE_ACTION = "action"
    STAGE_REVIEW = "review"
    STAGES = (
        STAGE_INTAKE,
        STAGE_RESEARCH,
        STAGE_ANALYSIS,
        STAGE_ACTION,
        STAGE_REVIEW,
    )

    slug = models.CharField(max_length=64, db_index=True)
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True, default="")
    #: Free-form doctrine/issue slugs ("contract-formation", "negligence").
    #: The study-plan linkage (BL-20260817-04) maps these onto LSAT concepts.
    issue_tags = models.JSONField(default=list, blank=True)
    jurisdiction = models.CharField(max_length=64, blank=True, default="")
    stage = models.CharField(max_length=16, default=STAGE_INTAKE, db_index=True)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="matters",
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)
    archived_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-updated_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["owner", "slug"], name="uniq_matter_owner_slug"
            )
        ]

    def __str__(self) -> str:  # pragma: no cover - admin/debug convenience
        return f"Matter({self.slug})"

    @property
    def is_archived(self) -> bool:
        return self.archived_at is not None

    def as_row(self) -> dict[str, Any]:
        """The list shape: identity only, never another user's data."""
        return {
            "id": self.pk,
            "slug": self.slug,
            "name": self.name,
            "stage": self.stage,
            "issue_tags": list(self.issue_tags or []),
            "jurisdiction": self.jurisdiction,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

    def as_payload(self) -> dict[str, Any]:
        body = self.as_row()
        body.update(
            {
                "description": self.description,
                "created_at": (
                    self.created_at.isoformat() if self.created_at else None
                ),
                "archived": self.is_archived,
            }
        )
        return body


class MatterArtifact(models.Model):
    """Something produced while working a matter: a note, an analysis, a draft."""

    KIND_NOTE = "note"
    KIND_ANALYSIS = "analysis"
    KIND_RESEARCH = "research"
    KIND_DRAFT = "draft"
    KIND_DOCUMENT = "document"
    KINDS = (KIND_NOTE, KIND_ANALYSIS, KIND_RESEARCH, KIND_DRAFT, KIND_DOCUMENT)

    matter = models.ForeignKey(
        Matter, on_delete=models.CASCADE, related_name="artifacts"
    )
    kind = models.CharField(max_length=32, default=KIND_NOTE, db_index=True)
    title = models.CharField(max_length=200, blank=True, default="")
    body = models.JSONField(default=dict, blank=True)
    #: Provenance join: the trace that produced this artifact, when an agent did.
    trace_id = models.CharField(max_length=64, blank=True, default="", db_index=True)
    #: The persisted Analysis Studio run this artifact points at, if any.
    analysis_id = models.CharField(max_length=64, blank=True, default="")
    source = models.CharField(max_length=64, blank=True, default="")
    confidence = models.FloatField(default=0.0)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="matter_artifacts",
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    archived_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:  # pragma: no cover
        return f"MatterArtifact({self.matter_id}, {self.kind})"

    def as_payload(self) -> dict[str, Any]:
        return {
            "id": self.pk,
            "kind": self.kind,
            "title": self.title,
            "body": self.body,
            "trace_id": self.trace_id,
            "analysis_id": self.analysis_id,
            "source": self.source,
            "confidence": self.confidence,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class MatterAuthority(models.Model):
    """An authority (case, statute section) this matter relies on.

    ``verified_at`` is the HITL gate: an authority a human has checked is the
    only kind the retrieval boost set will promote (BL-20260817-05), because
    boosting an unverified hallucination would be worse than not boosting at
    all.
    """

    matter = models.ForeignKey(
        Matter, on_delete=models.CASCADE, related_name="authorities"
    )
    #: Graph node id (``Case.id``/``StatuteSection.id``) this refers to.
    node_id = models.CharField(max_length=128, db_index=True)
    node_label = models.CharField(max_length=32, default="Case")
    citation = models.CharField(max_length=256, blank=True, default="")
    title = models.CharField(max_length=256, blank=True, default="")
    note = models.TextField(blank=True, default="")
    source = models.CharField(max_length=64, blank=True, default="")
    confidence = models.FloatField(default=0.0)
    verified_at = models.DateTimeField(null=True, blank=True)
    verified_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="verified_authorities",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    archived_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["matter", "node_id"], name="uniq_matter_authority_node"
            )
        ]

    def __str__(self) -> str:  # pragma: no cover
        return f"MatterAuthority({self.matter_id}, {self.node_id})"

    @property
    def is_verified(self) -> bool:
        return self.verified_at is not None

    def as_payload(self) -> dict[str, Any]:
        return {
            "id": self.pk,
            "node_id": self.node_id,
            "node_label": self.node_label,
            "citation": self.citation,
            "title": self.title,
            "note": self.note,
            "source": self.source,
            "confidence": self.confidence,
            "verified": self.is_verified,
            "verified_at": (self.verified_at.isoformat() if self.verified_at else None),
        }


class MatterTask(models.Model):
    """A dated piece of work in a matter's action stage (BL-20260817-02).

    Due dates are **user-entered**: spec 036 NG1 rules out computing court
    deadlines from rules of procedure, and nothing here does. A task is a
    reminder the user set for themselves.
    """

    STATUS_OPEN = "open"
    STATUS_DONE = "done"
    STATUS_CANCELLED = "cancelled"
    STATUSES = (STATUS_OPEN, STATUS_DONE, STATUS_CANCELLED)

    matter = models.ForeignKey(Matter, on_delete=models.CASCADE, related_name="tasks")
    title = models.CharField(max_length=200)
    detail = models.TextField(blank=True, default="")
    due_at = models.DateTimeField(null=True, blank=True, db_index=True)
    status = models.CharField(max_length=16, default=STATUS_OPEN, db_index=True)
    source_artifact = models.ForeignKey(
        MatterArtifact,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="tasks",
    )
    #: Set once a reminder has been emitted, so the beat never double-notifies.
    reminded_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="matter_tasks",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    archived_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["due_at", "-created_at"]
        indexes = [models.Index(fields=["status", "due_at"])]

    def __str__(self) -> str:  # pragma: no cover
        return f"MatterTask({self.matter_id}, {self.title})"

    def as_payload(self) -> dict[str, Any]:
        return {
            "id": self.pk,
            "title": self.title,
            "detail": self.detail,
            "due_at": self.due_at.isoformat() if self.due_at else None,
            "status": self.status,
            "source_artifact_id": self.source_artifact_id,
            "reminded_at": (self.reminded_at.isoformat() if self.reminded_at else None),
            "completed_at": (
                self.completed_at.isoformat() if self.completed_at else None
            ),
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


__all__ = [
    "SLUG_RE",
    "Matter",
    "MatterArtifact",
    "MatterAuthority",
    "MatterTask",
]
