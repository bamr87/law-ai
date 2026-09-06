"""Tests for law_ai.core.telemetry (spec 010 T-003)."""

from __future__ import annotations

import pytest

from law_ai.core import telemetry
from django.conf import settings


def test_disabled_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "PHOENIX_COLLECTOR_ENDPOINT", None)
    assert telemetry.is_enabled() is False
    assert telemetry.init_tracing() is False
    assert telemetry.phoenix_trace_url("abc") is None


def test_phoenix_trace_url_disabled_returns_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "PHOENIX_COLLECTOR_ENDPOINT", None)
    assert telemetry.phoenix_trace_url(None) is None
    assert telemetry.phoenix_trace_url("trace-123") is None


def test_phoenix_trace_url_enabled_builds_link(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        settings, "PHOENIX_COLLECTOR_ENDPOINT", "http://phoenix:6006/v1/traces"
    )
    monkeypatch.setattr(settings, "PHOENIX_UI_URL", "http://localhost:6006")
    monkeypatch.setattr(settings, "PHOENIX_PROJECT_NAME", "law_ai")
    url = telemetry.phoenix_trace_url("abc123")
    assert url == "http://localhost:6006/projects/law_ai/traces/abc123"


def test_init_tracing_is_noop_without_endpoint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "PHOENIX_COLLECTOR_ENDPOINT", "")
    # Reset module cache so a previous test enabling tracing doesn't poison.
    monkeypatch.setattr(telemetry, "_INITIALIZED", False)
    assert telemetry.init_tracing() is False


def test_init_tracing_handles_missing_optional_deps(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When the local-ai extra is not installed, init returns False, not raise."""
    monkeypatch.setattr(
        settings, "PHOENIX_COLLECTOR_ENDPOINT", "http://phoenix:6006/v1/traces"
    )
    monkeypatch.setattr(telemetry, "_INITIALIZED", False)
    # Stub the OTEL imports out by injecting a broken finder via builtins.
    import builtins

    real_import = builtins.__import__

    def fake_import(name, *a, **kw):
        if name.startswith("opentelemetry"):
            raise ImportError(f"forced: {name}")
        return real_import(name, *a, **kw)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    assert telemetry.init_tracing() is False


# ---------------------------------------------------------------------------
# BL-20260503-23: Django, not FastAPI
# ---------------------------------------------------------------------------
def test_the_dead_fastapi_path_is_gone() -> None:
    """`init_tracing` takes no app and names no FastAPI symbol any more."""
    import inspect

    assert inspect.signature(telemetry.init_tracing).parameters == {}
    source = inspect.getsource(telemetry)
    assert "FastAPIInstrumentor" not in source


def test_django_is_instrumented_when_tracing_is_live(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        settings, "PHOENIX_COLLECTOR_ENDPOINT", "http://phoenix:6006/v1/traces"
    )
    monkeypatch.setattr(settings, "OBSERVABILITY_BACKEND", "phoenix")
    monkeypatch.setattr(telemetry, "_INITIALIZED", False)

    instrumented: list[object] = []

    class FakeDjangoInstrumentor:
        def instrument(self, **kwargs: object) -> None:
            instrumented.append(kwargs.get("tracer_provider"))

    import sys
    import types

    module = types.ModuleType("opentelemetry.instrumentation.django")
    module.DjangoInstrumentor = FakeDjangoInstrumentor  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "opentelemetry.instrumentation.django", module)

    assert telemetry.init_tracing() is True
    assert len(instrumented) == 1
    monkeypatch.setattr(telemetry, "_INITIALIZED", False)


# ---------------------------------------------------------------------------
# BL-20260502-07: the exporter is chosen by OBSERVABILITY_BACKEND
# ---------------------------------------------------------------------------
def test_none_backend_disables_tracing_even_with_an_endpoint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        settings, "PHOENIX_COLLECTOR_ENDPOINT", "http://phoenix:6006/v1/traces"
    )
    monkeypatch.setattr(settings, "OBSERVABILITY_BACKEND", "none")
    assert telemetry.exporter_config() is None
    assert telemetry.is_enabled() is False
    assert telemetry.trace_url("abc") is None


def test_an_unknown_backend_disables_tracing_loudly(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setattr(settings, "OBSERVABILITY_BACKEND", "datadog")
    with caplog.at_level("WARNING", logger="law_ai.telemetry"):
        assert telemetry.backend() == "none"
    assert any(
        "unknown OBSERVABILITY_BACKEND" in r.getMessage() for r in caplog.records
    )


def test_phoenix_backend_uses_the_phoenix_endpoint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "OBSERVABILITY_BACKEND", "phoenix")
    monkeypatch.setattr(
        settings, "PHOENIX_COLLECTOR_ENDPOINT", "http://phoenix:6006/v1/traces"
    )
    monkeypatch.setattr(settings, "OTEL_EXPORTER_OTLP_ENDPOINT", "")
    monkeypatch.setattr(settings, "OTEL_EXPORTER_OTLP_HEADERS", "")
    endpoint, headers = telemetry.exporter_config()  # type: ignore[misc]
    assert endpoint == "http://phoenix:6006/v1/traces"
    assert headers == {}


def test_langfuse_backend_builds_the_otel_endpoint_and_basic_auth(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "OBSERVABILITY_BACKEND", "langfuse")
    monkeypatch.setattr(settings, "LANGFUSE_HOST", "https://cloud.langfuse.test/")
    monkeypatch.setattr(settings, "LANGFUSE_PUBLIC_KEY", "pk-1")
    monkeypatch.setattr(settings, "LANGFUSE_SECRET_KEY", "sk-2")
    monkeypatch.setattr(settings, "OTEL_EXPORTER_OTLP_ENDPOINT", "")
    monkeypatch.setattr(settings, "OTEL_EXPORTER_OTLP_HEADERS", "")

    endpoint, headers = telemetry.exporter_config()  # type: ignore[misc]
    assert endpoint == "https://cloud.langfuse.test/api/public/otel/v1/traces"
    # base64("pk-1:sk-2")
    assert headers["Authorization"] == "Basic cGstMTpzay0y"
    assert telemetry.trace_url("abc") == "https://cloud.langfuse.test/trace/abc"


def test_langfuse_without_keys_is_disabled_rather_than_half_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "OBSERVABILITY_BACKEND", "langfuse")
    monkeypatch.setattr(settings, "LANGFUSE_HOST", "https://cloud.langfuse.test")
    monkeypatch.setattr(settings, "LANGFUSE_PUBLIC_KEY", "")
    monkeypatch.setattr(settings, "LANGFUSE_SECRET_KEY", "")
    assert telemetry.exporter_config() is None


def test_an_explicit_otlp_endpoint_overrides_the_backend(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "OBSERVABILITY_BACKEND", "phoenix")
    monkeypatch.setattr(settings, "PHOENIX_COLLECTOR_ENDPOINT", "http://phoenix:6006")
    monkeypatch.setattr(
        settings, "OTEL_EXPORTER_OTLP_ENDPOINT", "http://collector:4318/v1/traces"
    )
    monkeypatch.setattr(settings, "OTEL_EXPORTER_OTLP_HEADERS", "x-key=abc, bad")
    endpoint, headers = telemetry.exporter_config()  # type: ignore[misc]
    assert endpoint == "http://collector:4318/v1/traces"
    assert headers == {"x-key": "abc"}


def test_phoenix_trace_url_is_still_the_public_name() -> None:
    """AnalysisStudio reads a `phoenix_trace_url` field — keep the alias."""
    assert telemetry.phoenix_trace_url is telemetry.trace_url
