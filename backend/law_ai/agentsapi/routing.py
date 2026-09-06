"""Channels websocket urlpatterns (spec 011 FR-12)."""

from __future__ import annotations

from django.urls import re_path

from .consumers import AgentRunConsumer, OpsDashboardConsumer

websocket_urlpatterns = [
    # Ordered before the run pattern on purpose: `[\w\-]+` would otherwise
    # swallow "ops" and route the dashboard into a run group named "ops".
    re_path(r"^ws/agents/ops/?$", OpsDashboardConsumer.as_asgi()),
    re_path(r"^ws/agents/(?P<run_id>[\w\-]+)/?$", AgentRunConsumer.as_asgi()),
]
