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
the socket must present it (``?api_key=`` — browsers cannot set headers on
a WebSocket handshake — or an ``X-API-Key`` header for non-browser
clients). With no key configured the socket stays open, matching the
default-open localhost posture of the REST routers.
"""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import parse_qs

from channels.generic.websocket import AsyncJsonWebsocketConsumer

from law_ai.core.auth import _resolve_env_key

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


class AgentRunConsumer(AsyncJsonWebsocketConsumer):
    """Subscribes the client to ``agent-run-<run_id>`` and emits ``ready``."""

    def _presented_key(self) -> str | None:
        """Pull the API key from the query string or handshake headers."""
        query = parse_qs((self.scope.get("query_string") or b"").decode())
        values = query.get("api_key") or query.get("token") or []
        if values and values[0]:
            return str(values[0])
        for raw_name, raw_value in self.scope.get("headers") or []:
            if raw_name.decode().lower() == "x-api-key":
                return str(raw_value.decode())
        return None

    async def connect(self) -> None:
        run_id = str(self.scope["url_route"]["kwargs"]["run_id"])
        if not STREAM_ID_RE.match(run_id):
            await self.close(code=CLOSE_BAD_STREAM_ID)
            return

        required = _resolve_env_key("AGENT_API_KEY")
        if required and self._presented_key() != required:
            # Reject before joining the group so an unauthorized socket
            # never receives a single event.
            await self.close(code=CLOSE_UNAUTHORIZED)
            return

        self.run_id = run_id
        self.group_name = stream_group(run_id)
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()
        await self.send_json({"type": "ready", "run_id": self.run_id})

    async def disconnect(self, code: int) -> None:
        if hasattr(self, "group_name"):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def agent_event(self, event: dict[str, Any]) -> None:
        """Producer-side group_send → forwarded as JSON to the WS client."""
        payload = event.get("payload") or {}
        await self.send_json(payload)
