"""Producer-side helper for the agent-run WebSocket channel (BL-20260811-15).

One function, :func:`emit_stream_event`, publishes a progress payload to the
``agent-run-<stream_id>`` group that :class:`~law_ai.agentsapi.consumers.
AgentRunConsumer` forwards to subscribed clients. It started life inside
``analysis/urls.py`` and was hoisted here so the other long-running paths — the
LSAT tutor, the autonomy cycle — can stream progress without importing the
analysis app or, worse, growing their own slightly-different copy.

Two invariants come with it and must not be relaxed:

* **Fire-and-forget.** A channel-layer failure (no Redis, no subscriber) is
  logged and swallowed. A Redis outage must never abort the work the events
  describe (spec 021 AC-2, FR-1).
* **Transport bookkeeping, not an agent call.** Each emit writes a
  ``ws_event_sent`` provenance event, deliberately distinct from agent events
  so dashboards' latency/confidence/count metrics stay unpolluted.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer

from law_ai.agentsapi import replay
from law_ai.agentsapi.consumers import OPS_GROUP, STREAM_ID_RE, stream_group
from law_ai.core.provenance import provenance

logger = logging.getLogger(__name__)

__all__ = [
    "METRICS_CHANGED",
    "RUNS_CHANGED",
    "emit_stream_event",
    "emit_stream_event_sync",
    "notify_ops",
    "notify_ops_nowait",
]


async def emit_stream_event(
    stream_key: str,
    payload: dict[str, Any],
    *,
    source: str = "unknown",
) -> None:
    """Send one progress event to the ``agent-run-{stream_key}`` WS group.

    ``stream_key`` is the client-chosen ``stream_id`` (spec 032): a client that
    subscribed *before* starting the work receives these live. ``source`` names
    the producing subsystem on the provenance event ("analysis", "lsat_tutor",
    "autonomy") so one stream's events can be told from another's after the
    fact.
    """
    if not STREAM_ID_RE.match(stream_key):
        # The consumer rejects these outright, so a group_send would go
        # nowhere; failing quietly here keeps a bad client id from being an
        # error the producing work has to handle.
        logger.warning("refusing to emit on invalid stream id %r", stream_key[:80])
        return
    try:
        # Stamp and buffer first (BL-20260811-14): the `seq` a reconnecting
        # client cursors on has to be the same number live subscribers saw, so
        # the recorded payload — not the caller's — is what goes on the wire.
        stamped = await replay.record(stream_key, payload)
        layer = get_channel_layer()
        if layer is None:
            return
        await layer.group_send(
            # Shared helper so producer and consumer group names cannot drift.
            stream_group(stream_key),
            {"type": "agent_event", "payload": stamped},
        )
        provenance.log_event(
            "ws_event_sent",
            {
                "source": source,
                "analysis_id": stream_key,
                "stream_id": stream_key,
                "ws_event_type": str(payload.get("type")),
            },
        )
    except Exception:
        logger.warning(
            "WS event emit failed for stream_key=%s (source=%s)",
            stream_key,
            source,
            exc_info=True,
        )


def emit_stream_event_sync(
    stream_key: str,
    payload: dict[str, Any],
    *,
    source: str = "unknown",
) -> None:
    """:func:`emit_stream_event` for synchronous producers (Celery, commands).

    A no-op inside a running event loop rather than a crash: ``async_to_sync``
    refuses there, and the autonomy cycle runs on both paths. An async caller
    should await :func:`emit_stream_event` directly.
    """
    try:
        async_to_sync(emit_stream_event)(stream_key, payload, source=source)
    except Exception:
        logger.warning(
            "sync WS event emit skipped for stream_key=%s (source=%s)",
            stream_key,
            source,
            exc_info=True,
        )


# ---------------------------------------------------------------------------
# Ops dashboard invalidation (BL-20260429-16)
# ---------------------------------------------------------------------------
#: Change kinds the dashboard understands. Deliberately coarse: the socket
#: says *something changed*, the client re-fetches through the same REST
#: endpoints. Pushing the data itself would duplicate every serializer over a
#: second transport and make the socket a second source of truth.
RUNS_CHANGED = "runs_changed"
METRICS_CHANGED = "metrics_changed"


def _ops_push_enabled() -> bool:
    """Whether change notifications are published at all.

    Off in the test settings: the suite makes hundreds of agent calls and
    every one would spawn a socket write no assertion reads. Tests for this
    feature turn it on explicitly.
    """
    from django.conf import settings

    return bool(getattr(settings, "AGENT_OPS_PUSH_ENABLED", False))


async def notify_ops(kind: str, **fields: Any) -> None:
    """Tell every open dashboard that *kind* of data changed.

    Fire-and-forget, like :func:`emit_stream_event`: this runs inside the
    provenance writer, and a Redis outage must cost a dashboard its liveness,
    never an agent its run.
    """
    if not _ops_push_enabled():
        return
    try:
        layer = get_channel_layer()
        if layer is None:
            return
        await layer.group_send(
            OPS_GROUP, {"type": "ops_event", "payload": {"type": kind, **fields}}
        )
    except Exception:
        logger.debug("ops dashboard notify failed (%s)", kind, exc_info=True)


def notify_ops_nowait(kind: str, **fields: Any) -> None:
    """:func:`notify_ops` from any context, sync or async, without blocking.

    In an event loop the send is scheduled as a task and never awaited — the
    caller is a hot audit path and must not take on the latency of a Redis
    round-trip. Outside one it runs inline through ``async_to_sync``. Every
    failure, including "there is no channel layer here", is swallowed.
    """
    if not _ops_push_enabled():
        return
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        try:
            async_to_sync(notify_ops)(kind, **fields)
        except Exception:
            logger.debug("ops dashboard notify skipped (%s)", kind, exc_info=True)
        return
    task = loop.create_task(notify_ops(kind, **fields))
    # Without a callback an exception inside the task is only reported when it
    # is garbage-collected, as an unraisable warning in an unrelated test.
    task.add_done_callback(lambda done: done.exception())
