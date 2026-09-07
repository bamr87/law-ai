from __future__ import annotations

from typing import TYPE_CHECKING

from django.contrib import admin

from .models import AuditEvent

# `admin.ModelAdmin` is generic to django-stubs but NOT subscriptable at
# runtime: class bases are evaluated even under `from __future__ import
# annotations`, so writing `admin.ModelAdmin[AuditEvent]` directly raises
# TypeError inside `django.setup()` and takes the whole app registry — and
# every test — down with it. Aliasing under TYPE_CHECKING gives mypy the type
# argument and the interpreter the plain class.
if TYPE_CHECKING:
    _ModelAdmin = admin.ModelAdmin[AuditEvent]
else:
    _ModelAdmin = admin.ModelAdmin


@admin.register(AuditEvent)
class AuditEventAdmin(_ModelAdmin):
    list_display = ("id", "kind", "timestamp", "trace_id")
    list_filter = ("kind",)
    search_fields = ("trace_id", "agent_version")
    date_hierarchy = "timestamp"
    readonly_fields = ("kind", "timestamp", "trace_id", "agent_version", "payload")
