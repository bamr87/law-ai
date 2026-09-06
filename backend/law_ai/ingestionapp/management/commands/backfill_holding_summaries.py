"""``backfill_holding_summaries`` — fill ``:Case.holding_summary`` (BL-20260905-99).

``IngestionScout.extract`` now derives a deterministic opinion excerpt and
``MERGE_CASE_CYPHER`` persists it, but every ``:Case`` ingested before that
change still has the property empty — so GraphRAG renders "(no holding summary
stored)" in each of their passages, and the ``case_fulltext`` index has nothing
but the title to match on for them.

``:Case`` does not store opinion text, so unlike ``resolve_statute_citations``
this backfill cannot work offline: the excerpt has to come from the opinion
body, which means re-fetching it from the source. That is what ``--refetch``
does, through the same ``CourtListenerClient`` the original ingest used and the
same :func:`derive_holding_summary` rule, so a backfilled excerpt is
byte-identical to what a re-ingest would write. A title-only summary was the
other option on the table and is deliberately **not** offered: it would put a
copy of ``title`` into the field GraphRAG presents as the holding, which reads
as substance the graph does not have.

Safety posture mirrors ``resolve_statute_citations``:

* **Read-only by default.** Nothing is written unless ``--commit``.
* **Write-once.** ``SET_HOLDING_SUMMARY_CYPHER`` only fills an empty property,
  so a re-run cannot clobber a summary a later ingest or model pass wrote.
* **Batched** via a keyset cursor on ``Case.id``.
* Every batch is logged through ``core.provenance`` (constitution §4).

    make manage CMD='backfill_holding_summaries'                    # audit only
    make manage CMD='backfill_holding_summaries --refetch'          # dry run
    make manage CMD='backfill_holding_summaries --refetch --commit --limit 200'
"""

from __future__ import annotations

import time
from typing import Any

from asgiref.sync import async_to_sync
from django.core.management.base import BaseCommand, CommandError
from neo4j import AsyncSession

from law_ai.core.neo4j.driver import get_neo4j_driver
from law_ai.core.neo4j.queries import (
    list_cases_missing_holding_summary,
    set_holding_summary,
)
from law_ai.core.provenance import provenance
from law_ai.ingestionapp.services.scout import derive_holding_summary

#: Sources whose documents can be re-fetched by ``:Case.id``. Statute and
#: ordinance corpora do not produce ``:Case`` nodes, and a case ingested from
#: an adapter with no per-document endpoint cannot be recovered this way.
REFETCHABLE_SOURCES = ("courtlistener",)

#: Printed on every run: what the command cannot do, stated out loud (§13).
REFETCH_CAVEAT = (
    "Offline limit: :Case nodes store no opinion text, so an excerpt can only "
    "come from a re-fetch. Without --refetch this run only reports the gap. "
    f"Only cases from {', '.join(REFETCHABLE_SOURCES)} can be re-fetched by id; "
    "anything else has to be re-ingested through its own adapter."
)


class HoldingBackfillStats:
    """Mutable counters for one backfill run."""

    def __init__(self) -> None:
        self.scanned = 0
        self.refetched = 0
        self.derived = 0
        self.written = 0
        self.unfetchable = 0
        self.failed = 0

    def as_dict(self) -> dict[str, int]:
        return {
            "scanned": self.scanned,
            "refetched": self.refetched,
            "derived": self.derived,
            "written": self.written,
            "unfetchable": self.unfetchable,
            "failed": self.failed,
        }


def _opinion_text(opinion: dict[str, Any]) -> tuple[str, bool]:
    """Pick the body to excerpt, mirroring ``IngestionScout.extract``."""
    text = opinion.get("plain_text") or ""
    if text.strip():
        return str(text), False
    html = opinion.get("html_with_citations") or opinion.get("html") or ""
    return str(html), True


async def _fill_one(
    session: AsyncSession,
    row: dict[str, Any],
    *,
    client: Any,
    commit: bool,
    stats: HoldingBackfillStats,
) -> str | None:
    """Re-fetch one case's opinion and (optionally) write its excerpt."""
    case_id = row["case_id"]
    if (row.get("source") or "") not in REFETCHABLE_SOURCES:
        stats.unfetchable += 1
        return f"  {case_id}: source={row.get('source')!r} is not re-fetchable"

    try:
        opinion = await client.fetch_opinion(case_id)
    except Exception as exc:
        stats.failed += 1
        return f"  {case_id}: fetch failed ({type(exc).__name__}: {exc})"
    stats.refetched += 1

    text, is_html = _opinion_text(opinion)
    summary = derive_holding_summary(text, is_html=is_html)
    if not summary:
        return f"  {case_id}: re-fetched but no excerpt could be derived"
    stats.derived += 1
    if not commit:
        return f"  {case_id}: would set {summary[:60]!r}…"
    if await set_holding_summary(session, case_id, summary=summary, kind="excerpt"):
        stats.written += 1
        return f"  {case_id}: excerpt written"
    return f"  {case_id}: already filled by another writer"  # pragma: no cover


async def run_backfill(
    *, commit: bool, refetch: bool, batch_size: int, limit: int | None, client: Any
) -> tuple[HoldingBackfillStats, list[str]]:
    """Walk every summary-less case, batch by batch."""
    stats = HoldingBackfillStats()
    report: list[str] = []
    driver = get_neo4j_driver()
    after = ""

    async with driver.session() as session:
        while True:
            take = (
                batch_size if limit is None else min(batch_size, limit - stats.scanned)
            )
            if take <= 0:
                break
            started = time.perf_counter()
            batch = await list_cases_missing_holding_summary(
                session, after=after, limit=take
            )
            if not batch:
                break
            stats.scanned += len(batch)
            for row in batch:
                if not refetch:
                    report.append(
                        f"  {row['case_id']}: no holding_summary "
                        f"(source={row.get('source')!r})"
                    )
                    continue
                line = await _fill_one(
                    session, row, client=client, commit=commit, stats=stats
                )
                if line:
                    report.append(line)
            after = batch[-1]["case_id"]
            provenance.log_graph_query(
                cypher="backfill_holding_summaries.batch",
                params={
                    "after": after,
                    "limit": take,
                    "commit": commit,
                    "refetch": refetch,
                    "cases": len(batch),
                },
                result_count=stats.written,
                latency_ms=(time.perf_counter() - started) * 1000.0,
            )
    return stats, report


class Command(BaseCommand):
    help = (
        "Backfill :Case.holding_summary on nodes ingested before the excerpt "
        "existed. Reports the gap by default; --refetch re-reads the opinion "
        "from its source, and only --commit writes."
    )

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument(
            "--commit",
            action="store_true",
            help="actually write the excerpts (default: report only)",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="explicit no-write mode (the default; the opposite of --commit)",
        )
        parser.add_argument(
            "--refetch",
            action="store_true",
            help="re-fetch each opinion from its source to derive the excerpt",
        )
        parser.add_argument(
            "--batch-size",
            type=int,
            default=100,
            help="cases read per Neo4j round-trip (default 100)",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=None,
            help="max cases to process this run (default: all)",
        )
        parser.add_argument(
            "--verbose-cases",
            action="store_true",
            help="print one line per case, not just the totals",
        )

    def handle(self, *args: Any, **opts: Any) -> None:
        if opts["commit"] and opts["dry_run"]:
            raise CommandError("--commit and --dry-run are mutually exclusive")
        batch_size = int(opts["batch_size"])
        if batch_size < 1:
            raise CommandError("--batch-size must be >= 1")
        limit = opts["limit"]
        if limit is not None and int(limit) < 1:
            raise CommandError("--limit must be >= 1")
        commit = bool(opts["commit"])
        refetch = bool(opts["refetch"])
        if commit and not refetch:
            raise CommandError(
                "--commit needs --refetch: the excerpt can only come from the "
                "opinion body, which :Case does not store"
            )

        self.stdout.write(
            self.style.MIGRATE_HEADING(
                "backfill_holding_summaries: "
                + (
                    "COMMIT mode — excerpts will be written."
                    if commit
                    else "dry run — no writes; pass --refetch --commit to apply."
                )
            )
        )

        stats, report = async_to_sync(self._run)(
            commit=commit,
            refetch=refetch,
            batch_size=batch_size,
            limit=None if limit is None else int(limit),
        )
        if opts["verbose_cases"]:
            for line in report:
                self.stdout.write(line)

        counts = stats.as_dict()
        self.stdout.write(
            self.style.SUCCESS(
                "scanned={scanned} refetched={refetched} derived={derived} "
                "written={written} unfetchable={unfetchable} failed={failed}".format(
                    **counts
                )
            )
        )
        if refetch and not commit and counts["derived"]:
            self.stdout.write(
                self.style.WARNING(
                    f"Re-run with --commit to write the {counts['derived']} "
                    "pending excerpt(s)."
                )
            )
        self.stdout.write(self.style.WARNING(REFETCH_CAVEAT))

    async def _run(
        self, *, commit: bool, refetch: bool, batch_size: int, limit: int | None
    ) -> tuple[HoldingBackfillStats, list[str]]:
        """Open a source client only when the run actually re-fetches."""
        if not refetch:
            return await run_backfill(
                commit=False,
                refetch=False,
                batch_size=batch_size,
                limit=limit,
                client=None,
            )
        from law_ai.ingestionapp.services.courtlistener import CourtListenerClient

        async with CourtListenerClient() as client:
            return await run_backfill(
                commit=commit,
                refetch=True,
                batch_size=batch_size,
                limit=limit,
                client=client,
            )
