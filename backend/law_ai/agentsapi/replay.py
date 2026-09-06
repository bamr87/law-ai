"""A short server-side ring buffer per agent stream (BL-20260811-14).

A dropped WebSocket used to lose the in-flight trace outright: the producer
fires and forgets, the consumer forwards live frames only, and a client that
reconnects has no way to ask what it missed. That is worst exactly when it
matters — a long run on a flaky connection.

So every emitted payload is stamped with a monotonic ``seq`` and appended to a
short, expiring buffer. A client reconnects with ``?since=<seq>`` and the
consumer replays everything after that cursor before resuming live forwarding.

Two deliberate limits:

* **Short.** ``MAX_EVENTS`` payloads, ``TTL_SECONDS`` of life. This is a
  reconnect window, not an event store — the durable record of a run is the
  audit log, and a buffer that outlived the run would quietly become a second,
  weaker one.
* **Never load-bearing.** Redis is the backend when it is reachable (so the
  buffer is shared by every daphne worker), and an in-process dict when it is
  not. Both paths swallow their own failures: spec 021 AC-2 says a Redis
  outage costs liveness, never the work itself.

``AGENT_STREAM_REPLAY_URL`` overrides which Redis is used, and an empty value
pins the in-process buffer — which is what the test settings do, so the suite
neither depends on nor pollutes a shared Redis.
"""

from __future__ import annotations

import json
import logging
from collections import deque
from typing import Any

from law_ai.core.settings_proxy import settings_proxy as settings

logger = logging.getLogger(__name__)

__all__ = ["MAX_EVENTS", "TTL_SECONDS", "events_since", "record", "reset"]

#: How many recent payloads one stream keeps. A run emits a handful of steps;
#: 200 covers a token stream's worth of chatter without turning into storage.
MAX_EVENTS = 200

#: How long a buffer survives its last write. Long enough for a laptop lid to
#: close and reopen, short enough that abandoned runs cost nothing.
TTL_SECONDS = 900

#: Per-process fallback: stream id -> recent payloads (each already stamped).
_memory: dict[str, deque[dict[str, Any]]] = {}
_memory_seq: dict[str, int] = {}


def _events_key(stream_id: str) -> str:
    return f"agent-run:{stream_id}:events"


def _seq_key(stream_id: str) -> str:
    return f"agent-run:{stream_id}:seq"


def _client() -> Any:
    """A redis.asyncio client on ``REDIS_URL``, or ``None``.

    Built per call rather than cached: this is off the hot path (one small
    write per emitted event), and a cached client outliving a connection reset
    is a subtler failure than reconnecting.
    """
    configured = getattr(settings, "AGENT_STREAM_REPLAY_URL", None)
    url = str(
        (configured if configured is not None else getattr(settings, "REDIS_URL", ""))
        or ""
    ).strip()
    if not url:
        return None
    try:
        import redis.asyncio as aioredis

        # redis's async factory carries no annotations, so --strict sees an
        # untyped call; the client itself is used through `Any` either way.
        return aioredis.from_url(  # type: ignore[no-untyped-call]
            url, decode_responses=True
        )
    except Exception:  # pragma: no cover - import/config failure
        logger.debug("replay buffer: no redis client available", exc_info=True)
        return None


def _memory_record(stream_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    seq = _memory_seq.get(stream_id, 0) + 1
    _memory_seq[stream_id] = seq
    stamped = {**payload, "seq": seq}
    _memory.setdefault(stream_id, deque(maxlen=MAX_EVENTS)).append(stamped)
    return stamped


async def record(stream_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Append *payload* to the stream's buffer, returning it stamped with ``seq``.

    The caller sends the returned dict rather than the one it passed in, so the
    sequence number a reconnecting client cursors on is the same one live
    subscribers already saw.
    """
    client = _client()
    if client is None:
        return _memory_record(stream_id, payload)
    try:
        seq = int(await client.incr(_seq_key(stream_id)))
        stamped = {**payload, "seq": seq}
        pipe = client.pipeline()
        pipe.rpush(_events_key(stream_id), json.dumps(stamped, default=str))
        pipe.ltrim(_events_key(stream_id), -MAX_EVENTS, -1)
        pipe.expire(_events_key(stream_id), TTL_SECONDS)
        pipe.expire(_seq_key(stream_id), TTL_SECONDS)
        await pipe.execute()
        return stamped
    except Exception:
        logger.debug("replay buffer write fell back to memory", exc_info=True)
        return _memory_record(stream_id, payload)
    finally:
        await _aclose(client)


async def events_since(stream_id: str, since: int) -> list[dict[str, Any]]:
    """Buffered payloads with ``seq`` greater than *since*, oldest first.

    An empty list is the honest answer to every unanswerable case — no buffer,
    a cursor past the end, a Redis that has gone away — because a reconnecting
    client can always fall back to the REST result it would have polled.
    """
    client = _client()
    if client is None:
        return _memory_since(stream_id, since)
    try:
        raw = await client.lrange(_events_key(stream_id), 0, -1)
    except Exception:
        logger.debug("replay buffer read fell back to memory", exc_info=True)
        return _memory_since(stream_id, since)
    finally:
        await _aclose(client)
    return [event for event in _decode(raw) if int(event.get("seq", 0)) > since]


def _decode(raw: list[str]) -> list[dict[str, Any]]:
    """Parse stored frames, skipping any that no longer decode."""
    out: list[dict[str, Any]] = []
    for item in raw or []:
        try:
            event = json.loads(item)
        except (TypeError, ValueError):
            continue
        if isinstance(event, dict):
            out.append(event)
    return out


def _memory_since(stream_id: str, since: int) -> list[dict[str, Any]]:
    return [
        event
        for event in _memory.get(stream_id, ())
        if int(event.get("seq", 0)) > since
    ]


async def _aclose(client: Any) -> None:
    try:
        await client.aclose()
    except Exception:  # pragma: no cover - close must never raise upward
        logger.debug("replay buffer: client close failed", exc_info=True)


def reset() -> None:
    """Drop the in-process buffer (test helper)."""
    _memory.clear()
    _memory_seq.clear()
