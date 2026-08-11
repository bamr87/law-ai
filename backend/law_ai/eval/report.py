"""Report writer + delta calculator for LegalBench runs (spec 018 T-002).

Writes a structured JSON report to disk and optionally computes a delta
against a previously recorded baseline (``baseline.json``).

Report schema::

    {
      "run_id": "<uuid4>",
      "model": "<ollama-tag>",
      "timestamp": "<ISO-8601 UTC>",
      "subsets": [
        {"subset": "core_reasoning", "n": 50, "correct": 38, "accuracy": 0.76, "items": [...]},
        ...
      ],
      "delta": {                         # present only when baseline.json exists
        "core_reasoning": {"before": 0.75, "after": 0.76, "delta_pp": 1.0},
        ...
      }
    }
"""

from __future__ import annotations

import json
import logging
import time
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from law_ai.eval.legalbench import LegalBenchConfig

from law_ai.eval.paths import BASELINE_PATH, HISTORY_PATH

logger = logging.getLogger("law_ai.eval.report")


def _load_baseline() -> dict[str, float] | None:
    """Return ``{subset: accuracy}`` from ``baseline.json`` or ``None`` if absent."""
    if not BASELINE_PATH.exists():
        return None
    try:
        raw = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
        # Accept the full report format, the `accuracies` envelope written by
        # `update_baseline`, and a bare {subset: accuracy} mapping.
        if "subsets" in raw:
            return {row["subset"]: row["accuracy"] for row in raw["subsets"]}
        if "accuracies" in raw:
            return {k: float(v) for k, v in raw["accuracies"].items()}
        return {k: float(v) for k, v in raw.items()}
    except Exception as exc:
        logger.warning("Could not load baseline.json: %s", exc)
        return None


def _append_history(report: dict[str, Any]) -> None:
    """Append a compact per-run row to ``history.jsonl``.

    Without this there was no score history at all — every run overwrote
    nothing and informed nothing, so "accuracy over time" could not be
    answered even in principle (BL-20260810-04).
    """
    row = {
        "run_id": report.get("run_id"),
        "timestamp": report.get("timestamp"),
        "model": report.get("model"),
        "accuracies": {r["subset"]: r["accuracy"] for r in report.get("subsets", [])},
        "scored": {
            r["subset"]: r.get("scored", r.get("n")) for r in report.get("subsets", [])
        },
        "errored": {
            r["subset"]: r.get("errored", 0) for r in report.get("subsets", [])
        },
        "synthetic": {
            r["subset"]: r.get("synthetic", False) for r in report.get("subsets", [])
        },
    }
    try:
        HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
        with HISTORY_PATH.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, default=str) + "\n")
    except Exception as exc:  # pragma: no cover - history is best-effort
        logger.warning("could not append eval history: %s", exc)


def write_report(
    subset_results: list[dict[str, Any]],
    *,
    config: LegalBenchConfig,
) -> dict[str, Any]:
    """Assemble the JSON report dict, write it to disk, and return it.

    Args:
        subset_results: List of per-subset dicts with ``subset``, ``n``,
            ``correct``, ``accuracy``, and ``items`` keys (as produced
            by :func:`law_ai.eval.legalbench.run_eval`).
        config: The :class:`~law_ai.eval.legalbench.LegalBenchConfig`
            for this run (supplies ``run_id``, ``model``, ``report_path``).

    Returns:
        The full report dict.
    """
    timestamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    baseline = _load_baseline()
    delta: dict[str, Any] = {}
    if baseline:
        for row in subset_results:
            subset = row["subset"]
            before = baseline.get(subset)
            if before is not None:
                after = row["accuracy"]
                delta[subset] = {
                    "before": round(before, 4),
                    "after": round(after, 4),
                    "delta_pp": round((after - before) * 100, 2),
                }

    report: dict[str, Any] = {
        "run_id": config.run_id,
        "model": config.model,
        "timestamp": timestamp,
        # A run built from stub fixtures must never read as a measurement.
        "synthetic": any(r.get("synthetic") for r in subset_results),
        "subsets": subset_results,
    }
    if delta:
        report["delta"] = delta

    _append_history(report)

    if config.report_path:
        config.report_path.parent.mkdir(parents=True, exist_ok=True)
        config.report_path.write_text(
            json.dumps(report, indent=2, default=str),
            encoding="utf-8",
        )
        logger.info("Report written to %s", config.report_path)

    return report
