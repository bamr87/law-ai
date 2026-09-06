#!/usr/bin/env python3
"""mypy strict ratchet — BL-20260429-04.

``mypy law_ai --strict`` is not clean yet, so CI used to run it with
``continue-on-error: true`` and nobody ever looked at the output. A big-bang
"annotate all 78 files" PR is not landable, so this script turns the gate into
a *ratchet* instead: the committed baseline at ``backend/mypy-baseline.txt``
records how many strict errors each file is allowed to have, and the gate fails
when any file gets worse or a file that was clean stops being clean.

The invariants, in order of how loudly they fail:

* A file with errors that is **not in the baseline** fails. New code — and any
  file somebody burned down to zero and removed from the baseline — must be
  strict-clean forever after.
* A file whose error count is **above** its baseline entry fails.
* The **total** may never exceed the baseline total (this is implied by the two
  rules above, but it is checked explicitly so the failure message can lead
  with the number people actually track).

Improvements never fail. They are reported as reclaimable *slack* with the
command to bank them, because a baseline you cannot lower is not a ratchet.

Baseline format is one ``<count>\\t<path>`` line per offending file, sorted by
path, under a comment header carrying the total. Counts rather than full error
lines: line numbers churn on every unrelated edit, so a line-keyed baseline
would go stale between the time you generate it and the time CI reads it.

Usage — from a directory where ``mypy law_ai --strict`` runs (``backend/``, or
``/app`` in the container)::

    python3 scripts/mypy_ratchet.py --run            # check
    python3 scripts/mypy_ratchet.py --run --update   # bank the current state

``--run`` shells out to mypy; ``--report FILE`` (or stdin) reads output you
already have, which is what the unit tests use. ``make typecheck`` wires up the
first form and ``make mypy-baseline`` the second. Exit code is 0 when the
ratchet holds, 1 when it does not, and 2 when mypy crashed or the input could
not be parsed.

Stdlib-only, like scripts/spec_validator.py and scripts/backlog_lint.py — the
only external thing it touches is the mypy it optionally shells out to.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_BASELINE = REPO_ROOT / "backend" / "mypy-baseline.txt"

# `law_ai/core/llm/base.py:88: error: ...  [no-untyped-def]`
#
# Only `error:` lines count. mypy also emits `note:` continuation lines (and,
# with warn_unused_configs, a `pyproject.toml: note:` line that has no file
# path at all); counting those would make the baseline depend on how verbose a
# given mypy release chooses to be.
_ERROR_RE = re.compile(r"^(?P<path>[^\s:][^:]*):(?P<line>\d+):(?:\d+:)? error: ")

_HEADER = """\
# mypy --strict ratchet baseline — BL-20260429-04.
#
# One `<count>\\t<path>` line per file that still has strict errors. The gate
# (scripts/mypy_ratchet.py, run by `make typecheck` and CI's backend-lint job)
# fails if any count grows or a file not listed here starts erroring.
#
# Burn a file down, then run `make mypy-baseline` to bank it. When this file
# reaches zero entries, delete it and drop the ratchet call so plain
# `mypy law_ai --strict` is the gate.
#
# total: {total}
"""


def parse_report(text: str) -> dict[str, int]:
    """Count `error:` lines per file path in mypy's output."""
    counts: dict[str, int] = {}
    for raw in text.splitlines():
        match = _ERROR_RE.match(raw.strip())
        if match is None:
            continue
        path = match.group("path")
        counts[path] = counts.get(path, 0) + 1
    return counts


def parse_baseline(text: str) -> dict[str, int]:
    """Read a `<count>\\t<path>` baseline, ignoring comments and blanks."""
    counts: dict[str, int] = {}
    for lineno, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split("\t", 1) if "\t" in line else line.split(None, 1)
        if len(parts) != 2 or not parts[0].isdigit():
            raise ValueError(
                f"baseline line {lineno} is not `<count>\\t<path>`: {raw!r}"
            )
        counts[parts[1].strip()] = int(parts[0])
    return counts


def render_baseline(counts: dict[str, int]) -> str:
    total = sum(counts.values())
    body = "".join(f"{counts[path]}\t{path}\n" for path in sorted(counts))
    return _HEADER.format(total=total) + body


def compare(
    current: dict[str, int], baseline: dict[str, int]
) -> tuple[list[str], list[str]]:
    """Return (failures, slack) messages comparing current against baseline."""
    failures: list[str] = []
    slack: list[str] = []

    for path in sorted(current):
        now = current[path]
        allowed = baseline.get(path)
        if allowed is None:
            failures.append(
                f"{path}: {now} new strict error(s) in a file the baseline "
                f"expects to be clean"
            )
        elif now > allowed:
            failures.append(f"{path}: {now} strict errors, baseline allows {allowed}")
        elif now < allowed:
            slack.append(f"{path}: {now} strict errors, baseline allows {allowed}")

    for path in sorted(baseline):
        if path not in current:
            slack.append(f"{path}: now clean, baseline allows {baseline[path]}")

    total_now, total_allowed = sum(current.values()), sum(baseline.values())
    if total_now > total_allowed:
        failures.insert(
            0, f"total strict errors {total_now} exceeds baseline {total_allowed}"
        )
    return failures, slack


def _load_report(path: Path | None) -> str:
    if path is None:
        return sys.stdin.read()
    if not path.is_file():
        raise SystemExit(f"mypy report not found: {path}")
    return path.read_text(encoding="utf-8")


def run_mypy(package: str = "law_ai") -> str:
    """Run `mypy <package> --strict` in the cwd and return its stdout.

    Exit status 0 means clean and 1 means "errors found" — both are normal
    inputs to the ratchet. Anything above that is mypy itself failing (bad
    config, a plugin that could not import the settings module, an internal
    error), which must not be mistaken for "no errors".
    """
    proc = subprocess.run(
        [sys.executable, "-m", "mypy", package, "--strict", "--no-error-summary"],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.stderr.strip():
        print(proc.stderr.rstrip(), file=sys.stderr)
    if proc.returncode > 1:
        print(proc.stdout.rstrip(), file=sys.stderr)
        raise SystemExit(
            f"mypy ratchet: mypy exited {proc.returncode} — this is a mypy or "
            f"config failure, not a type error count."
        )
    return proc.stdout


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--run",
        action="store_true",
        help="run `mypy law_ai --strict` in the cwd instead of reading a report",
    )
    parser.add_argument(
        "--report",
        type=Path,
        default=None,
        help="file holding `mypy law_ai --strict` output (default: stdin)",
    )
    parser.add_argument(
        "--baseline",
        type=Path,
        default=DEFAULT_BASELINE,
        help=f"baseline file (default: {DEFAULT_BASELINE})",
    )
    parser.add_argument(
        "--update",
        action="store_true",
        help="rewrite the baseline from the report instead of checking it",
    )
    args = parser.parse_args(argv)

    report = run_mypy() if args.run else _load_report(args.report)
    current = parse_report(report)

    if args.update:
        args.baseline.parent.mkdir(parents=True, exist_ok=True)
        args.baseline.write_text(render_baseline(current), encoding="utf-8")
        total = sum(current.values())
        print(
            f"mypy ratchet: wrote {args.baseline} "
            f"({total} error(s) across {len(current)} file(s))"
        )
        return 0

    if not args.baseline.is_file():
        if not current:
            print("mypy ratchet: no baseline and no errors — strict-clean.")
            return 0
        print(f"mypy ratchet: baseline {args.baseline} is missing.", file=sys.stderr)
        print("Create it with `make mypy-baseline`.", file=sys.stderr)
        return 2

    try:
        baseline = parse_baseline(args.baseline.read_text(encoding="utf-8"))
    except ValueError as exc:
        print(f"mypy ratchet: {exc}", file=sys.stderr)
        return 2

    failures, slack = compare(current, baseline)
    total_now, total_allowed = sum(current.values()), sum(baseline.values())

    if failures:
        print("mypy ratchet: FAILED — strict errors got worse", file=sys.stderr)
        for message in failures:
            print(f"  - {message}", file=sys.stderr)
        regressed = {
            path
            for path in current
            if path not in baseline or current[path] > baseline[path]
        }
        offending = [
            line
            for line in report.splitlines()
            if line.split(":", 1)[0] in regressed and " error: " in line
        ]
        if offending:
            print("\nErrors in the files that regressed:", file=sys.stderr)
            for line in offending:
                print(f"  {line}", file=sys.stderr)
        print(
            "\nFix the new errors, or (if the regression is deliberate and "
            "reviewed) re-bank the baseline with `make mypy-baseline`.",
            file=sys.stderr,
        )
        return 1

    print(
        f"mypy ratchet: OK — {total_now} strict error(s) across "
        f"{len(current)} file(s), baseline allows {total_allowed}."
    )
    if slack:
        print(f"{len(slack)} file(s) improved; bank them with `make mypy-baseline`:")
        for message in slack:
            print(f"  - {message}")
    if not current:
        print(
            "Zero strict errors. Delete backend/mypy-baseline.txt and drop the "
            "ratchet so `mypy law_ai --strict` is the gate on its own."
        )
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
