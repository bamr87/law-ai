from __future__ import annotations

from typing import TYPE_CHECKING

from django.contrib import admin

from .models import ApiToken

# `admin.ModelAdmin` is generic to django-stubs but NOT subscriptable at
# runtime: class bases are evaluated even under `from __future__ import
# annotations`, so writing `admin.ModelAdmin[ApiToken]` directly raises
# TypeError inside `django.setup()` and takes the whole app registry — and
# every test — down with it. Aliasing under TYPE_CHECKING gives mypy the type
# argument and the interpreter the plain class.
if TYPE_CHECKING:
    _ModelAdmin = admin.ModelAdmin[ApiToken]
else:
    _ModelAdmin = admin.ModelAdmin


@admin.register(ApiToken)
class ApiTokenAdmin(_ModelAdmin):
    list_display = ("id", "scope", "name", "created_at", "revoked_at")
    list_filter = ("scope",)
    search_fields = ("name",)
    readonly_fields = ("key_hash", "created_at")
