"""Beat-scheduled sweep of approved quarantine rows (BL-20260811-02).

Spec 029 shipped the approval → commit service and a Celery task, but nothing
scheduled it: a reviewer's approval sat unapplied until somebody ran
``manage.py review_queue commit`` by hand. This pins the beat entry, the
``commit_approved`` cycle kind, and the ``AUTONOMY_ENABLED`` kill-switch.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

import pytest

from law_ai.celery import app as celery_app
from law_ai.core.management.commands.run_autonomy import _run_commit_approved
from law_ai.core.tasks import autonomy_cycle

ENTRY = "ingestion-commit-approved"


# ---------------------------------------------------------------------------
# Beat entry shape
# ---------------------------------------------------------------------------


def test_beat_entry_exists_and_targets_the_autonomy_cycle() -> None:
    entry = celery_app.conf.beat_schedule[ENTRY]
    assert entry["task"] == "law_ai.core.tasks.autonomy_cycle"
    assert entry["kwargs"]["kind"] == "commit_approved"
    assert entry["options"]["queue"] == "autonomy"


def test_beat_entry_is_budget_capped() -> None:
    """A large backlog must not monopolise a worker (approval.py's sweep cap)."""
    from law_ai.ingestionapp.services.approval import DEFAULT_SWEEP_LIMIT

    budget = celery_app.conf.beat_schedule[ENTRY]["kwargs"]["budget"]
    assert isinstance(budget, int)
    assert 0 < budget <= DEFAULT_SWEEP_LIMIT


def test_beat_entry_runs_at_least_hourly() -> None:
    schedule = celery_app.conf.beat_schedule[ENTRY]["schedule"]
    assert isinstance(schedule, (int, float))
    assert 0 < schedule <= 3600


# ---------------------------------------------------------------------------
# The runner
# ---------------------------------------------------------------------------


def test_runner_reports_processed_committed_and_failed() -> None:
    results = [
        {"id": "a", "committed": True},
        {"id": "b", "committed": False, "error": "boom"},
    ]
    with patch(
        "law_ai.ingestionapp.services.approval.commit_approved_reviews",
        return_value=results,
    ) as sweep:
        out = _run_commit_approved({"cycle_id": "c-1"}, budget=7)

    sweep.assert_called_once_with(7)
    assert out["processed"] == 2
    assert out["committed"] == 1
    assert out["failed"] == 1
    assert out["cycle_id"] == "c-1"


def test_runner_defaults_to_the_service_sweep_limit() -> None:
    from law_ai.ingestionapp.services.approval import DEFAULT_SWEEP_LIMIT

    with patch(
        "law_ai.ingestionapp.services.approval.commit_approved_reviews",
        return_value=[],
    ) as sweep:
        _run_commit_approved({}, budget=None)
    sweep.assert_called_once_with(DEFAULT_SWEEP_LIMIT)


def test_runner_caps_an_absurd_budget() -> None:
    with patch(
        "law_ai.ingestionapp.services.approval.commit_approved_reviews",
        return_value=[],
    ) as sweep:
        _run_commit_approved({}, budget=10_000)
    assert sweep.call_args.args[0] <= 200


# ---------------------------------------------------------------------------
# Kill-switch + wiring
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_cycle_is_disabled_when_autonomy_is_off(settings: Any) -> None:
    settings.AUTONOMY_ENABLED = False
    with patch(
        "law_ai.ingestionapp.services.approval.commit_approved_reviews"
    ) as sweep:
        result = autonomy_cycle(kind="commit_approved", budget=25)
    assert result["status"] == "disabled"
    sweep.assert_not_called()


@pytest.mark.django_db
def test_cycle_sweeps_when_autonomy_is_enabled(settings: Any) -> None:
    settings.AUTONOMY_ENABLED = True
    with patch(
        "law_ai.ingestionapp.services.approval.commit_approved_reviews",
        return_value=[{"id": "a", "committed": True}],
    ) as sweep:
        result = autonomy_cycle(kind="commit_approved", budget=25)
    sweep.assert_called_once_with(25)
    assert result["status"] != "disabled"


def test_management_command_accepts_the_new_kind() -> None:
    from law_ai.core.management.commands.run_autonomy import Command

    parser = Command().create_parser("manage.py", "run_autonomy")
    args = parser.parse_args(["--kind", "commit_approved", "--dry-run"])
    assert args.kind == "commit_approved"
