"""Live activity feed: `compact_event` projection + `AgentActivityConsumer` (WS3).

Two layers:
  * `compact_event` — pure field-selection + ``http_request`` filter (no I/O).
  * `AgentActivityConsumer` — connect → ``ready`` envelope → a frame published
    on the ``agents-activity`` group is forwarded verbatim → disconnect.

The consumer is driven via a direct ``group_send`` (mirroring
``test_consumer.py``). ``broadcast_activity`` itself dispatches the send to a
worker thread, so the regression test below checks that it works from inside a
running event loop (the bug: it used to ``async_to_sync`` on the caller's loop
and silently no-op, so agent calls from async views never reached the feed).
"""

from __future__ import annotations

import pytest
from channels.layers import get_channel_layer
from channels.testing import WebsocketCommunicator

import lawgraph.agentsapi.broadcast as broadcast_mod
from lawgraph.agentsapi.broadcast import (
    ACTIVITY_GROUP,
    broadcast_activity,
    compact_event,
)
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
    await layer.group_send(ACTIVITY_GROUP, {"type": "activity.event", "event": frame})
    forwarded = await communicator.receive_json_from()
    assert forwarded == frame

    await communicator.disconnect()


class _InlineExecutor:
    """Runs submitted work synchronously so the dispatch is assertable."""

    def submit(self, fn, *args, **kwargs):
        fn(*args, **kwargs)


@pytest.mark.asyncio
async def test_broadcast_activity_dispatches_from_async_context(monkeypatch) -> None:
    """Regression: calling broadcast_activity from inside a running event loop
    must still dispatch the compact frame (it used to async_to_sync on the
    caller's loop and silently no-op — agent calls from async views were lost).
    """
    captured: list[dict] = []
    monkeypatch.setattr(broadcast_mod, "_send", captured.append)
    monkeypatch.setattr(broadcast_mod, "_dispatch", _InlineExecutor())

    # We are inside a running event loop (this is an async test).
    broadcast_activity(
        {"type": "agent_call", "agent": "LegalAnalyst", "input_hash": 999}
    )

    assert captured == [{"type": "agent_call", "agent": "LegalAnalyst"}]


def test_broadcast_activity_skips_http_requests(monkeypatch) -> None:
    """http_request frames are filtered before any dispatch."""
    calls: list = []
    monkeypatch.setattr(
        broadcast_mod,
        "_dispatch",
        type("E", (), {"submit": lambda self, *a: calls.append(a)})(),
    )
    broadcast_activity({"type": "http_request", "path": "/x"})
    assert calls == []
