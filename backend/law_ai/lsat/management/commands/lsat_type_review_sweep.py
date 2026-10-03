"""``lsat_type_review_sweep`` — blind-read question types, queue the disagreements.

Spec 054. The stem-cue classifier stamped every bank item's type (spec 053);
this asks ``LSATTypeReviewer`` to read each item without the stamp and files
every disagreement as a ``typecheck`` proposal. Approving one restamps the
item with the model's read (``promote_typecheck``); rejecting it keeps the
stamp. Same shape as ``lsat_cross_check_sweep``: a budget cap, a dry run,
cached reads skipped unless ``--refresh``, degraded reads never filed.

    make lsat-type-review ARGS='--section LR --limit 10'
"""

from __future__ import annotations

from typing import Any

from asgiref.sync import async_to_sync
from django.core.management.base import BaseCommand, CommandError

from law_ai.agents_runtime.crews.lsat_type_reviewer import (
    CACHE_KIND,
    TypeReview,
    review_type,
)
from law_ai.lsat.services import llm_cache
from law_ai.lsat.services import proposals as proposals_store
from law_ai.lsat.services.bank import Question, load_bank

_SECTIONS = ("LR", "RC", "LG")
TYPECHECK_KIND = "typecheck"


def reviewed_question_ids() -> set[str]:
    return {
        str(row["question_id"])
        for row in llm_cache.entries(CACHE_KIND)
        if isinstance(row.get("question_id"), str)
    }


def pending_typecheck_ids() -> set[str]:
    out: set[str] = set()
    for row in proposals_store.list_proposals("pending", limit=1000):
        if row.get("proposal_kind") != TYPECHECK_KIND:
            continue
        qid = (row.get("draft") or {}).get("question_id")
        if isinstance(qid, str):
            out.add(qid)
    return out


def file_disagreement(q: Question, review: TypeReview) -> str:
    """Record one type disagreement as a pending ``typecheck`` proposal."""
    return proposals_store.record_proposal(
        {
            "question_id": q.id,
            "section": q.section,
            "difficulty": q.difficulty,
            "stem": q.stem,
            "stamped_archetype": review.stamped_archetype,
            "cue_archetype": review.cue_archetype,
            "model_archetype": review.model_archetype,
            "rationale": review.rationale,
            "confidence": review.confidence,
            "model": review.model,
        },
        agent_trace_id="",
        model=review.model,
        confidence=review.confidence,
        proposal_kind=TYPECHECK_KIND,
    )


class Command(BaseCommand):
    help = "Blind-read bank question types; disagreements with the stamp go to the HITL queue."

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument("--section", default=None, help="LR | RC | LG")
        parser.add_argument(
            "--limit", type=int, default=5, help="budget cap (default 5)"
        )
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument(
            "--refresh", action="store_true", help="re-read cached items"
        )

    def _targets(self, section: str | None, *, refresh: bool) -> list[str]:
        bank = load_bank()
        skip = pending_typecheck_ids()
        if not refresh:
            skip |= reviewed_question_ids()
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
                f"{len(targets)} unreviewed question(s); reading up to {limit} this run."
            )
        )
        if opts["dry_run"]:
            for qid in targets[:limit]:
                self.stdout.write(f"  would read: {qid}")
            return
        bank = load_bank()
        agreed = filed = degraded = 0
        for qid in targets[:limit]:
            review = async_to_sync(review_type)(
                bank[qid], refresh=bool(opts["refresh"])
            )
            if not review.used_llm:
                degraded += 1
                self.stdout.write(self.style.WARNING(f"  {qid}: degraded — skipped"))
                continue
            if review.agrees:
                agreed += 1
                self.stdout.write(f"  {qid}: agrees ({review.stamped_archetype})")
                continue
            pid = file_disagreement(bank[qid], review)
            filed += 1
            self.stdout.write(
                self.style.WARNING(
                    f"  {qid}: DISAGREES — stamp {review.stamped_archetype}, "
                    f"model {review.model_archetype} → {pid}"
                )
            )
        self.stdout.write(
            self.style.MIGRATE_HEADING(
                f"\nDone: {agreed} agreed, {filed} queued, {degraded} degraded skipped."
            )
        )
