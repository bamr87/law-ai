"""Provenance & audit logging on Django ORM (spec 011 FR-7, NFR-AUDIT-1).

Public surface preserved from the legacy ``app.core.provenance``:
``ProvenanceLogger.log_request``, ``log_agent_call``, ``log_graph_query``,
``logged_node`` decorator, and the module-level ``provenance`` instance.

Storage: every event also calls ``AuditEvent.objects.create`` (sync) to
keep the JSONL writer + a queryable Postgres row in sync. On DB failure,
the JSONL fallback is invoked synchronously *and* a Celery task is
enqueued so the row eventually lands in Postgres.
"""

from __future__ import annotations

import functools
import hashlib
import inspect
import json
import logging
import time
from datetime import UTC, datetime
from typing import Any, TypeVar
from collections.abc import Callable
from uuid import uuid4

from lawgraph.core import audit_jsonl as audit_store

logger = logging.getLogger("lawgraph.provenance")

F = TypeVar("F", bound=Callable[..., Any])


def _persist(event: dict[str, Any]) -> None:
    """Persist ``event`` to ``AuditEvent`` with JSONL + Celery fallback."""
    try:
        audit_store.record(event)
    except Exception as exc:  # pragma: no cover
        logger.warning("audit JSONL persistence failed: %s", exc)

    try:
        from lawgraph.audit.models import AuditEvent

        kind = event.get("type") or "unknown"
        AuditEvent.objects.create(
            kind=kind,
            trace_id=event.get("trace_id", "") or "",
            agent_version=event.get("agent_version", "") or "",
            payload=event,
        )
    except Exception as exc:
        logger.debug("audit DB persistence skipped: %s", exc)
        # Fallback: enqueue Celery task to retry async (FR-7 + spec 011 FR-11).
        try:
            from lawgraph.core.tasks import persist_audit_event

            persist_audit_event.delay(event)
        except Exception:
            pass


class ProvenanceLogger:
    """Central audit logger for LawGraph AI."""

    @staticmethod
    def log_request(request: Any, response: Any) -> None:
        """Log incoming HTTP request with basic metadata.

        Accepts both Django ``HttpRequest`` and FastAPI/Starlette ``Request``
        for spec-011 cutover continuity.
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
        confidence: float | None = None,
        sources: list[dict] | None = None,
    ) -> str:
        trace_id = str(uuid4())
        log_entry = {
            "trace_id": trace_id,
            "timestamp": datetime.now(UTC).isoformat(),
            "agent": agent_name,
            "model": model,
            "latency_ms": latency_ms,
            "confidence": confidence,
            "input_hash": hash(str(input_data)),
            "output_summary": str(output_data)[:500],
            "sources_count": len(sources) if sources else 0,
            "sources": sources[:3] if sources else [],
            "type": "agent_call",
        }
        logger.info(json.dumps(log_entry))
        _persist(log_entry)
        return trace_id

    @staticmethod
    def log_graph_query(
        cypher: str, params: dict, result_count: int, latency_ms: float
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
    logger.info(json.dumps(event, default=str))
    _persist(event)
    return trace_id


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
                state = args[0] if args else kwargs.get("state")
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
            state = args[0] if args else kwargs.get("state")
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
