#!/usr/bin/env python3
"""Spec drift validator for LexGraph AI specs/.

Enforces that every spec under ``specs/NNN-*`` is internally consistent:

* ``spec.md``, ``plan.md``, and ``tasks.md`` all exist.
* No unresolved ``OPEN QUESTION OQ-N`` blocks remain in ``spec.md``.
* Every ``FR-*``, ``NFR-*``, and ``AC-*`` ID defined in ``spec.md`` is
  referenced by at least one task in ``tasks.md``.
* ``tasks.md`` contains a ``## Follow-ups Discovered`` section so every
  implementation cycle is forced to record next-step work — even if the
  list is explicitly empty (the section must literally say ``_none_``).

Exit code is non-zero if any spec fails. Used as a CI gate.

Usage::

    python scripts/spec_validator.py            # validate all specs/
    python scripts/spec_validator.py specs/001-foo
"""
from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Iterable

REPO_ROOT = Path(__file__).resolve().parent.parent
SPECS_DIR = REPO_ROOT / "specs"
SPEC_DIR_RE = re.compile(r"^\d{3}-[a-z0-9][a-z0-9-]*$")
ID_RE = re.compile(r"\b((?:FR|NFR|AC)-[A-Z0-9-]+)\b")
OPEN_Q_RE = re.compile(r"OPEN QUESTION\s+OQ-\d+", re.IGNORECASE)
TEMPLATE_PLACEHOLDER = "FR-1"  # appears in _template; ignored there


def _iter_spec_dirs(targets: list[str]) -> Iterable[Path]:
    if targets:
        for t in targets:
            p = (REPO_ROOT / t).resolve()
            if p.is_dir():
                yield p
        return
    if not SPECS_DIR.is_dir():
        return
    for child in sorted(SPECS_DIR.iterdir()):
        if child.is_dir() and SPEC_DIR_RE.match(child.name):
            yield child


def _extract_ids(text: str) -> set[str]:
    return set(ID_RE.findall(text))


def validate_spec(spec_dir: Path) -> list[str]:
    errors: list[str] = []
    spec = spec_dir / "spec.md"
    plan = spec_dir / "plan.md"
    tasks = spec_dir / "tasks.md"

    for required in (spec, plan, tasks):
        if not required.is_file():
            errors.append(f"missing {required.relative_to(REPO_ROOT)}")
    if errors:
        return errors

    spec_text = spec.read_text(encoding="utf-8")
    tasks_text = tasks.read_text(encoding="utf-8")

    open_qs = OPEN_Q_RE.findall(spec_text)
    if open_qs:
        errors.append(
            f"{spec.relative_to(REPO_ROOT)}: {len(open_qs)} unresolved OPEN QUESTION block(s)"
        )

    spec_ids = _extract_ids(spec_text)
    task_ids = _extract_ids(tasks_text)

    missing = sorted(spec_ids - task_ids)
    if missing:
        errors.append(
            f"{tasks.relative_to(REPO_ROOT)}: requirement(s) not referenced by any task: "
            + ", ".join(missing)
        )

    if "## Follow-ups Discovered" not in tasks_text:
        errors.append(
            f"{tasks.relative_to(REPO_ROOT)}: missing required section '## Follow-ups Discovered' "
            "(use '_none_' if there are truly no follow-ups)"
        )

    return errors


def main(argv: list[str]) -> int:
    spec_dirs = list(_iter_spec_dirs(argv[1:]))
    if not spec_dirs:
        print("spec_validator: no specs to validate (this is fine)")
        return 0

    failed = 0
    for d in spec_dirs:
        errs = validate_spec(d)
        rel = d.relative_to(REPO_ROOT)
        if errs:
            failed += 1
            print(f"FAIL {rel}")
            for e in errs:
                print(f"  - {e}")
        else:
            print(f"PASS {rel}")

    if failed:
        print(f"\n{failed} spec(s) failed validation")
        return 1
    print(f"\nAll {len(spec_dirs)} spec(s) valid")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
