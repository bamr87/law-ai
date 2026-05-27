"""``manage.py run_autonomy`` — trigger an autonomy cycle from the CLI.

Wraps :func:`lawgraph.core.autonomy.run_cycle` with a Django management
command so it can be called from:

* The Makefile (``make autonomy-run AUTONOMY_KIND=corpus_growth``).
* The nightly GitHub Actions workflow.
* Ad-hoc operator sessions.

Exit codes:
  0  — cycle completed (or was short-circuited because AUTONOMY_ENABLED=False).
  1  — policy violation (source not in allow-list, or HITL gate tripped).
  2  — unexpected runtime error (details in stderr).

All runs are logged through ``lawgraph.core.autonomy`` which emits paired
``autonomy_cycle.start`` / ``autonomy_cycle.end`` provenance events.
"""

from __future__ import annotations

import json
import logging
import sys
from typing import Any

from django.core.management.base import BaseCommand, CommandError

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Run one autonomy cycle (test_pillar, corpus_growth, or digest)."

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument(
            "--kind",
            default="test_pillar",
            choices=["test_pillar", "corpus_growth", "digest"],
            help="Kind of cycle to run (default: test_pillar).",
        )
        parser.add_argument(
            "--source",
            default=None,
            help=(
                "Source adapter name to dispatch (corpus_growth only). "
                "Must appear in AUTONOMY_ALLOWED_SOURCES."
            ),
        )
        parser.add_argument(
            "--budget",
            type=int,
            default=None,
            help="Max docs to ingest this cycle (overrides AUTONOMY_MAX_INGEST_PER_CYCLE).",
        )
        parser.add_argument(
            "--cycle-id",
            dest="cycle_id",
            default=None,
            help="Optional idempotency key (UUID4). Reuse to re-check a prior run.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            default=False,
            help="Print what would run without invoking the cycle.",
        )

    def handle(self, *args: object, **options: object) -> None:
        from lawgraph.core import autonomy

        kind: str = options["kind"]  # type: ignore[assignment]
        source: str | None = options["source"]  # type: ignore[assignment]
        budget: int | None = options["budget"]  # type: ignore[assignment]
        cycle_id: str | None = options["cycle_id"]  # type: ignore[assignment]
        dry_run: bool = options["dry_run"]  # type: ignore[assignment]

        # ------------------------------------------------------------------
        # Policy checks before touching autonomy.run_cycle
        # (skip in --dry-run: we only want to *show* what would run)
        # ------------------------------------------------------------------
        if not dry_run and source and not autonomy.is_source_allowed(source):
            autonomy.record_policy_violation(
                cycle_id=cycle_id or "pre-flight",
                reason="source_not_allowed",
                payload={"source": source, "kind": kind},
            )
            raise CommandError(
                f"Source {source!r} is not in AUTONOMY_ALLOWED_SOURCES. "
                "Add it to the setting to permit this dispatch.",
                returncode=1,
            )

        payload: dict[str, Any] = {"kind": kind}
        if source:
            payload["source"] = source
        if budget is not None:
            payload["budget"] = budget
        if cycle_id:
            payload["cycle_id"] = cycle_id

        if dry_run:
            self.stdout.write(self.style.WARNING("[dry-run] would run:"))
            self.stdout.write(json.dumps(payload, indent=2))
            enabled = autonomy.is_enabled()
            self.stdout.write(
                f"AUTONOMY_ENABLED={enabled}  "
                f"allowed_sources={list(autonomy.allowed_sources())}"
            )
            return

        # ------------------------------------------------------------------
        # Delegate to the audited entry point
        # ------------------------------------------------------------------
        def _runner(context: dict[str, Any]) -> dict[str, Any]:
            """Dispatch to the appropriate sub-runner for the requested kind."""
            if kind == "test_pillar":
                return _run_test_pillar(context, budget=budget)
            if kind == "corpus_growth":
                return _run_corpus_growth(context, source=source, budget=budget)
            if kind == "digest":
                return _run_digest(context)
            raise ValueError(f"Unknown kind: {kind!r}")  # unreachable via argparse

        try:
            result = autonomy.run_cycle(kind, _runner, payload=payload)
        except Exception as exc:
            self.stderr.write(self.style.ERROR(f"autonomy cycle failed: {exc}"))
            sys.exit(2)

        status = result.get("status", "unknown")
        cycle_id_out = result.get("cycle_id", "")
        if status == "disabled":
            self.stdout.write(
                self.style.WARNING(
                    f"Autonomy disabled (kill-switch). cycle_id={cycle_id_out}"
                )
            )
        elif status == "ok":
            sub = result.get("result", {})
            self.stdout.write(
                self.style.SUCCESS(
                    f"Cycle complete. kind={kind} cycle_id={cycle_id_out} "
                    f"result={json.dumps(sub, default=str)}"
                )
            )
        else:
            self.stderr.write(
                self.style.ERROR(
                    f"Cycle ended with status={status}. "
                    f"error={result.get('error', '')} cycle_id={cycle_id_out}"
                )
            )
            sys.exit(2)


# ---------------------------------------------------------------------------
# Sub-runners (thin stubs — real logic will be added in T-004 and T-007)
# ---------------------------------------------------------------------------


def _run_test_pillar(context: dict[str, Any], *, budget: int | None) -> dict[str, Any]:
    """Placeholder for T-004 TestSynthesizer integration.

    # STUB — BL-20260511-01: Wire up TestSynthesizer crew here.
    # See specs/018-autonomous-framework/tasks.md T-004.
    """
    logger.warning(
        "test_pillar runner is a stub (BL-20260511-01) — returning 0 proposed tests"
    )
    context["note"] = "test_pillar runner not yet implemented (T-004)"
    return {"proposed_tests": 0, "budget": budget}


def _run_corpus_growth(
    context: dict[str, Any],
    *,
    source: str | None,
    budget: int | None,
) -> dict[str, Any]:
    """Placeholder for T-007 TopicFrontier integration.

    # STUB — BL-20260511-02: Wire up TopicFrontier workflow here.
    # See specs/018-autonomous-framework/tasks.md T-007.
    """
    logger.warning(
        "corpus_growth runner is a stub (BL-20260511-02) — returning 0 docs queued"
    )
    context["note"] = "corpus_growth runner not yet implemented (T-007)"
    return {"source": source, "docs_queued": 0, "budget": budget}


def _run_digest(context: dict[str, Any]) -> dict[str, Any]:
    """Invoke :func:`lawgraph.core.autonomy.compose_digest` (T-010)."""
    from lawgraph.core.autonomy import compose_digest

    digest_path = compose_digest()
    context["digest_path"] = str(digest_path)
    return {"digest_path": str(digest_path)}
