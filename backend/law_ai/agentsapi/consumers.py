"""WebSocket consumer for live agent traces (spec 011 FR-12, spec 032).

Subscription contract (spec 032 / BL-20260810-06)
-------------------------------------------------
``run_id`` is a **client-chosen** correlation id. The client:

1. picks a `stream_id`,
2. connects to ``/ws/agents/<stream_id>`` and waits for ``ready``,
3. POSTs ``/api/analysis`` with the same ``stream_id``.

That ordering is what makes streaming possible at all. Previously the group
was keyed on the server-generated analysis id, which the client could only
learn from the *response* — i.e. after the run had already finished — so no
client could ever subscribe in time to receive an event.

Authentication mirrors the REST gate: when an agents API key is configured
the socket must present it — as a short-lived ``?ticket=`` minted by a
server that holds the key (the browser path, BL-20260430-07), a raw
``?api_key=`` (kept for non-browser clients and existing scripts), or an
``X-API-Key`` header. With no key configured the socket stays open, matching
the default-open localhost posture of the REST routers.

The ticket exists because a browser cannot set headers on a WebSocket
handshake: without it the raw key would have to be in the page, which is the
bundle leak the REST proxy just removed. See ``law_ai.core.ws_ticket``.
"""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import parse_qs

from channels.generic.websocket import AsyncJsonWebsocketConsumer

from law_ai.core.auth import _resolve_env_key
from law_ai.core.ws_ticket import verify_ticket

#: Channels group names allow ``[A-Za-z0-9._-]`` and must stay under 100
#: chars. Anything else is rejected rather than sanitised, so a client can
#: never smuggle itself into another run's group.
STREAM_ID_RE = re.compile(r"^[A-Za-z0-9._-]{1,64}$")

#: Application-defined close codes (4000-4999 range).
CLOSE_UNAUTHORIZED = 4401
CLOSE_BAD_STREAM_ID = 4400


def stream_group(stream_id: str) -> str:
    """Channel-layer group name for a run stream."""
    return f"agent-run-{stream_id}"


#: The one group every ops dashboard joins (BL-20260429-16). Not a run stream:
#: it carries change notifications, so N dashboards cost one group_send.
OPS_GROUP = "ops-dashboard"

#: Reserved stream id a ticket for the ops channel is signed against, so the
#: browser can authenticate without the raw key (BL-20260430-07).
OPS_STREAM_ID = "ops"


class _TicketAuth(AsyncJsonWebsocketConsumer):
    """The handshake gate shared by every consumer in this app.

    A raw ``AGENT_API_KEY`` (non-browser clients and scripts) or a
    short-lived, stream-scoped ticket minted by a server that holds the key
    (the browser path, BL-20260430-07). Extracted so a second consumer cannot
    quietly ship a weaker gate than the first.
    """

    def _query(self) -> dict[str, list[str]]:
        return parse_qs((self.scope.get("query_string") or b"").decode())

    def _presented_key(self) -> str | None:
        """Pull the API key from the query string or handshake headers."""
        query = self._query()
        values = query.get("api_key") or query.get("token") or []
        if values and values[0]:
            return str(values[0])
        for raw_name, raw_value in self.scope.get("headers") or []:
            if raw_name.decode().lower() == "x-api-key":
                return str(raw_value.decode())
        return None

    def _presented_ticket(self) -> str | None:
        """The short-lived ``?ticket=`` a browser was handed for this stream."""
        values = self._query().get("ticket") or []
        return str(values[0]) if values and values[0] else None

    def _authorized(self, required: str, run_id: str) -> bool:
        """A raw key or a valid ticket for *this* run — nothing else."""
        if self._presented_key() == required:
            return True
        return verify_ticket(self._presented_ticket(), run_id, required)


class AgentRunConsumer(_TicketAuth):
    """Subscribes the client to ``agent-run-<run_id>`` and emits ``ready``."""

    async def connect(self) -> None:
        run_id = str(self.scope["url_route"]["kwargs"]["run_id"])
        if not STREAM_ID_RE.match(run_id):
            await self.close(code=CLOSE_BAD_STREAM_ID)
            return

        required = _resolve_env_key("AGENT_API_KEY")
        if required and not self._authorized(required, run_id):
            # Reject before joining the group so an unauthorized socket
            # never receives a single event.
            await self.close(code=CLOSE_UNAUTHORIZED)
            return

        self.run_id = run_id
        self.group_name = stream_group(run_id)
        # Join before replaying, so an event produced *during* the catch-up is
        # queued for delivery rather than lost in the gap between the two.
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()
        since = self._since()
        await self.send_json({"type": "ready", "run_id": self.run_id, "since": since})
        await self._replay(since)

    def _since(self) -> int:
        """The ``?since=<seq>`` cursor a reconnecting client presented.

        Anything unparseable is 0 — "send me everything you still have" — which
        is the safe direction to be wrong in: a duplicate frame is deduped by
        seq on the client, a skipped one is gone (BL-20260811-14).
        """
        values = self._query().get("since") or []
        try:
            return max(0, int(values[0]))
        except (IndexError, TypeError, ValueError):
            return 0

    async def _replay(self, since: int) -> None:
        """Send the buffered events after *since*, before any live frame."""
        if since <= 0 and not self._wants_replay():
            return
        from law_ai.agentsapi import replay

        for payload in await replay.events_since(self.run_id, since):
            await self.send_json(payload)

    def _wants_replay(self) -> bool:
        """True when the client asked for catch-up without a cursor.

        A fresh subscriber (the normal spec-032 flow: subscribe, *then* post)
        must not be handed a previous run's buffer just because it reused a
        stream id, so replay from zero is opt-in via ``?replay=1``.
        """
        values = self._query().get("replay") or []
        return bool(values) and str(values[0]).lower() in {"1", "true", "yes"}

    async def disconnect(self, code: int) -> None:
        if hasattr(self, "group_name"):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def agent_event(self, event: dict[str, Any]) -> None:
        """Producer-side group_send → forwarded as JSON to the WS client."""
        payload = event.get("payload") or {}
        await self.send_json(payload)


class OpsDashboardConsumer(_TicketAuth):
    """Push channel for the ops dashboard (BL-20260429-16).

    The dashboard polled six REST endpoints every five seconds regardless of
    whether anything had changed — 72 requests a minute per open tab, and the
    cost is multiplied by every reviewer watching. This socket carries a
    *change notification*, not the data: the client still fetches through the
    same REST endpoints, but only when something actually happened.

    Deliberately not a per-run stream. There is exactly one group,
    :data:`OPS_GROUP`, and the payload is a compact
    ``{"type": "runs_changed", ...}`` invalidation, so a burst of agent calls
    costs one small frame each rather than a fan-out of run payloads.

    Auth is the same gate as :class:`AgentRunConsumer` — a raw key, or a
    ticket minted for the reserved stream id :data:`OPS_STREAM_ID`.
    """

    async def connect(self) -> None:
        required = _resolve_env_key("AGENT_API_KEY")
        if required and not self._authorized(required, OPS_STREAM_ID):
            await self.close(code=CLOSE_UNAUTHORIZED)
            return
        await self.channel_layer.group_add(OPS_GROUP, self.channel_name)
        await self.accept()
        await self.send_json({"type": "ready", "channel": OPS_GROUP})

    async def disconnect(self, code: int) -> None:
        await self.channel_layer.group_discard(OPS_GROUP, self.channel_name)

    async def ops_event(self, event: dict[str, Any]) -> None:
        """Producer-side group_send → forwarded as JSON to every dashboard."""
        await self.send_json(event.get("payload") or {})
