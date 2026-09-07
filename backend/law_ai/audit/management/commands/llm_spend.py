"""``manage.py llm_spend`` — what the model chain cost, by agent and by tier.

The read side of the token/cost accounting the router writes onto every
``llm_call`` audit event (BL-20260811-21 wrote it, BL-20260905-69 noticed
nothing read it back). ``make llm-spend`` is the operator-facing wrapper.

``--json`` emits the same numbers as a machine-readable document, so this can
be piped somewhere without re-deriving the query.
"""

from __future__ import annotations

import json
from typing import Any

from django.core.management.base import BaseCommand, CommandParser

from law_ai.audit.spend import SpendBucket, spend_report

_HEADER = f"{'':<34}{'CALLS':>7} {'IN':>10} {'OUT':>10} {'USD':>12} {'UNPRICED':>9}"


def _row(bucket: SpendBucket) -> str:
    return (
        f"{bucket.key[:33]:<34}{bucket.calls:>7} "
        f"{bucket.input_tokens:>10} {bucket.output_tokens:>10} "
        f"{bucket.cost_usd:>12.6f} {bucket.unpriced_calls:>9}"
    )


class Command(BaseCommand):
    help = "Roll up llm_call audit events into per-agent and per-tier spend."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument(
            "--days",
            type=int,
            default=30,
            help="Trailing window in days (default 30). 0 means all time.",
        )
        parser.add_argument(
            "--json",
            action="store_true",
            dest="as_json",
            help="Emit the rollup as JSON instead of a table.",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        days_opt = int(options.get("days") or 0)
        days = days_opt if days_opt > 0 else None
        report = spend_report(days=days)

        if options.get("as_json"):
            self.stdout.write(json.dumps(report.as_dict(), indent=2, sort_keys=True))
            return

        window = f"last {days} day(s)" if days else "all time"
        self.stdout.write(f"LLM spend — {window}")
        if report.total.calls == 0:
            self.stdout.write("No llm_call events in this window.")
            return

        for title, buckets in (
            ("By agent", report.by_agent),
            ("By provider/model", report.by_tier),
        ):
            self.stdout.write("")
            self.stdout.write(title)
            self.stdout.write(_HEADER)
            self.stdout.write("-" * len(_HEADER))
            for bucket in buckets:
                self.stdout.write(_row(bucket))

        self.stdout.write("")
        self.stdout.write(_row(report.total))
        if report.total.unpriced_calls:
            # Unpriced is not free: say so, or the total reads as the bill.
            self.stdout.write(
                f"{report.total.unpriced_calls} successful call(s) had no price "
                "table entry — the USD total is a floor, not the bill."
            )
        if report.total.failed_calls:
            self.stdout.write(
                f"{report.total.failed_calls} call(s) failed through the whole chain."
            )
