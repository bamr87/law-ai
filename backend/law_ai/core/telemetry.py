"""OpenTelemetry wiring for spec 010 FR-4.

When ``settings.PHOENIX_COLLECTOR_ENDPOINT`` is unset (the default in tests
and offline runs) ``init_tracing`` becomes a complete no-op so we never
touch the global tracer provider. When it *is* set, we register an
OTLP/HTTP exporter pointed at the self-hosted Arize Phoenix container and
auto-instrument FastAPI + httpx so every request span ends up in Phoenix
alongside the LangGraph node spans emitted by ``app.core.provenance.logged_node``.

All imports are lazy + guarded so a developer who hasn't installed the
``local-ai`` extra still gets a working backend.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from law_ai.core.settings_proxy import settings_proxy as settings

if TYPE_CHECKING:  # pragma: no cover - typing only
    from fastapi import FastAPI

logger = logging.getLogger("law_ai.telemetry")

_INITIALIZED = False


def is_enabled() -> bool:
    return bool(settings.PHOENIX_COLLECTOR_ENDPOINT)


def init_tracing(app: FastAPI | None = None) -> bool:
    """Configure OTEL → Phoenix; idempotent. Returns ``True`` when tracing is live.

    Failures (missing optional deps, unreachable collector at boot) log a
    warning and return ``False``; the application continues to run with
    tracing disabled.
    """
    global _INITIALIZED
    if not is_enabled():
        logger.debug("telemetry disabled (PHOENIX_COLLECTOR_ENDPOINT unset)")
        return False
    if _INITIALIZED:
        return True

    try:
        from opentelemetry import trace
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
            OTLPSpanExporter,
        )
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
    except ImportError as exc:
        logger.warning(
            "telemetry: opentelemetry packages missing (%s); "
            "install the local-ai extra to enable Phoenix tracing",
            exc,
        )
        return False

    resource = Resource.create(
        {
            "service.name": settings.PHOENIX_PROJECT_NAME,
            "service.version": "0.1.0",
            "deployment.environment": settings.ENVIRONMENT,
        }
    )
    provider = TracerProvider(resource=resource)
    exporter = OTLPSpanExporter(endpoint=settings.PHOENIX_COLLECTOR_ENDPOINT)
    provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(provider)

    if app is not None:
        try:
            from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

            FastAPIInstrumentor.instrument_app(app, tracer_provider=provider)
        except ImportError:  # pragma: no cover - extra missing
            logger.warning("telemetry: FastAPI instrumentation not available")

    try:
        from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor

        HTTPXClientInstrumentor().instrument(tracer_provider=provider)
    except ImportError:  # pragma: no cover - extra missing
        logger.warning("telemetry: httpx instrumentation not available")

    _INITIALIZED = True
    logger.info(
        "telemetry: exporting to %s (project=%s)",
        settings.PHOENIX_COLLECTOR_ENDPOINT,
        settings.PHOENIX_PROJECT_NAME,
    )
    return True


def phoenix_trace_url(trace_id: str | None) -> str | None:
    """Build a deep-link to the Phoenix UI for ``trace_id``.

    Returns ``None`` when telemetry is disabled or the trace id is falsy
    so callers can omit the field from API responses without branching.
    """
    if not trace_id or not is_enabled():
        return None
    base = settings.PHOENIX_UI_URL.rstrip("/")
    project = settings.PHOENIX_PROJECT_NAME
    return f"{base}/projects/{project}/traces/{trace_id}"
