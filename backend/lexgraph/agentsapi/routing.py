"""Channels websocket urlpatterns (spec 011 FR-12)."""
from __future__ import annotations

from django.urls import re_path

from .consumers import AgentRunConsumer

websocket_urlpatterns = [
    re_path(r"^ws/agents/(?P<run_id>[\w\-]+)/?$", AgentRunConsumer.as_asgi()),
]
