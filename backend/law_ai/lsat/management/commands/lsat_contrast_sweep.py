"""``lsat_contrast_sweep`` — draft contrast variations into the HITL queue (spec 054).

For each root question without a variation of a given type, run
``LSATContrastAuthor`` through the gates → ``LSATDraftJudge`` → revise loop
(:mod:`law_ai.lsat.factory.revise`) and file the result as a pending
``question`` proposal carrying its lineage and its revision history. Targets
come from the root's playbook ``confused_with`` list first — the pairs
learners actually swap — then the rest of the section.

Every round bills a provider call, so ``--limit`` defaults small; degraded
runs (no provider) file nothing. Nothing here writes to the bank.

    make lsat-contrast-sweep ARGS='--source lr-002 --target lr-strengthen'
    make lsat-contrast-sweep ARGS='--limit 3 --dry-run'
"""

from __future__ import annotations

from typing import Any

from asgiref.sync import async_to_sync
from django.core.management.base import BaseCommand, CommandError

from law_ai.lsat.services import proposals as proposals_store
from law_ai.lsat.services.bank import load_bank
from law_ai.lsat.services.contrast import draft_variation, pivot_targets
from law_ai.lsat.services.playbooks import load_playbooks


def pending_pairs() -> set[tuple[str, str]]:
    """``(source_id, target_archetype)`` pairs already waiting in the queue."""
    out: set[tuple[str, str]] = set()
    for row in proposals_store.list_proposals("pending", limit=1000):
        meta = row.get("meta") or {}
        src = meta.get("variation_of")
        target = (meta.get("factory") or {}).get("archetype_id")
        if isinstance(src, str) and isinstance(target, str):
            out.add((src, target))
    return out


def plan_pairs(
    *, source: str | None, target: str | None, section: str | None, limit: int
) -> list[tuple[str, str]]:
    """The ``(source, target)`` pairs this run would draft, in order."""
    bank = load_bank()
    skip = pending_pairs()
    if source is not None:
        if source not in bank:
            raise CommandError(f"unknown question {source!r}")
        roots = [bank[source]]
    else:
        roots = sorted(
            (
                q
                for q in bank.values()
                if q.variation_of is None
                and q.archetype is not None
                and (section is None or q.section == section)
            ),
            key=lambda q: q.id,
        )
    pairs: list[tuple[str, str]] = []
    for q in roots:
        targets = [target] if target is not None else pivot_targets(q)[:1]
        for t in targets:
            if (q.id, t) not in skip and t != q.archetype:
                pairs.append((q.id, t))
            if len(pairs) >= limit:
                return pairs
    return pairs


class Command(BaseCommand):
    help = (
        "Draft contrast variations (same stimulus, different question type) "
        "through the judge/revise loop into the HITL proposal queue."
    )

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument("--source", default=None, help="one root question id")
        parser.add_argument(
            "--target", default=None, help="archetype id to re-ask the source as"
        )
        parser.add_argument("--section", default=None, help="LR only for now")
        parser.add_argument(
            "--limit", type=int, default=3, help="max drafts (default 3)"
        )
        parser.add_argument(
            "--max-rounds", type=int, default=3, help="author/judge rounds per draft"
        )
        parser.add_argument(
            "--no-judge", action="store_true", help="skip LSATDraftJudge"
        )
        parser.add_argument("--dry-run", action="store_true", help="plan only")

    def handle(self, *args: Any, **opts: Any) -> None:
        target = opts["target"]
        if target is not None and target not in load_playbooks():
            raise CommandError(f"unknown archetype {target!r}")
        section = opts["section"]
        if section is not None and section != "LR":
            raise CommandError("contrast variations are LR-only in this release")
        if int(opts["limit"]) < 1:
            raise CommandError("--limit must be >= 1")
        pairs = plan_pairs(
            source=opts["source"],
            target=target,
            section=section,
            limit=int(opts["limit"]),
        )
        self.stdout.write(
            self.style.MIGRATE_HEADING(f"{len(pairs)} variation(s) to draft this run.")
        )
        if opts["dry_run"]:
            for src, tgt in pairs:
                self.stdout.write(f"  would draft: {src} → {tgt}")
            return
        filed = degraded = unaccepted = 0
        for src, tgt in pairs:
            result = async_to_sync(draft_variation)(
                src,
                tgt,
                max_rounds=int(opts["max_rounds"]),
                use_judge=not opts["no_judge"],
            )
            if result.proposal_id is None:
                degraded += 1
                self.stdout.write(
                    self.style.WARNING(
                        f"  {src} → {tgt}: degraded (no provider) — nothing filed"
                    )
                )
                continue
            filed += 1
            if not result.accepted:
                unaccepted += 1
            verdict = "accepted" if result.accepted else "NOT accepted after the cap"
            self.stdout.write(
                f"  {src} → {tgt}: {result.proposal_id} ({result.rounds} round(s), {verdict})"
            )
        self.stdout.write(
            self.style.MIGRATE_HEADING(
                f"\nDone: {filed} filed ({unaccepted} flagged unaccepted), "
                f"{degraded} degraded. Review on the Authoring tab."
            )
        )
