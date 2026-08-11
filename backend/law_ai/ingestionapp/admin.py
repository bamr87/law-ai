from __future__ import annotations

from typing import Any

from django.contrib import admin, messages
from django.db.models import QuerySet
from django.http import HttpRequest

from .models import PendingReview


@admin.register(PendingReview)
class PendingReviewAdmin(admin.ModelAdmin):
    """HITL review queue.

    Spec 029: approving here now actually commits to the knowledge graph
    (previously ``approved`` had no consumer at all), and every decision
    records **who** made it — the admin user — plus an optional rationale.
    """

    list_display = (
        "id",
        "source",
        "kind",
        "confidence",
        "created_at",
        "approved",
        "committed_at",
        "commit_error",
    )
    list_filter = ("source", "kind", "approved", "committed_at")
    search_fields = ("id", "source", "reason", "reviewer")
    date_hierarchy = "created_at"
    readonly_fields = (
        "id",
        "source",
        "kind",
        "payload",
        "confidence",
        "reason",
        "created_at",
        "reviewed_at",
        "committed_at",
        "commit_error",
    )
    actions = ("approve_and_commit", "reject_selected")

    @admin.action(description="Approve + commit selected to the knowledge graph")
    def approve_and_commit(
        self, request: HttpRequest, queryset: QuerySet[PendingReview]
    ) -> None:
        from law_ai.ingestionapp.services.approval import (
            commit_approved_review,
            record_decision,
        )
        from asgiref.sync import async_to_sync

        reviewer = getattr(request.user, "username", "") or "admin"
        committed = failed = skipped = 0
        for review in queryset:
            if review.committed_at is not None:
                skipped += 1
                continue
            record_decision(review, approved=True, reviewer=reviewer)
            outcome: dict[str, Any] = async_to_sync(commit_approved_review)(review)
            if outcome.get("committed"):
                committed += 1
            else:
                failed += 1
        if committed:
            self.message_user(
                request, f"{committed} committed to the graph.", messages.SUCCESS
            )
        if skipped:
            self.message_user(
                request, f"{skipped} already committed (skipped).", messages.INFO
            )
        if failed:
            self.message_user(
                request,
                f"{failed} failed — see the commit_error column.",
                messages.ERROR,
            )

    @admin.action(description="Reject selected (record decision, do not commit)")
    def reject_selected(
        self, request: HttpRequest, queryset: QuerySet[PendingReview]
    ) -> None:
        from law_ai.ingestionapp.services.approval import record_decision

        reviewer = getattr(request.user, "username", "") or "admin"
        count = 0
        for review in queryset:
            record_decision(review, approved=False, reviewer=reviewer)
            count += 1
        self.message_user(request, f"{count} rejected.", messages.SUCCESS)
