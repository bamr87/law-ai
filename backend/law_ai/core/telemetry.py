"""OpenTelemetry → Arize Phoenix wiring (spec 010 FR-4, rewritten by spec 037).

Spec 037 measured what this module actually produced: 500 spans, all
``span_kind=UNKNOWN``, spread across 499 traces, carrying no prompt, no
completion, and no model. Three things caused that, and this module fixes
all three:

* **Project** — Phoenix keys projects off the ``openinference.project.name``
  resource attribute, not ``service.name``. ``phoenix.otel.register`` sets
  it, so ``PHOENIX_PROJECT_NAME`` finally takes effect (RC-3).
* **Content** — Phoenix's LLM UI is driven by OpenInference semantic
  conventions. ``LangChainInstrumentor`` supplies them for every call through
  ``ChatProviderChain`` and every LangGraph node (RC-1).
* **Structure** — ``DjangoInstrumentor`` gives each request a root server
  span, so client and LLM spans nest under it instead of each becoming its
  own orphan trace (RC-2). The FastAPI instrumentation this module used to
  reach for has been dead code since the backend became Django/daphne.

Instrumentors are installed **explicitly**, never via
``register(auto_instrument=True)``: entry-point discovery would let a future
transitive dependency start emitting spans nobody reviewed (spec 037 OQ-3).

Two invariants worth stating because they are easy to erode:

* When ``PHOENIX_COLLECTOR_ENDPOINT`` is unset, ``init_tracing`` is a complete
  no-op — no provider registered, no instrumentor installed, no global state
  touched — and every import stays lazy + guarded so a build without the
  ``local-ai`` extra still boots.
* Tracing is a *debugging* surface. ``law_ai.core.provenance`` remains the
  constitution-§4 record of truth, and nothing here may make an audit write
  conditional on tracing being enabled.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from law_ai.core.settings_proxy import settings_proxy as settings

logger = logging.getLogger("law_ai.telemetry")

_INITIALIZED = False

#: Cached Phoenix project ID (base64 GraphQL id, e.g. ``UHJvamVjdDox``).
_PROJECT_ID: str | None = None
#: Monotonic deadline before which a failed lookup will not be retried. A
#: plain lazy cache would re-attempt on every response and hand an unreachable
#: Phoenix a timeout's worth of latency per request (spec 037 NFR-PERF-1).
_PROJECT_ID_RETRY_AFTER: float = 0.0
_PROJECT_LOOKUP_TIMEOUT_S = 2.0
_PROJECT_LOOKUP_COOLDOWN_S = 60.0


def is_enabled() -> bool:
    return bool(settings.PHOENIX_COLLECTOR_ENDPOINT)


def _trace_config() -> Any:
    """Build the OpenInference ``TraceConfig`` for the configured posture.

    With ``PHOENIX_TRACE_CONTENT`` off (the ``settings/base.py`` default),
    prompt and completion text is suppressed by OpenInference itself — the
    ``llm.{input,output}_messages.*`` attributes are dropped and
    ``input.value`` / ``output.value`` become ``__REDACTED__`` — while span
    kind, model name, provider, and the parent/child tree survive intact
    (spec 037 FR-7). Never a hand-rolled attribute scrubber.
    """
    from openinference.instrumentation import TraceConfig

    capture = bool(getattr(settings, "PHOENIX_TRACE_CONTENT", False))
    if capture:
        return TraceConfig()
    return TraceConfig(hide_inputs=True, hide_outputs=True)


def init_tracing() -> bool:
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
        from opentelemetry.sdk.resources import Resource
        from phoenix.otel import register
    except ImportError as exc:
        logger.warning(
            "telemetry: arize-phoenix-otel missing (%s); "
            "install the local-ai extra to enable Phoenix tracing",
            exc,
        )
        return False

    try:
        provider = register(
            endpoint=settings.PHOENIX_COLLECTOR_ENDPOINT,
            project_name=settings.PHOENIX_PROJECT_NAME,
            # BatchSpanProcessor, never Simple: export must stay off the
            # request path (spec 037 NFR-PERF-1).
            batch=True,
            set_global_tracer_provider=True,
            verbose=False,
            # Forwarded to the TracerProvider constructor. register() merges
            # `openinference.project.name` into whatever resource we pass, so
            # these survive alongside it (they did not before spec 037,
            # because `service.name` was doing the project's job and failing).
            resource=Resource.create(
                {
                    "service.version": "0.1.0",
                    "deployment.environment": settings.ENVIRONMENT,
                }
            ),
        )
    except Exception as exc:  # pragma: no cover - defensive; boot must not fail
        logger.warning("telemetry: Phoenix registration failed (%s)", exc)
        return False

    config = _trace_config()
    _instrument_django(provider)
    _instrument_langchain(provider, config)
    _instrument_httpx(provider)

    _INITIALIZED = True
    logger.info(
        "telemetry: exporting to %s (project=%s, content=%s)",
        settings.PHOENIX_COLLECTOR_ENDPOINT,
        settings.PHOENIX_PROJECT_NAME,
        "on" if getattr(settings, "PHOENIX_TRACE_CONTENT", False) else "off",
    )
    return True


def _instrument_django(provider: Any) -> None:
    """Root server span per request — what makes traces a tree (FR-3)."""
    try:
        from opentelemetry.instrumentation.django import DjangoInstrumentor

        DjangoInstrumentor().instrument(tracer_provider=provider)
    except ImportError:  # pragma: no cover - extra missing
        logger.warning("telemetry: Django instrumentation not available")


def _instrument_langchain(provider: Any, config: Any) -> None:
    """OpenInference LLM/CHAIN spans for the provider chain (FR-2)."""
    try:
        from openinference.instrumentation.langchain import LangChainInstrumentor

        LangChainInstrumentor().instrument(tracer_provider=provider, config=config)
    except ImportError:  # pragma: no cover - extra missing
        logger.warning("telemetry: LangChain instrumentation not available")


def _instrument_httpx(provider: Any) -> None:
    """Transport-level spans.

    Deliberately installed with **no** request/response hooks: hooks are the
    only way header values could reach a span attribute, and the Claude OAuth
    token and ``ANTHROPIC_API_KEY`` travel in headers (spec 037 NFR-SEC-1).
    """
    try:
        from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor

        HTTPXClientInstrumentor().instrument(tracer_provider=provider)
    except ImportError:  # pragma: no cover - extra missing
        logger.warning("telemetry: httpx instrumentation not available")


def _resolve_project_id() -> str | None:
    """Phoenix's own ID for ``PHOENIX_PROJECT_NAME``, or ``None``.

    Phoenix's UI addresses projects by base64 GraphQL id (``UHJvamVjdDox``),
    not by name, so a deep-link needs one ``GET /v1/projects`` lookup.
    Resolution is lazy (boot must not depend on Phoenix being reachable —
    spec 037 FR-8/G4), cached for the process lifetime on success, and
    negative-cached for a cooldown on failure so an unreachable Phoenix costs
    at most one bounded timeout per minute rather than one per response.

    Never raises: every failure path logs at debug and returns ``None``,
    exactly as the tracing-disabled path does.
    """
    global _PROJECT_ID, _PROJECT_ID_RETRY_AFTER

    if _PROJECT_ID is not None:
        return _PROJECT_ID
    if time.monotonic() < _PROJECT_ID_RETRY_AFTER:
        return None

    try:
        import httpx

        from law_ai.agents_runtime.prompts.phoenix import phoenix_base_url

        base = phoenix_base_url()
        if not base:
            raise ValueError("no Phoenix base URL configured")

        response = httpx.get(
            f"{base}/v1/projects", timeout=httpx.Timeout(_PROJECT_LOOKUP_TIMEOUT_S)
        )
        response.raise_for_status()
        wanted = settings.PHOENIX_PROJECT_NAME
        for project in response.json().get("data") or []:
            if project.get("name") == wanted:
                _PROJECT_ID = str(project["id"])
                return _PROJECT_ID
        raise LookupError(f"no Phoenix project named {wanted!r}")
    except Exception as exc:
        logger.debug("telemetry: Phoenix project id unresolved (%s)", exc)
        _PROJECT_ID_RETRY_AFTER = time.monotonic() + _PROJECT_LOOKUP_COOLDOWN_S
        return None


def reset_project_id_cache() -> None:
    """Clear the resolver cache. Tests only."""
    global _PROJECT_ID, _PROJECT_ID_RETRY_AFTER
    _PROJECT_ID = None
    _PROJECT_ID_RETRY_AFTER = 0.0


def phoenix_trace_url(trace_id: str | None) -> str | None:
    """Build a deep-link to the Phoenix UI for ``trace_id``.

    Returns ``None`` when telemetry is disabled, the trace id is falsy, or the
    project id cannot be resolved — so callers can omit the field from API
    responses without branching, and a Phoenix outage degrades the link rather
    than the request.
    """
    if not trace_id or not is_enabled():
        return None
    project_id = _resolve_project_id()
    if not project_id:
        return None
    base = settings.PHOENIX_UI_URL.rstrip("/")
    return f"{base}/projects/{project_id}/spans/{trace_id}"
