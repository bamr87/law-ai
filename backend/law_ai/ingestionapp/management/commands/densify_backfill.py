"""``densify_backfill`` — re-run citation densification over historical Cases.

Spec 002 follow-up BL-20260429-11. Ingests that ran before a cited case (or
its ``aliases``) existed left ``(:Case)-[:HAS_CITATION]->(:Citation)`` pairs
with no matching ``(:Case)-[:CITES]->(:Case)`` edge. This command walks those
pairs in batches, re-resolves each citation with
:func:`law_ai.core.neo4j.citation_resolver.resolve_citations`, and MERGEs the
missing ``CITES`` edges.

Safety posture:

* **Read-only by default.** Nothing is written unless ``--commit`` is passed;
  ``--dry-run`` is the (default) explicit opposite and reports what *would*
  be written.
* **MERGE-only, edges-only.** No ``:Case`` property is ever touched and
  nothing is deleted, so the command is idempotent and re-runnable.
* **Batched.** ``--batch-size`` bounds each read; ``--limit`` bounds the whole
  run, so an unattended pass can never open one giant transaction.

Every batch is logged through ``core.provenance`` (constitution §4).

    make manage CMD='densify_backfill'                  # dry run, reports only
    make manage CMD='densify_backfill --commit'
    make manage CMD='densify_backfill --commit --limit 500 --batch-size 50'
"""

from __future__ import annotations

import time
from datetime import UTC, datetime
from typing import Any

from asgiref.sync import async_to_sync
from django.core.management.base import (
    BaseCommand,
    CommandError,
)
from neo4j import AsyncSession

from law_ai.core.neo4j.citation_resolver import resolve_citations
from law_ai.core.neo4j.driver import get_neo4j_driver
from law_ai.core.neo4j.queries import (
    MERGE_CITES_CYPHER,
    list_cases_with_unlinked_citations,
)
from law_ai.core.provenance import provenance


class BackfillStats:
    """Mutable counters for one backfill run."""

    def __init__(self) -> None:
        self.scanned = 0
        self.resolved = 0
        self.edges_created = 0
        self.self_citations = 0

    def as_dict(self) -> dict[str, int]:
        return {
            "scanned": self.scanned,
            "resolved": self.resolved,
            "edges_created": self.edges_created,
            "self_citations": self.self_citations,
        }


async def _merge_cites(
    session: AsyncSession, src_id: str, dst_id: str, confidence: float
) -> bool:
    """MERGE one ``CITES`` edge; return True when Neo4j returned a relationship."""
    result = await session.run(
        MERGE_CITES_CYPHER,
        {
            "src_id": src_id,
            "dst_id": dst_id,
            "confidence": confidence,
            "ingest_timestamp": datetime.now(UTC).isoformat(),
        },
    )
    records = [record async for record in result]
    return bool(records)


async def _backfill_case(
    session: AsyncSession,
    row: dict[str, Any],
    *,
    commit: bool,
    stats: BackfillStats,
) -> list[str]:
    """Resolve one case's pending citations and (optionally) write the edges."""
    case_id = row["case_id"]
    pending: list[dict[str, Any]] = row["pending"]
    stats.scanned += len(pending)

    # One round-trip for the whole case (NFR-PERF-1).
    mapping = await resolve_citations(session, [p["normalized"] for p in pending])

    lines: list[str] = []
    for entry in pending:
        target = mapping.get(entry["normalized"])
        if target is None:
            continue
        stats.resolved += 1
        if target == case_id:
            # A case whose own alias appears in its citation list: a CITES
            # self-loop is meaningless, so skip it rather than write it.
            stats.self_citations += 1
            lines.append(f"    {entry['normalized']} -> {target} (self, skipped)")
            continue
        if commit and await _merge_cites(
            session, case_id, target, float(entry["confidence"])
        ):
            stats.edges_created += 1
            lines.append(f"    {entry['normalized']} -> {target} (edge merged)")
        elif commit:
            lines.append(f"    {entry['normalized']} -> {target} (target missing)")
        else:
            lines.append(f"    {entry['normalized']} -> {target} (would merge)")
    return lines


async def run_backfill(
    *, commit: bool, batch_size: int, limit: int | None
) -> tuple[BackfillStats, list[str]]:
    """Walk every case with unlinked citations, batch by batch."""
    stats = BackfillStats()
    report: list[str] = []
    driver = get_neo4j_driver()
    after = ""
    cases_seen = 0

    async with driver.session() as session:
        while True:
            take = batch_size if limit is None else min(batch_size, limit - cases_seen)
            if take <= 0:
                break
            started = time.perf_counter()
            batch = await list_cases_with_unlinked_citations(
                session, after=after, limit=take
            )
            if not batch:
                break
            for row in batch:
                report.append(f"  {row['case_id']}:")
                report.extend(
                    await _backfill_case(session, row, commit=commit, stats=stats)
                )
            cases_seen += len(batch)
            # Keyset cursor: rows are ordered by case_id, so resuming after the
            # last id of this batch is correct whether or not the rows we just
            # fixed dropped out of the predicate.
            after = batch[-1]["case_id"]
            provenance.log_graph_query(
                cypher="densify_backfill.batch",
                params={
                    "after": after,
                    "limit": take,
                    "commit": commit,
                    "cases": len(batch),
                },
                result_count=stats.edges_created,
                latency_ms=(time.perf_counter() - started) * 1000.0,
            )
    return stats, report


class Command(BaseCommand):
    help = (
        "Re-run citation densification over historical :Case nodes, merging the "
        ":CITES edges that earlier ingests could not resolve. Read-only unless "
        "--commit is passed."
    )

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument(
            "--commit",
            action="store_true",
            help="actually MERGE the CITES edges (default: report only)",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="explicit no-write mode (the default; the opposite of --commit)",
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
            "--verbose-pairs",
            action="store_true",
            help="print every citation -> case pair, not just the totals",
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

        self.stdout.write(
            self.style.MIGRATE_HEADING(
                "densify_backfill: "
                + ("COMMIT mode — CITES edges will be written." if commit else "")
                + ("dry run — no writes; pass --commit to apply." if not commit else "")
            )
        )
        stats, report = async_to_sync(run_backfill)(
            commit=commit,
            batch_size=batch_size,
            limit=None if limit is None else int(limit),
        )
        if opts["verbose_pairs"]:
            for line in report:
                self.stdout.write(line)

        counts = stats.as_dict()
        self.stdout.write(
            self.style.SUCCESS(
                "scanned={scanned} resolved={resolved} "
                "edges_created={edges_created} "
                "self_citations={self_citations}".format(**counts)
            )
        )
        if not commit and counts["resolved"]:
            self.stdout.write(
                self.style.WARNING(
                    "Re-run with --commit to merge the "
                    f"{counts['resolved'] - counts['self_citations']} pending edge(s)."
                )
            )
