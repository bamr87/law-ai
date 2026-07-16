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
    """Mirror of the FastAPI root response from ``app/main.py``."""
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
    # URL shape exactly matches the FastAPI ancestor.
    path("health", include("law_ai.core.urls_health")),
    path("health/", include("law_ai.core.urls_health")),
    path("api/agents", include("law_ai.agentsapi.urls")),
    path("api/agents/", include("law_ai.agentsapi.urls")),
    path("api/analysis", include("law_ai.analysis.urls")),
    path("api/analysis/", include("law_ai.analysis.urls")),
    path("api/graph/", include("law_ai.graph.urls")),
    path("api/lsat/", include("law_ai.lsat.urls")),
]
