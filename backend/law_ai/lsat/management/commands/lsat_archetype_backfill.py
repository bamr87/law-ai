"""Stamp every bank item with the archetype it instantiates (spec 053 FR-2).

BL-20260905-54 left the 208 existing items unstamped because a stamp copied
from the concept proxy would have frozen a guess. The stem-cue classifier in
:mod:`law_ai.lsat.services.playbooks` decides differently: it reads the
question sentence the way a learner is taught to, so a stamp it writes is the
same call the diagnosis exercise will mark a learner on. The bank stays the
source of truth — this command edits the JSON in place and the diff is
reviewed in the pull request that carries it (the HITL gate for bank content).

Usage::

    make manage CMD='lsat_archetype_backfill --check'   # report, change nothing
    make manage CMD='lsat_archetype_backfill'           # write missing stamps
    make manage CMD='lsat_archetype_backfill --force'   # re-derive every stamp
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from django.core.management.base import BaseCommand, CommandError

from law_ai.lsat.services import bank as bank_mod
from law_ai.lsat.services.bank import Question
from law_ai.lsat.services.playbooks import Classification, classify

BANK_FILES = ("lr_bank.json", "rc_bank.json", "lg_bank.json")


def plan_stamps(
    *, force: bool = False, data_dir: Path | None = None
) -> tuple[dict[str, Classification], list[str]]:
    """Decide the stamp for every item; return ``{id: classification}`` + unresolved ids.

    ``force`` re-derives stamped items from their stems too, so a stamp that
    disagrees with the classifier is surfaced rather than trusted.
    """
    root = data_dir or bank_mod.DATA_DIR
    decided: dict[str, Classification] = {}
    unresolved: list[str] = []
    for fname in BANK_FILES:
        path = root / fname
        if not path.is_file():
            continue
        for entry in json.loads(path.read_text(encoding="utf-8")).get("items", []):
            q = Question.model_validate(entry)
            if q.archetype is not None and not force:
                decided[q.id] = Classification(
                    question_id=q.id, archetype_id=q.archetype, method="stamped"
                )
                continue
            probe = q.model_copy(update={"archetype": None}) if force else q
            result = classify(probe)
            if result.archetype_id is None:
                unresolved.append(q.id)
            decided[q.id] = result
    return decided, unresolved


def write_stamps(
    decided: dict[str, Classification], *, data_dir: Path | None = None
) -> int:
    """Write the decided stamps into the bank files; return how many changed."""
    root = data_dir or bank_mod.DATA_DIR
    changed = 0
    for fname in BANK_FILES:
        path = root / fname
        if not path.is_file():
            continue
        raw: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
        touched = False
        for entry in raw.get("items", []):
            result = decided.get(entry["id"])
            if result is None or result.archetype_id is None:
                continue
            if entry.get("archetype") != result.archetype_id:
                entry["archetype"] = result.archetype_id
                touched = True
                changed += 1
        if touched:
            path.write_text(
                json.dumps(raw, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
            )
    return changed


class Command(BaseCommand):
    help = "Stamp bank items with the archetype their stem identifies (spec 053)."

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument(
            "--check",
            action="store_true",
            help="Report what would change and exit non-zero if anything would.",
        )
        parser.add_argument(
            "--force",
            action="store_true",
            help="Re-derive every stamp from the stem, not only missing ones.",
        )

    def handle(self, *args: Any, **opts: Any) -> None:
        decided, unresolved = plan_stamps(force=bool(opts["force"]))
        by_method: dict[str, int] = {}
        for result in decided.values():
            by_method[result.method] = by_method.get(result.method, 0) + 1
        self.stdout.write(
            "classified {n} items: {m}".format(
                n=len(decided),
                m=", ".join(f"{k}={v}" for k, v in sorted(by_method.items())),
            )
        )
        if unresolved:
            self.stdout.write(self.style.WARNING(f"unresolved: {unresolved}"))
        if opts["check"]:
            pending = [r.question_id for r in decided.values() if r.method != "stamped"]
            if pending or unresolved:
                raise CommandError(
                    f"{len(pending)} item(s) need a stamp, {len(unresolved)} unresolved"
                )
            self.stdout.write(self.style.SUCCESS("every item is stamped"))
            return
        changed = write_stamps(decided)
        bank_mod.reset_caches()
        self.stdout.write(self.style.SUCCESS(f"stamped {changed} item(s)"))
        if unresolved:
            raise CommandError(f"{len(unresolved)} item(s) could not be classified")
