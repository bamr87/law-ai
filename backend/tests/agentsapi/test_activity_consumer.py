"""Live activity feed: `compact_event` projection + `AgentActivityConsumer` (WS3).

Two layers:
  * `compact_event` — pure field-selection + ``http_request`` filter (no I/O).
  * `AgentActivityConsumer` — connect → ``ready`` envelope → a frame published
    on the ``agents-activity`` group is forwarded verbatim → disconnect.

The consumer is driven via a direct ``group_send`` (mirroring
``test_consumer.py``) rather than ``broadcast_activity``: the helper wraps
``async_to_sync``, which is a no-op inside a running event loop, so it is
exercised through its pure ``compact_event`` core instead.
"""

from __future__ import annotations

import pytest
from channels.layers import get_channel_layer
from channels.testing import WebsocketCommunicator

from lawgraph.agentsapi.broadcast import ACTIVITY_GROUP, compact_event
from lawgraph.agentsapi.consumers import AgentActivityConsumer


def test_compact_event_keeps_only_safe_fields() -> None:
    frame = compact_event(
        {
            "type": "agent_call",
            "agent": "LegalAnalyst",
            "model": "claude-opus-4-8",
            "trace_id": "abc-123",
            "session_id": "sess-1",
            "latency_ms": 42.0,
            "confidence": 0.91,
            "output_summary": "should be dropped",
            "input_hash": 999,
        }
    )
    assert frame == {
        "type": "agent_call",
        "agent": "LegalAnalyst",
        "model": "claude-opus-4-8",
        "trace_id": "abc-123",
        "session_id": "sess-1",
        "latency_ms": 42.0,
        "confidence": 0.91,
    }


def test_compact_event_filters_http_requests() -> None:
    assert compact_event({"type": "http_request", "path": "/api/health"}) is None


def test_compact_event_falls_back_to_kind_and_default_type() -> None:
    assert compact_event({"kind": "graph_query", "agent": "X"})["type"] == "graph_query"
    assert compact_event({"agent": "X"})["type"] == "event"


@pytest.mark.asyncio
async def test_activity_consumer_ready_and_forwards_frame() -> None:
    communicator = WebsocketCommunicator(
        AgentActivityConsumer.as_asgi(),
        "/ws/agents/activity/",
    )
    connected, _ = await communicator.connect()
    assert connected is True

    ready = await communicator.receive_json_from()
    assert ready == {"type": "ready", "feed": ACTIVITY_GROUP}

    frame = {"type": "agent_call", "agent": "LegalAnalyst", "trace_id": "abc-123"}
    layer = get_channel_layer()
    assert layer is not None
    await layer.group_send(
        ACTIVITY_GROUP, {"type": "activity.event", "event": frame}
    )
    forwarded = await communicator.receive_json_from()
    assert forwarded == frame

    await communicator.disconnect()
