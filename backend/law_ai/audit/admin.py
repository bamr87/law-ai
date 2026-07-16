from __future__ import annotations

from django.contrib import admin

from .models import AuditEvent


@admin.register(AuditEvent)
class AuditEventAdmin(admin.ModelAdmin):
    list_display = ("id", "kind", "timestamp", "trace_id")
    list_filter = ("kind",)
    search_fields = ("trace_id", "agent_version")
    date_hierarchy = "timestamp"
    readonly_fields = ("kind", "timestamp", "trace_id", "agent_version", "payload")
