"""Channels websocket urlpatterns (spec 011 FR-12)."""

from __future__ import annotations

from django.urls import re_path

from .consumers import AgentActivityConsumer, AgentRunConsumer

websocket_urlpatterns = [
    # Activity feed must precede the run_id catch-all (first match wins).
    re_path(r"^ws/agents/activity/?$", AgentActivityConsumer.as_asgi()),
    re_path(r"^ws/agents/(?P<run_id>[\w\-]+)/?$", AgentRunConsumer.as_asgi()),
]
