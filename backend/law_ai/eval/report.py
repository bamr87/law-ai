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
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from law_ai.eval.legalbench import LegalBenchConfig

logger = logging.getLogger("law_ai.eval.report")

_CACHE_ROOT = Path("backend/var/legalbench")


def _load_baseline() -> dict[str, float] | None:
    """Return ``{subset: accuracy}`` from ``baseline.json`` or ``None`` if absent."""
    baseline_path = _CACHE_ROOT / "baseline.json"
    if not baseline_path.exists():
        return None
    try:
        raw = json.loads(baseline_path.read_text(encoding="utf-8"))
        # Accept both a flat dict and our full report format.
        if "subsets" in raw:
            return {row["subset"]: row["accuracy"] for row in raw["subsets"]}
        return {k: float(v) for k, v in raw.items()}
    except Exception as exc:
        logger.warning("Could not load baseline.json: %s", exc)
        return None


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
        "subsets": subset_results,
    }
    if delta:
        report["delta"] = delta

    if config.report_path:
        config.report_path.parent.mkdir(parents=True, exist_ok=True)
        config.report_path.write_text(
            json.dumps(report, indent=2, default=str),
            encoding="utf-8",
        )
        logger.info("Report written to %s", config.report_path)

    return report
