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


# --- Spec 032 / BL-20260810-06: deliverable + authenticated streaming ---


def _communicator(run_id: str, *, query: str = "", headers=None):
    comm = WebsocketCommunicator(
        AgentRunConsumer.as_asgi(),
        f"/ws/agents/runs/{run_id}/" + (f"?{query}" if query else ""),
        headers=headers,
    )
    comm.scope["url_route"] = {"kwargs": {"run_id": run_id}}
    if query:
        comm.scope["query_string"] = query.encode()
    return comm


@pytest.mark.asyncio
async def test_rejects_malformed_stream_id() -> None:
    """A group name is never sanitised into existence — it is rejected."""
    from law_ai.agentsapi.consumers import CLOSE_BAD_STREAM_ID

    comm = _communicator("bad id/../other")
    connected, code = await comm.connect()
    assert connected is False
    assert code == CLOSE_BAD_STREAM_ID


@pytest.mark.asyncio
async def test_requires_api_key_when_configured(settings) -> None:
    from law_ai.agentsapi.consumers import CLOSE_UNAUTHORIZED

    settings.AGENT_API_KEY = "secret-key"

    unauth = _communicator("run-abc")
    connected, code = await unauth.connect()
    assert connected is False
    assert code == CLOSE_UNAUTHORIZED

    wrong = _communicator("run-abc", query="api_key=nope")
    connected, code = await wrong.connect()
    assert connected is False
    assert code == CLOSE_UNAUTHORIZED


@pytest.mark.asyncio
async def test_accepts_valid_api_key_via_query_and_header(settings) -> None:
    """Browsers cannot set handshake headers, so the query param must work."""
    settings.AGENT_API_KEY = "secret-key"

    via_query = _communicator("run-abc", query="api_key=secret-key")
    connected, _ = await via_query.connect()
    assert connected is True
    assert (await via_query.receive_json_from())["type"] == "ready"
    await via_query.disconnect()

    via_header = _communicator("run-abc", headers=[(b"x-api-key", b"secret-key")])
    connected, _ = await via_header.connect()
    assert connected is True
    await via_header.disconnect()


@pytest.mark.asyncio
async def test_open_when_no_key_configured(settings) -> None:
    """Matches the REST routers' default-open localhost posture."""
    settings.AGENT_API_KEY = ""
    comm = _communicator("run-open")
    connected, _ = await comm.connect()
    assert connected is True
    await comm.disconnect()


@pytest.mark.asyncio
async def test_client_stream_id_receives_events_during_the_run(settings) -> None:
    """The end-to-end fix: subscribe first, then post, and events arrive.

    Previously the group was keyed on the server-generated analysis id, so
    a client could not subscribe until the response (and thus the whole
    run) had already completed.
    """
    from httpx import ASGITransport, AsyncClient

    from law_ai.asgi import application as app

    settings.AGENT_API_KEY = ""
    stream_id = "client-chosen-123"

    comm = _communicator(stream_id)
    connected, _ = await comm.connect()
    assert connected is True
    assert (await comm.receive_json_from())["type"] == "ready"

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        res = await client.post(
            "/api/analysis",
            json={
                "text": "Contract dispute.",
                "use_langgraph": False,
                "stream_id": stream_id,
            },
        )
    assert res.status_code == 200

    seen = [await comm.receive_json_from() for _ in range(3)]
    kinds = [e["type"] for e in seen]
    assert kinds.count("agent_step") == 2
    assert kinds[-1] == "complete"
    assert {e["agent"] for e in seen if e["type"] == "agent_step"} == {
        "LegalAnalyst",
        "PrecedentHunter",
    }
    assert seen[-1]["analysis_id"] == res.json()["id"]
    await comm.disconnect()


@pytest.mark.asyncio
async def test_rejects_invalid_stream_id_at_the_api_boundary() -> None:
    from httpx import ASGITransport, AsyncClient

    from law_ai.asgi import application as app

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        res = await client.post(
            "/api/analysis",
            json={"text": "x", "use_langgraph": False, "stream_id": "bad id/../x"},
        )
    assert res.status_code == 422
