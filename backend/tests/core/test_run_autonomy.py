"""Tests for the ``run_autonomy`` management command (spec 018 T-009)."""

from __future__ import annotations

from io import StringIO
from unittest.mock import patch

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError


@pytest.fixture()
def _autonomy_enabled(settings: object) -> None:  # type: ignore[type-arg]
    """Temporarily enable the autonomy kill-switch for a single test."""
    from django.conf import settings as dj

    dj.AUTONOMY_ENABLED = True
    dj.AUTONOMY_ALLOWED_SOURCES = ["courtlistener", "colorado_statutes"]
    yield
    dj.AUTONOMY_ENABLED = False
    dj.AUTONOMY_ALLOWED_SOURCES = []


class TestRunAutonomyBasic:
    def test_disabled_exits_0_with_warning(self, settings: object) -> None:  # type: ignore[type-arg]
        """When AUTONOMY_ENABLED=False the command should still exit 0."""
        from django.conf import settings as dj

        dj.AUTONOMY_ENABLED = False  # type: ignore[assignment]
        out = StringIO()
        # No exception = exit 0
        call_command("run_autonomy", "--kind", "test_pillar", stdout=out)
        assert "disabled" in out.getvalue().lower()

    def test_dry_run_prints_payload(self) -> None:
        out = StringIO()
        call_command(
            "run_autonomy",
            "--kind",
            "corpus_growth",
            "--source",
            "courtlistener",
            "--budget",
            "5",
            "--dry-run",
            stdout=out,
        )
        body = out.getvalue()
        assert "corpus_growth" in body
        assert "courtlistener" in body

    def test_policy_violation_on_unknown_source(self) -> None:
        """Source not in allow-list → CommandError with returncode 1."""
        with pytest.raises(CommandError, match="not in AUTONOMY_ALLOWED_SOURCES"):
            call_command(
                "run_autonomy",
                "--kind",
                "corpus_growth",
                "--source",
                "totally_unknown_adapter",
            )

    @pytest.mark.usefixtures("_autonomy_enabled")
    def test_dry_run_shows_enabled_status(self) -> None:
        out = StringIO()
        call_command(
            "run_autonomy",
            "--kind",
            "test_pillar",
            "--dry-run",
            stdout=out,
        )
        body = out.getvalue()
        assert "AUTONOMY_ENABLED=True" in body

    @pytest.mark.usefixtures("_autonomy_enabled")
    def test_run_cycle_called_with_correct_kind(self) -> None:
        """Happy path: run_cycle is invoked with the requested kind."""
        out = StringIO()
        fake_result = {
            "status": "ok",
            "cycle_id": "test-cycle-1",
            "result": {"proposed_tests": 0},
        }

        with patch(
            "lawgraph.core.autonomy.run_cycle", return_value=fake_result
        ) as mock_run:
            call_command("run_autonomy", "--kind", "test_pillar", stdout=out)

        mock_run.assert_called_once()
        call_args = mock_run.call_args
        assert call_args.args[0] == "test_pillar"
        assert (
            "test_pillar" in out.getvalue().lower() or "cycle" in out.getvalue().lower()
        )

    @pytest.mark.usefixtures("_autonomy_enabled")
    def test_run_cycle_corpus_growth_kind(self) -> None:
        out = StringIO()
        fake_result = {
            "status": "ok",
            "cycle_id": "test-cycle-2",
            "result": {"docs_queued": 0},
        }

        with patch(
            "lawgraph.core.autonomy.run_cycle", return_value=fake_result
        ) as mock_run:
            call_command(
                "run_autonomy",
                "--kind",
                "corpus_growth",
                "--source",
                "courtlistener",
                "--budget",
                "10",
                stdout=out,
            )

        mock_run.assert_called_once()
        call_args = mock_run.call_args
        assert call_args.args[0] == "corpus_growth"

    @pytest.mark.usefixtures("_autonomy_enabled")
    def test_run_cycle_error_status_exits_2(self) -> None:
        """If run_cycle returns status=error the command should raise SystemExit(2)."""
        err = StringIO()
        fake_result = {
            "status": "error",
            "cycle_id": "test-cycle-3",
            "error": "something exploded",
        }

        with (
            patch("lawgraph.core.autonomy.run_cycle", return_value=fake_result),
            pytest.raises(SystemExit) as exc_info,
        ):
            call_command("run_autonomy", "--kind", "digest", stderr=err)

        assert exc_info.value.code == 2


class TestCeleryAutonomyTask:
    """Smoke-tests for the ``autonomy_cycle`` Celery task (T-009 beat integration)."""

    def test_task_registered(self) -> None:
        from lawgraph.celery import app
        import lawgraph.core.tasks  # trigger autodiscovery for this module  # noqa: F401

        assert "lawgraph.core.tasks.autonomy_cycle" in app.tasks

    def test_task_delegates_to_run_cycle_disabled(self) -> None:
        """When AUTONOMY_ENABLED=False the task returns status=disabled."""
        from lawgraph.core.tasks import autonomy_cycle

        result = autonomy_cycle(kind="test_pillar")
        assert result["status"] == "disabled"

    def test_beat_schedule_keys_present(self) -> None:
        from lawgraph.celery import app

        schedule = app.conf.beat_schedule
        assert "autonomy-content-sweep" in schedule
        assert "autonomy-nightly-tests" in schedule
        assert "autonomy-daily-digest" in schedule

    def test_beat_tasks_point_at_autonomy_cycle(self) -> None:
        from lawgraph.celery import app

        for key, entry in app.conf.beat_schedule.items():
            assert (
                entry["task"] == "lawgraph.core.tasks.autonomy_cycle"
            ), f"Beat entry {key!r} points at wrong task"
