"""ASGI middleware (spec 011 FR-7).

* ``CorsHeadersMiddleware`` — minimal CORS that matches the FastAPI defaults
  in ``app/main.py`` so the frontend dev server keeps working without a new
  third-party dep.
* ``ProvenanceMiddleware`` — wraps every request and records an audit event
  via :func:`law_ai.core.provenance.ProvenanceLogger.log_request`.
"""

from __future__ import annotations

import logging
from collections.abc import Callable

from django.conf import settings
from django.http import HttpRequest, HttpResponse

logger = logging.getLogger("law_ai")

_ALLOWED_HEADERS = "Content-Type, Authorization, X-API-Key"
_ALLOWED_METHODS = "GET, POST, PUT, PATCH, DELETE, OPTIONS"


class CorsHeadersMiddleware:
    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]):
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        if request.method == "OPTIONS":
            response = HttpResponse(status=204)
        else:
            response = self.get_response(request)
        origin = request.META.get("HTTP_ORIGIN")
        allow = getattr(settings, "CORS_ALLOWED_ORIGINS", [])
        if origin and origin in allow:
            response["Access-Control-Allow-Origin"] = origin
            response["Access-Control-Allow-Credentials"] = "true"
            response["Access-Control-Allow-Methods"] = _ALLOWED_METHODS
            response["Access-Control-Allow-Headers"] = _ALLOWED_HEADERS
        return response


class ProvenanceMiddleware:
    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]):
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        response = self.get_response(request)
        try:
            from law_ai.core.provenance import ProvenanceLogger

            ProvenanceLogger.log_request(request, response)
        except Exception as exc:  # pragma: no cover
            logger.debug("provenance log_request skipped: %s", exc)
        return response
