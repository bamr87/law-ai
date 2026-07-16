from __future__ import annotations

from django.contrib import admin

from .models import ApiToken


@admin.register(ApiToken)
class ApiTokenAdmin(admin.ModelAdmin):
    list_display = ("id", "scope", "name", "created_at", "revoked_at")
    list_filter = ("scope",)
    search_fields = ("name",)
    readonly_fields = ("key_hash", "created_at")
