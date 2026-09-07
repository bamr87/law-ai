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
    # `since` echoes the replay cursor the server understood — 0 for a fresh
    # subscriber (BL-20260811-14).
    assert ready == {"type": "ready", "run_id": "run-123", "since": 0}

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
async def test_accepts_a_stream_scoped_ticket(settings) -> None:
    """The browser path (BL-20260430-07): a ticket, never the key itself.

    A browser cannot set a handshake header, and the key is no longer in the
    bundle, so the frontend's server mints a short-lived ticket signed with
    the shared key. It is good for one stream, briefly.
    """
    from law_ai.core.ws_ticket import mint_ticket

    settings.AGENT_API_KEY = "secret-key"
    ticket = mint_ticket("run-abc", "secret-key")

    ok = _communicator("run-abc", query=f"ticket={ticket}")
    connected, _ = await ok.connect()
    assert connected is True
    assert (await ok.receive_json_from())["type"] == "ready"
    await ok.disconnect()


@pytest.mark.asyncio
async def test_rejects_a_ticket_minted_for_another_stream(settings) -> None:
    from law_ai.agentsapi.consumers import CLOSE_UNAUTHORIZED
    from law_ai.core.ws_ticket import mint_ticket

    settings.AGENT_API_KEY = "secret-key"
    other = mint_ticket("run-other", "secret-key")

    comm = _communicator("run-abc", query=f"ticket={other}")
    connected, code = await comm.connect()
    assert connected is False
    assert code == CLOSE_UNAUTHORIZED


@pytest.mark.asyncio
async def test_rejects_an_expired_ticket(settings) -> None:
    from law_ai.agentsapi.consumers import CLOSE_UNAUTHORIZED
    from law_ai.core.ws_ticket import mint_ticket

    settings.AGENT_API_KEY = "secret-key"
    stale = mint_ticket("run-abc", "secret-key", ttl=-1)

    comm = _communicator("run-abc", query=f"ticket={stale}")
    connected, code = await comm.connect()
    assert connected is False
    assert code == CLOSE_UNAUTHORIZED


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


# --- BL-20260811-14: reconnect + event replay ---


@pytest.fixture(autouse=True)
def _memory_replay(monkeypatch: pytest.MonkeyPatch):
    """Force the in-process buffer so these tests never depend on Redis."""
    from law_ai.agentsapi import replay

    # Belt and braces: the test settings already pin AGENT_STREAM_REPLAY_URL to
    # "" so the in-process buffer is used, and this keeps the tests honest if
    # that ever changes.
    monkeypatch.setattr(replay, "_client", lambda: None)
    replay.reset()
    yield
    replay.reset()


async def _emit(stream_id: str, payload: dict) -> dict:
    from law_ai.agentsapi.streaming import emit_stream_event

    await emit_stream_event(stream_id, payload, source="test")
    from law_ai.agentsapi import replay

    return (await replay.events_since(stream_id, 0))[-1]


@pytest.mark.asyncio
async def test_token_deltas_never_enter_the_replay_buffer() -> None:
    """BL-20260906-77: a long answer must not evict the run's milestones.

    The buffer is 200 payloads deep. One frame per token delta filled it
    several times over, so a reconnecting client replayed the tail of a token
    stream it discards anyway and none of the ``agent_step`` frames it needed.
    """
    from law_ai.agentsapi import replay
    from law_ai.agentsapi.streaming import emit_stream_event

    await emit_stream_event("run-deltas", {"type": "agent_step", "agent": "A"})
    for i in range(50):
        await emit_stream_event(
            "run-deltas",
            {"type": "analysis_token", "text": "x", "chars": i + 1},
            source="analysis",
        )
    await emit_stream_event(
        "run-deltas", {"type": "tutor_token", "text": "y"}, source="lsat_tutor"
    )
    await emit_stream_event("run-deltas", {"type": "complete"})

    buffered = await replay.events_since("run-deltas", 0)
    assert [e["type"] for e in buffered] == ["agent_step", "complete"]
    # Milestones keep a dense, contiguous cursor: deltas consume no seq.
    assert [e["seq"] for e in buffered] == [1, 2]


@pytest.mark.asyncio
async def test_a_token_delta_still_reaches_a_live_subscriber() -> None:
    """Unbuffered is not undelivered — and it carries no ``seq`` to cursor on."""
    from law_ai.agentsapi.streaming import emit_stream_event

    comm = _communicator("run-live-delta")
    assert (await comm.connect())[0]
    await comm.receive_json_from()  # ready

    await emit_stream_event(
        "run-live-delta",
        {"type": "analysis_token", "text": "partial", "chars": 7},
        source="analysis",
    )
    frame = await comm.receive_json_from()
    assert frame["type"] == "analysis_token"
    assert frame["text"] == "partial"
    assert "seq" not in frame
    await comm.disconnect()


@pytest.mark.asyncio
async def test_emitted_events_carry_a_monotonic_seq() -> None:
    """The cursor a reconnecting client uses has to exist on the live frames."""
    from law_ai.agentsapi import replay

    await _emit("run-seq", {"type": "agent_step", "agent": "A"})
    await _emit("run-seq", {"type": "agent_step", "agent": "B"})
    await _emit("run-seq", {"type": "complete"})

    seqs = [e["seq"] for e in await replay.events_since("run-seq", 0)]
    assert seqs == [1, 2, 3]


@pytest.mark.asyncio
async def test_a_reconnect_with_since_receives_only_what_it_missed() -> None:
    await _emit("run-drop", {"type": "agent_step", "agent": "A"})
    await _emit("run-drop", {"type": "agent_step", "agent": "B"})
    await _emit("run-drop", {"type": "complete"})

    comm = _communicator("run-drop", query="since=1")
    connected, _ = await comm.connect()
    assert connected is True
    assert await comm.receive_json_from() == {
        "type": "ready",
        "run_id": "run-drop",
        "since": 1,
    }

    replayed = [await comm.receive_json_from() for _ in range(2)]
    assert [e["seq"] for e in replayed] == [2, 3]
    assert replayed[0]["agent"] == "B"
    await comm.disconnect()


@pytest.mark.asyncio
async def test_replay_is_followed_by_live_events() -> None:
    """Catch-up must not swallow anything produced during the reconnect."""
    await _emit("run-mixed", {"type": "agent_step", "agent": "A"})

    comm = _communicator("run-mixed", query="since=0&replay=1")
    connected, _ = await comm.connect()
    assert connected is True
    await comm.receive_json_from()  # ready

    assert (await comm.receive_json_from())["seq"] == 1
    await _emit("run-mixed", {"type": "complete"})
    live = await comm.receive_json_from()
    assert live["type"] == "complete"
    assert live["seq"] == 2
    await comm.disconnect()


@pytest.mark.asyncio
async def test_a_fresh_subscriber_is_not_handed_an_old_run() -> None:
    """The spec-032 flow subscribes *before* posting; replay is opt-in."""
    await _emit("run-reused", {"type": "complete"})

    comm = _communicator("run-reused")
    connected, _ = await comm.connect()
    assert connected is True
    await comm.receive_json_from()  # ready
    assert await comm.receive_nothing() is True
    await comm.disconnect()


@pytest.mark.asyncio
async def test_a_garbage_cursor_reads_as_no_cursor() -> None:
    comm = _communicator("run-garbage", query="since=not-a-number")
    connected, _ = await comm.connect()
    assert connected is True
    assert (await comm.receive_json_from())["since"] == 0
    await comm.disconnect()


@pytest.mark.asyncio
async def test_a_cursor_past_the_end_replays_nothing() -> None:
    await _emit("run-ahead", {"type": "complete"})

    comm = _communicator("run-ahead", query="since=99")
    connected, _ = await comm.connect()
    assert connected is True
    await comm.receive_json_from()  # ready
    assert await comm.receive_nothing() is True
    await comm.disconnect()


@pytest.mark.asyncio
async def test_the_buffer_is_bounded(monkeypatch: pytest.MonkeyPatch) -> None:
    """A reconnect window, not an event store."""
    from law_ai.agentsapi import replay

    monkeypatch.setattr(replay, "MAX_EVENTS", 3)
    for index in range(5):
        replay._memory_record("run-cap", {"type": "agent_step", "i": index})

    kept = await replay.events_since("run-cap", 0)
    assert [e["i"] for e in kept] == [2, 3, 4]


# --- BL-20260906-09: the socket accepts the same credentials REST does ---


class TestSocketAcceptsSessionAndApiToken:
    """A signed-in browser user could start a run and not watch it.

    Every REST route has accepted a Django session since spec 036 FR-2, but
    the consumer compared a query-string key against ``AGENT_API_KEY`` and
    nothing else. These pin the two legs that closes: a provisioned
    ``ApiToken`` with the agent scope, and an authenticated session.
    """

    @pytest.mark.asyncio
    @pytest.mark.django_db(transaction=True)
    async def test_agent_scoped_api_token_is_accepted(self, settings) -> None:
        from channels.db import database_sync_to_async

        from law_ai.core.models import ApiToken

        settings.AGENT_API_KEY = "secret-key"
        await database_sync_to_async(ApiToken.objects.create)(
            scope=ApiToken.SCOPE_AGENT,
            name="ws",
            key_hash=ApiToken.hash_key("provisioned-token"),
        )

        comm = _communicator("run-abc", query="api_key=provisioned-token")
        connected, _ = await comm.connect()
        assert connected is True
        await comm.disconnect()

    @pytest.mark.asyncio
    @pytest.mark.django_db(transaction=True)
    async def test_a_token_for_another_scope_is_not_a_socket_credential(
        self, settings
    ) -> None:
        from channels.db import database_sync_to_async

        from law_ai.agentsapi.consumers import CLOSE_UNAUTHORIZED
        from law_ai.core.models import ApiToken

        settings.AGENT_API_KEY = "secret-key"
        await database_sync_to_async(ApiToken.objects.create)(
            scope=ApiToken.SCOPE_LSAT,
            name="ws-lsat",
            key_hash=ApiToken.hash_key("lsat-only"),
        )

        comm = _communicator("run-abc", query="api_key=lsat-only")
        connected, code = await comm.connect()
        assert connected is False
        assert code == CLOSE_UNAUTHORIZED

    @pytest.mark.asyncio
    @pytest.mark.django_db(transaction=True)
    async def test_a_revoked_token_is_no_credential_at_all(self, settings) -> None:
        from channels.db import database_sync_to_async
        from django.utils import timezone

        from law_ai.agentsapi.consumers import CLOSE_UNAUTHORIZED
        from law_ai.core.models import ApiToken

        settings.AGENT_API_KEY = "secret-key"
        await database_sync_to_async(ApiToken.objects.create)(
            scope=ApiToken.SCOPE_AGENT,
            name="ws-dead",
            key_hash=ApiToken.hash_key("revoked-token"),
            revoked_at=timezone.now(),
        )

        comm = _communicator("run-abc", query="api_key=revoked-token")
        connected, code = await comm.connect()
        assert connected is False
        assert code == CLOSE_UNAUTHORIZED

    @pytest.mark.asyncio
    @pytest.mark.django_db(transaction=True)
    async def test_an_authenticated_session_opens_the_socket(self, settings) -> None:
        """The browser case the item names: signed in, holding no key."""
        from channels.db import database_sync_to_async
        from django.contrib.auth import get_user_model

        settings.AGENT_API_KEY = "secret-key"
        user = await database_sync_to_async(get_user_model().objects.create_user)(
            username="ws-user", password="pw"
        )

        comm = _communicator("run-abc")
        comm.scope["user"] = user
        connected, _ = await comm.connect()
        assert connected is True
        await comm.disconnect()

    @pytest.mark.asyncio
    @pytest.mark.django_db(transaction=True)
    async def test_an_anonymous_scope_user_is_still_refused(self, settings) -> None:
        from django.contrib.auth.models import AnonymousUser

        from law_ai.agentsapi.consumers import CLOSE_UNAUTHORIZED

        settings.AGENT_API_KEY = "secret-key"

        comm = _communicator("run-abc")
        comm.scope["user"] = AnonymousUser()
        connected, code = await comm.connect()
        assert connected is False
        assert code == CLOSE_UNAUTHORIZED

    @pytest.mark.asyncio
    @pytest.mark.django_db(transaction=True)
    async def test_the_ops_channel_takes_the_same_credentials(self, settings) -> None:
        from channels.testing import WebsocketCommunicator
        from django.contrib.auth import get_user_model

        from channels.db import database_sync_to_async
        from law_ai.agentsapi.consumers import OpsDashboardConsumer

        settings.AGENT_API_KEY = "secret-key"
        user = await database_sync_to_async(get_user_model().objects.create_user)(
            username="ops-user", password="pw"
        )

        comm = WebsocketCommunicator(OpsDashboardConsumer.as_asgi(), "/ws/agents/ops")
        comm.scope["user"] = user
        connected, _ = await comm.connect()
        assert connected is True
        await comm.disconnect()
