"""Periodic spec + backlog triage — BL-20260503-14.

The failure modes worth pinning are not "does it run": they are the three ways
a triage job quietly stops being a triage job. It reports nothing because it
could not find the repo and nobody notices. It runs one validator and calls
that both. It opens a fresh issue every single run because the idempotency
lookup missed.
"""

from __future__ import annotations

import json
from pathlib import Path
from subprocess import CompletedProcess
from typing import Any

import pytest

from law_ai.core import governance

pytestmark = pytest.mark.unit

CLEAN_BACKLOG = "No ## Open items older than 60 days.\n"
STALE_BACKLOG = "## Open items older than 60 days\n\n- BL-20260101-01 — something\n"


def _repo(tmp_path: Path) -> Path:
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    (scripts / "backlog_lint.py").write_text("# stub\n")
    (scripts / "spec_validator.py").write_text("# stub\n")
    return tmp_path


def _runner(backlog: str, spec: str = "", spec_code: int = 0) -> Any:
    calls: list[list[str]] = []

    def run(args: list[str], **kwargs: Any) -> CompletedProcess[str]:
        calls.append(list(args))
        if "backlog_lint.py" in args[1]:
            return CompletedProcess(args, 0, backlog, "")
        return CompletedProcess(args, spec_code, spec, "")

    run.calls = calls  # type: ignore[attr-defined]
    return run


class TestCollectReport:
    def test_runs_both_validators_not_just_the_backlog(self, tmp_path: Path) -> None:
        """The item asked for backlog_lint *and* spec_validator."""
        runner = _runner(CLEAN_BACKLOG)
        governance.collect_report(_repo(tmp_path), runner=runner)
        scripts = [args[1] for args in runner.calls]
        assert "scripts/backlog_lint.py" in scripts
        assert "scripts/spec_validator.py" in scripts

    def test_clean_repo_needs_no_triage(self, tmp_path: Path) -> None:
        report = governance.collect_report(
            _repo(tmp_path), runner=_runner(CLEAN_BACKLOG)
        )
        assert report.repo_available
        assert not report.backlog_stale
        assert report.spec_ok
        assert not report.needs_triage

    def test_a_stale_backlog_needs_triage(self, tmp_path: Path) -> None:
        report = governance.collect_report(
            _repo(tmp_path), runner=_runner(STALE_BACKLOG)
        )
        assert report.backlog_stale
        assert report.needs_triage

    def test_an_inconsistent_spec_needs_triage_on_its_own(self, tmp_path: Path) -> None:
        """Spec drift must surface even when the backlog is spotless.

        This is the half the workflow-only version never reported: it ran
        backlog_lint and nothing else, so a spec left inconsistent for a month
        reached no human.
        """
        report = governance.collect_report(
            _repo(tmp_path),
            runner=_runner(
                CLEAN_BACKLOG, spec="spec 007: task T-004 has no FR", spec_code=1
            ),
        )
        assert not report.backlog_stale
        assert not report.spec_ok
        assert report.needs_triage
        assert "task T-004 has no FR" in report.as_markdown()

    def test_a_missing_repo_is_reported_not_mistaken_for_clean(
        self, tmp_path: Path
    ) -> None:
        """ "Could not look" must never read as "found nothing"."""
        report = governance.collect_report(tmp_path, runner=_runner(CLEAN_BACKLOG))
        assert not report.repo_available
        assert not report.needs_triage  # nothing to report — but see below
        assert report.repo_root == str(tmp_path)

    def test_the_body_carries_both_validators(self, tmp_path: Path) -> None:
        report = governance.collect_report(
            _repo(tmp_path), runner=_runner(STALE_BACKLOG)
        )
        body = report.as_markdown()
        assert "Stale `## Open` backlog items" in body
        assert "spec_validator.py" in body
        assert "BL-20260101-01" in body


class _Opener:
    """Minimal urlopen stand-in that records requests and replays canned bodies."""

    def __init__(self, responses: list[Any]) -> None:
        self._responses = list(responses)
        self.requests: list[tuple[str, str, dict[str, Any] | None]] = []

    def __call__(self, request: Any, timeout: int = 0) -> Any:
        body = request.data.decode() if request.data else None
        self.requests.append(
            (
                request.get_method(),
                request.full_url,
                json.loads(body) if body else None,
            )
        )
        payload = self._responses.pop(0)

        class _Response:
            def __enter__(self_inner) -> Any:
                return self_inner

            def __exit__(self_inner, *args: Any) -> None:
                return None

            def read(self_inner) -> bytes:
                return json.dumps(payload).encode()

        return _Response()


class TestTriageIssue:
    def _stale(self) -> governance.GovernanceReport:
        return governance.GovernanceReport(
            repo_available=True,
            backlog_output=STALE_BACKLOG,
            backlog_stale=True,
            spec_ok=True,
            spec_output="",
        )

    def test_nothing_stale_opens_nothing(self) -> None:
        clean = governance.GovernanceReport(
            repo_available=True,
            backlog_output=CLEAN_BACKLOG,
            backlog_stale=False,
            spec_ok=True,
            spec_output="",
        )
        opener = _Opener([])
        result = governance.open_triage_issue(
            clean, repo="o/r", token="t", opener=opener
        )
        assert result["action"] == "skipped"
        assert opener.requests == []

    def test_no_credential_reports_without_filing(self) -> None:
        result = governance.open_triage_issue(self._stale(), repo="", token="")
        assert result["action"] == "skipped"
        assert "credential" in result["reason"]

    def test_first_run_creates_the_issue(self) -> None:
        opener = _Opener([[], {"number": 42}])
        result = governance.open_triage_issue(
            self._stale(), repo="o/r", token="t", opener=opener
        )
        assert result == {"action": "created", "number": 42}
        method, url, payload = opener.requests[1]
        assert method == "POST" and url.endswith("/issues")
        assert payload["title"] == governance.ISSUE_TITLE
        assert payload["labels"] == [governance.ISSUE_LABEL]

    def test_second_run_comments_instead_of_duplicating(self) -> None:
        """The whole point of the label lookup.

        The workflow this replaces searched by title through GitHub's search
        API — and the title contains a colon, which search reads as a
        qualifier, so the lookup could miss and open a duplicate every run.
        """
        opener = _Opener([[{"number": 7, "title": governance.ISSUE_TITLE}], {}])
        result = governance.open_triage_issue(
            self._stale(), repo="o/r", token="t", opener=opener
        )
        assert result == {"action": "commented", "number": 7}
        method, url, _ = opener.requests[1]
        assert method == "POST" and url.endswith("/issues/7/comments")
        # And the lookup itself must never be a search query.
        assert "search" not in opener.requests[0][1]
        assert f"labels={governance.ISSUE_LABEL}" in opener.requests[0][1]

    def test_a_github_outage_never_raises(self) -> None:
        """A governance report is not worth taking the worker down for."""

        def boom(request: Any, timeout: int = 0) -> Any:
            raise OSError("connection reset")

        result = governance.open_triage_issue(
            self._stale(), repo="o/r", token="t", opener=boom
        )
        assert result["action"] == "skipped"
        assert "github error" in result["reason"]


class TestBeatWiring:
    def test_the_beat_schedule_has_a_governance_entry(self) -> None:
        """BL-20260503-14 asked for a *Celery beat* job, not only a CI step."""
        from law_ai.celery import app

        entry = app.conf.beat_schedule.get("governance-triage")
        assert entry, "no governance-triage entry in the beat schedule"
        assert entry["task"] == "law_ai.core.tasks.governance_triage"
        # It reports; it takes no autonomous action, so it must keep running
        # on an instance with AUTONOMY_ENABLED=false and off that queue.
        assert entry.get("options", {}).get("queue") != "autonomy"

    def test_the_task_runs_the_triage_and_logs_provenance(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from law_ai.core import tasks

        seen: dict[str, Any] = {}

        def fake_run_triage(repo_root: Path, **kwargs: Any) -> dict[str, Any]:
            seen["kwargs"] = kwargs
            return {
                "repo_available": True,
                "backlog_stale": True,
                "spec_ok": False,
                "needs_triage": True,
                "issue": {"action": "skipped", "reason": "no github credential"},
                "report": "body",
            }

        events: list[tuple[str, dict[str, Any]]] = []
        monkeypatch.setattr(governance, "run_triage", fake_run_triage)
        from law_ai.core.provenance import provenance

        monkeypatch.setattr(
            provenance,
            "log_event",
            lambda kind, payload: events.append((kind, payload)),
        )

        result = tasks.governance_triage(stale_days=30)
        assert result["needs_triage"] is True
        assert seen["kwargs"]["stale_days"] == 30
        assert events and events[0][0] == "governance_triage"
        assert events[0][1]["backlog_stale"] is True
        assert events[0][1]["spec_ok"] is False
