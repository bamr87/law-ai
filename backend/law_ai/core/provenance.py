"""Provenance & audit logging on Django ORM (spec 011 FR-7, NFR-AUDIT-1).

Public surface preserved from the legacy ``app.core.provenance``:
``ProvenanceLogger.log_request``, ``log_agent_call``, ``log_graph_query``,
``logged_node`` decorator, and the module-level ``provenance`` instance.

Storage (spec 030, BL-20260810-10, BL-20260811-07): JSONL is the durable
append-only record and is always written first, so an audit event is never
lost because the database blinked. The Postgres ``AuditEvent`` row is then
written by whichever strategy the execution context allows — see
:func:`_persist`. Repeated DB-leg failures are surfaced at warning level;
a single transient one is not, because JSONL already holds the event.
"""

from __future__ import annotations

import atexit
import functools
import hashlib
import inspect
import json
import logging
import threading
import time
from datetime import UTC, datetime
from typing import Any, TypeVar
from collections.abc import Callable
from uuid import uuid4

from law_ai.core import audit_jsonl as audit_store

logger = logging.getLogger("law_ai.provenance")

F = TypeVar("F", bound=Callable[..., Any])


def _in_async_context() -> bool:
    """True when called from inside a running event loop.

    Django's ORM raises ``SynchronousOnlyOperation`` there, so the direct
    write is skipped rather than attempted-and-caught (BL-20260810-10): the
    old code failed on *every* async agent path and hid it at debug level.
    """
    import asyncio

    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return False
    return True


def _write_audit_row(event: dict[str, Any]) -> None:
    """Synchronous ``AuditEvent`` insert. Caller guarantees a sync context."""
    from law_ai.audit.models import AuditEvent

    AuditEvent.objects.create(
        kind=event.get("type") or "unknown",
        trace_id=event.get("trace_id", "") or "",
        agent_version=event.get("agent_version", "") or "",
        payload=event,
    )


#: Consecutive DB-leg failures. A single failure is noise (JSONL has the
#: event and Celery will retry); a *run* of them means audit rows are
#: silently not landing, which is exactly what BL-20260810-10 asked to see.
_DB_FAILURE_STREAK = 0
_PERSISTENT_FAILURE_THRESHOLD = 3
_FAILURE_LOCK = threading.Lock()

_AUDIT_EXECUTOR: Any = None
_EXECUTOR_LOCK = threading.Lock()


def _thread_offload_enabled() -> bool:
    """Whether the async+eager path may reach the ORM from a worker thread."""
    try:
        from django.conf import settings

        return bool(getattr(settings, "AUDIT_DB_THREAD_OFFLOAD", False))
    except Exception:  # pragma: no cover - settings always configured
        return False


def _note_db_result(ok: bool, context: str) -> None:
    """Track the DB leg's health and warn once a failure becomes persistent."""
    global _DB_FAILURE_STREAK
    with _FAILURE_LOCK:
        if ok:
            _DB_FAILURE_STREAK = 0
            return
        _DB_FAILURE_STREAK += 1
        streak = _DB_FAILURE_STREAK
    if streak >= _PERSISTENT_FAILURE_THRESHOLD:
        logger.warning(
            "audit DB persistence has failed %d times in a row (%s); "
            "JSONL is currently the only record",
            streak,
            context,
        )


def _audit_executor() -> Any:
    """Single-worker executor for offloaded audit inserts.

    One worker, so inserts stay ordered and a burst cannot open a connection
    per event. Daemon threads plus an atexit shutdown mean a pending insert
    never keeps the interpreter alive.
    """
    global _AUDIT_EXECUTOR
    with _EXECUTOR_LOCK:
        if _AUDIT_EXECUTOR is None:
            from concurrent.futures import ThreadPoolExecutor

            _AUDIT_EXECUTOR = ThreadPoolExecutor(
                max_workers=1, thread_name_prefix="law-ai-audit-db"
            )
            atexit.register(_shutdown_audit_executor)
    return _AUDIT_EXECUTOR


def _shutdown_audit_executor() -> None:  # pragma: no cover - interpreter exit
    global _AUDIT_EXECUTOR
    executor, _AUDIT_EXECUTOR = _AUDIT_EXECUTOR, None
    if executor is not None:
        executor.shutdown(wait=False)


def _write_audit_row_offloaded(event: dict[str, Any], jsonl_ok: bool) -> None:
    """Insert one audit row from a worker thread.

    ``close_old_connections()`` on both sides is not optional: this thread
    gets its own DB connection, and without the bracket a connection that the
    server closed underneath us would be reused and fail on the next event.
    """
    from django.db import close_old_connections

    close_old_connections()
    try:
        _write_audit_row(event)
        _note_db_result(True, "thread offload")
    except Exception as exc:
        _note_db_result(False, "thread offload")
        level = logger.warning if not jsonl_ok else logger.debug
        level("audit DB write failed in worker thread: %s", exc)
    finally:
        close_old_connections()


def _persist(event: dict[str, Any]) -> None:
    """Persist ``event`` to JSONL (always) and Postgres (context-dependent).

    JSONL is the durable append-only record and is written first, so an
    audit event is never lost even when the database leg fails.

    The Postgres leg picks a strategy by execution context:

    * **sync** (Celery worker, management command, WSGI) — write directly.
    * **async** (daphne/ASGI agent paths) — the ORM cannot be called here,
      so hand the row to the ``persist_audit_event`` Celery task, which
      executes it in a worker's sync context.
    * **async + eager Celery** (tests/dev) — the eager task would run inline
      in this same async context and fail identically. With
      ``AUDIT_DB_THREAD_OFFLOAD`` on (the dev default, BL-20260811-07) the
      insert is handed to a worker thread that brackets it with
      ``close_old_connections()``, so dev matches prod; with it off (the test
      default, because pytest-django wraps each test in a transaction a second
      connection cannot see) the DB leg is skipped and JSONL is the record.
    """
    jsonl_ok = True
    try:
        audit_store.record(event)
    except Exception as exc:  # pragma: no cover
        jsonl_ok = False
        logger.warning("audit JSONL persistence failed: %s", exc)

    if not _in_async_context():
        try:
            _write_audit_row(event)
            _note_db_result(True, "sync write")
            return
        except Exception as exc:
            _note_db_result(False, "sync write")
            logger.debug("audit DB write failed, deferring to Celery: %s", exc)

    try:
        from django.conf import settings

        eager = bool(getattr(settings, "CELERY_TASK_ALWAYS_EAGER", False))
    except Exception:  # pragma: no cover - settings always configured
        eager = False

    if eager and _in_async_context():
        # Nothing to gain from dispatching: eager execution is inline. A
        # worker thread is the only way to reach the ORM from here.
        if _thread_offload_enabled():
            try:
                _audit_executor().submit(_write_audit_row_offloaded, event, jsonl_ok)
                return
            except Exception as exc:  # pragma: no cover - executor exhausted
                logger.warning("audit thread offload failed: %s", exc)
        if not jsonl_ok:
            logger.warning(
                "audit event %s has NO durable record: JSONL failed and the "
                "DB leg is unavailable in this async/eager context",
                event.get("type"),
            )
        return

    try:
        from law_ai.core.tasks import persist_audit_event

        persist_audit_event.delay(event)
        _note_db_result(True, "celery dispatch")
    except Exception as exc:
        _note_db_result(False, "celery dispatch")
        # Only a genuine data-loss risk deserves a warning: JSONL already
        # holds the event in the normal case.
        level = logger.warning if not jsonl_ok else logger.debug
        level("audit Celery dispatch failed (%s): %s", type(exc).__name__, exc)


def _notify_ops_of_run(agent_name: str, trace_id: str) -> None:
    """Tell open ops dashboards a run landed (BL-20260429-16).

    An agent call is exactly the event the dashboard's five-second poll was
    looking for, so this is where the push belongs. Import is local and the
    call is best-effort in every direction: the notifier itself swallows
    channel-layer failures, and this guard covers the import (a management
    command with no channels app loaded) — the audit write above has already
    happened either way.
    """
    try:
        from law_ai.agentsapi.streaming import RUNS_CHANGED, notify_ops_nowait

        notify_ops_nowait(RUNS_CHANGED, agent=agent_name, trace_id=trace_id)
    except Exception:  # pragma: no cover - defensive
        logger.debug("ops dashboard notify unavailable", exc_info=True)


class ProvenanceLogger:
    """Central audit logger for Law AI."""

    @staticmethod
    def log_request(request: Any, response: Any) -> None:
        """Log incoming HTTP request with basic metadata.

        Accepts a Django ``HttpRequest``, or any object exposing the same
        ``method``/``path``/``META`` surface — the ASGI scope wrappers the
        agent paths hand in do.
        """
        method = getattr(request, "method", "?")
        path = getattr(request, "path", None)
        if path is None:
            url = getattr(request, "url", None)
            path = getattr(url, "path", "?") if url is not None else "?"
        client_ip: str
        meta = getattr(request, "META", None)
        if meta is not None:
            client_ip = meta.get("REMOTE_ADDR", "unknown")
            user_agent = meta.get("HTTP_USER_AGENT", "unknown")
        else:
            client = getattr(request, "client", None)
            client_ip = getattr(client, "host", "unknown") if client else "unknown"
            user_agent = getattr(request, "headers", {}).get("user-agent", "unknown")
        status_code = getattr(response, "status_code", 0)
        log_entry = {
            "timestamp": datetime.now(UTC).isoformat(),
            "request_id": str(uuid4()),
            "method": method,
            "path": path,
            "client_ip": client_ip,
            "status_code": status_code,
            "user_agent": user_agent,
            "type": "http_request",
        }
        logger.info(json.dumps(log_entry))
        _persist(log_entry)

    @staticmethod
    def log_agent_call(
        agent_name: str,
        input_data: dict[str, Any],
        output_data: dict[str, Any],
        model: str,
        latency_ms: float,
        # Keyword-only: keeps the positional arity at 5 (ruff PLR0917) and
        # matches every existing call site, none of which pass these by
        # position.
        *,
        confidence: float | None = None,
        sources: list[dict[str, Any]] | None = None,
        prompt_id: str | None = None,
        prompt_version: str | None = None,
    ) -> str:
        trace_id = str(uuid4())
        child_trace_ids = (
            input_data.get("child_trace_ids") if isinstance(input_data, dict) else None
        )
        is_error = (
            bool(input_data.get("error")) if isinstance(input_data, dict) else False
        )
        log_entry: dict[str, Any] = {
            "trace_id": trace_id,
            "timestamp": datetime.now(UTC).isoformat(),
            "agent": agent_name,
            "model": model,
            "latency_ms": latency_ms,
            "confidence": confidence,
            # _stable_hash, not Python's salted hash(): audit hashes must be
            # reproducible across processes/restarts to prove what an agent saw.
            "input_hash": _stable_hash(input_data),
            "output_summary": str(output_data)[:500],
            "sources_count": len(sources) if sources else 0,
            "sources": sources[:3] if sources else [],
            "type": "agent_call",
        }
        if prompt_id:
            log_entry["prompt_id"] = prompt_id
        if prompt_version:
            log_entry["prompt_version"] = prompt_version
        # Preserve a minimal `input` view so the audit store can correlate
        # multi-agent runs (parent → children) and flag error events without
        # leaking full prompts.
        input_view: dict[str, Any] = {}
        if isinstance(child_trace_ids, list) and child_trace_ids:
            input_view["child_trace_ids"] = [
                c for c in child_trace_ids if isinstance(c, str)
            ]
        if is_error:
            input_view["error"] = True
        if input_view:
            log_entry["input"] = input_view
        logger.info(json.dumps(log_entry))
        _persist(log_entry)
        _notify_ops_of_run(agent_name, trace_id)
        return trace_id

    @staticmethod
    def log_event(event_type: str, payload: dict[str, Any]) -> None:
        """Log a lightweight non-agent event (e.g. WS delivery bookkeeping).

        Keeps infrastructure bookkeeping OUT of the ``agent_call`` taxonomy so
        agent metrics (latency, confidence, call counts) are not polluted by
        transport events.
        """
        log_entry: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "type": event_type,
            **payload,
        }
        logger.info(json.dumps(log_entry, default=str))
        _persist(log_entry)

    @staticmethod
    def log_graph_query(
        cypher: str, params: dict[str, Any], result_count: int, latency_ms: float
    ) -> None:
        log_entry = {
            "timestamp": datetime.now(UTC).isoformat(),
            "type": "graph_query",
            "cypher": cypher[:300],
            "params_keys": list(params.keys()),
            "result_count": result_count,
            "latency_ms": latency_ms,
        }
        logger.info(json.dumps(log_entry))
        _persist(log_entry)


provenance = ProvenanceLogger()


# ---------------------------------------------------------------------------
# @logged_node — unchanged from legacy app.core.provenance (spec 010 FR-5).
# ---------------------------------------------------------------------------


def _stable_hash(payload: Any) -> str:
    try:
        blob = json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
    except (TypeError, ValueError):
        blob = repr(payload).encode("utf-8")
    return hashlib.blake2b(blob, digest_size=8).hexdigest()


def _current_trace_id() -> str | None:
    try:
        from opentelemetry import trace

        span = trace.get_current_span()
        ctx = span.get_span_context()
        if not ctx.is_valid:
            return None
        return f"{ctx.trace_id:032x}"
    except Exception:
        return None


def _record_node_event(
    *,
    node: str,
    state: Any,
    output: Any,
    latency_ms: float,
    extra: dict[str, Any] | None,
) -> str:
    trace_id = _current_trace_id() or str(uuid4())
    event: dict[str, Any] = {
        "timestamp": datetime.now(UTC).isoformat(),
        "type": "langgraph_node",
        "node": node,
        "trace_id": trace_id,
        "input_hash": _stable_hash(state),
        "output_hash": _stable_hash(output),
        "latency_ms": round(latency_ms, 2),
    }
    if extra:
        event.update(extra)
    served_by = _node_model_label(output)
    if served_by is not None:
        event["model"] = served_by
    logger.info(json.dumps(event, default=str))
    _persist(event)
    return trace_id


def _node_model_label(output: Any) -> str | None:
    """The tier that actually served this node's call, when the node says.

    :func:`logged_node` binds ``model`` at decoration time, so a node running
    on the provider chain could only ever record the static ``(provider
    chain)`` placeholder while the tier that answered was known elsewhere —
    in graph state and on the OTel span, but not on the audit row itself.
    LegalWorkflow's LLM nodes already return the serving tier as
    ``model_label``; preferring it makes the per-node audit trail name the
    real provider (BL-20260905-86). A node that returns none — the
    deterministic ones, and the refusal paths that never called a model —
    keeps the decorator's static label.
    """
    if not isinstance(output, dict):
        return None
    label = output.get("model_label")
    if not isinstance(label, str):
        return None
    return label.strip() or None


def _pick_state(args: tuple[Any, ...], kwargs: dict[str, Any]) -> Any:
    """Locate the workflow-state argument for a ``logged_node`` call.

    Decorated node functions are usually bound methods ``(self, state)`` —
    hashing ``args[0]`` there hashes the instance ``repr`` (with its memory
    address), which is non-reproducible and information-free. The state is
    the first Mapping-shaped positional arg (LangGraph states are dicts).
    """
    if "state" in kwargs:
        return kwargs["state"]
    for arg in args:
        if isinstance(arg, dict):
            return arg
    return args[0] if args else None


def logged_node(
    name: str,
    *,
    model: str | None = None,
    prompt_id: str | None = None,
    prompt_version: str | None = None,
) -> Callable[[F], F]:
    def decorator(func: F) -> F:
        is_coro = inspect.iscoroutinefunction(func)

        if is_coro:

            @functools.wraps(func)
            async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
                state = _pick_state(args, kwargs)
                started = time.perf_counter()
                output = await func(*args, **kwargs)
                latency = (time.perf_counter() - started) * 1000.0
                _record_node_event(
                    node=name,
                    state=state,
                    output=output,
                    latency_ms=latency,
                    extra={
                        "model": model,
                        "prompt_id": prompt_id,
                        "prompt_version": prompt_version,
                    },
                )
                return output

            return async_wrapper  # type: ignore[return-value]

        @functools.wraps(func)
        def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
            state = _pick_state(args, kwargs)
            started = time.perf_counter()
            output = func(*args, **kwargs)
            latency = (time.perf_counter() - started) * 1000.0
            _record_node_event(
                node=name,
                state=state,
                output=output,
                latency_ms=latency,
                extra={
                    "model": model,
                    "prompt_id": prompt_id,
                    "prompt_version": prompt_version,
                },
            )
            return output

        return sync_wrapper  # type: ignore[return-value]

    return decorator


__all__ = ["ProvenanceLogger", "_stable_hash", "logged_node", "provenance"]
