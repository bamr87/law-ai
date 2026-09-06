"""Periodic repo-governance triage — BL-20260503-14.

The two stdlib validators in ``scripts/`` are the repo's own conscience:
``spec_validator.py`` catches spec/plan/tasks drift and ``backlog_lint.py``
catches BACKLOG.md drift. Both run in CI on the diff in front of them, which
means neither ever notices the thing nobody is diffing — a spec left
inconsistent for a month, an ``## Open`` item nobody has touched since spring.

This module is the periodic half: run both validators over the checked-out
repo, decide whether anything needs a human, and (when a credential is
configured) open one idempotent triage issue. :func:`law_ai.core.tasks.
governance_triage` is the Celery task, and ``celery.py``'s
``governance-triage`` beat entry is the schedule.

Two design notes worth keeping:

* **The repo has to be reachable.** The production backend image COPYs only
  ``backend/``; ``scripts/`` and ``BACKLOG.md`` exist in the worker solely
  through the dev ``./:/repo`` bind mount plus ``REPO_ROOT=/repo``. When the
  repo is not there the task reports that plainly instead of pretending it
  found nothing wrong. Never confuse "no findings" with "could not look".
* **No credential, no issue.** The worker holds no GitHub token by default, so
  issue creation is opt-in via ``GOVERNANCE_TRIAGE_GITHUB_TOKEN`` +
  ``GOVERNANCE_TRIAGE_GITHUB_REPO``. Without them the report still lands in
  provenance and in the worker log — the finding is not lost, only its
  delivery channel is.

Idempotency is by title against the open issues carrying the triage label. It
deliberately does not use GitHub's search API: the natural title contains a
colon, which search parses as a qualifier, and a lookup that quietly misses
opens a duplicate issue on every single run.
"""

from __future__ import annotations

import json
import logging
import subprocess
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from collections.abc import Callable

logger = logging.getLogger("law_ai.governance")

#: Title of the one open issue this triage maintains.
ISSUE_TITLE = "backlog: stale open items need triage"

#: Label it carries, so the lookup never has to guess.
ISSUE_LABEL = "backlog-triage"

#: Sentinel `backlog_lint.py --stale-report` prints when nothing is stale.
_NO_STALE_PREFIX = "No ## Open items older than"

_TIMEOUT_S = 120


@dataclass(frozen=True)
class GovernanceReport:
    """What the two validators said about the repo as it stands."""

    #: False when the repo (scripts/, BACKLOG.md) is not mounted at all.
    repo_available: bool
    backlog_output: str
    backlog_stale: bool
    spec_ok: bool
    spec_output: str
    repo_root: str = ""

    @property
    def needs_triage(self) -> bool:
        """Is there something a human has to look at?"""
        return self.repo_available and (self.backlog_stale or not self.spec_ok)

    def as_markdown(self) -> str:
        """The issue body — both validators, not just the backlog half."""
        parts = [
            "_Opened by the `governance-triage` Celery beat job "
            "(`law_ai.core.governance`, BL-20260503-14). Updated in place; "
            "close it when the list is empty._",
            "",
            "## Stale `## Open` backlog items",
            "",
            "```",
            (self.backlog_output.strip() or "(no output)"),
            "```",
            "",
            "## Spec consistency (`scripts/spec_validator.py`)",
            "",
            (
                "Clean."
                if self.spec_ok
                else "```\n" + self.spec_output.strip() + "\n```"
            ),
        ]
        return "\n".join(parts)


def _run(args: list[str], cwd: Path, runner: Callable[..., Any]) -> tuple[int, str]:
    result = runner(
        args,
        cwd=str(cwd),
        capture_output=True,
        text=True,
        timeout=_TIMEOUT_S,
        check=False,
    )
    output = f"{result.stdout or ''}{result.stderr or ''}"
    return int(result.returncode), output


def collect_report(
    repo_root: Path,
    *,
    stale_days: int = 60,
    runner: Callable[..., Any] = subprocess.run,
) -> GovernanceReport:
    """Run both validators over ``repo_root``.

    ``runner`` is injected so tests never shell out.
    """
    scripts = repo_root / "scripts"
    if (
        not (scripts / "backlog_lint.py").is_file()
        or not (scripts / "spec_validator.py").is_file()
    ):
        return GovernanceReport(
            repo_available=False,
            backlog_output="",
            backlog_stale=False,
            spec_ok=True,
            spec_output="",
            repo_root=str(repo_root),
        )

    _, backlog_output = _run(
        [
            "python3",
            "scripts/backlog_lint.py",
            "--stale-report",
            "--stale-days",
            str(stale_days),
        ],
        repo_root,
        runner,
    )
    spec_code, spec_output = _run(
        ["python3", "scripts/spec_validator.py"], repo_root, runner
    )
    return GovernanceReport(
        repo_available=True,
        backlog_output=backlog_output,
        # --stale-report always exits 0; the sentinel line is the signal.
        backlog_stale=_NO_STALE_PREFIX not in backlog_output,
        spec_ok=spec_code == 0,
        spec_output=spec_output,
        repo_root=str(repo_root),
    )


def _api(
    method: str,
    url: str,
    token: str,
    payload: dict[str, Any] | None = None,
    *,
    opener: Callable[..., Any] = urllib.request.urlopen,
) -> Any:
    data = json.dumps(payload).encode() if payload is not None else None
    request = urllib.request.Request(url, data=data, method=method)
    request.add_header("Authorization", f"Bearer {token}")
    request.add_header("Accept", "application/vnd.github+json")
    request.add_header("X-GitHub-Api-Version", "2022-11-28")
    if data is not None:
        request.add_header("Content-Type", "application/json")
    with opener(request, timeout=30) as response:
        body = response.read().decode()
    return json.loads(body) if body else None


def open_triage_issue(
    report: GovernanceReport,
    *,
    repo: str,
    token: str,
    opener: Callable[..., Any] = urllib.request.urlopen,
) -> dict[str, Any]:
    """Open the triage issue, or comment on the one that is already open.

    Returns ``{"action": "created"|"commented"|"skipped", ...}``. Never raises
    for an API fault: a governance report that cannot be delivered must not
    take the worker down with it.
    """
    if not report.needs_triage:
        return {"action": "skipped", "reason": "nothing stale"}
    if not (repo and token):
        return {"action": "skipped", "reason": "no github credential configured"}

    base = f"https://api.github.com/repos/{repo}"
    try:
        # Listing by label, not the search API: the title's colon makes a
        # search qualifier, and a miss duplicates the issue every run.
        existing = (
            _api(
                "GET",
                f"{base}/issues?state=open&labels={ISSUE_LABEL}&per_page=100",
                token,
                opener=opener,
            )
            or []
        )
        match = next(
            (i for i in existing if i.get("title") == ISSUE_TITLE),
            None,
        )
        if match:
            _api(
                "POST",
                f"{base}/issues/{match['number']}/comments",
                token,
                {"body": report.as_markdown()},
                opener=opener,
            )
            return {"action": "commented", "number": match["number"]}

        created = _api(
            "POST",
            f"{base}/issues",
            token,
            {
                "title": ISSUE_TITLE,
                "body": report.as_markdown(),
                "labels": [ISSUE_LABEL],
            },
            opener=opener,
        )
        return {"action": "created", "number": (created or {}).get("number")}
    except (urllib.error.URLError, OSError, ValueError, KeyError) as exc:
        logger.warning("governance triage could not reach GitHub: %s", exc)
        return {"action": "skipped", "reason": f"github error: {exc}"}


def run_triage(
    repo_root: Path,
    *,
    stale_days: int = 60,
    repo: str = "",
    token: str = "",
    runner: Callable[..., Any] = subprocess.run,
    opener: Callable[..., Any] = urllib.request.urlopen,
) -> dict[str, Any]:
    """Collect the report and deliver it. The Celery task is a thin wrapper."""
    report = collect_report(repo_root, stale_days=stale_days, runner=runner)
    if not report.repo_available:
        logger.warning(
            "governance triage: scripts/ not found under %s — the worker needs "
            "the repo bind-mounted (REPO_ROOT=/repo). Reporting nothing is not "
            "the same as finding nothing.",
            report.repo_root,
        )
    issue = open_triage_issue(report, repo=repo, token=token, opener=opener)
    return {
        "repo_available": report.repo_available,
        "backlog_stale": report.backlog_stale,
        "spec_ok": report.spec_ok,
        "needs_triage": report.needs_triage,
        "issue": issue,
        "report": report.as_markdown() if report.needs_triage else "",
    }


__all__ = [
    "ISSUE_LABEL",
    "ISSUE_TITLE",
    "GovernanceReport",
    "collect_report",
    "open_triage_issue",
    "run_triage",
]
