from __future__ import annotations

from django.contrib import admin

from .models import PendingReview


@admin.register(PendingReview)
class PendingReviewAdmin(admin.ModelAdmin):
    list_display = ("id", "source", "confidence", "created_at", "approved")
    list_filter = ("source", "approved")
    search_fields = ("id", "source", "reason")
    date_hierarchy = "created_at"
    readonly_fields = ("id", "source", "payload", "confidence", "reason", "created_at")
