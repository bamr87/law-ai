"""WebSocket consumer for live agent traces (spec 011 FR-12, AC-7)."""
from __future__ import annotations

from channels.generic.websocket import AsyncJsonWebsocketConsumer


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
