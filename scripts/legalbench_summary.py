#!/usr/bin/env python3
"""Render the LegalBench score history as a Markdown table (BL-20260811-12).

The history at ``backend/var/legalbench/history.jsonl`` was only ever a
downloadable CI artifact — which is where reviewers do not look. Nightly pipes
this into ``$GITHUB_STEP_SUMMARY`` so the last runs, their scorers, and their
synthetic status show up on the run page itself:

    python3 scripts/legalbench_summary.py >> "$GITHUB_STEP_SUMMARY"
    python3 scripts/legalbench_summary.py --limit 20

Stdlib only, and it never exits non-zero: a missing or half-written history
must not fail a nightly. The durable surface is the autonomy digest's
"LegalBench Delta" section, fed by the `autonomy_legalbench_delta` events the
harness now emits; this is the cheap reviewer-facing mirror of it.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys

HISTORY = (
    pathlib.Path(__file__).resolve().parent.parent
    / "backend"
    / "var"
    / "legalbench"
    / "history.jsonl"
)


def load_rows(path: pathlib.Path, limit: int) -> list[dict[str, object]]:
    """Return the last ``limit`` parseable rows of the history file."""
    if not path.exists():
        return []
    rows: list[dict[str, object]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            parsed = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            rows.append(parsed)
    return rows[-limit:]


def _cell(row: dict[str, object], field: str, subset: str) -> str:
    values = row.get(field)
    if not isinstance(values, dict):
        return "—"
    value = values.get(subset)
    if value is None:
        return "—"
    if isinstance(value, float):
        return f"{value:.4f}"
    return str(value)


def render(rows: list[dict[str, object]]) -> str:
    """Render history rows as a Markdown section."""
    lines = ["## LegalBench score history", ""]
    if not rows:
        lines += [
            "_No runs recorded._ Cache the dataset (`make legalbench-cache`) "
            "and run `make test-legalbench-gate`.",
            "",
        ]
        return "\n".join(lines)

    subsets: list[str] = []
    for row in rows:
        accuracies = row.get("accuracies")
        if isinstance(accuracies, dict):
            for name in accuracies:
                if name not in subsets:
                    subsets.append(name)

    header = ["Run", "Model", *subsets, "Scorers", "Stub data?"]
    lines.append("| " + " | ".join(header) + " |")
    lines.append("|" + "---|" * len(header))
    for row in rows:
        synthetic = row.get("synthetic")
        stub = (
            "**yes**"
            if isinstance(synthetic, dict) and any(synthetic.values())
            else "no"
        )
        scorers = row.get("scorer")
        scorer_text = (
            ", ".join(sorted({str(v) for v in scorers.values()}))
            if isinstance(scorers, dict) and scorers
            else "default_match"
        )
        cells = [
            str(row.get("timestamp") or "?"),
            str(row.get("model") or "?"),
            *[_cell(row, "accuracies", subset) for subset in subsets],
            scorer_text,
            stub,
        ]
        lines.append("| " + " | ".join(cells) + " |")
    lines.append("")
    lines.append(
        "_A row flagged as stub data scored synthetic fixtures, not LegalBench._"
    )
    lines.append("")
    return "\n".join(lines)


def main(argv: list[str]) -> int:
    """CLI entry point; always returns 0."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--path", default=str(HISTORY))
    args = parser.parse_args(argv)
    try:
        rows = load_rows(pathlib.Path(args.path), max(1, args.limit))
        sys.stdout.write(render(rows))
    except Exception as exc:  # pragma: no cover - a summary must never fail CI
        sys.stdout.write(f"## LegalBench score history\n\n_unavailable: {exc}_\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
