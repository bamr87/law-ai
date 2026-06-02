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
            choices=["test_pillar", "corpus_growth", "digest", "lsat_content"],
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
            if kind == "lsat_content":
                return _run_lsat_content(context, budget=budget)
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
# Sub-runners (T-004, T-007)
# ---------------------------------------------------------------------------


def _run_test_pillar(context: dict[str, Any], *, budget: int | None) -> dict[str, Any]:
    """Invoke TestSynthesizer for the lowest-coverage modules (T-004).

    Reads coverage data via ``lawgraph.eval.coverage_audit``, then calls
    :class:`~lawgraph.agents_runtime.crews.test_synthesizer.TestSynthesizer`
    for each under-threshold module up to *budget*.
    """
    from lawgraph.agents_runtime.crews.test_synthesizer import (
        ProposedTestInput,
        TestSynthesizer,
    )
    from lawgraph.eval.coverage_audit import (
        COVERAGE_WARN_THRESHOLD,
        load_coverage_report,
    )

    records = load_coverage_report()
    below = [r for r in records if r.pct < COVERAGE_WARN_THRESHOLD]
    if not below:
        logger.info(
            "test_pillar: no modules below %.0f%% threshold", COVERAGE_WARN_THRESHOLD
        )
        return {"proposed_tests": 0, "budget": budget}

    limit = budget if budget is not None else len(below)
    synth = TestSynthesizer()
    proposed = 0

    for rec in below[:limit]:
        try:
            inp = ProposedTestInput(
                module_path=rec.module,
                missing_lines=rec.missing_lines[:20],
            )
            synth.run(inp)
            proposed += 1
        except Exception as exc:
            logger.warning(
                "test_pillar: TestSynthesizer failed for %s: %s", rec.module, exc
            )

    context["proposed_tests"] = proposed
    return {"proposed_tests": proposed, "budget": budget}


def _run_corpus_growth(
    context: dict[str, Any],
    *,
    source: str | None,
    budget: int | None,
) -> dict[str, Any]:
    """Invoke TopicFrontier workflow for corpus expansion (T-007).

    Runs the :class:`~lawgraph.agents_runtime.graphs.topic_frontier.TopicFrontier`
    async workflow and returns the dispatch summary.
    """
    import asyncio

    from lawgraph.agents_runtime.graphs.topic_frontier import TopicFrontier

    tf = TopicFrontier()
    output = asyncio.run(tf.run())

    context["dispatched_count"] = len(output.dispatched)
    return {
        "source": source,
        "docs_queued": len(output.dispatched),
        "budget": budget,
        "human_approval_required": output.human_approval_required,
    }


def _run_digest(context: dict[str, Any]) -> dict[str, Any]:
    """Invoke :func:`lawgraph.core.autonomy.compose_digest` (T-010)."""
    from lawgraph.core.autonomy import compose_digest

    digest_path = compose_digest()
    context["digest_path"] = str(digest_path)
    return {"digest_path": str(digest_path)}


def _run_lsat_content(
    context: dict[str, Any], *, budget: int | None
) -> dict[str, Any]:
    """Draft LSAT questions targeting the weakest measured `(section, concept)`.

    Spec 019 FR-10. Always persists drafts to the proposal queue with
    ``status="pending"`` — never auto-approves (constitution §5).
    """
    import asyncio

    from lawgraph.agents_runtime.crews.lsat_content_author import (
        GenerateQuestionsInput,
        LSATContentAuthor,
    )
    from lawgraph.lsat.services import proposals as proposals_store

    count = max(1, min(budget or 5, 10))
    gaps = proposals_store.gap_analysis(limit=1)
    if gaps:
        target_section = gaps[0]["section"]
        target_concepts = [gaps[0]["concept"]] if gaps[0]["concept"] != "(uncategorised)" else []
        target_difficulty = "med"
    else:
        target_section = "LR"
        target_concepts = []
        target_difficulty = "med"

    inp = GenerateQuestionsInput(
        section=target_section,
        difficulty=target_difficulty,
        count=count,
        concepts=target_concepts,
    )
    agent = LSATContentAuthor()
    output = asyncio.run(agent.run(inp.model_dump()))
    persisted = 0
    for draft in output.drafts:
        proposals_store.record_proposal(
            draft.model_dump(),
            agent_trace_id=output.trace_id or "",
            model=output.model,
            confidence=output.confidence,
            source_concept_ids=target_concepts,
        )
        persisted += 1

    summary = {
        "drafts_persisted": persisted,
        "section": target_section,
        "difficulty": target_difficulty,
        "target_concepts": target_concepts,
        "model": output.model,
        "degraded": output.degraded,
        "trace_id": output.trace_id,
    }
    context.update(summary)
    return summary
