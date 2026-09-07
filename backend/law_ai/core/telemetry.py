"""OpenTelemetry wiring for spec 010 FR-4.

With no collector configured (the default in tests and offline runs)
``init_tracing`` is a complete no-op, so the global tracer provider is never
touched. When one *is* configured, we register an OTLP/HTTP exporter and
auto-instrument Django + httpx, so every request span lands beside the
LangGraph node spans emitted by ``law_ai.core.provenance.logged_node``.

BL-20260503-23: the instrumentor is ``DjangoInstrumentor``. The FastAPI
branch it replaced was dead code — the app has been Django/daphne since spec
011, ``fastapi`` is not a backend dependency, and the only caller passed
``None``, so the branch could never run.

BL-20260502-07: the collector is chosen by ``settings.OBSERVABILITY_BACKEND``
(``phoenix`` — the default — ``langfuse``, or ``none``) rather than hardcoded,
so a licensing change at one vendor is a config edit rather than a code
change. ``OTEL_EXPORTER_OTLP_ENDPOINT``/``_HEADERS`` reach any other
OTLP/HTTP collector. The response field stays named ``phoenix_trace_url``
because clients already read it; :func:`trace_url` is the backend-agnostic
implementation behind that name.

All imports are lazy + guarded so a developer who has not installed the
``local-ai`` extra still gets a working backend.
"""

from __future__ import annotations

import logging

from law_ai.core.settings_proxy import settings_proxy as settings

logger = logging.getLogger("law_ai.telemetry")

_INITIALIZED = False


PHOENIX = "phoenix"
LANGFUSE = "langfuse"
NONE = "none"


def backend() -> str:
    """The configured observability backend, normalised.

    Anything unrecognised is treated as ``none`` and warned about once, so a
    typo disables tracing loudly instead of silently exporting nowhere.
    """
    name = str(getattr(settings, "OBSERVABILITY_BACKEND", PHOENIX) or "").lower()
    if name in {PHOENIX, LANGFUSE, NONE}:
        return name
    logger.warning(
        "telemetry: unknown OBSERVABILITY_BACKEND=%r — tracing disabled", name
    )
    return NONE


def _basic_auth_header(public_key: str, secret_key: str) -> str:
    import base64

    raw = f"{public_key}:{secret_key}".encode()
    return "Basic " + base64.b64encode(raw).decode("ascii")


def _parse_headers(raw: str) -> dict[str, str]:
    """Parse the OTLP ``k=v,k=v`` header form. Malformed pairs are skipped."""
    headers: dict[str, str] = {}
    for pair in str(raw or "").split(","):
        key, sep, value = pair.partition("=")
        if sep and key.strip():
            headers[key.strip()] = value.strip()
    return headers


def exporter_config() -> tuple[str, dict[str, str]] | None:
    """``(endpoint, headers)`` for the configured backend, or ``None``.

    BL-20260502-07: the exporter is chosen here rather than hardcoded, so
    swapping Phoenix for Langfuse (or any other OTLP/HTTP collector) is a
    config edit. ``OTEL_EXPORTER_OTLP_ENDPOINT`` overrides the backend's own
    endpoint for collectors we do not name.
    """
    name = backend()
    if name == NONE:
        return None

    headers = _parse_headers(getattr(settings, "OTEL_EXPORTER_OTLP_HEADERS", ""))
    override = str(getattr(settings, "OTEL_EXPORTER_OTLP_ENDPOINT", "") or "")

    if name == LANGFUSE:
        public_key = str(getattr(settings, "LANGFUSE_PUBLIC_KEY", "") or "")
        secret_key = str(getattr(settings, "LANGFUSE_SECRET_KEY", "") or "")
        host = str(getattr(settings, "LANGFUSE_HOST", "") or "").rstrip("/")
        if not (public_key and secret_key and (host or override)):
            return None
        headers.setdefault("Authorization", _basic_auth_header(public_key, secret_key))
        return override or f"{host}/api/public/otel/v1/traces", headers

    endpoint = override or str(
        getattr(settings, "PHOENIX_COLLECTOR_ENDPOINT", "") or ""
    )
    if not endpoint:
        return None
    return endpoint, headers


def is_enabled() -> bool:
    return exporter_config() is not None


def init_tracing() -> bool:
    """Configure OTEL export; idempotent. ``True`` when tracing is live.

    Failures (missing optional deps, unreachable collector at boot) log a
    warning and return ``False``; the application continues to run with
    tracing disabled.
    """
    global _INITIALIZED
    config = exporter_config()
    if config is None:
        logger.debug(
            "telemetry disabled (OBSERVABILITY_BACKEND=%s, no endpoint)", backend()
        )
        return False
    if _INITIALIZED:
        return True
    endpoint, headers = config

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
    exporter = OTLPSpanExporter(endpoint=endpoint, headers=headers or None)
    provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(provider)

    try:
        from opentelemetry.instrumentation.django import DjangoInstrumentor

        DjangoInstrumentor().instrument(tracer_provider=provider)
    except ImportError:  # pragma: no cover - extra missing
        logger.warning("telemetry: Django instrumentation not available")

    try:
        from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor

        HTTPXClientInstrumentor().instrument(tracer_provider=provider)
    except ImportError:  # pragma: no cover - extra missing
        logger.warning("telemetry: httpx instrumentation not available")

    _INITIALIZED = True
    logger.info(
        "telemetry: exporting to %s via %s (project=%s)",
        endpoint,
        backend(),
        settings.PHOENIX_PROJECT_NAME,
    )
    return True


def trace_url(trace_id: str | None) -> str | None:
    """Deep-link to whichever observability UI is configured.

    Returns ``None`` when tracing is disabled or the trace id is falsy, so
    callers can omit the field from API responses without branching.
    """
    if not trace_id or not is_enabled():
        return None
    project = settings.PHOENIX_PROJECT_NAME
    if backend() == LANGFUSE:
        host = str(getattr(settings, "LANGFUSE_HOST", "") or "").rstrip("/")
        return f"{host}/trace/{trace_id}" if host else None
    base = str(settings.PHOENIX_UI_URL).rstrip("/")
    return f"{base}/projects/{project}/traces/{trace_id}"


#: The API response field is still called ``phoenix_trace_url`` (shipped by
#: BL-20260502-05 and read by AnalysisStudio), so the old name stays as the
#: public alias while the implementation is backend-agnostic.
phoenix_trace_url = trace_url
