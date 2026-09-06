"""``lsat_cross_check_sweep`` — blind-solve the bank, queue the disagreements.

BL-20260831-21. The spec 045 FR-14 cross-check is a single-question primitive
behind ``POST /api/lsat/questions/<id>/cross-check``; nothing ever ran it
across the bank, so an un-reviewed mis-keyed question stayed invisible until
somebody happened to open it. This command mirrors ``lsat_guide_backfill``:
it walks unchecked questions section by section under a budget cap, solves
each one blind through the provider chain, and files every *disagreement* as
a ``crosscheck`` proposal so it lands in the same HITL queue reviewers already
watch — the validation report alone was read-only and easy to miss.

Approving such a row means "the key is right after all" and promotes nothing
into the bank (:func:`law_ai.lsat.services.proposals.promote_crosscheck`);
rejecting it means the key is wrong and the question needs a human edit.

Every run bills provider calls, so ``--limit`` defaults deliberately small and
questions already carrying a cached verdict are skipped unless ``--refresh``.
Degraded verdicts (no provider reachable) are never filed: an outage is not a
disagreement.

The same sweep also runs on a cadence (BL-20260905-58): the
``lsat_cross_check`` autonomy kind reuses the helpers below, and the weekly
``autonomy-lsat-cross-check`` beat (Tuesdays 05:00 UTC, budget 5) dispatches it
under the ``AUTONOMY_ENABLED`` kill-switch, so coverage grows without anyone
remembering to type this.

    make manage CMD='lsat_cross_check_sweep --section LR --limit 5'
    make manage CMD='lsat_cross_check_sweep --dry-run'
    make lsat-cross-check-sweep ARGS='--section RC --limit 3'
"""

from __future__ import annotations

from typing import Any

from asgiref.sync import async_to_sync
from django.core.management.base import (
    BaseCommand,
    CommandError,
)

from law_ai.lsat.services import llm_cache
from law_ai.lsat.services import proposals as proposals_store
from law_ai.lsat.services.bank import Question, load_bank
from law_ai.lsat.services.crosscheck import CrossCheckResult, cross_check

_SECTIONS = ("LR", "RC", "LG")

#: Proposal kind for a filed disagreement; approving one changes no content.
CROSSCHECK_KIND = "crosscheck"


def checked_question_ids() -> set[str]:
    """Question ids that already carry a stored cross-check verdict."""
    return {
        str(row["question_id"])
        for row in llm_cache.entries("crosscheck")
        if isinstance(row.get("question_id"), str)
    }


def pending_crosscheck_ids() -> set[str]:
    """Question ids with a cross-check row already waiting in the HITL queue."""
    out: set[str] = set()
    for row in proposals_store.list_proposals("pending", limit=1000):
        if row.get("proposal_kind") != CROSSCHECK_KIND:
            continue
        qid = (row.get("draft") or {}).get("question_id")
        if isinstance(qid, str):
            out.add(qid)
    return out


def file_disagreement(q: Question, result: CrossCheckResult) -> str:
    """Record one disagreement as a pending ``crosscheck`` proposal."""
    return proposals_store.record_proposal(
        {
            "question_id": q.id,
            "section": q.section,
            "difficulty": q.difficulty,
            "stem": q.stem,
            "bank_choice": result.bank_choice,
            "model_choice": result.model_choice,
            "rationale": result.rationale,
            "model": result.model,
        },
        agent_trace_id="",
        model=result.model,
        confidence=0.0,
        proposal_kind=CROSSCHECK_KIND,
    )


class Command(BaseCommand):
    help = (
        "Blind-solve unchecked bank questions through the provider chain; "
        "disagreements land in the HITL proposal queue for re-verification."
    )

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument(
            "--section", default=None, help="restrict to one section: LR | RC | LG"
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=5,
            help="max questions to solve this run (budget cap, default 5)",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="list the questions that would be solved, then exit",
        )
        parser.add_argument(
            "--refresh",
            action="store_true",
            help="re-solve questions that already have a stored verdict",
        )

    def _targets(self, section: str | None, *, refresh: bool) -> list[str]:
        """Unchecked question ids with no pending cross-check row, id-sorted."""
        bank = load_bank()
        skip = pending_crosscheck_ids()
        if not refresh:
            skip |= checked_question_ids()
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
                f"{len(targets)} unchecked question(s)"
                + (f" in {section}" if section else "")
                + f"; solving up to {limit} this run."
            )
        )
        if opts["dry_run"]:
            for qid in targets[:limit]:
                self.stdout.write(f"  would solve: {qid}")
            remaining = max(0, len(targets) - limit)
            if remaining:
                self.stdout.write(f"  (+{remaining} more beyond the limit)")
            return

        bank = load_bank()
        agreed = filed = degraded = failed = 0
        for qid in targets[:limit]:
            try:
                result = async_to_sync(cross_check)(
                    bank[qid], refresh=bool(opts["refresh"])
                )
            except Exception as exc:
                failed += 1
                self.stdout.write(self.style.ERROR(f"  {qid}: failed ({exc})"))
                continue
            if not result.used_llm:
                degraded += 1
                self.stdout.write(
                    self.style.WARNING(f"  {qid}: degraded (no provider) — skipped")
                )
                continue
            if result.agree:
                agreed += 1
                self.stdout.write(f"  {qid}: agrees ({result.bank_choice})")
                continue
            pid = file_disagreement(bank[qid], result)
            filed += 1
            self.stdout.write(
                self.style.WARNING(
                    f"  {qid}: DISAGREES — bank {result.bank_choice}, "
                    f"model {result.model_choice} → {pid}"
                )
            )

        self.stdout.write(
            self.style.MIGRATE_HEADING(
                f"\nDone: {agreed} agreed, {filed} queued for review, "
                f"{degraded} degraded skipped, {failed} failed. "
                "Review disagreements on the Authoring tab."
            )
        )
