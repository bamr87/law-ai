"""Dashboard-wide live activity broadcast (WS3 real-time, spec 022 NG3).

A best-effort fan-out of provenance events to the ``agents-activity`` Channels
group, which :class:`AgentActivityConsumer` forwards to every connected
dashboard. Called from :func:`lawgraph.core.provenance._persist`.

**Never raises** — broadcasting is a UI nicety, not part of the audit path. If
the channel layer is absent, or we're inside a running event loop (some async
call sites), it silently no-ops and the dashboard's HTTP poll still updates.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger("lawgraph.agentsapi.broadcast")

ACTIVITY_GROUP = "agents-activity"

# Compact, non-sensitive fields forwarded to the live feed.
_FIELDS = (
    "type",
    "agent",
    "model",
    "trace_id",
    "session_id",
    "cycle_id",
    "cycle_type",
    "status",
    "timestamp",
    "latency_ms",
    "confidence",
)
# High-volume / low-signal event types we don't stream to the feed.
_SKIP_TYPES = {"http_request"}


def compact_event(event: dict[str, Any]) -> dict[str, Any] | None:
    """Project ``event`` onto the compact, non-sensitive feed frame.

    Returns ``None`` for event types we don't stream (e.g. ``http_request``),
    so the caller can skip the broadcast entirely. Pure — no I/O — which keeps
    the field-selection contract unit-testable without a channel layer.
    """
    etype = str(event.get("type") or event.get("kind") or "event")
    if etype in _SKIP_TYPES:
        return None
    frame: dict[str, Any] = {k: event[k] for k in _FIELDS if event.get(k) is not None}
    frame["type"] = etype
    return frame


def broadcast_activity(event: dict[str, Any]) -> None:
    frame = compact_event(event)
    if frame is None:
        return
    try:
        from asgiref.sync import async_to_sync
        from channels.layers import get_channel_layer

        layer = get_channel_layer()
        if layer is None:
            return
        async_to_sync(layer.group_send)(
            ACTIVITY_GROUP, {"type": "activity.event", "event": frame}
        )
    except Exception as exc:  # pragma: no cover - UI nicety, never break audit
        logger.debug("activity broadcast skipped: %s", exc)
