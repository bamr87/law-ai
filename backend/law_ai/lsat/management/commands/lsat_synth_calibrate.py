"""``lsat_synth_calibrate`` — is the difficulty band telling the truth?

BL-20260903-14. Two measurements, neither of which changes a schema on its own.

Default (graded fold-back): join ``lsat_grade`` events to the schema that
produced each item and report per-schema accuracy, the band that accuracy puts
the schema in, and where that disagrees with the declared band. Schemas below
``MIN_ATTEMPTS`` are listed as "thin" rather than banded.

``--structural``: sweep the registry offline and report the difficulty proxy —
per-schema mean score, the bands it emits, and the percentile cuts the current
score distribution implies. Run it after adding or changing schemas; if the
suggested cuts have moved far from ``difficulty.SCORE_CUTS``, update the
constant deliberately and expect existing items to re-band.

    make lsat-synth-calibrate
    make lsat-synth-calibrate ARGS='--structural'
    make lsat-synth-calibrate ARGS='--structural --seeds 2'   # cuts, gate depth
"""

from __future__ import annotations

import json
import statistics
from pathlib import Path
from typing import Any

from django.core.management.base import BaseCommand

from law_ai.lsat.synth.calibrate import (
    ACCURACY_CUTS,
    MIN_ATTEMPTS,
    schema_accuracy,
)
from law_ai.lsat.synth.difficulty import SCORE_CUTS
from law_ai.lsat.synth.generate import generate
from law_ai.lsat.synth.lexicon import load_domains
from law_ai.lsat.synth.schemas import all_schemas

#: Where the report lands, relative to the process cwd (``/app`` in Docker).
_REPORT = "var/lsat_synth/calibration.json"

#: Seeds per (schema, domain) pair in the structural sweep. Five for a stable
#: per-schema mean; the shipped ``SCORE_CUTS`` are pinned at ``--seeds 2``,
#: which is the depth the difficulty gate re-derives them at, so quote the
#: suggestion from a ``--seeds 2`` run when updating the constant.
_SEEDS = 5


class Command(BaseCommand):
    help = "Measure synthesis difficulty: graded accuracy, or the structural proxy."

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument(
            "--structural",
            action="store_true",
            help="Sweep the registry and report the offline difficulty proxy "
            "instead of graded accuracy.",
        )
        parser.add_argument(
            "--window",
            type=int,
            default=20_000,
            help="Audit events to scan for the graded report.",
        )
        parser.add_argument("--seeds", type=int, default=_SEEDS)
        parser.add_argument("--out", help=f"Report path. Default {_REPORT}.")

    # -- graded -------------------------------------------------------------

    def _graded(self, opts: dict[str, Any]) -> dict[str, Any]:
        rows = schema_accuracy(window=opts["window"])
        self.stdout.write(self.style.MIGRATE_HEADING("\nMeasured difficulty"))
        if not rows:
            self.stdout.write(
                "  no graded attempts on synthesized items yet — every schema "
                "keeps its structural band"
            )
        for row in rows:
            measured = row.measured or "thin"
            flag = ""
            if row.agrees is False:
                flag = self.style.WARNING("  ← disagrees with declared")
            self.stdout.write(
                f"  {row.schema_id:38s} n={row.attempts:5d} "
                f"acc={row.accuracy:5.2f} declared={row.declared:5s} "
                f"measured={measured:5s}{flag}"
            )
        confident = [r for r in rows if r.confident]
        disagreeing = [r for r in rows if r.agrees is False]
        self.stdout.write(
            f"\n  {len(confident)} of {len(rows)} schema(s) clear "
            f"{MIN_ATTEMPTS} attempts; {len(disagreeing)} disagree with the "
            "declared band"
        )
        return {
            "kind": "graded",
            "min_attempts": MIN_ATTEMPTS,
            "accuracy_cuts": [[c, b] for c, b in ACCURACY_CUTS],
            "schemas": [r.dump() for r in rows],
            "disagreements": [r.schema_id for r in disagreeing],
        }

    # -- structural ---------------------------------------------------------

    def _sweep_scores(self, seeds: int) -> tuple[list[float], list[dict[str, Any]]]:
        domains = list(load_domains().values())
        scores: list[float] = []
        per_schema: list[dict[str, Any]] = []
        for schema in all_schemas():
            meta = schema.meta
            mine: list[float] = []
            bands: dict[str, int] = {}
            for domain in domains:
                if not domain.supports(meta.capability):
                    continue
                for seed in range(seeds):
                    try:
                        item = generate(meta.id, domain.id, seed=seed)
                    except Exception:
                        continue
                    complexity = item.provenance.complexity
                    if complexity is None:
                        continue
                    mine.append(float(complexity["score"]))
                    band = str(complexity["band"])
                    bands[band] = bands.get(band, 0) + 1
            scores.extend(mine)
            per_schema.append(
                {
                    "schema_id": meta.id,
                    "declared": meta.difficulty,
                    "proof_kind": meta.proof_kind,
                    "items": len(mine),
                    "mean_score": round(statistics.mean(mine), 3) if mine else None,
                    "bands": bands,
                }
            )
        return scores, per_schema

    def _structural(self, opts: dict[str, Any]) -> dict[str, Any]:
        scores, per_schema = self._sweep_scores(max(1, int(opts["seeds"])))
        self.stdout.write(self.style.MIGRATE_HEADING("\nStructural difficulty proxy"))
        for row in per_schema:
            if row["mean_score"] is None:
                self.stdout.write(
                    f"  {row['schema_id']:38s} declared={row['declared']:5s} "
                    "structural — no model space, declared band stands"
                )
                continue
            emitted = ", ".join(f"{b}={n}" for b, n in sorted(row["bands"].items()))
            self.stdout.write(
                f"  {row['schema_id']:38s} declared={row['declared']:5s} "
                f"mean={row['mean_score']:6.2f}  {emitted}"
            )
        suggested: list[float] = []
        if scores:
            ordered = sorted(scores)
            suggested = [round(ordered[int(len(ordered) * p)], 2) for p in (0.40, 0.75)]
            self.stdout.write(
                f"\n  {len(scores)} proved item(s); score range "
                f"{ordered[0]:.2f} to {ordered[-1]:.2f}"
            )
            self.stdout.write(
                f"  cuts in use {list(SCORE_CUTS)}; this sweep suggests {suggested}"
            )
        return {
            "kind": "structural",
            "seeds": opts["seeds"],
            "cuts_in_use": list(SCORE_CUTS),
            "cuts_suggested": suggested,
            "items": len(scores),
            "schemas": per_schema,
        }

    def handle(self, *args: Any, **opts: Any) -> None:
        report = self._structural(opts) if opts["structural"] else self._graded(opts)
        out = Path(opts["out"] or _REPORT)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        self.stdout.write(self.style.SUCCESS(f"  wrote {out}"))
