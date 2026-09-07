"""Read-mostly admin for Analysis Studio runs and their share links.

BL-20260906-12: neither model had an admin, so archiving a run or revoking a
share link needed a shell. Both are operator actions with a real audience (a
client asks for a shared link to stop working), and both are soft — a delete
would be the wrong lever:

* ``AnalysisRun.archived_at`` hides a run from the studio; the row stays so a
  provenance trace still resolves.
* ``ShareLink.revoked_at`` kills a URL and *keeps the slug taken*, so nobody
  can re-mint it and quietly resurrect the old link. Deleting the row would
  free the slug, which is exactly the failure the model docstring warns about.

So neither ModelAdmin permits adding or deleting rows, and every field is
displayed read-only: the admin actions are the only writes.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.contrib import admin
from django.db.models import QuerySet
from django.http import HttpRequest
from django.utils import timezone

from .models import AnalysisRun, ShareLink

# See `law_ai.audit.admin`: `admin.ModelAdmin[...]` is not subscriptable at
# runtime, so the type argument lives under TYPE_CHECKING only.
if TYPE_CHECKING:
    _RunAdmin = admin.ModelAdmin[AnalysisRun]
    _ShareAdmin = admin.ModelAdmin[ShareLink]
else:
    _RunAdmin = admin.ModelAdmin
    _ShareAdmin = admin.ModelAdmin


@admin.register(AnalysisRun)
class AnalysisRunAdmin(_RunAdmin):
    list_display = (
        "analysis_id",
        "engine",
        "confidence",
        "requires_human_review",
        "shareable",
        "created_by",
        "created_at",
        "archived_at",
    )
    list_filter = ("engine", "requires_human_review", "shareable")
    search_fields = ("analysis_id", "trace_id")
    date_hierarchy = "created_at"
    readonly_fields = tuple(f.name for f in AnalysisRun._meta.fields)
    actions = ("archive_runs", "unarchive_runs")

    def has_add_permission(self, request: HttpRequest) -> bool:
        return False

    def has_delete_permission(
        self, request: HttpRequest, obj: AnalysisRun | None = None
    ) -> bool:
        return False

    @admin.action(description="Archive selected runs (soft; hides from studio)")
    def archive_runs(
        self, request: HttpRequest, queryset: QuerySet[AnalysisRun]
    ) -> None:
        updated = queryset.filter(archived_at__isnull=True).update(
            archived_at=timezone.now()
        )
        self.message_user(request, f"Archived {updated} run(s).")

    @admin.action(description="Un-archive selected runs")
    def unarchive_runs(
        self, request: HttpRequest, queryset: QuerySet[AnalysisRun]
    ) -> None:
        updated = queryset.filter(archived_at__isnull=False).update(archived_at=None)
        self.message_user(request, f"Un-archived {updated} run(s).")


@admin.register(ShareLink)
class ShareLinkAdmin(_ShareAdmin):
    list_display = (
        "slug",
        "analysis",
        "label",
        "created_by",
        "created_at",
        "revoked_at",
    )
    list_filter = ("revoked_at",)
    search_fields = ("slug", "label", "analysis__analysis_id")
    readonly_fields = tuple(f.name for f in ShareLink._meta.fields)
    actions = ("revoke_links",)

    def has_add_permission(self, request: HttpRequest) -> bool:
        return False

    def has_delete_permission(
        self, request: HttpRequest, obj: ShareLink | None = None
    ) -> bool:
        return False

    @admin.action(description="Revoke selected share links (slug stays taken)")
    def revoke_links(self, request: HttpRequest, queryset: QuerySet[ShareLink]) -> None:
        updated = queryset.filter(revoked_at__isnull=True).update(
            revoked_at=timezone.now()
        )
        self.message_user(request, f"Revoked {updated} share link(s).")
