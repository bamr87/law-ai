"""Root URLconf (spec 011 FR-9).

Every API surface from ``backend/app/api/`` ports here unchanged in
shape. ``/health`` stays open; everything under ``/api/`` is gated by
``ApiKeyAuthentication`` + per-router ``HasScope`` permissions
(``backend/lawgraph/core/auth.py``).
"""

from __future__ import annotations

from django.contrib import admin
from django.http import JsonResponse
from django.urls import include, path
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularRedocView,
    SpectacularSwaggerView,
)


def root(_request: object) -> JsonResponse:
    """Mirror of the FastAPI root response from ``app/main.py``."""
    return JsonResponse(
        {
            "message": "LawGraph AI - Open Legal Intelligence Platform",
            "version": "0.1.0",
            "status": "operational",
            "docs": "/api/docs",
            "agents": "/api/agents",
        }
    )


urlpatterns = [
    path("", root),
    path("admin/", admin.site.urls),
    # OpenAPI schema + interactive docs generated from the DRF views by
    # drf-spectacular (ADR 0004). Kept in sync with the code automatically.
    path("api/schema", SpectacularAPIView.as_view(), name="schema"),
    path(
        "api/docs",
        SpectacularSwaggerView.as_view(url_name="schema"),
        name="swagger-ui",
    ),
    path(
        "api/redoc",
        SpectacularRedocView.as_view(url_name="schema"),
        name="redoc",
    ),
    # Both trailing-slash and slashless variants are accepted so the
    # URL shape exactly matches the FastAPI ancestor.
    path("health", include("lawgraph.core.urls_health")),
    path("health/", include("lawgraph.core.urls_health")),
    path("api/agents", include("lawgraph.agentsapi.urls")),
    path("api/agents/", include("lawgraph.agentsapi.urls")),
    path("api/analysis", include("lawgraph.analysis.urls")),
    path("api/analysis/", include("lawgraph.analysis.urls")),
    path("api/graph/", include("lawgraph.graph.urls")),
    path("api/lsat/", include("lawgraph.lsat.urls")),
]
