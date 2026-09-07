"""``migrate_neo4j`` — apply the Cypher migration set with bookkeeping.

BL-20260509-02. Replaces the bare ``cypher-shell -f`` loop in
``backend/scripts/init-db.sh``: every applied file is recorded as a
``(:_Migration {id, applied_at, checksum})`` node, so a migration that is not
idempotent by construction still runs exactly once.

    make migrate                      # runs this after the Django migrations
    make manage CMD='migrate_neo4j --dry-run'
    make manage CMD='migrate_neo4j --list'
"""

from __future__ import annotations

from typing import Any

from asgiref.sync import async_to_sync
from django.core.management.base import BaseCommand

from law_ai.core.neo4j import migrator
from law_ai.core.neo4j.driver import get_neo4j_driver


async def _list_state() -> tuple[list[str], dict[str, str | None]]:
    driver = get_neo4j_driver()
    return [migrator.migration_id(p) for p in migrator.discover()], (
        await migrator.applied_migrations(driver)
    )


async def _apply(dry_run: bool) -> migrator.MigrationPlan:
    return await migrator.apply_migrations(get_neo4j_driver(), dry_run=dry_run)


class Command(BaseCommand):
    help = (
        "Apply backend/law_ai/core/neo4j/migrations/*.cypher, recording each "
        "one as a (:_Migration) node so it is applied exactly once."
    )

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="report what would be applied without running any Cypher",
        )
        parser.add_argument(
            "--list",
            action="store_true",
            dest="list_only",
            help="show every migration and whether it has been applied",
        )

    def _handle_list(self) -> None:
        known, applied = async_to_sync(_list_state)()
        self.stdout.write(self.style.MIGRATE_HEADING("Neo4j migrations"))
        for mid in known:
            mark = "applied" if mid in applied else "pending"
            self.stdout.write(f"  [{mark}] {mid}")
        orphans = sorted(set(applied) - set(known))
        for mid in orphans:
            self.stdout.write(
                self.style.WARNING(f"  [recorded] {mid} (no file on disk)")
            )

    def handle(self, *args: Any, **opts: Any) -> None:
        if opts["list_only"]:
            self._handle_list()
            return

        dry_run = bool(opts["dry_run"])
        plan = async_to_sync(_apply)(dry_run)

        for mid in plan.applied:
            verb = "would apply" if dry_run else "applied"
            self.stdout.write(self.style.SUCCESS(f"  {verb}: {mid}"))
        for mid in plan.checksum_mismatches:
            self.stdout.write(
                self.style.WARNING(
                    f"  {mid}: file changed since it was applied — not re-run. "
                    "Add a new migration instead of editing an applied one."
                )
            )
        for mid, statement in plan.unsupported:
            head = " ".join(statement.split())[:70]
            self.stdout.write(
                self.style.WARNING(
                    f"  {mid}: this Neo4j edition rejected `{head}…` "
                    "(Enterprise-only). The migration is left pending and will "
                    "re-apply in full against an Enterprise database."
                )
            )
        self.stdout.write(
            self.style.MIGRATE_HEADING(
                f"{len(plan.applied)} applied, {len(plan.skipped)} already recorded, "
                f"{len(plan.deferred)} deferred, "
                f"{plan.statements_run} statement(s) run."
            )
        )
