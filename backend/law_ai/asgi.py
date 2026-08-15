"""ASGI entrypoint for Law AI (spec 011 FR-3, FR-12).

daphne serves both HTTP (Django views via DRF) and WebSocket (Channels
consumers under ``/ws/agents/...``) protocols.
"""

from __future__ import annotations

import os

from channels.auth import AuthMiddlewareStack
from channels.routing import ProtocolTypeRouter, URLRouter
from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "law_ai.settings.dev")

# Initialise Django ASGI application early so that AppConfig.ready() runs and
# imports for relocated agent code resolve before Channels consumers attach.
django_asgi_app = get_asgi_application()

from law_ai.agentsapi.routing import websocket_urlpatterns  # noqa: E402

application = ProtocolTypeRouter(
    {
        "http": django_asgi_app,
        "websocket": AuthMiddlewareStack(URLRouter(websocket_urlpatterns)),
    }
)


def _wrap_with_tracing(app: object) -> object:
    """Give every HTTP request a root server span (spec 037 FR-3).

    `DjangoInstrumentor` is installed by `core.telemetry` and does insert its
    middleware into `settings.MIDDLEWARE`, but under daphne/ASGI it produces
    no server span — verified live: an `/api/analysis` trace was rooted at
    `legal_workflow.invoke`, and every other request stayed a single-span
    orphan. `plan.md` §9 named this risk and this fallback.

    Wrapping the *outermost* ASGI callable is what makes the span a true root:
    it opens before Django's middleware chain and closes after it, so the
    LangGraph, LangChain, and httpx spans raised inside the view all nest
    under it instead of each starting its own trace.

    No-ops when tracing is disabled or the optional package is absent, so
    FR-8's default-off promise is unchanged.
    """
    from law_ai.core.telemetry import is_enabled

    if not is_enabled():
        return app
    try:
        from opentelemetry.instrumentation.asgi import OpenTelemetryMiddleware
    except ImportError:  # pragma: no cover - extra missing
        return app
    return OpenTelemetryMiddleware(app)


application = _wrap_with_tracing(application)
