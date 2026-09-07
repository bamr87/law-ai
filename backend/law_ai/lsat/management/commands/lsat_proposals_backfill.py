"""``lsat_proposals_backfill`` — replay the JSONL proposal log into Postgres.

BL-20260527-05. The proposal store is an append-only JSONL log replayed on
every read; :class:`law_ai.lsat.models.LsatProposal` is its indexed mirror.
Rows recorded before the table existed have no mirror row, which is exactly
why ``LSAT_PROPOSALS_DB_READS`` defaults to off — reading a partial mirror
would silently hide older proposals from the HITL queue.

This command is the one-time catch-up: it replays the log and upserts every
proposal, after which the read path can be switched on.

    make manage CMD='lsat_proposals_backfill --dry-run'
    make manage CMD='lsat_proposals_backfill'
"""

from __future__ import annotations

from typing import Any

from django.core.management.base import BaseCommand

from law_ai.lsat.services import proposals as proposals_store


class Command(BaseCommand):
    help = (
        "Replay the JSONL proposal log into the LsatProposal table so the "
        "indexed read path can serve the whole queue."
    )

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="report how many proposals would be written, then exit",
        )

    def handle(self, *args: Any, **opts: Any) -> None:
        state = proposals_store._replay_log()
        if opts["dry_run"]:
            self.stdout.write(
                self.style.WARNING(
                    f"[dry-run] would mirror {len(state)} proposal(s) "
                    f"from {proposals_store._proposals_path()}"
                )
            )
            return

        written = proposals_store.mirror_all()
        self.stdout.write(
            self.style.SUCCESS(
                f"Mirrored {written} proposal(s) into LsatProposal. "
                "Set LSAT_PROPOSALS_DB_READS=true to serve reads from the "
                "table; the JSONL log stays the audit trail either way."
            )
        )
