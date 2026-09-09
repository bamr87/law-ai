"""``lsat_question_review_sweep`` — judge the bank; rewrite what the judge objects to.

Spec 054 FR-11. Walks bank questions under a budget cap, asks
``LSATDraftJudge`` to attack each as it stands, and for every objection runs
``LSATQuestionEditor`` through the gates → judge → revise loop and a Fable
final review, filing the rewrite as a pending ``rewrite`` proposal.
Approving one replaces the item in place; rejecting it keeps the original.
Clean verdicts are cached, so a re-run only pays for what it has not seen.

    make lsat-question-review ARGS='--section LR --limit 10'
    make lsat-question-review ARGS='--dry-run'
"""

from __future__ import annotations

from typing import Any

from asgiref.sync import async_to_sync
from django.core.management.base import BaseCommand, CommandError

from law_ai.lsat.services.bank import load_bank
from law_ai.lsat.services.rewrite import (
    judged_question_ids,
    pending_rewrite_ids,
    review_question,
)

_SECTIONS = ("LR", "RC", "LG")


class Command(BaseCommand):
    help = "Judge bank questions; rewrite the ones the judge objects to, into the HITL queue."

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument("--section", default=None, help="LR | RC | LG")
        parser.add_argument(
            "--limit", type=int, default=5, help="budget cap (default 5)"
        )
        parser.add_argument("--max-rounds", type=int, default=3)
        parser.add_argument(
            "--no-final", action="store_true", help="skip the Fable final review"
        )
        parser.add_argument(
            "--refresh", action="store_true", help="re-judge cached items"
        )
        parser.add_argument("--dry-run", action="store_true")

    def _targets(self, section: str | None, *, refresh: bool) -> list[str]:
        bank = load_bank()
        skip = pending_rewrite_ids()
        if not refresh:
            skip |= judged_question_ids()
        return sorted(
            q.id
            for q in bank.values()
            if q.id not in skip and (section is None or q.section == section)
        )

    def handle(self, *args: Any, **opts: Any) -> None:
        section = opts["section"]
        if section is not None and section not in _SECTIONS:
            raise CommandError(f"--section must be one of {', '.join(_SECTIONS)}")
        limit = int(opts["limit"])
        if limit < 1:
            raise CommandError("--limit must be >= 1")
        targets = self._targets(section, refresh=bool(opts["refresh"]))
        self.stdout.write(
            self.style.MIGRATE_HEADING(
                f"{len(targets)} unjudged question(s); reviewing up to {limit} this run."
            )
        )
        if opts["dry_run"]:
            for qid in targets[:limit]:
                self.stdout.write(f"  would review: {qid}")
            return
        clean = filed = unaccepted = degraded = 0
        for qid in targets[:limit]:
            r = async_to_sync(review_question)(
                qid,
                max_rounds=int(opts["max_rounds"]),
                refresh=bool(opts["refresh"]),
                use_final_review=not opts["no_final"],
            )
            if r.degraded:
                degraded += 1
                self.stdout.write(self.style.WARNING(f"  {qid}: degraded — skipped"))
            elif r.clean:
                clean += 1
                self.stdout.write(f"  {qid}: {r.verdict} — clean")
            elif r.proposal_id:
                filed += 1
                if not r.accepted:
                    unaccepted += 1
                self.stdout.write(
                    self.style.WARNING(
                        f"  {qid}: {r.verdict} ({len(r.issues)} issue(s)) → rewrite "
                        f"{r.proposal_id} after {r.rounds} round(s)"
                        + (f", final {r.final_verdict}" if r.final_verdict else "")
                        + ("" if r.accepted else " — NOT accepted")
                    )
                )
            else:
                degraded += 1
                self.stdout.write(
                    self.style.WARNING(
                        f"  {qid}: {r.verdict} — editor produced nothing"
                    )
                )
        self.stdout.write(
            self.style.MIGRATE_HEADING(
                f"\nDone: {clean} clean, {filed} rewrites queued ({unaccepted} flagged), "
                f"{degraded} degraded/skipped."
            )
        )
