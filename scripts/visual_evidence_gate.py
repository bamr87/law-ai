#!/usr/bin/env python3
"""Visual-evidence gate — BL-20260905-05.

AGENTS.md § "Evaluation & Quality Gates" and docs/ui-ux-review.md § "Visual
evidence" both say a UI change ships with a screenshot, and
.github/pull_request_template.md has a section asking for one. None of that
fails anything: a PR could rewrite every screen in ``frontend/`` or
``lsat-static/`` and attach nothing at all. This script is the mechanical half.

A change that touches those paths passes if **either**:

1. the PR body references an image — a markdown ``![...]``, an ``<img`` tag, a
   GitHub ``user-attachments/assets`` upload, or a link to a file under
   ``docs/images/``; or
2. the diff adds or changes a file under ``docs/images/``.

Branch 2 is the label-free escape hatch: a fork contributor cannot add the
``no-visual-change`` label to their own PR, but they can commit a screenshot.
The opt-out itself is applied in CI, not here — see
``.github/workflows/ci.yml``.

This is a heuristic and is meant to be: it proves someone *attached* something,
not that the picture is of the right screen or that the link resolves. The
reviewer still has to look. The gate exists to stop the silent case, which is
where the actual failure mode lives.

Usage (what CI does)::

    PR_BODY="$BODY" python3 scripts/visual_evidence_gate.py \\
        --changed-files changed.txt

Stdlib only, like the other scripts in this directory, so it runs in the
host-python CI job with no container.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

#: Paths whose change requires visual evidence.
VISUAL_PREFIXES = ("frontend/", "lsat-static/")

#: Where a committed screenshot lives.
IMAGE_DIR = "docs/images/"

#: Body patterns that count as "an image is attached".
_BODY_PATTERNS = (
    re.compile(r"!\[[^\]]*\]\([^)]+\)"),  # markdown image
    re.compile(r"<img\b", re.IGNORECASE),  # inline html
    re.compile(r"user-attachments/assets/", re.IGNORECASE),  # GH upload
    re.compile(r"githubusercontent\.com/\S*docs/images/", re.IGNORECASE),
    re.compile(re.escape(IMAGE_DIR), re.IGNORECASE),  # link to a committed one
)

DOC_POINTER = (
    "See docs/ui-ux-review.md § 'Visual evidence' for what to attach, and "
    "AGENTS.md § 'Evaluation & Quality Gates' for why. To opt out of this "
    "gate on a change that genuinely has no visual effect (a refactor, a "
    "test-only change), add the `no-visual-change` label to the PR."
)


def touches_visual_paths(paths: list[str]) -> list[str]:
    """The changed files that put a PR under this gate."""
    return [p for p in paths if p.startswith(VISUAL_PREFIXES)]


def has_body_image(body: str) -> bool:
    """Does the PR body reference an image?"""
    return any(pattern.search(body) for pattern in _BODY_PATTERNS)


def has_committed_image(paths: list[str]) -> list[str]:
    """Changed files that are committed screenshots."""
    return [p for p in paths if p.startswith(IMAGE_DIR)]


def evaluate(body: str, paths: list[str]) -> tuple[bool, str]:
    """``(passed, message)`` — the whole decision, so tests need no subprocess."""
    visual = touches_visual_paths(paths)
    if not visual:
        return True, "No frontend/ or lsat-static/ files changed; gate does not apply."

    committed = has_committed_image(paths)
    if committed:
        return True, "Visual evidence: committed image(s) " + ", ".join(
            sorted(committed)[:5]
        )
    if has_body_image(body):
        return True, "Visual evidence: image referenced in the PR body."

    sample = ", ".join(sorted(visual)[:5])
    more = f" (+{len(visual) - 5} more)" if len(visual) > 5 else ""
    return False, (
        f"This PR changes {len(visual)} file(s) under "
        f"{' / '.join(VISUAL_PREFIXES)} — {sample}{more} — but attaches no "
        f"visual evidence: no image in the PR body and no new or changed file "
        f"under {IMAGE_DIR}.\n\n{DOC_POINTER}"
    )


def _read_changed_files(path: str | None) -> list[str]:
    if path:
        text = Path(path).read_text(encoding="utf-8")
    else:
        text = sys.stdin.read()
    return [line.strip() for line in text.splitlines() if line.strip()]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Visual-evidence gate")
    parser.add_argument(
        "--changed-files",
        help="file with one changed path per line (default: read stdin)",
    )
    parser.add_argument(
        "--body",
        help="PR body text (default: the PR_BODY environment variable)",
    )
    args = parser.parse_args(argv)

    body = args.body if args.body is not None else os.environ.get("PR_BODY", "")
    paths = _read_changed_files(args.changed_files)

    passed, message = evaluate(body, paths)
    print(("PASS " if passed else "FAIL ") + "visual-evidence gate")
    print(message)
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
