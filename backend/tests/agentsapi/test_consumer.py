"""WebSocket smoke for `AgentRunConsumer` (spec 011 FR-12, AC-7).

Exercises the public contract: connect → ``ready`` envelope → group_send
``agent_event`` → forwarded payload → disconnect.
"""

from __future__ import annotations

import pytest
from channels.layers import get_channel_layer
from channels.testing import WebsocketCommunicator

from law_ai.agentsapi.consumers import AgentRunConsumer


@pytest.mark.asyncio
async def test_agent_run_consumer_ready_and_group_event() -> None:
    communicator = WebsocketCommunicator(
        AgentRunConsumer.as_asgi(),
        "/ws/agents/run-123/",
    )
    # Channels' WebsocketCommunicator does not populate `url_route` itself.
    communicator.scope["url_route"] = {"kwargs": {"run_id": "run-123"}}

    connected, _ = await communicator.connect()
    assert connected is True

    ready = await communicator.receive_json_from()
    assert ready == {"type": "ready", "run_id": "run-123"}

    layer = get_channel_layer()
    assert layer is not None
    await layer.group_send(
        "agent-run-run-123",
        {"type": "agent_event", "payload": {"step": "analysis", "ok": True}},
    )
    forwarded = await communicator.receive_json_from()
    assert forwarded == {"step": "analysis", "ok": True}

    await communicator.disconnect()
