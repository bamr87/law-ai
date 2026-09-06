"""``manage.py run_autonomy`` — trigger an autonomy cycle from the CLI.

Wraps :func:`law_ai.core.autonomy.run_cycle` with a Django management
command so it can be called from:

* The Makefile (``make autonomy-run AUTONOMY_KIND=corpus_growth``).
* The nightly GitHub Actions workflow.
* Ad-hoc operator sessions.

Exit codes:
  0  — cycle completed (or was short-circuited because AUTONOMY_ENABLED=False).
  1  — policy violation (source not in allow-list, or HITL gate tripped).
  2  — unexpected runtime error (details in stderr).

All runs are logged through ``law_ai.core.autonomy`` which emits paired
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
            choices=[
                "test_pillar",
                "corpus_growth",
                "digest",
                "lsat_content",
                "lsat_factory",
                "lsat_library",
                "commit_approved",
            ],
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
            help=(
                "Idempotency key (UUID4). Reusing a key that already completed "
                "replays that run's recorded result instead of running the "
                "cycle again."
            ),
        )
        parser.add_argument(
            "--window-to-now",
            dest="window_to_now",
            action="store_true",
            default=False,
            help=(
                "digest only: end the digest window at *now* instead of the "
                "previous UTC midnight, so a digest composed inside a CI run "
                "includes that run's own events (BL-20260511-19)."
            ),
        )
        parser.add_argument(
            "--stream-id",
            dest="stream_id",
            default=None,
            help=(
                "WebSocket correlation id (BL-20260811-15). Subscribe to "
                "/ws/agents/<stream-id> before starting the cycle to watch its "
                "start/end events live; charset ^[A-Za-z0-9._-]{1,64}$."
            ),
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            default=False,
            help="Print what would run without invoking the cycle.",
        )

    def handle(self, *args: object, **options: object) -> None:
        from law_ai.core import autonomy

        kind: str = options["kind"]  # type: ignore[assignment]
        source: str | None = options["source"]  # type: ignore[assignment]
        budget: int | None = options["budget"]  # type: ignore[assignment]
        cycle_id: str | None = options["cycle_id"]  # type: ignore[assignment]
        stream_id: str | None = options["stream_id"]  # type: ignore[assignment]
        window_to_now: bool = options["window_to_now"]  # type: ignore[assignment]
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

        payload: dict[str, Any] = {
            "kind": kind,
            **{
                key: value
                for key, value in (
                    ("source", source),
                    ("budget", budget),
                    ("cycle_id", cycle_id),
                    ("stream_id", stream_id),
                )
                if value is not None and value != ""
            },
        }

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
        # PLR0911 is suppressed below: one `if` per autonomy kind is the clearest
        # form this dispatch can take; the pillar count, not the function, grew.
        def _runner(context: dict[str, Any]) -> dict[str, Any]:  # noqa: PLR0911
            """Dispatch to the appropriate sub-runner for the requested kind."""
            if kind == "test_pillar":
                return _run_test_pillar(context, budget=budget)
            if kind == "corpus_growth":
                return _run_corpus_growth(context, source=source, budget=budget)
            if kind == "digest":
                return _run_digest(context, window_to_now=window_to_now)
            if kind == "lsat_content":
                return _run_lsat_content(context, budget=budget)
            if kind == "lsat_factory":
                return _run_lsat_factory(context, budget=budget)
            if kind == "lsat_library":
                return _run_lsat_library(context, budget=budget)
            if kind == "commit_approved":
                return _run_commit_approved(context, budget=budget)
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
            # BL-20260511-29: say plainly that nothing ran, so an operator who
            # reuses a --cycle-id is never misled into thinking it did.
            verb = (
                "Cycle replayed (already ran)."
                if result.get("replayed")
                else ("Cycle complete.")
            )
            self.stdout.write(
                self.style.SUCCESS(
                    f"{verb} kind={kind} cycle_id={cycle_id_out} "
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

    Reads coverage data via ``law_ai.eval.coverage_audit``, then calls
    :class:`~law_ai.agents_runtime.crews.test_synthesizer.TestSynthesizer`
    for each under-threshold module up to *budget*.
    """
    from law_ai.agents_runtime.crews.test_synthesizer import (
        ProposedTestInput,
        TestSynthesizer,
    )
    from law_ai.eval.coverage_audit import (
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


async def _topic_frontier_cycle(factory: Any) -> Any:
    """Run one TopicFrontier cycle under a checkpointer when one is available.

    ``build_checkpointer`` returns a bare saver for ``memory`` and an async
    context manager for ``postgres``/``redis``; both shapes are handled here so
    the graph gets durable node-level checkpoints (BL-20260511-31). Any failure
    to obtain a saver is logged and the cycle runs unpersisted.
    """
    from contextlib import AbstractAsyncContextManager

    from law_ai.agents_runtime.graphs.runtime import build_checkpointer

    try:
        maybe_saver = build_checkpointer()
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("topic_frontier: no checkpointer (%s); running unpersisted", exc)
        return await factory().run()

    if isinstance(maybe_saver, AbstractAsyncContextManager):
        async with maybe_saver as saver:
            return await factory(checkpointer=saver).run()
    return await factory(checkpointer=maybe_saver).run()


def _run_corpus_growth(
    context: dict[str, Any],
    *,
    source: str | None,
    budget: int | None,
) -> dict[str, Any]:
    """Invoke TopicFrontier workflow for corpus expansion (T-007).

    Runs the :class:`~law_ai.agents_runtime.graphs.topic_frontier.TopicFrontier`
    async workflow and returns the dispatch summary.

    BL-20260511-31: the cycle is checkpointed when a saver can be built, so a
    crashed dispatch resumes instead of re-scanning the graph from scratch. A
    checkpointer that will not open degrades to an unpersisted run rather than
    failing the cycle.
    """
    import asyncio

    from law_ai.agents_runtime.graphs.topic_frontier import TopicFrontier

    output = asyncio.run(_topic_frontier_cycle(TopicFrontier))

    context["dispatched_count"] = len(output.dispatched)
    return {
        "source": source,
        "docs_queued": len(output.dispatched),
        "budget": budget,
        "human_approval_required": output.human_approval_required,
    }


def _run_digest(
    context: dict[str, Any], *, window_to_now: bool = False
) -> dict[str, Any]:
    """Compose the digest, then push it to the configured channels (T-010).

    BL-20260511-05: the ``digest-<date>.md`` file used to be the only
    surface. ``deliver_digest`` fans it out to Slack and/or email when those
    are configured and is a no-op otherwise, so the file remains the fallback
    surface for an operator who has configured nothing.

    BL-20260511-19: ``window_to_now`` ends the digest window at *now* rather
    than the previous UTC midnight. A CI run that composes a digest of its own
    work needs that — the default window would otherwise exclude every event
    the same run just produced.
    """
    from datetime import UTC, datetime

    from law_ai.core.autonomy import compose_digest, deliver_digest

    digest_path = compose_digest(
        window_end=datetime.now(UTC) if window_to_now else None
    )
    context["digest_path"] = str(digest_path)
    delivery = deliver_digest(digest_path)
    context["digest_delivered"] = delivery["delivered"]
    return {
        "digest_path": str(digest_path),
        "delivery": delivery,
    }


def _run_lsat_content(context: dict[str, Any], *, budget: int | None) -> dict[str, Any]:
    """Draft LSAT questions targeting the weakest measured `(section, concept)`.

    Spec 019 FR-10. Always persists drafts to the proposal queue with
    ``status="pending"`` — never auto-approves (constitution §5).
    """
    import asyncio

    from law_ai.agents_runtime.crews.lsat_content_author import (
        GenerateQuestionsInput,
        LSATContentAuthor,
    )
    from law_ai.agents_runtime.crews.lsat_content_reviewer import review_drafts
    from law_ai.lsat.services import proposals as proposals_store

    count = max(1, min(budget or 5, 10))
    gaps = proposals_store.gap_analysis(limit=1)
    if gaps:
        target_section = gaps[0]["section"]
        target_concepts = (
            [gaps[0]["concept"]] if gaps[0]["concept"] != "(uncategorised)" else []
        )
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
    # BL-20260606-02: a skewed answer-key batch reaches the HITL queue carrying
    # the flag, so the reviewer sees the skew the prompt failed to prevent.
    base_meta: dict[str, Any] = (
        {"balance_flag": output.balance_flag} if output.balance_flag else {}
    )
    # BL-20260527-04: blind pre-review so a human reads the borderline drafts
    # first. Advisory only — a low score never blocks the proposal.
    reviews = asyncio.run(review_drafts([d.model_dump() for d in output.drafts]))
    flagged = 0
    for draft, review in zip(output.drafts, reviews, strict=True):
        meta: dict[str, Any] = dict(base_meta)
        if review is not None:
            meta["review"] = review
            flagged += int(bool(review.get("flagged")))
        proposals_store.record_proposal(
            draft.model_dump(),
            agent_trace_id=output.trace_id or "",
            model=output.model,
            confidence=output.confidence,
            source_concept_ids=target_concepts,
            meta=meta or None,
        )
        persisted += 1

    summary = {
        "drafts_persisted": persisted,
        "drafts_flagged": flagged,
        "section": target_section,
        "difficulty": target_difficulty,
        "target_concepts": target_concepts,
        "model": output.model,
        "degraded": output.degraded,
        "balance_flag": output.balance_flag,
        "trace_id": output.trace_id,
    }
    context.update(summary)
    return summary


def _run_lsat_factory(context: dict[str, Any], *, budget: int | None) -> dict[str, Any]:
    """Run one coverage-driven factory batch on the local model (spec 024 FR-8).

    BL-20260702-04. plan → compile → run(ollama) → intake, pinned to the local
    provider so a nightly beat can never bill a hosted tier, and capped by the
    cycle budget so a small box is not asked for a hundred items at 03:00. Like
    every other LSAT pillar this only *drafts*: survivors land as ``pending``
    proposals for a human (constitution §5).
    """
    import asyncio

    from law_ai.lsat.factory import FactoryConfig, compile_plan, execute_manifest
    from law_ai.lsat.factory.executors import ExecutorUnavailable, OllamaExecutor

    max_jobs = max(1, min(budget or 4, 12))
    config = FactoryConfig.from_settings().model_copy(update={"max_jobs": max_jobs})
    manifest, manifest_path = compile_plan(config)
    if not manifest.jobs:
        summary = {
            "manifest_id": manifest.manifest_id,
            "jobs": 0,
            "accepted": 0,
            "rejected": 0,
            "errors": 0,
            "note": "coverage is at target; nothing to generate",
        }
        context.update(summary)
        return summary

    try:
        executor = OllamaExecutor(config)
    except ExecutorUnavailable as exc:  # pragma: no cover - defensive
        summary = {
            "manifest_id": manifest.manifest_id,
            "jobs": 0,
            "accepted": 0,
            "rejected": 0,
            "errors": 1,
            "note": f"executor unavailable: {exc}",
        }
        context.update(summary)
        return summary

    results = asyncio.run(execute_manifest(manifest, executor, config))
    summary = {
        "manifest_id": manifest.manifest_id,
        "manifest_path": str(manifest_path),
        "jobs": len(results),
        "accepted": sum(len(r.accepted) for r in results),
        "rejected": sum(len(r.rejected) for r in results),
        "errors": sum(1 for r in results if r.error),
        "executor": executor.name,
        "judge_enabled": config.judge_enabled,
    }
    context.update(summary)
    return summary


def _run_commit_approved(
    context: dict[str, Any], *, budget: int | None
) -> dict[str, Any]:
    """Sweep human-approved quarantine rows into the graph (BL-20260811-02).

    Approvals used to need a manual ``manage.py review_queue commit`` (or a
    hand-run Celery task) before reaching Neo4j, so a reviewer's decision
    could sit unapplied indefinitely. Routing the sweep through
    ``autonomy.run_cycle`` gives it the ``AUTONOMY_ENABLED`` kill-switch
    (constitution §12 I3) and the cycle audit event for free.

    Not an autonomy *decision*: every row here was already approved by a
    person, so the HITL gate (§5) is upstream of this runner — it only
    applies decisions humans already made, capped by ``budget``.
    """
    from law_ai.ingestionapp.services.approval import (
        DEFAULT_SWEEP_LIMIT,
        commit_approved_reviews,
    )

    limit = max(1, min(budget or DEFAULT_SWEEP_LIMIT, 200))
    results = commit_approved_reviews(limit)
    committed = sum(1 for r in results if r.get("committed"))
    failed = sum(1 for r in results if r.get("error"))
    return {
        "kind": "commit_approved",
        "cycle_id": context.get("cycle_id", ""),
        "processed": len(results),
        "committed": committed,
        "failed": failed,
        "limit": limit,
    }


def _run_lsat_library(context: dict[str, Any], *, budget: int | None) -> dict[str, Any]:
    """Work the knowledge library's own audit findings (spec 048 FR-17).

    The cycle picks its own targets: ``pick_librarian_targets`` ranks the
    deterministic audit into reviews (unreviewed, thin, unreachable) and a
    capped tail of gap-driven expansions, so no human target list is needed
    (BL-20260903-08).

    Proposals only. A review files a ``library_finding``, an expansion files
    the merged article as a ``library_article``; both land ``pending``,
    nothing under ``data/library/`` is touched, and promotion stays a
    deliberate human act (spec 048 AC-10, constitution §5).
    """
    import asyncio

    from law_ai.agents_runtime.crews.lsat_librarian import LSATLibrarian
    from law_ai.lsat.services import proposals as proposals_store
    from law_ai.lsat.services.library import (
        library_audit,
        merge_expansion,
        pick_librarian_targets,
    )

    count = max(1, min(budget or 3, 10))
    report = library_audit()
    requests = pick_librarian_targets(report, limit=count)

    agent = LSATLibrarian()
    reviews = 0
    expansions = 0
    findings = 0
    degraded = False
    for request in requests:
        output = asyncio.run(agent.run(request.to_input()))
        degraded = degraded or output.degraded
        if output.degraded:
            # An offline fallback carries no review; filing it would only add
            # noise a reviewer has to reject.
            continue
        draft: dict[str, Any] = {
            "article_id": request.article_id,
            "summary": output.summary,
            "reason": request.reason,
        }
        if request.action == "expand" and output.proposed_markdown:
            draft["gap"] = request.gap
            draft["markdown"] = merge_expansion(
                request.article_id, output.proposed_markdown
            )
            kind = "library_article"
            expansions += 1
        else:
            draft["findings"] = [f.model_dump() for f in output.findings]
            kind = "library_finding"
            findings += len(output.findings)
            reviews += 1
        proposals_store.record_proposal(
            draft,
            agent_trace_id=output.trace_id or "",
            model=output.model,
            confidence=output.confidence,
            proposal_kind=kind,
        )

    summary = {
        "articles_reviewed": len(requests),
        "reviews_filed": reviews,
        "expansions_filed": expansions,
        "findings": findings,
        "targets": [r.article_id for r in requests],
        "picked": [
            {"action": r.action, "article_id": r.article_id, "reason": r.reason}
            for r in requests
        ],
        "degraded": degraded,
    }
    context.update(summary)
    return summary
