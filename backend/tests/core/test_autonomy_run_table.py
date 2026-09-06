"""The promoted ``audit.AutonomyRun`` table (BL-20260511-04).

Cycles were queryable only as generic ``AuditEvent`` rows whose ``payload``
had to be unpacked in Python, so the digest's single window filter was the
only query the data could support. The table is the queryable projection of
the same cycles — and it is written *in addition to*, never instead of, the
``autonomy_cycle.*`` provenance events (constitution §4).

Every write here is best-effort: a Postgres outage must degrade a report, not
kill a cycle. Half these tests exist to prove exactly that.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from django.conf import settings

from law_ai.core import autonomy


@pytest.fixture()
def audit_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    target = tmp_path / "provenance.jsonl"
    monkeypatch.setattr(settings, "AUDIT_PATH", str(target))
    return target


def _events(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines()]


@pytest.mark.django_db
class TestRunRowLifecycle:
    def test_a_successful_cycle_opens_and_closes_one_row(
        self, audit_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from law_ai.audit.models import AutonomyRun

        monkeypatch.setattr(settings, "AUTONOMY_ENABLED", True)

        def runner(context: dict[str, Any]) -> dict[str, Any]:
            context["docs_queued"] = 3
            return {"docs_queued": 3}

        result = autonomy.run_cycle(
            "corpus_growth", runner, payload={"source": "courtlistener"}
        )

        row = AutonomyRun.objects.get(cycle_id=result["cycle_id"])
        assert row.kind == "corpus_growth"
        assert row.source == "courtlistener"
        assert row.status == "ok"
        assert row.ended_at is not None
        assert row.duration_ms is not None and row.duration_ms >= 0
        # The columns are what queries sort on; the free-form counts live in
        # `summary` because each pillar reports different ones.
        assert row.summary["docs_queued"] == 3
        assert row.summary["result"] == {"docs_queued": 3}

    def test_the_provenance_events_are_still_written(
        self, audit_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The table is a projection, not a replacement (constitution §4)."""
        monkeypatch.setattr(settings, "AUTONOMY_ENABLED", True)
        autonomy.run_cycle("digest", lambda _: "ok")

        assert [e["type"] for e in _events(audit_path)] == [
            "autonomy_cycle.start",
            "autonomy_cycle.end",
        ]

    def test_a_failed_cycle_records_status_error_and_the_message(
        self, audit_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from law_ai.audit.models import AutonomyRun

        monkeypatch.setattr(settings, "AUTONOMY_ENABLED", True)

        def boom(_: dict[str, Any]) -> None:
            raise RuntimeError("boom")

        with pytest.raises(RuntimeError, match="boom"):
            autonomy.run_cycle("test_pillar", boom)

        row = AutonomyRun.objects.order_by("-started_at").first()
        assert row is not None
        assert row.status == "error"
        assert "RuntimeError" in row.error
        assert row.ended_at is not None

    def test_the_kill_switch_still_leaves_a_row(
        self, audit_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """ "Nothing ran" is an answer the dashboard has to be able to give."""
        from law_ai.audit.models import AutonomyRun

        monkeypatch.setattr(settings, "AUTONOMY_ENABLED", False)
        result = autonomy.run_cycle("test_pillar", lambda _: "should-not-run")

        row = AutonomyRun.objects.get(cycle_id=result["cycle_id"])
        assert row.status == "disabled"
        assert row.duration_ms == 0.0

    def test_a_replayed_cycle_is_recorded_as_replayed(
        self, audit_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A reused --cycle-id must not look like a second real run."""
        from law_ai.audit.models import AutonomyRun

        monkeypatch.setattr(settings, "AUTONOMY_ENABLED", True)
        autonomy.run_cycle("digest", lambda _: "ok", cycle_id="cid-run-1")
        autonomy.run_cycle("digest", lambda _: "ok", cycle_id="cid-run-1")

        statuses = list(
            AutonomyRun.objects.filter(cycle_id="cid-run-1")
            .order_by("started_at")
            .values_list("status", flat=True)
        )
        assert statuses == ["ok", "replayed"]


class TestBestEffortWrites:
    """No DB (this class has no ``django_db``) — the cycle still completes."""

    def test_a_cycle_runs_and_is_audited_without_the_table(
        self, audit_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(settings, "AUTONOMY_ENABLED", True)

        result = autonomy.run_cycle("test_pillar", lambda _: {"ok": True})

        assert result["status"] == "ok"
        assert result["result"] == {"ok": True}
        assert [e["type"] for e in _events(audit_path)] == [
            "autonomy_cycle.start",
            "autonomy_cycle.end",
        ]

    def test_an_insert_failure_never_reaches_the_caller(
        self, audit_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from unittest.mock import MagicMock, patch

        monkeypatch.setattr(settings, "AUTONOMY_ENABLED", True)
        model = MagicMock()
        model.objects.create.side_effect = RuntimeError("connection refused")

        with patch("law_ai.audit.models.AutonomyRun", model):
            result = autonomy.run_cycle("digest", lambda _: "ok")

        assert result["status"] == "ok"

    def test_a_save_failure_never_reaches_the_caller(
        self, audit_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from unittest.mock import MagicMock, patch

        monkeypatch.setattr(settings, "AUTONOMY_ENABLED", True)
        row = MagicMock()
        row.save.side_effect = RuntimeError("connection lost mid-cycle")
        model = MagicMock()
        model.objects.create.return_value = row

        with patch("law_ai.audit.models.AutonomyRun", model):
            result = autonomy.run_cycle("digest", lambda _: "ok")

        assert result["status"] == "ok"
        row.save.assert_called_once()


@pytest.mark.django_db
class TestDigestReadsTheTable:
    def test_cycles_appear_in_the_digest(
        self, audit_path: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from law_ai.audit.models import AutonomyRun

        monkeypatch.setattr(settings, "AUTONOMY_DIGEST_DIR", str(tmp_path))
        anchor = datetime(2026, 5, 11, 7, 0, tzinfo=UTC)
        inside = anchor.replace(hour=0) - timedelta(hours=3)

        AutonomyRun.objects.create(
            cycle_id="cid-in",
            kind="corpus_growth",
            started_at=inside,
            ended_at=inside,
            status="ok",
            duration_ms=1234.0,
        )
        # Outside the [yesterday 00:00, today 00:00) window.
        AutonomyRun.objects.create(
            cycle_id="cid-out",
            kind="test_pillar",
            started_at=anchor,
            status="ok",
            duration_ms=1.0,
        )

        path = autonomy.compose_digest(date=anchor)
        text = path.read_text(encoding="utf-8")

        assert "## Autonomy Cycles" in text
        assert "cid-in" in text
        assert "corpus_growth" in text
        assert "cid-out" not in text

    def test_an_empty_window_still_renders_the_section(
        self, audit_path: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(settings, "AUTONOMY_DIGEST_DIR", str(tmp_path))
        path = autonomy.compose_digest(date=datetime(2026, 5, 11, 7, 0, tzinfo=UTC))
        text = path.read_text(encoding="utf-8")

        section = text.split("## Autonomy Cycles", 1)[1]
        assert section.lstrip().startswith("- *(none)*")


class TestDigestFoldsTheRunSummary:
    """BL-20260906-22: the summary the runner reported is rendered, not lost."""

    def test_summary_entries_land_in_the_four_sections(
        self, audit_path: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from law_ai.audit.models import AutonomyRun

        monkeypatch.setattr(settings, "AUTONOMY_DIGEST_DIR", str(tmp_path))
        anchor_dt = datetime(2026, 5, 11, 7, 0, tzinfo=UTC)
        AutonomyRun.objects.create(
            cycle_id="cid-sum",
            kind="evolve",
            started_at=anchor_dt.replace(hour=0) - timedelta(hours=3),
            status="ok",
            duration_ms=10.0,
            summary={
                "result": {
                    "prs_opened": ["https://example.test/pr/1"],
                    "backlog_ids": ["BL-20260906-99"],
                    "quarantined": ["https://example.test/opinion/7"],
                    "legalbench_delta": {"abercrombie": 0.02},
                    "docs_queued": 3,
                }
            },
        )

        text = autonomy.compose_digest(date=anchor_dt).read_text(encoding="utf-8")

        assert "https://example.test/pr/1" in text.split("## PRs Opened", 1)[1]
        assert "BL-20260906-99" in text.split("## BACKLOG Items Appended", 1)[1]
        assert "opinion/7" in text.split("## Docs Quarantined", 1)[1]
        assert "abercrombie: +0.02" in text.split("## LegalBench Delta", 1)[1]
        # The numeric counts ride on the cycle line, so a reader no longer has
        # to reconstruct them from an AuditEvent scan.
        assert "docs_queued=3" in text.split("## Autonomy Cycles", 1)[1]

    def test_an_event_and_a_summary_naming_the_same_thing_are_not_doubled(
        self, audit_path: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from law_ai.audit.models import AuditEvent, AutonomyRun

        monkeypatch.setattr(settings, "AUTONOMY_DIGEST_DIR", str(tmp_path))
        anchor_dt = datetime(2026, 5, 11, 7, 0, tzinfo=UTC)
        when = anchor_dt.replace(hour=0) - timedelta(hours=3)
        AuditEvent.objects.create(
            kind="autonomy_pr_opened",
            timestamp=when,
            payload={"url": "https://example.test/pr/1"},
        )
        AutonomyRun.objects.create(
            cycle_id="cid-dup",
            kind="evolve",
            started_at=when,
            status="ok",
            duration_ms=10.0,
            summary={"result": {"prs_opened": ["https://example.test/pr/1"]}},
        )

        text = autonomy.compose_digest(date=anchor_dt).read_text(encoding="utf-8")
        prs = text.split("## PRs Opened", 1)[1].split("##", 1)[0]
        assert prs.count("https://example.test/pr/1") == 1

    def test_a_summaryless_window_is_unchanged(
        self, audit_path: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Legacy rows carry no summary; the sections must still render."""
        from law_ai.audit.models import AutonomyRun

        monkeypatch.setattr(settings, "AUTONOMY_DIGEST_DIR", str(tmp_path))
        anchor_dt = datetime(2026, 5, 11, 7, 0, tzinfo=UTC)
        AutonomyRun.objects.create(
            cycle_id="cid-plain",
            kind="digest",
            started_at=anchor_dt.replace(hour=0) - timedelta(hours=3),
            status="ok",
            duration_ms=5.0,
            summary={},
        )
        text = autonomy.compose_digest(date=anchor_dt).read_text(encoding="utf-8")
        assert "- *(none)*" in text.split("## PRs Opened", 1)[1]
        assert "cid-plain" in text


class TestDigestSurvivesTheTableBeingUnreadable:
    def test_no_db_still_writes_a_usable_digest(
        self, audit_path: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Legacy windows and DB-less containers must still get a file."""
        monkeypatch.setattr(settings, "AUTONOMY_DIGEST_DIR", str(tmp_path))

        path = autonomy.compose_digest(date=datetime(2026, 5, 11, 7, 0, tzinfo=UTC))

        assert path.exists()
        text = path.read_text(encoding="utf-8")
        for header in (
            "## Autonomy Cycles",
            "## PRs Opened",
            "## BACKLOG Items Appended",
            "## Docs Quarantined",
            "## LegalBench Delta",
        ):
            assert header in text

    def test_the_retrying_task_still_sees_the_error(
        self, audit_path: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from unittest.mock import MagicMock, patch

        from django.db import OperationalError

        monkeypatch.setattr(settings, "AUTONOMY_DIGEST_DIR", str(tmp_path))
        model = MagicMock()
        model.objects.filter.side_effect = OperationalError("connection closed")

        with (
            patch("law_ai.audit.models.AutonomyRun", model),
            pytest.raises(OperationalError, match="connection closed"),
        ):
            autonomy.compose_digest(
                date=datetime(2026, 5, 11, 7, 0, tzinfo=UTC),
                raise_on_db_error=True,
            )
