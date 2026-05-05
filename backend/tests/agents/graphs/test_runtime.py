"""Unit tests for the LangGraph checkpointer factory (spec 010 T-002)."""

from __future__ import annotations

import pytest

from lawgraph.agents_runtime.graphs import runtime
from lawgraph.agents_runtime.graphs.runtime import (
    CheckpointerUnavailableError,
    build_checkpointer,
)
from django.conf import settings


def test_build_checkpointer_unknown_kind() -> None:
    with pytest.raises(ValueError, match="unknown LANGGRAPH_CHECKPOINTER"):
        build_checkpointer("sqlite-on-the-moon")


def test_memory_branch_when_extra_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    """`memory` should raise CheckpointerUnavailableError when langgraph isn't installed.

    We don't assume the dev environment has the local-ai extra; instead we
    assert that the failure mode is the explicit error class our health
    probe handles, never a bare ImportError.
    """
    monkeypatch.setattr(settings, "LANGGRAPH_CHECKPOINTER", "memory")
    try:
        result = build_checkpointer()
    except CheckpointerUnavailableError:
        pytest.skip("langgraph extra not installed; verified explicit error class")
    else:
        # MemorySaver may or may not be an async CM depending on langgraph
        # version; either is acceptable as long as we get a saver back.
        assert result is not None


def test_postgres_branch_lazy_import(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "LANGGRAPH_CHECKPOINTER", "postgres")
    try:
        cm = build_checkpointer()
    except CheckpointerUnavailableError:
        pytest.skip("langgraph-checkpoint-postgres not installed")
    else:
        assert hasattr(cm, "__aenter__"), "postgres saver should be an async CM"


def test_redis_branch_lazy_import(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "LANGGRAPH_CHECKPOINTER", "redis")
    try:
        cm = build_checkpointer()
    except CheckpointerUnavailableError:
        pytest.skip("langgraph-checkpoint-redis not installed")
    else:
        assert hasattr(cm, "__aenter__"), "redis saver should be an async CM"


def test_kind_override_wins_over_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "LANGGRAPH_CHECKPOINTER", "postgres")
    with pytest.raises(ValueError):
        build_checkpointer("not-a-real-backend")


def test_module_exposes_error_class() -> None:
    assert issubclass(runtime.CheckpointerUnavailableError, RuntimeError)
