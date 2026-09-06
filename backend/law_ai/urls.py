"""Root URLconf (spec 011 FR-9).

Every API surface from ``backend/app/api/`` ports here unchanged in
shape. ``/health`` stays open; everything under ``/api/`` is gated by
``ApiKeyAuthentication`` + per-router ``HasScope`` permissions
(``backend/law_ai/core/auth.py``).
"""

from __future__ import annotations

from django.contrib import admin
from django.http import JsonResponse
from django.urls import include, path


def root(_request: object) -> JsonResponse:
    """Service banner for the API root."""
    return JsonResponse(
        {
            "message": "Law AI - Open Legal Intelligence Platform",
            "version": "0.1.0",
            "status": "operational",
            "docs": "/admin/doc/",
            "agents": "/api/agents",
        }
    )


urlpatterns = [
    path("", root),
    path("admin/", admin.site.urls),
    # Both trailing-slash and slashless variants are accepted so the
    # URL shape is stable for existing clients.
    path("health", include("law_ai.core.urls_health")),
    path("health/", include("law_ai.core.urls_health")),
    # Session accounts (spec 036 FR-2 / BL-20260503-13). Additive: the
    # X-API-Key path is unchanged and these routes are AllowAny.
    path("api/auth/", include("law_ai.core.urls_auth")),
    # Server-persisted setting values (BL-20260830-07). The precedence engine
    # stays in the frontend; this is storage + authorisation only.
    path("api/settings/", include("law_ai.core.urls_settings")),
    path("api/agents", include("law_ai.agentsapi.urls")),
    path("api/agents/", include("law_ai.agentsapi.urls")),
    path("api/analysis", include("law_ai.analysis.urls")),
    path("api/analysis/", include("law_ai.analysis.urls")),
    # Public share links (BL-20260429-26): unauthenticated by design, the
    # slug is the credential. See law_ai/analysis/urls_shared.py.
    path("api/shared/", include("law_ai.analysis.urls_shared")),
    path("api/graph/", include("law_ai.graph.urls")),
    path("api/lsat/", include("law_ai.lsat.urls")),
    # Matters — the user-owned spine of the legal journey (spec 036). Every
    # route is session-gated and owner-scoped; see law_ai/matters/urls.py.
    path("api/matters", include("law_ai.matters.urls")),
    path("api/matters/", include("law_ai.matters.urls")),
    # Account self-service: data export + deletion (BL-20260817-01).
    path("api/account/", include("law_ai.core.urls_account")),
    # Quarantine review queue for the web app (BL-20260811-01). Same audited
    # approval service the admin actions and `manage.py review_queue` use.
    path("api/ingestion/", include("law_ai.ingestionapp.urls")),
]
