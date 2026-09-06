"""``_persist`` strategy selection (BL-20260810-10, BL-20260811-07).

Spec 030 made the DB leg pick a strategy by execution context, but nothing
tested the selection — a regression there is invisible, because JSONL keeps
working and the missing Postgres rows only show up in a query nobody runs
until they need the audit trail. These tests pin all three branches, the
thread offload that closes the dev/prod gap, and the warning that fires when
the DB leg fails persistently rather than once.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from law_ai.core import provenance as prov

pytestmark = [pytest.mark.unit]


@pytest.fixture(autouse=True)
def _quiet_jsonl(monkeypatch: pytest.MonkeyPatch) -> None:
    """JSONL is not under test here; make it a no-op that always succeeds."""
    monkeypatch.setattr(prov.audit_store, "record", lambda event: None)
    monkeypatch.setattr(prov, "_DB_FAILURE_STREAK", 0)


EVENT = {"type": "unit_test_event", "trace_id": "t-1"}


# --------------------------------------------------------------------------
# Strategy selection
# --------------------------------------------------------------------------
def test_sync_context_writes_the_row_directly(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    written: list[dict[str, Any]] = []
    dispatched: list[dict[str, Any]] = []
    monkeypatch.setattr(prov, "_write_audit_row", written.append)
    monkeypatch.setattr(prov, "_in_async_context", lambda: False)
    monkeypatch.setattr(
        prov, "_audit_executor", lambda: pytest.fail("no thread in sync context")
    )

    prov._persist(dict(EVENT))

    assert written == [EVENT]
    assert dispatched == []


def test_async_context_hands_the_row_to_celery(
    monkeypatch: pytest.MonkeyPatch, settings
) -> None:
    settings.CELERY_TASK_ALWAYS_EAGER = False
    monkeypatch.setattr(prov, "_in_async_context", lambda: True)
    monkeypatch.setattr(
        prov, "_write_audit_row", lambda event: pytest.fail("ORM in async context")
    )

    dispatched: list[dict[str, Any]] = []

    class FakeTask:
        @staticmethod
        def delay(event: dict[str, Any]) -> None:
            dispatched.append(event)

    import law_ai.core.tasks as tasks_module

    monkeypatch.setattr(tasks_module, "persist_audit_event", FakeTask)

    prov._persist(dict(EVENT))

    assert dispatched == [EVENT]


def test_async_and_eager_without_offload_skips_the_db_leg(
    monkeypatch: pytest.MonkeyPatch, settings
) -> None:
    """Today's behaviour, kept: eager + async has nowhere safe to write."""
    settings.CELERY_TASK_ALWAYS_EAGER = True
    settings.AUDIT_DB_THREAD_OFFLOAD = False
    monkeypatch.setattr(prov, "_in_async_context", lambda: True)
    monkeypatch.setattr(
        prov, "_write_audit_row", lambda event: pytest.fail("ORM in async context")
    )
    monkeypatch.setattr(
        prov, "_audit_executor", lambda: pytest.fail("offload is disabled")
    )

    prov._persist(dict(EVENT))  # must not raise


def test_async_and_eager_with_offload_uses_a_worker_thread(
    monkeypatch: pytest.MonkeyPatch, settings
) -> None:
    """BL-20260811-07: dev parity — the row is written, not skipped."""
    settings.CELERY_TASK_ALWAYS_EAGER = True
    settings.AUDIT_DB_THREAD_OFFLOAD = True
    monkeypatch.setattr(prov, "_in_async_context", lambda: True)

    submitted: list[tuple[Any, ...]] = []

    class FakeExecutor:
        @staticmethod
        def submit(fn: Any, *args: Any) -> None:
            submitted.append((fn, *args))

    monkeypatch.setattr(prov, "_audit_executor", lambda: FakeExecutor)

    prov._persist(dict(EVENT))

    assert len(submitted) == 1
    fn, event, jsonl_ok = submitted[0]
    assert fn is prov._write_audit_row_offloaded
    assert event == EVENT
    assert jsonl_ok is True


def test_the_offload_setting_is_off_for_the_suite(settings) -> None:
    """pytest-django's per-test transaction is invisible to a second thread."""
    assert settings.AUDIT_DB_THREAD_OFFLOAD is False


# --------------------------------------------------------------------------
# The offloaded write itself
# --------------------------------------------------------------------------
def test_the_offloaded_write_brackets_the_insert_with_close_old_connections(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    import django.db as django_db

    monkeypatch.setattr(
        django_db, "close_old_connections", lambda: calls.append("close")
    )
    monkeypatch.setattr(prov, "_write_audit_row", lambda event: calls.append("insert"))

    prov._write_audit_row_offloaded(dict(EVENT), True)

    assert calls == ["close", "insert", "close"]


def test_the_offloaded_write_never_raises_into_the_worker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def boom(event: dict[str, Any]) -> None:
        raise RuntimeError("connection refused")

    monkeypatch.setattr(prov, "_write_audit_row", boom)
    prov._write_audit_row_offloaded(dict(EVENT), True)  # must not raise


@pytest.mark.django_db(transaction=True)
def test_the_offloaded_write_actually_lands_a_row(
    monkeypatch: pytest.MonkeyPatch, settings
) -> None:
    """The point of the offload: an AuditEvent row exists afterwards.

    ``transaction=True`` is required — the worker thread has its own DB
    connection and cannot see the transaction pytest-django normally wraps a
    test in, which is exactly why the offload is off for the rest of the suite.
    """
    from law_ai.audit.models import AuditEvent

    settings.CELERY_TASK_ALWAYS_EAGER = True
    settings.AUDIT_DB_THREAD_OFFLOAD = True
    monkeypatch.setattr(prov, "_AUDIT_EXECUTOR", None)

    async def run_it() -> None:
        # A real running loop — the context where the ORM is off-limits and
        # the old code simply skipped the DB leg.
        prov._persist({"type": "offload_probe", "trace_id": "t-offload"})

    before = AuditEvent.objects.filter(kind="offload_probe").count()
    asyncio.run(run_it())

    # Drain the worker before asserting; the submit itself is non-blocking.
    executor = prov._AUDIT_EXECUTOR
    assert executor is not None, "the offload never reached the executor"
    executor.shutdown(wait=True)

    assert AuditEvent.objects.filter(kind="offload_probe").count() == before + 1


# --------------------------------------------------------------------------
# Persistent failure is surfaced at warning level
# --------------------------------------------------------------------------
def test_a_single_db_failure_stays_quiet(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level("WARNING", logger="law_ai.provenance"):
        prov._note_db_result(False, "unit")
    assert not [r for r in caplog.records if "failed" in r.getMessage()]


def test_a_run_of_failures_warns(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """BL-20260810-10: "surface persistent failure at warning level"."""
    with caplog.at_level("WARNING", logger="law_ai.provenance"):
        for _ in range(prov._PERSISTENT_FAILURE_THRESHOLD):
            prov._note_db_result(False, "unit")

    warnings = [
        r for r in caplog.records if "failed 3 times in a row" in r.getMessage()
    ]
    assert len(warnings) == 1


def test_a_success_resets_the_streak(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    prov._note_db_result(False, "unit")
    prov._note_db_result(False, "unit")
    prov._note_db_result(True, "unit")
    with caplog.at_level("WARNING", logger="law_ai.provenance"):
        prov._note_db_result(False, "unit")
    assert not [r for r in caplog.records if "in a row" in r.getMessage()]


def test_jsonl_is_always_written_first(monkeypatch: pytest.MonkeyPatch) -> None:
    """Whatever the DB leg does, the durable record is written first."""
    order: list[str] = []
    monkeypatch.setattr(prov.audit_store, "record", lambda event: order.append("jsonl"))
    monkeypatch.setattr(prov, "_write_audit_row", lambda event: order.append("db"))
    monkeypatch.setattr(prov, "_in_async_context", lambda: False)

    prov._persist(dict(EVENT))

    assert order == ["jsonl", "db"]
