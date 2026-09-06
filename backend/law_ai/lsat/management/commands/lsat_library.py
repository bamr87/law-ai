"""``lsat_library`` — audit, review and promote the LSAT knowledge library.

Spec 048 FR-17. Three subcommands, all Docker-first via ``make``:

``audit``
    The deterministic health report (FR-14). No model call — it runs with no
    provider configured, because it is the number behind the claim that the
    library is being maintained.

``review``
    Runs :class:`LSATLibrarian` over one or more articles and files every
    result as a **pending proposal**. Writes nothing under ``data/library/``
    (spec 048 AC-10). With no explicit target it picks its own from the audit
    — :func:`pick_librarian_targets`: unreviewed and stale articles first,
    then thin ones, then articles nothing links to, then a capped tail of
    gap-driven expansions, then a routine sweep.

``promote``
    The only path that mutates library content, and it takes an explicit
    proposal id. The draft is re-parsed and the whole library re-loaded before
    the write is kept.

    make lsat-library-audit
    make lsat-library-review ARGS='--limit 3'
    make manage CMD='lsat_library promote --proposal prop-abc123 --reviewer me'
"""

from __future__ import annotations

import json
from typing import Any

from asgiref.sync import async_to_sync
from django.core.management.base import BaseCommand, CommandError

from law_ai.lsat.services import proposals as proposals_store
from law_ai.lsat.services.library import (
    LibrarianRequest,
    library_audit,
    load_library,
    merge_expansion,
    pick_librarian_targets,
)

_ACTIONS = ("audit", "review", "promote")


class Command(BaseCommand):
    help = (
        "Audit the LSAT knowledge library, run the HITL-gated librarian review "
        "loop over it, or promote an approved draft (spec 048)."
    )

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument("action", choices=_ACTIONS)
        parser.add_argument(
            "--article",
            action="append",
            default=[],
            help="Article id to review. Repeatable. Default: the stalest articles.",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=3,
            help="Maximum articles to review in one run (default: 3).",
        )
        parser.add_argument(
            "--proposal",
            help="Proposal id to promote (required for the promote action).",
        )
        parser.add_argument(
            "--reviewer",
            default="anonymous",
            help="Who approved the promotion; recorded in the audit trail.",
        )
        parser.add_argument(
            "--include-degraded",
            action="store_true",
            help="File offline-fallback results too (they are always rejected).",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be reviewed without invoking the agent.",
        )
        parser.add_argument(
            "--json",
            action="store_true",
            help="Emit the audit report as JSON rather than a summary.",
        )

    # -- audit --------------------------------------------------------------

    def _audit(self, opts: dict[str, Any]) -> None:
        report = library_audit()
        if opts["json"]:
            self.stdout.write(json.dumps(report, indent=2))
            return

        counts, words = report["counts"], report["words"]
        coverage, freshness, graph = (
            report["coverage"],
            report["freshness"],
            report["graph"],
        )
        self.stdout.write(
            self.style.MIGRATE_HEADING(
                f"\nLSAT knowledge library — {counts['articles']} articles, "
                f"{counts['tracks']} tracks, {words['total']:,} words"
            )
        )
        self.stdout.write(
            f"  by kind    : {counts['by_kind']}\n"
            f"  by section : {counts['by_section']}\n"
            f"  by status  : {counts['by_status']}\n"
            f"  words      : mean {words['mean']}, "
            f"min {words['min']}, max {words['max']}"
        )

        def _report(label: str, rows: list[Any]) -> None:
            if rows:
                self.stdout.write(
                    self.style.WARNING(f"  {label}: {len(rows)} — {rows[:8]}")
                )
            else:
                self.stdout.write(self.style.SUCCESS(f"  {label}: none"))

        _report("thin articles", words["thin_articles"])
        _report("untaught concepts", coverage["concepts_untaught"])
        _report("uncovered archetypes", coverage["archetypes_uncovered"])
        _report("stale articles", freshness["stale_articles"])
        _report("orphan articles", graph["orphan_articles"])
        _report("articles in no track", graph["articles_in_no_track"])
        self.stdout.write(
            f"\n  concept coverage : {coverage['concepts_taught']}"
            f"/{coverage['concepts_total']}\n"
            f"  archetype coverage: {coverage['archetypes_covered']}"
            f"/{coverage['archetypes_total']}\n"
        )

    # -- review -------------------------------------------------------------

    def _targets(self, opts: dict[str, Any]) -> list[LibrarianRequest]:
        articles = load_library()
        limit = max(1, opts["limit"])
        if opts["article"]:
            unknown = [a for a in opts["article"] if a not in articles]
            if unknown:
                raise CommandError(f"unknown article(s): {', '.join(unknown)}")
            return [
                LibrarianRequest(article_id=a, reason="named on the command line")
                for a in opts["article"]
            ][:limit]
        # No explicit target: the picker reads the audit and ranks it
        # (BL-20260903-08). It always returns something on a healthy corpus,
        # so the scheduled cycle stays useful rather than idling.
        return pick_librarian_targets(library_audit(), limit=limit)

    def _file(self, request: LibrarianRequest, output: Any) -> str:
        """Persist one librarian result as a pending proposal; return its id."""
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
        else:
            draft["findings"] = [f.model_dump() for f in output.findings]
            kind = "library_finding"
        return proposals_store.record_proposal(
            draft,
            agent_trace_id=output.trace_id or "",
            model=output.model,
            confidence=output.confidence,
            proposal_kind=kind,
        )

    def _review(self, opts: dict[str, Any]) -> None:
        targets = self._targets(opts)
        self.stdout.write(
            self.style.MIGRATE_HEADING(
                f"Reviewing {len(targets)} article(s): "
                + ", ".join(t.article_id for t in targets)
            )
        )
        if opts["dry_run"]:
            for request in targets:
                self.stdout.write(
                    f"  would {request.action}: {request.article_id} "
                    f"({request.reason})"
                )
            return

        from law_ai.agents_runtime.crews.lsat_librarian import LSATLibrarian

        agent = LSATLibrarian()
        filed = skipped = failed = 0
        for request in targets:
            article_id = request.article_id
            try:
                output = async_to_sync(agent.run)(request.to_input())
            except Exception as exc:
                failed += 1
                self.stdout.write(self.style.ERROR(f"  {article_id}: failed ({exc})"))
                continue
            if output.degraded and not opts["include_degraded"]:
                skipped += 1
                self.stdout.write(
                    self.style.WARNING(
                        f"  {article_id}: degraded (no provider) — skipped"
                    )
                )
                continue
            proposal_id = self._file(request, output)
            filed += 1
            self.stdout.write(
                self.style.SUCCESS(
                    f"  {article_id}: {request.action} — {len(output.findings)} "
                    f"finding(s) → {proposal_id} (model={output.model})"
                )
            )

        self.stdout.write(
            self.style.MIGRATE_HEADING(
                f"\nDone: {filed} filed for review, {skipped} degraded skipped, "
                f"{failed} failed. Nothing under data/library/ was modified."
            )
        )

    # -- promote ------------------------------------------------------------

    def _promote(self, opts: dict[str, Any]) -> None:
        proposal_id = opts["proposal"]
        if not proposal_id:
            raise CommandError("promote requires --proposal <id>")
        try:
            row = proposals_store.promote_library_article(
                proposal_id, reviewer=opts["reviewer"]
            )
        except (KeyError, ValueError) as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(
            self.style.SUCCESS(
                f"promoted {proposal_id} → status {row.get('status')} "
                f"(reviewer {opts['reviewer']})"
            )
        )

    def handle(self, *args: Any, **opts: Any) -> None:
        action = opts["action"]
        if action == "audit":
            self._audit(opts)
        elif action == "review":
            self._review(opts)
        else:
            self._promote(opts)
