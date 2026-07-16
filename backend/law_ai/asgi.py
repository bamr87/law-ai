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
