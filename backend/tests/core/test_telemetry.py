"""Tests for app.core.telemetry (spec 010 T-003)."""

from __future__ import annotations

import pytest

from lawgraph.core import telemetry
from django.conf import settings


def test_disabled_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "PHOENIX_COLLECTOR_ENDPOINT", None)
    assert telemetry.is_enabled() is False
    assert telemetry.init_tracing(None) is False
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
    monkeypatch.setattr(settings, "PHOENIX_PROJECT_NAME", "lawgraph")
    url = telemetry.phoenix_trace_url("abc123")
    assert url == "http://localhost:6006/projects/lawgraph/traces/abc123"


def test_init_tracing_is_noop_without_endpoint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "PHOENIX_COLLECTOR_ENDPOINT", "")
    # Reset module cache so a previous test enabling tracing doesn't poison.
    monkeypatch.setattr(telemetry, "_INITIALIZED", False)
    assert telemetry.init_tracing(None) is False


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
    assert telemetry.init_tracing(None) is False
