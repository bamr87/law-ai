"""``lsat_guide_backfill`` — draft solve guides for guide-less bank questions.

Spec 041 follow-up BL-20260830-11: iterates questions that have no solve
guide (and no pending guide proposal), runs :class:`LSATSolveGuideAuthor`
for each, and records the drafts in the HITL proposal queue as
``proposal_kind="guide"``. Nothing this command produces serves to learners
until a reviewer approves it on the Authoring tab (or via the API).

Budget-capped by ``--limit`` so an unattended run can never fan out across
the whole bank at once. Degraded (offline-fallback) drafts are skipped by
default — they carry no real content and would only clutter the queue;
pass ``--include-degraded`` to record them anyway for audit visibility.

    make manage CMD='lsat_guide_backfill --section LR --limit 5'
    make manage CMD='lsat_guide_backfill --dry-run'
"""

from __future__ import annotations

from typing import Any

from asgiref.sync import async_to_sync
from django.core.management.base import (
    BaseCommand,
    CommandError,
)

from law_ai.lsat.services import proposals as proposals_store
from law_ai.lsat.services.bank import load_bank
from law_ai.lsat.services.guides import load_guides

_SECTIONS = ("LR", "RC", "LG")


class Command(BaseCommand):
    help = (
        "Draft solve guides for guide-less questions via LSATSolveGuideAuthor; "
        "drafts land in the HITL proposal queue, never in guides.json directly."
    )

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument(
            "--section", default=None, help="restrict to one section: LR | RC | LG"
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=5,
            help="max questions to draft this run (budget cap, default 5)",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="list the questions that would be drafted, then exit",
        )
        parser.add_argument(
            "--include-degraded",
            action="store_true",
            help="record offline-fallback drafts instead of skipping them",
        )

    def _targets(self, section: str | None) -> list[str]:
        """Guide-less question ids with no pending guide proposal, id-sorted."""
        bank = load_bank()
        guides = load_guides()
        pending_guide_qids = {
            (row.get("draft") or {}).get("question_id")
            for row in proposals_store.list_proposals("pending", limit=1000)
            if row.get("proposal_kind") == "guide"
        }
        return sorted(
            q.id
            for q in bank.values()
            if q.id not in guides
            and q.id not in pending_guide_qids
            and (section is None or q.section == section)
        )

    def handle(self, *args: Any, **opts: Any) -> None:
        section = opts["section"]
        if section is not None and section not in _SECTIONS:
            raise CommandError(f"--section must be one of {', '.join(_SECTIONS)}")
        limit = int(opts["limit"])
        if limit < 1:
            raise CommandError("--limit must be >= 1")

        targets = self._targets(section)
        self.stdout.write(
            self.style.MIGRATE_HEADING(
                f"{len(targets)} guide-less question(s)"
                + (f" in {section}" if section else "")
                + f"; drafting up to {limit} this run."
            )
        )
        if opts["dry_run"]:
            for qid in targets[:limit]:
                self.stdout.write(f"  would draft: {qid}")
            remaining = max(0, len(targets) - limit)
            if remaining:
                self.stdout.write(f"  (+{remaining} more beyond the limit)")
            return

        from law_ai.agents_runtime.crews.lsat_guide_reviewer import review_guide
        from law_ai.agents_runtime.crews.lsat_solve_guide_author import (
            LSATSolveGuideAuthor,
        )

        agent = LSATSolveGuideAuthor()
        drafted = skipped_degraded = failed = 0
        for qid in targets[:limit]:
            try:
                output = async_to_sync(agent.run)({"question_id": qid})
            except Exception as exc:
                failed += 1
                self.stdout.write(self.style.ERROR(f"  {qid}: failed ({exc})"))
                continue
            if output.degraded and not opts["include_degraded"]:
                skipped_degraded += 1
                self.stdout.write(
                    self.style.WARNING(f"  {qid}: degraded (no provider) — skipped")
                )
                continue
            # BL-20260830-15: judge tier verdict rides with the pending row.
            review = async_to_sync(review_guide)(output.guide)
            pid = proposals_store.record_proposal(
                output.guide.model_dump(by_alias=True),
                agent_trace_id=output.trace_id or "",
                model=output.model,
                confidence=output.confidence,
                proposal_kind="guide",
                meta={"review": review} if review is not None else None,
            )
            drafted += 1
            verdict = (review or {}).get("verdict", "unreviewed")
            self.stdout.write(
                self.style.SUCCESS(
                    f"  {qid}: drafted → {pid} "
                    f"(model={output.model}, conf={output.confidence}, "
                    f"review={verdict})"
                )
            )

        self.stdout.write(
            self.style.MIGRATE_HEADING(
                f"\nDone: {drafted} queued for review, "
                f"{skipped_degraded} degraded skipped, {failed} failed. "
                "Review pending drafts on the Authoring tab."
            )
        )
