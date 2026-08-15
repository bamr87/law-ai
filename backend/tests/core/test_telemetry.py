"""Tests for law_ai.core.telemetry (spec 010 T-003, rewritten by spec 037).

`test_phoenix_trace_url_enabled_builds_link` used to assert
``http://localhost:6006/projects/law_ai/traces/abc123`` — i.e. it encoded
spec 037's RC-4 as expected behavior. Spec 037 R-1 requires that assertion be
*rewritten*, not deleted, so the suite keeps a regression guard on FR-6.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx
from django.conf import settings
from opentelemetry import trace as otel_trace

from law_ai.core import telemetry

pytestmark = pytest.mark.unit

PHOENIX_ENDPOINT = "http://phoenix:6006/v1/traces"
PHOENIX_BASE = "http://phoenix:6006"
PROJECT_ID = "UHJvamVjdDox"


@pytest.fixture(autouse=True)
def _clear_project_cache() -> Iterator[None]:
    """The resolver caches for the process lifetime; tests must not bleed."""
    telemetry.reset_project_id_cache()
    yield
    telemetry.reset_project_id_cache()


@pytest.fixture
def enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "PHOENIX_COLLECTOR_ENDPOINT", PHOENIX_ENDPOINT)
    monkeypatch.setattr(settings, "PHOENIX_UI_URL", "http://localhost:6006")
    monkeypatch.setattr(settings, "PHOENIX_PROJECT_NAME", "law_ai")
    monkeypatch.setattr(settings, "PHOENIX_BASE_URL", "")


def _projects_payload(*names: str) -> dict[str, Any]:
    return {
        "data": [
            {"name": name, "description": "", "id": PROJECT_ID if i == 0 else f"X{i}"}
            for i, name in enumerate(names)
        ],
        "next_cursor": None,
    }


# ---------------------------------------------------------------------------
# Default-off posture (FR-8, AC-5)
# ---------------------------------------------------------------------------


def test_disabled_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "PHOENIX_COLLECTOR_ENDPOINT", None)
    assert telemetry.is_enabled() is False
    assert telemetry.init_tracing() is False
    assert telemetry.phoenix_trace_url("abc") is None


def test_init_tracing_is_noop_without_endpoint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "PHOENIX_COLLECTOR_ENDPOINT", "")
    monkeypatch.setattr(telemetry, "_INITIALIZED", False)
    assert telemetry.init_tracing() is False


def test_init_tracing_sets_no_provider_when_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AC-5: the disabled path must not touch global OTEL state at all."""
    monkeypatch.setattr(settings, "PHOENIX_COLLECTOR_ENDPOINT", "")
    monkeypatch.setattr(telemetry, "_INITIALIZED", False)
    before = otel_trace.get_tracer_provider()

    assert telemetry.init_tracing() is False

    assert otel_trace.get_tracer_provider() is before
    # A span opened on the default provider is a no-op with an invalid context,
    # which is what makes FR-4's unconditional span free (OQ-4).
    span = otel_trace.get_tracer(__name__).start_span("probe")
    assert span.get_span_context().is_valid is False
    span.end()


def test_init_tracing_handles_missing_optional_deps(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When the local-ai extra is not installed, init returns False, not raise."""
    monkeypatch.setattr(settings, "PHOENIX_COLLECTOR_ENDPOINT", PHOENIX_ENDPOINT)
    monkeypatch.setattr(telemetry, "_INITIALIZED", False)
    import builtins

    real_import = builtins.__import__

    def fake_import(name: str, *a: Any, **kw: Any) -> Any:
        if name.startswith(("phoenix", "opentelemetry")):
            raise ImportError(f"forced: {name}")
        return real_import(name, *a, **kw)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    assert telemetry.init_tracing() is False


# ---------------------------------------------------------------------------
# phoenix_trace_url + project-id resolution (FR-6, AC-4, AC-7, NFR-PERF-1)
# ---------------------------------------------------------------------------


@respx.mock
def test_phoenix_trace_url_enabled_builds_link(enabled: None) -> None:
    """Rewritten from the RC-4 assertion (R-1): address the project by ID."""
    respx.get(f"{PHOENIX_BASE}/v1/projects").mock(
        return_value=httpx.Response(200, json=_projects_payload("law_ai", "default"))
    )
    url = telemetry.phoenix_trace_url("abc123")
    assert url == f"http://localhost:6006/projects/{PROJECT_ID}/spans/abc123"
    # The old, broken form must never come back.
    assert "/projects/law_ai/" not in (url or "")


def test_phoenix_trace_url_disabled_returns_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "PHOENIX_COLLECTOR_ENDPOINT", None)
    assert telemetry.phoenix_trace_url(None) is None
    assert telemetry.phoenix_trace_url("trace-123") is None


@respx.mock
def test_project_id_resolution_caches(enabled: None) -> None:
    """Two links, one lookup — the request path stays free of repeat I/O."""
    route = respx.get(f"{PHOENIX_BASE}/v1/projects").mock(
        return_value=httpx.Response(200, json=_projects_payload("law_ai"))
    )
    assert telemetry.phoenix_trace_url("t1") is not None
    assert telemetry.phoenix_trace_url("t2") is not None
    assert route.call_count == 1


@respx.mock
def test_project_id_resolution_failure_returns_none_and_backs_off(
    enabled: None,
) -> None:
    """AC-7: an unreachable Phoenix degrades the link, never the request."""
    route = respx.get(f"{PHOENIX_BASE}/v1/projects").mock(
        return_value=httpx.Response(500)
    )
    assert telemetry.phoenix_trace_url("t1") is None
    # Negative-cached: a second response must not pay another timeout.
    assert telemetry.phoenix_trace_url("t2") is None
    assert route.call_count == 1


@respx.mock
def test_project_id_resolution_survives_timeout(enabled: None) -> None:
    respx.get(f"{PHOENIX_BASE}/v1/projects").mock(
        side_effect=httpx.ConnectTimeout("phoenix is down")
    )
    assert telemetry.phoenix_trace_url("t1") is None


@respx.mock
def test_project_absent_returns_none(enabled: None) -> None:
    """Today's live state: only `default` and `playground` exist."""
    respx.get(f"{PHOENIX_BASE}/v1/projects").mock(
        return_value=httpx.Response(
            200, json=_projects_payload("default", "playground")
        )
    )
    assert telemetry.phoenix_trace_url("t1") is None


# ---------------------------------------------------------------------------
# Content capture (FR-7, AC-6, NFR-PRIVACY-1)
# ---------------------------------------------------------------------------


def test_trace_config_hides_content_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    """The *unconfigured* posture — a regression in the default fails here."""
    monkeypatch.setattr(settings, "PHOENIX_TRACE_CONTENT", False)
    config = telemetry._trace_config()
    assert config.hide_inputs is True
    assert config.hide_outputs is True


def test_trace_config_captures_content_when_enabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "PHOENIX_TRACE_CONTENT", True)
    config = telemetry._trace_config()
    assert config.hide_inputs is False
    assert config.hide_outputs is False


# ---------------------------------------------------------------------------
# Dead-code sweep (FR-3, AC-10)
# ---------------------------------------------------------------------------

_CORE_DIR = Path(telemetry.__file__).resolve().parent
_FASTAPI_RE = re.compile(r"FastAPIInstrumentor|from fastapi|import fastapi|uvicorn")


def test_no_fastapi_or_uvicorn_references_in_core() -> None:
    """AC-10 as a test, so the sweep cannot silently rot back in."""
    offenders = [
        f"{path.name}:{i}"
        for path in sorted(_CORE_DIR.rglob("*.py"))
        for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1)
        if _FASTAPI_RE.search(line)
    ]
    assert not offenders, f"FastAPI/uvicorn references survive in core/: {offenders}"


# ---------------------------------------------------------------------------
# Root server span (FR-3, AC-2)
# ---------------------------------------------------------------------------


def test_django_instrumentation_produces_a_root_server_span(
    client: Any,
) -> None:
    """FR-3/AC-2: without this span every client call is its own orphan trace.

    The spec's census found 499 traces across 500 spans precisely because no
    request-level span existed for downstream spans to nest under.
    """
    from opentelemetry.instrumentation.django import DjangoInstrumentor
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
        InMemorySpanExporter,
    )

    memory = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(memory))

    instrumentor = DjangoInstrumentor()
    instrumentor.instrument(tracer_provider=provider)
    try:
        response = client.get("/")
        assert response.status_code == 200
        spans = memory.get_finished_spans()
    finally:
        instrumentor.uninstrument()

    assert spans, "DjangoInstrumentor produced no span for a real request"
    roots = [s for s in spans if s.parent is None]
    assert len(roots) == 1, f"expected exactly one root span, got {len(roots)}"
    assert roots[0].kind.name == "SERVER"
