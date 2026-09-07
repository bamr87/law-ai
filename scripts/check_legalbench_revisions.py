#!/usr/bin/env python3
"""Report when the pinned LegalBench revisions have drifted from upstream.

BL-20260906-30. ``backend/law_ai/eval/fetch.py`` pins two commits by hand — the
Hugging Face dataset ``nguha/legalbench`` (``DATA_REVISION``) and the GitHub
repo ``HazyResearch/legalbench`` for prompt templates and licence READMEs
(``PROMPT_REVISION``). Pinning is the right call: a benchmark that moves under
the harness makes the 1 pp regression policy meaningless (docs/legalbench.md).
But nothing watched the pins, so the benchmark aged by neglect rather than by
decision — nobody would learn that upstream had moved until someone
re-benchmarked for an unrelated reason.

This is the watcher. It reads the two pins out of the source (no Django, no
imports of the app), asks each upstream for its current HEAD, and prints a
report. Drift is *news*, not a failure: bumping a benchmark revision is a
deliberate act with a re-baseline attached, so the exit code stays 0 unless
``--strict`` is passed.

    python3 scripts/check_legalbench_revisions.py
    python3 scripts/check_legalbench_revisions.py --strict   # exit 1 on drift

The intended follow-through, once a bump is decided, is documented in
docs/legalbench.md: ``MANIFEST=update make legalbench-cache`` and then a
re-baseline.

Stdlib only, like every other script in this directory.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

FETCH_PY = Path("backend") / "law_ai" / "eval" / "fetch.py"

#: Where each pin's upstream HEAD is published, and how to read the sha out.
DATA_HEAD_URL = "https://huggingface.co/api/datasets/nguha/legalbench"
PROMPT_HEAD_URL = "https://api.github.com/repos/HazyResearch/legalbench/commits/main"

TIMEOUT_S = 20


@dataclass(frozen=True)
class Pin:
    """One pinned revision and what upstream currently says."""

    name: str
    pinned: str
    upstream: str | None
    error: str | None = None

    @property
    def drifted(self) -> bool:
        """Upstream moved. Unknown (an unreachable upstream) is not drift."""
        return self.upstream is not None and self.upstream != self.pinned

    def line(self) -> str:
        if self.error:
            return f"  {self.name}: pinned {self.pinned[:12]} — could not check ({self.error})"
        assert self.upstream is not None
        if self.drifted:
            return (
                f"  {self.name}: pinned {self.pinned[:12]} -> "
                f"upstream {self.upstream[:12]}  DRIFTED"
            )
        return f"  {self.name}: pinned {self.pinned[:12]} — current"


def read_pin(source: str, name: str) -> str:
    """Pull ``NAME = "<sha>"`` out of fetch.py without importing it."""
    match = re.search(rf'^{name}\s*=\s*"([0-9a-f]{{40}})"', source, flags=re.MULTILINE)
    if not match:
        raise SystemExit(f"{FETCH_PY}: no 40-char {name} found")
    return match.group(1)


def _get_json(url: str) -> dict[str, object]:
    headers = {
        "Accept": "application/json",
        "User-Agent": "law-ai-revision-check",
    }
    # Both URLs are the fixed https constants above.
    request = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(request, timeout=TIMEOUT_S) as response:
        return json.loads(response.read().decode("utf-8"))  # type: ignore[no-any-return]


def fetch_head(url: str, key: str) -> tuple[str | None, str | None]:
    """``(sha, error)`` — never raises, because an outage is not a drift."""
    try:
        payload = _get_json(url)
    except (urllib.error.URLError, TimeoutError, ValueError, OSError) as exc:
        return None, str(exc)[:120]
    value = payload.get(key)
    if not isinstance(value, str):
        return None, f"no {key!r} in the response"
    return value, None


def collect(source: str, *, offline: bool = False) -> list[Pin]:
    pins = [
        ("DATA_REVISION", DATA_HEAD_URL, "sha"),
        ("PROMPT_REVISION", PROMPT_HEAD_URL, "sha"),
    ]
    out: list[Pin] = []
    for name, url, key in pins:
        pinned = read_pin(source, name)
        if offline:
            out.append(Pin(name, pinned, None, "offline"))
            continue
        head, error = fetch_head(url, key)
        out.append(Pin(name, pinned, head, error))
    return out


def report(pins: list[Pin]) -> str:
    drifted = [p for p in pins if p.drifted]
    lines = ["LegalBench pinned revisions:"]
    lines += [p.line() for p in pins]
    if drifted:
        advice = (
            f"{len(drifted)} revision(s) have moved upstream. Bumping one is a "
            "deliberate act: decide the change is intended, then re-cache with "
            "`MANIFEST=update make legalbench-cache` and re-baseline "
            "(docs/legalbench.md)."
        )
        lines += ["", advice]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--strict",
        action="store_true",
        help="exit 1 when a pin has drifted (default: report and exit 0)",
    )
    parser.add_argument(
        "--offline",
        action="store_true",
        help="read the pins and skip the upstream calls",
    )
    args = parser.parse_args(argv)

    source = FETCH_PY.read_text(encoding="utf-8")
    pins = collect(source, offline=args.offline)
    print(report(pins))
    return 1 if args.strict and any(p.drifted for p in pins) else 0


if __name__ == "__main__":
    sys.exit(main())
