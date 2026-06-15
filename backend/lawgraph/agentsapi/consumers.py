"""WebSocket consumers for live agent traces (spec 011 FR-12, AC-7) and the
dashboard-wide live activity feed (spec 022 NG3, WS3)."""

from __future__ import annotations

from channels.generic.websocket import AsyncJsonWebsocketConsumer

from .broadcast import ACTIVITY_GROUP


class AgentRunConsumer(AsyncJsonWebsocketConsumer):
    """Subscribes the client to ``agent-run-<run_id>`` group and emits ``ready``."""

    async def connect(self) -> None:
        self.run_id = self.scope["url_route"]["kwargs"]["run_id"]
        self.group_name = f"agent-run-{self.run_id}"
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()
        await self.send_json({"type": "ready", "run_id": self.run_id})

    async def disconnect(self, code: int) -> None:
        if hasattr(self, "group_name"):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def agent_event(self, event: dict[str, object]) -> None:
        """Producer-side group_send → forwarded as JSON to the WS client."""
        payload = event.get("payload") or {}
        await self.send_json(payload)


class AgentActivityConsumer(AsyncJsonWebsocketConsumer):
    """Dashboard-wide live feed: joins the single ``agents-activity`` group and
    forwards every compact provenance event broadcast by
    :func:`lawgraph.agentsapi.broadcast.broadcast_activity`.

    Read-only fan-out — the consumer never accepts client input; clients that
    can't reach the socket fall back to the dashboard's HTTP poll.
    """

    async def connect(self) -> None:
        await self.channel_layer.group_add(ACTIVITY_GROUP, self.channel_name)
        await self.accept()
        await self.send_json({"type": "ready", "feed": ACTIVITY_GROUP})

    async def disconnect(self, code: int) -> None:
        await self.channel_layer.group_discard(ACTIVITY_GROUP, self.channel_name)

    async def activity_event(self, event: dict[str, object]) -> None:
        """Producer-side ``group_send`` (``type='activity.event'``) → WS client."""
        await self.send_json(event.get("event") or {})
