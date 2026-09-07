"""The replay buffer's Redis client is pooled, not rebuilt (BL-20260905-75).

``record`` runs once per emitted event, and a streamed IRAC answer emits one
per delta. Building a ``redis.asyncio`` client per call charged every delta a
connect/handshake/disconnect. These tests pin the two halves of the fix: the
client is reused across calls, and a failed call still falls back to the
in-process buffer *and* drops the pooled client so the next call reconnects.

No Redis here — ``redis.asyncio.from_url`` is the seam, so the fake client
below records exactly how often the module asked for one.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

import pytest

from law_ai.agentsapi import replay

pytestmark = pytest.mark.django_db(transaction=False)

_URL = "redis://replay-test:6379/0"


class _FakePipe:
    def rpush(self, *args: Any, **kwargs: Any) -> None:
        return None

    def ltrim(self, *args: Any, **kwargs: Any) -> None:
        return None

    def expire(self, *args: Any, **kwargs: Any) -> None:
        return None

    async def execute(self) -> list[Any]:
        return []


class _FakeClient:
    """Enough of redis.asyncio for :mod:`law_ai.agentsapi.replay`."""

    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.seq = 0
        self.closed = 0

    async def incr(self, key: str) -> int:
        if self.fail:
            raise ConnectionError("redis went away")
        self.seq += 1
        return self.seq

    def pipeline(self) -> _FakePipe:
        return _FakePipe()

    async def lrange(self, key: str, start: int, end: int) -> list[str]:
        if self.fail:
            raise ConnectionError("redis went away")
        return []

    async def aclose(self) -> None:
        self.closed += 1


class _Factory:
    """Stands in for ``redis.asyncio.from_url`` and counts its calls."""

    def __init__(self, *, fail: bool = False) -> None:
        self.calls = 0
        self.clients: list[_FakeClient] = []
        self._fail = fail

    def __call__(self, url: str, **kwargs: Any) -> _FakeClient:
        self.calls += 1
        client = _FakeClient(fail=self._fail)
        self.clients.append(client)
        return client


@pytest.fixture(autouse=True)
def _pinned_replay_url(settings: Any) -> Any:
    settings.AGENT_STREAM_REPLAY_URL = _URL
    replay.reset()
    yield
    replay.reset()


class TestPooledClient:
    async def test_the_client_is_built_once_and_reused(self) -> None:
        factory = _Factory()
        with patch("redis.asyncio.from_url", factory):
            first = await replay.record("run-pool", {"type": "agent_step"})
            second = await replay.record("run-pool", {"type": "agent_step"})
            await replay.events_since("run-pool", 0)

        assert factory.calls == 1  # one pool for three round trips
        assert factory.clients[0].closed == 0  # and it is not torn down
        assert [first["seq"], second["seq"]] == [1, 2]

    async def test_a_changed_url_rebuilds_the_client(self, settings: Any) -> None:
        factory = _Factory()
        with patch("redis.asyncio.from_url", factory):
            await replay.record("run-url", {"type": "agent_step"})
            settings.AGENT_STREAM_REPLAY_URL = "redis://elsewhere:6379/0"
            await replay.record("run-url", {"type": "agent_step"})

        assert factory.calls == 2

    async def test_a_failed_call_falls_back_and_drops_the_pool(self) -> None:
        factory = _Factory(fail=True)
        with patch("redis.asyncio.from_url", factory):
            stamped = await replay.record("run-broken", {"type": "agent_step"})
            # The in-process buffer answered instead of the caller seeing an error.
            assert stamped["seq"] == 1
            assert await replay.events_since("run-broken", 0) == [stamped]
            # ...and the dead client was closed rather than kept in the pool.
            assert factory.clients[0].closed == 1
            await replay.record("run-broken", {"type": "agent_step"})

        # Each failure reconnects: 1 for the write, 1 for the read, 1 for the
        # second write. Nothing is wedged onto a client that has gone away.
        assert factory.calls == 3
