from __future__ import annotations

from typing import TYPE_CHECKING

from django.contrib import admin
from django.http import HttpRequest

from .models import ApiToken, SettingValue

# `admin.ModelAdmin` is generic to django-stubs but NOT subscriptable at
# runtime: class bases are evaluated even under `from __future__ import
# annotations`, so writing `admin.ModelAdmin[ApiToken]` directly raises
# TypeError inside `django.setup()` and takes the whole app registry — and
# every test — down with it. Aliasing under TYPE_CHECKING gives mypy the type
# argument and the interpreter the plain class.
if TYPE_CHECKING:
    _ModelAdmin = admin.ModelAdmin[ApiToken]
    _SettingAdmin = admin.ModelAdmin[SettingValue]
else:
    _ModelAdmin = admin.ModelAdmin
    _SettingAdmin = admin.ModelAdmin


@admin.register(ApiToken)
class ApiTokenAdmin(_ModelAdmin):
    list_display = ("id", "scope", "name", "created_at", "revoked_at")
    list_filter = ("scope",)
    search_fields = ("name",)
    readonly_fields = ("key_hash", "created_at")


@admin.register(SettingValue)
class SettingValueAdmin(_SettingAdmin):
    """Inspect and clear persisted setting overrides (BL-20260906-12).

    A ``locked`` instance-scope row overrides every user preference beneath
    it, and until now the only way to see one — or take the lock off — was a
    shell. Two levers, and they are different: unticking ``locked`` leaves the
    instance default in place but lets users override it again, while deleting
    the row drops the override entirely and the frontend resolver falls back
    to the setting's own default. Deletion is therefore allowed here (unlike
    the analysis admin): these rows are a cache of choices, not a record of
    what happened.

    ``scope_type``/``scope_id``/``key`` are read-only on an existing row: they
    are the unique key the frontend resolves against, so editing one in place
    would silently re-target the override instead of changing it.
    """

    list_display = ("scope_type", "scope_id", "key", "value", "locked", "updated_at")
    list_filter = ("scope_type", "locked")
    search_fields = ("scope_id", "key")
    list_editable = ("locked",)
    readonly_fields = ("updated_at",)

    def get_readonly_fields(
        self, request: HttpRequest, obj: SettingValue | None = None
    ) -> tuple[str, ...]:
        if obj is None:
            return self.readonly_fields
        return (*self.readonly_fields, "scope_type", "scope_id", "key")
