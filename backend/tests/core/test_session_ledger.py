"""Tests for the WS4 change ledger: SessionRun upserts, provenance session
tagging, and autonomy-cycle → SessionRun linkage."""

from __future__ import annotations

import pytest


@pytest.mark.django_db
class TestSessionLedger:
    def test_start_then_finalize(self) -> None:
        from lawgraph.audit import session_ledger
        from lawgraph.audit.models import SessionRun

        s = session_ledger.start_session(
            "sess-1", agent_source="claude_code", agent_name="X", kind="evolve"
        )
        assert s is not None and s.status == "running"
        session_ledger.finalize_session(
            "sess-1",
            status="completed",
            summary="done",
            backlog_items_added=["BL-20260615-09"],
            prs_created=["pr#1"],
        )
        row = SessionRun.objects.get(session_id="sess-1")
        assert row.status == "completed"
        assert row.ended_at is not None
        assert row.backlog_items_added == ["BL-20260615-09"]
        assert row.summary == "done"

    def test_finalize_without_start_creates_row(self) -> None:
        from lawgraph.audit import session_ledger
        from lawgraph.audit.models import SessionRun

        session_ledger.finalize_session("sess-2", status="failed")
        assert SessionRun.objects.get(session_id="sess-2").status == "failed"

    def test_start_is_idempotent(self) -> None:
        from lawgraph.audit import session_ledger
        from lawgraph.audit.models import SessionRun

        session_ledger.start_session("sess-3", kind="a")
        session_ledger.start_session("sess-3", kind="b")  # must not clobber
        assert SessionRun.objects.filter(session_id="sess-3").count() == 1
        assert SessionRun.objects.get(session_id="sess-3").kind == "a"

    def test_blank_session_id_is_noop(self) -> None:
        from lawgraph.audit import session_ledger

        assert session_ledger.start_session("") is None
        assert session_ledger.finalize_session("") is None


@pytest.mark.django_db
class TestProvenanceSessionTagging:
    def test_explicit_args_tag_audit_event(self) -> None:
        from lawgraph.audit.models import AuditEvent
        from lawgraph.core.provenance import provenance

        tid = provenance.log_agent_call(
            "A",
            {},
            {"ok": 1},
            "m",
            1.0,
            session_id="sX",
            spec_id="specs/099-x",
            backlog_item_id="BL-9",
        )
        ev = AuditEvent.objects.get(trace_id=tid)
        assert ev.session_id == "sX"
        assert ev.payload.get("spec_id") == "specs/099-x"
        assert ev.payload.get("backlog_item_id") == "BL-9"

    def test_session_scope_ambient_tagging(self) -> None:
        from lawgraph.audit.models import AuditEvent
        from lawgraph.core.provenance import provenance, session_scope

        with session_scope("ambient-1", spec_id="specs/100"):
            tid = provenance.log_agent_call("A", {}, {}, "m", 1.0)
        ev = AuditEvent.objects.get(trace_id=tid)
        assert ev.session_id == "ambient-1"
        assert ev.payload.get("spec_id") == "specs/100"

    def test_no_session_leaves_blank(self) -> None:
        from lawgraph.audit.models import AuditEvent
        from lawgraph.core.provenance import provenance

        tid = provenance.log_agent_call("A", {}, {}, "m", 1.0)
        assert AuditEvent.objects.get(trace_id=tid).session_id == ""


@pytest.mark.django_db
class TestAutonomyCycleLedger:
    def test_cycle_creates_and_links_session(self, settings) -> None:
        settings.AUTONOMY_ENABLED = True
        from lawgraph.audit.models import AuditEvent, SessionRun
        from lawgraph.core.autonomy import run_cycle

        ctx = run_cycle("evolve", lambda c: {"did": "work"})
        cid = ctx["cycle_id"]
        row = SessionRun.objects.get(session_id=cid)
        assert row.status == "completed"
        assert row.kind == "evolve"
        assert row.agent_source == "celery"
        # The autonomy_cycle events are linked to the same session via session_id.
        assert AuditEvent.objects.filter(
            session_id=cid, kind="autonomy_cycle.end"
        ).exists()
