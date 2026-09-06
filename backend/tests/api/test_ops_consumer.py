"""Ops dashboard push channel (BL-20260429-16).

The dashboard polled six REST endpoints every five seconds whether or not
anything had changed. These tests pin the replacement's contract: one shared
group, a compact change notification rather than the data, the same auth gate
as the run stream, and — the invariant that matters most — an agent call that
still succeeds when the push cannot be delivered.
"""

from __future__ import annotations

import pytest
from channels.layers import get_channel_layer
from channels.testing import WebsocketCommunicator

from law_ai.agentsapi.consumers import (
    CLOSE_UNAUTHORIZED,
    OPS_GROUP,
    OPS_STREAM_ID,
    OpsDashboardConsumer,
)
from law_ai.core.ws_ticket import mint_ticket


def _communicator(query: str = "") -> WebsocketCommunicator:
    return WebsocketCommunicator(
        OpsDashboardConsumer.as_asgi(),
        "/ws/agents/ops" + (f"?{query}" if query else ""),
        headers=None,
    )


@pytest.mark.asyncio
async def test_ready_then_forwards_change_notifications() -> None:
    communicator = _communicator()
    connected, _ = await communicator.connect()
    assert connected is True
    assert await communicator.receive_json_from() == {
        "type": "ready",
        "channel": OPS_GROUP,
    }

    layer = get_channel_layer()
    assert layer is not None
    await layer.group_send(
        OPS_GROUP,
        {"type": "ops_event", "payload": {"type": "runs_changed", "agent": "X"}},
    )
    assert await communicator.receive_json_from() == {
        "type": "runs_changed",
        "agent": "X",
    }
    await communicator.disconnect()


@pytest.mark.asyncio
async def test_every_dashboard_receives_one_group_send() -> None:
    """One group, so N reviewers cost one send — the point of the item."""
    first, second = _communicator(), _communicator()
    for comm in (first, second):
        connected, _ = await comm.connect()
        assert connected is True
        await comm.receive_json_from()  # ready

    layer = get_channel_layer()
    assert layer is not None
    await layer.group_send(
        OPS_GROUP, {"type": "ops_event", "payload": {"type": "runs_changed"}}
    )

    for comm in (first, second):
        assert (await comm.receive_json_from())["type"] == "runs_changed"
        await comm.disconnect()


@pytest.mark.asyncio
async def test_rejects_a_connection_without_the_key(settings) -> None:
    settings.AGENT_API_KEY = "secret-key"
    communicator = _communicator()
    connected, code = await communicator.connect()
    assert connected is False
    assert code == CLOSE_UNAUTHORIZED


@pytest.mark.asyncio
async def test_accepts_a_ticket_minted_for_the_ops_stream(settings) -> None:
    settings.AGENT_API_KEY = "secret-key"
    ticket = mint_ticket(OPS_STREAM_ID, "secret-key")
    communicator = _communicator(f"ticket={ticket}")
    communicator.scope["query_string"] = f"ticket={ticket}".encode()

    connected, _ = await communicator.connect()
    assert connected is True
    await communicator.disconnect()


@pytest.mark.asyncio
async def test_a_ticket_for_another_stream_is_refused(settings) -> None:
    """The same scoping rule the run stream enforces."""
    settings.AGENT_API_KEY = "secret-key"
    ticket = mint_ticket("run-someone-elses", "secret-key")
    communicator = _communicator(f"ticket={ticket}")
    communicator.scope["query_string"] = f"ticket={ticket}".encode()

    connected, code = await communicator.connect()
    assert connected is False
    assert code == CLOSE_UNAUTHORIZED


@pytest.mark.asyncio
async def test_an_agent_call_notifies_open_dashboards(settings) -> None:
    settings.AGENT_OPS_PUSH_ENABLED = True
    communicator = _communicator()
    connected, _ = await communicator.connect()
    assert connected is True
    await communicator.receive_json_from()  # ready

    from law_ai.core.provenance import provenance

    trace_id = provenance.log_agent_call(
        agent_name="LegalAnalyst",
        input_data={},
        output_data={},
        model="test",
        latency_ms=1.0,
    )

    event = await communicator.receive_json_from()
    assert event == {
        "type": "runs_changed",
        "agent": "LegalAnalyst",
        "trace_id": trace_id,
    }
    await communicator.disconnect()


@pytest.mark.asyncio
async def test_the_push_is_off_by_default_in_the_suite(settings) -> None:
    """Hundreds of unrelated agent calls must not each write to a socket."""
    from django.conf import settings as django_settings

    assert django_settings.AGENT_OPS_PUSH_ENABLED is False


@pytest.mark.asyncio
async def test_a_dead_channel_layer_never_fails_an_agent_call(
    settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The dashboard loses liveness; the agent keeps its run."""
    from law_ai.agentsapi import streaming

    settings.AGENT_OPS_PUSH_ENABLED = True

    def _explode() -> object:
        raise RuntimeError("redis is gone")

    monkeypatch.setattr(streaming, "get_channel_layer", _explode)

    from law_ai.core.provenance import provenance

    trace_id = provenance.log_agent_call(
        agent_name="PrecedentHunter",
        input_data={},
        output_data={},
        model="test",
        latency_ms=1.0,
    )
    assert trace_id


def test_the_ops_route_wins_over_the_run_pattern() -> None:
    """`[\\w\\-]+` would otherwise route "ops" into a run group called "ops"."""
    from law_ai.agentsapi.routing import websocket_urlpatterns

    matched = [
        p for p in websocket_urlpatterns if p.pattern.regex.match("ws/agents/ops")
    ]
    assert matched, "no route matches the ops socket"
    assert matched[0].callback is not None
    assert "OpsDashboardConsumer" in repr(matched[0].callback)
