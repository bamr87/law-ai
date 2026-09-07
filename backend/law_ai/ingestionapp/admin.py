from __future__ import annotations

from typing import TYPE_CHECKING, Any

from django.contrib import admin, messages
from django.db.models import QuerySet
from django.http import HttpRequest

from .models import PendingReview

# `admin.ModelAdmin` is generic to django-stubs but NOT subscriptable at
# runtime: class bases are evaluated even under `from __future__ import
# annotations`, so writing `admin.ModelAdmin[PendingReview]` directly raises
# TypeError inside `django.setup()` and takes the whole app registry — and
# every test — down with it. Aliasing under TYPE_CHECKING gives mypy the type
# argument and the interpreter the plain class.
if TYPE_CHECKING:
    _ModelAdmin = admin.ModelAdmin[PendingReview]
else:
    _ModelAdmin = admin.ModelAdmin


@admin.register(PendingReview)
class PendingReviewAdmin(_ModelAdmin):
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
    actions = ("approve_and_commit", "reject_selected", "reextract_selected")

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
            record_decision(
                review, approved=True, reviewer=reviewer, reviewer_user=request.user
            )
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
            record_decision(
                review, approved=False, reviewer=reviewer, reviewer_user=request.user
            )
            count += 1
        self.message_user(request, f"{count} rejected.", messages.SUCCESS)

    @admin.action(description="Re-extract selected (refresh confidence, no commit)")
    def reextract_selected(
        self, request: HttpRequest, queryset: QuerySet[PendingReview]
    ) -> None:
        """Re-run the current extractor over each row's stored raw document.

        BL-20260503-10's third verb. Never commits: a fresh score that clears
        the threshold still needs a human approval (constitution §5).
        """
        from law_ai.ingestionapp.services.approval import (
            ApprovalError,
            reextract_review,
        )

        reviewer = getattr(request.user, "username", "") or "admin"
        refreshed = cleared = failed = 0
        for review in queryset:
            try:
                outcome = reextract_review(review, reviewer=reviewer)
            except ApprovalError as exc:
                failed += 1
                self.message_user(request, str(exc), messages.WARNING)
                continue
            if outcome.get("reextracted"):
                refreshed += 1
                if outcome.get("clears_threshold"):
                    cleared += 1
            elif outcome.get("error"):
                failed += 1
        if refreshed:
            self.message_user(request, f"{refreshed} re-extracted.", messages.SUCCESS)
        if cleared:
            self.message_user(
                request,
                f"{cleared} now clear the confidence threshold — approve to commit.",
                messages.INFO,
            )
        if failed:
            self.message_user(
                request, f"{failed} could not be re-extracted.", messages.ERROR
            )
