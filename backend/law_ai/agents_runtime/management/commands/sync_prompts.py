"""``manage.py sync_prompts`` — mirror local prompt files into Phoenix.

Spec 036: pushes every registry prompt (runtime ``*.v<N>.md``,
``legal_workflow/*.md``, and the repo-root AO-SDLC chain) into the
self-hosted Arize Phoenix prompt store. Idempotent — re-running with
unchanged files creates no new Phoenix versions.
"""

from __future__ import annotations

from typing import Any

from django.core.management.base import BaseCommand, CommandError, CommandParser


class Command(BaseCommand):
    help = (
        "Sync the prompt registry into Arize Phoenix prompt management "
        "(one-way: repo files are the source of truth)."
    )

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report what would change without writing to Phoenix.",
        )
        parser.add_argument(
            "--base-url",
            default=None,
            help=(
                "Phoenix REST base URL (default: PHOENIX_BASE_URL setting, "
                "else derived from PHOENIX_COLLECTOR_ENDPOINT)."
            ),
        )

    def handle(self, *args: object, **options: Any) -> None:
        from law_ai.agents_runtime.prompts.phoenix import sync_prompts

        dry_run = bool(options["dry_run"])
        try:
            report = sync_prompts(
                base_url=options["base_url"],
                dry_run=dry_run,
            )
        except RuntimeError as exc:
            raise CommandError(str(exc)) from exc

        for result in report.results:
            label = f"{result.name}{f' {result.tag}' if result.tag else ''}"
            line = f"{result.outcome:<8} {label}"
            if result.detail:
                line += f" ({result.detail})"
            if result.outcome == "error":
                self.stderr.write(self.style.ERROR(line))
            else:
                self.stdout.write(line)

        summary = (
            f"{'DRY RUN: ' if dry_run else ''}"
            f"{report.count('created')} created, "
            f"{report.count('updated')} updated, "
            f"{report.count('skipped')} skipped, "
            f"{report.count('error')} error(s) → {report.base_url}"
        )
        if not report.ok:
            raise CommandError(summary)
        self.stdout.write(self.style.SUCCESS(summary))
