#!/usr/bin/env python3
"""Decide whether a diff qualifies for the AM-1 auto-merge class (ADR 0004 §2).

AM-1 is the *only* class that may auto-merge (constitution §12 I1 as amended). A
diff is eligible **only if all** of:

1. Every changed file ends in ``.proposed.py`` (autonomy-proposed tests only).
2. There are **no added non-blank lines** — AM-1 is removal-only (un-skipping).
3. Every removed non-blank line is a ``@pytest.mark.skip("autonomy-proposed")``
   decorator — nothing else (no real code, no import churn).
4. At least one such skip decorator was removed (the change did something).

Reads a unified ``git diff`` on stdin; prints a JSON verdict; exit 0 = eligible,
1 = not. Stdlib only — the auto-merge workflow's load-bearing safety gate, so it
is small, strict, and tested.

    git diff origin/main...HEAD | python3 scripts/check_am1_eligible.py
"""

from __future__ import annotations

import json
import sys

_SKIP_MARKERS = ("pytest.mark.skip", "autonomy-proposed")
_HEADER_PREFIXES = (
    "--- ",
    "@@",
    "diff ",
    "index ",
    "rename ",
    "new file",
    "deleted file",
    "similarity ",
    "old mode",
    "new mode",
    "Binary files",
)


def analyze(diff_text: str) -> tuple[set[str], list[str], list[str]]:
    files: set[str] = set()
    added: list[str] = []
    removed: list[str] = []
    for line in diff_text.splitlines():
        if line.startswith("+++ "):
            path = line[4:].strip()
            path = path[2:] if path.startswith("b/") else path
            if path and path != "/dev/null":
                files.add(path)
            continue
        if line.startswith(_HEADER_PREFIXES):
            continue
        if line.startswith("+"):
            added.append(line[1:])
        elif line.startswith("-"):
            removed.append(line[1:])
    return files, added, removed


def evaluate(diff_text: str) -> dict[str, object]:
    files, added, removed = analyze(diff_text)
    reasons: list[str] = []

    if not files:
        reasons.append("empty diff")
    for f in sorted(files):
        if not f.endswith(".proposed.py"):
            reasons.append(f"non-proposed file changed: {f}")

    nonblank_added = [a for a in added if a.strip()]
    if nonblank_added:
        reasons.append(
            f"{len(nonblank_added)} added non-blank line(s) — AM-1 is removal-only"
        )

    skip_removed = 0
    for r in removed:
        s = r.strip()
        if not s:
            continue
        if all(m in s for m in _SKIP_MARKERS):
            skip_removed += 1
        else:
            reasons.append(f"removed non-skip line: {s[:60]}")

    if skip_removed == 0 and not reasons:
        reasons.append("no autonomy-proposed skip decorator removed")

    return {
        "eligible": len(reasons) == 0,
        "reasons": reasons,
        "files": sorted(files),
        "skip_decorators_removed": skip_removed,
    }


def main() -> int:
    verdict = evaluate(sys.stdin.read())
    print(json.dumps(verdict))
    return 0 if verdict["eligible"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
