"""``resolve_statute_citations`` — backfill ``CITES_STATUTE`` edges (BL-20260509-07).

``(:Case)-[:CITES_STATUTE]->(:StatuteSection)`` was declared in
[docs/data-model.md](../../../../../docs/data-model.md) from spec 015 but had no
writer, so an opinion that cited the CRS and the CRS section it cited sat in
the same graph unconnected. New ingests now create the edge inline
(``citation_resolver.densify_statute_extraction`` →
``queries.MERGE_CITES_STATUTE_CYPHER``); this command does the same for the
opinions ingested before the CRS corpus was loaded.

It reads the ``Citation.normalized`` strings the original ingest already stored
rather than re-scanning opinion text — ``:Case`` nodes do not persist the
opinion body, so a text re-scan would mean re-fetching every opinion from
upstream. That makes the backfill fully offline, and it bounds what the
backfill can recover: see :data:`RECALL_CAVEAT`, which every run prints. An
opinion ingested before the C.R.S. patterns landed has no C.R.S. citation
string to read, so only re-ingesting it can link it.

Safety posture mirrors ``densify_backfill``:

* **Read-only by default.** Nothing is written unless ``--commit``.
* **MERGE-only, edges-only.** No node property is touched, nothing is deleted,
  and the edge is merged only when the ``:StatuteSection`` really exists, so
  the run is idempotent and re-runnable.
* **Batched** via a keyset cursor on ``Case.id``, so an unattended pass never
  opens one giant transaction.

Every batch is logged through ``core.provenance`` (constitution §4).

    make manage CMD='resolve_statute_citations'                  # dry run
    make manage CMD='resolve_statute_citations --commit'
    make manage CMD='resolve_statute_citations --commit --limit 500'
"""

from __future__ import annotations

import time
from datetime import UTC, datetime
from typing import Any

from asgiref.sync import async_to_sync
from django.core.management.base import BaseCommand, CommandError
from neo4j import AsyncSession

from law_ai.core.neo4j.citation_resolver import (
    STATUTE_REPORTERS,
    resolve_statute_citations,
    statute_section_id_from_normalized,
)
from law_ai.core.neo4j.driver import get_neo4j_driver
from law_ai.core.neo4j.queries import (
    MERGE_CITES_STATUTE_CYPHER,
    list_cases_with_statute_citations,
    list_cases_without_statute_citations,
)
from law_ai.core.provenance import provenance

#: Provenance `source` written on every edge this command creates, so an
#: auditor can tell a backfilled edge from one an ingest wrote.
BACKFILL_SOURCE = "resolve_statute_citations_backfill"

#: Provenance `source` for edges recovered by re-reading the opinion upstream
#: (BL-20260906-88), kept distinct from the offline pass above so an auditor
#: can tell which cites came from stored strings and which from a re-fetch.
REFETCH_SOURCE = "resolve_statute_citations_refetch"

#: Corpora whose documents can be re-fetched by ``:Case.id``. Only opinions
#: with a per-document upstream endpoint qualify.
REFETCHABLE_SOURCES = ("courtlistener",)

#: The limit of what an offline pass can recover, printed on every run.
#:
#: This backfill can only see citation strings that an *earlier* ingest already
#: stored. Before the CRS patterns in ``scout._CRS_CITATION_RES`` landed, the
#: only statutory extractor was eyecite, which recognises the reporter
#: "Colo. Rev. Stat." but returns a bare ``UnknownCitation('§')`` for
#: "C.R.S. § 18-3-102" and nothing at all for "section 13-80-102, C.R.S." —
#: the two forms Colorado courts actually write. So for opinions ingested
#: before that change the strings simply are not there, and no offline pass
#: can conjure them: those cases must be re-ingested (their text re-run
#: through ``_extract_citations``) before this command can link them.
RECALL_CAVEAT = (
    "Recall limit: the offline pass reads the citation strings earlier ingests "
    "stored; it never re-reads opinion text (:Case nodes persist none). Opinions "
    "ingested before the C.R.S. patterns landed had only eyecite, which misses "
    '"C.R.S. § 18-3-102" and "section 13-80-102, C.R.S." entirely, so they hold '
    "no string to resolve. Pass --refetch to re-read those opinions upstream and "
    "re-run today's extractor over them (BL-20260906-88); without it, only "
    "re-ingestion recovers them."
)


class StatuteBackfillStats:
    """Mutable counters for one backfill run."""

    def __init__(self) -> None:
        self.scanned = 0
        self.candidates = 0
        self.resolved = 0
        self.edges_created = 0
        # BL-20260906-88: the recall pass's own counters.
        self.refetched = 0
        self.refetch_failed = 0
        self.recovered = 0

    def as_dict(self) -> dict[str, int]:
        return {
            "scanned": self.scanned,
            "candidates": self.candidates,
            "resolved": self.resolved,
            "edges_created": self.edges_created,
            "refetched": self.refetched,
            "refetch_failed": self.refetch_failed,
            "recovered": self.recovered,
        }


async def _merge_cites_statute(
    session: AsyncSession,
    case_id: str,
    section_id: str,
    confidence: float,
    *,
    source: str = BACKFILL_SOURCE,
) -> bool:
    """MERGE one ``CITES_STATUTE`` edge; True when Neo4j returned one."""
    result = await session.run(
        MERGE_CITES_STATUTE_CYPHER,
        {
            "case_id": case_id,
            "section_id": section_id,
            "confidence": confidence,
            "source": source,
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
    stats: StatuteBackfillStats,
) -> list[str]:
    """Resolve one case's statutory citations and (optionally) write the edges."""
    case_id = row["case_id"]
    pending: list[dict[str, Any]] = row["pending"]
    stats.scanned += len(pending)

    candidates: dict[str, str] = {}
    for entry in pending:
        section_id = statute_section_id_from_normalized(entry["normalized"])
        if section_id:
            candidates[entry["normalized"]] = section_id
    if not candidates:
        return []
    stats.candidates += len(candidates)

    # One round-trip for the whole case, as densify does (NFR-PERF-1).
    mapping = await resolve_statute_citations(session, sorted(set(candidates.values())))

    lines: list[str] = []
    for entry in pending:
        section_id = candidates.get(entry["normalized"])
        if section_id is None or not mapping.get(section_id):
            continue
        stats.resolved += 1
        if not commit:
            lines.append(f"    {entry['normalized']} -> {section_id} (would merge)")
            continue
        if await _merge_cites_statute(
            session, case_id, section_id, float(entry["confidence"])
        ):
            stats.edges_created += 1
            lines.append(f"    {entry['normalized']} -> {section_id} (edge merged)")
        else:  # pragma: no cover - only when the case vanished mid-run
            lines.append(f"    {entry['normalized']} -> {section_id} (case missing)")
    return lines


async def _refetch_case(
    session: AsyncSession,
    row: dict[str, Any],
    *,
    client: Any,
    commit: bool,
    stats: StatuteBackfillStats,
) -> list[str]:
    """Re-read one opinion upstream and link the statutes it cites.

    BL-20260906-88. The offline pass can only resolve citation strings an
    earlier ingest stored, and opinions ingested before the C.R.S. patterns
    landed stored none — eyecite misses both forms Colorado courts write. So
    this re-fetches the opinion, runs *today's* extractor over it, and merges
    the edges its citations resolve to. Nothing else about the case is
    rewritten: this is a citation-recall pass, not a re-ingest.
    """
    from law_ai.ingestionapp.services.scout import IngestionScout

    case_id = row["case_id"]
    try:
        opinion = await client.fetch_opinion(case_id)
    except Exception as exc:
        stats.refetch_failed += 1
        return [f"  {case_id}: re-fetch failed ({type(exc).__name__}: {exc})"]
    stats.refetched += 1

    result = IngestionScout().extract({**opinion, "id": case_id})
    candidates: dict[str, str] = {}
    for citation in result.citations:
        section_id = statute_section_id_from_normalized(citation.normalized)
        if section_id:
            candidates[citation.normalized] = section_id
    if not candidates:
        return []
    stats.candidates += len(candidates)

    mapping = await resolve_statute_citations(session, sorted(set(candidates.values())))
    lines: list[str] = []
    for normalized, section_id in candidates.items():
        if not mapping.get(section_id):
            continue
        stats.resolved += 1
        if not commit:
            lines.append(f"    {normalized} -> {section_id} (would merge, re-fetched)")
            continue
        if await _merge_cites_statute(
            session,
            case_id,
            section_id,
            float(result.confidence),
            source=REFETCH_SOURCE,
        ):
            stats.edges_created += 1
            stats.recovered += 1
            lines.append(f"    {normalized} -> {section_id} (edge merged, re-fetched)")
    return lines


async def run_refetch(
    *, commit: bool, batch_size: int, limit: int | None, client: Any
) -> tuple[StatuteBackfillStats, list[str]]:
    """Walk cases holding no statutory citation at all and re-read them."""
    stats = StatuteBackfillStats()
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
            batch = await list_cases_without_statute_citations(
                session,
                reporters=list(STATUTE_REPORTERS),
                sources=list(REFETCHABLE_SOURCES),
                after=after,
                limit=take,
            )
            if not batch:
                break
            stats.scanned += len(batch)
            for row in batch:
                lines = await _refetch_case(
                    session, row, client=client, commit=commit, stats=stats
                )
                if lines:
                    report.append(f"  {row['case_id']}:")
                    report.extend(lines)
            cases_seen += len(batch)
            after = batch[-1]["case_id"]
            provenance.log_graph_query(
                cypher="resolve_statute_citations.refetch_batch",
                params={
                    "after": after,
                    "limit": take,
                    "commit": commit,
                    "cases": len(batch),
                },
                result_count=stats.recovered,
                latency_ms=(time.perf_counter() - started) * 1000.0,
            )
    return stats, report


async def run_backfill(
    *, commit: bool, batch_size: int, limit: int | None
) -> tuple[StatuteBackfillStats, list[str]]:
    """Walk every case with statute-looking citations, batch by batch."""
    stats = StatuteBackfillStats()
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
            batch = await list_cases_with_statute_citations(
                session, reporters=list(STATUTE_REPORTERS), after=after, limit=take
            )
            if not batch:
                break
            for row in batch:
                lines = await _backfill_case(session, row, commit=commit, stats=stats)
                if lines:
                    report.append(f"  {row['case_id']}:")
                    report.extend(lines)
            cases_seen += len(batch)
            after = batch[-1]["case_id"]
            provenance.log_graph_query(
                cypher="resolve_statute_citations.batch",
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
        "Backfill (:Case)-[:CITES_STATUTE]->(:StatuteSection) edges over "
        "historical opinions, using the citation strings earlier ingests "
        "already stored. Read-only unless --commit is passed."
    )

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument(
            "--commit",
            action="store_true",
            help="actually MERGE the CITES_STATUTE edges (default: report only)",
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
            "--refetch",
            action="store_true",
            help=(
                "also re-read opinions that hold no statutory citation at all "
                "and re-run today's extractor over them (BL-20260906-88)"
            ),
        )
        parser.add_argument(
            "--verbose-pairs",
            action="store_true",
            help="print every citation -> section pair, not just the totals",
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
                "resolve_statute_citations: "
                + (
                    "COMMIT mode — CITES_STATUTE edges will be written."
                    if commit
                    else "dry run — no writes; pass --commit to apply."
                )
            )
        )
        stats, report = async_to_sync(run_backfill)(
            commit=commit,
            batch_size=batch_size,
            limit=None if limit is None else int(limit),
        )
        if opts["refetch"]:
            # BL-20260906-88: the second, upstream-reading pass. Its counters
            # are merged into the summary so one run reports one total.
            recall_stats, recall_report = async_to_sync(self._run_refetch)(
                commit=commit,
                batch_size=batch_size,
                limit=None if limit is None else int(limit),
            )
            report.extend(recall_report)
            stats.scanned += recall_stats.scanned
            stats.candidates += recall_stats.candidates
            stats.resolved += recall_stats.resolved
            stats.edges_created += recall_stats.edges_created
            stats.refetched += recall_stats.refetched
            stats.refetch_failed += recall_stats.refetch_failed
            stats.recovered += recall_stats.recovered

        if opts["verbose_pairs"]:
            for line in report:
                self.stdout.write(line)

        counts = stats.as_dict()
        self.stdout.write(
            self.style.SUCCESS(
                "scanned={scanned} candidates={candidates} "
                "resolved={resolved} edges_created={edges_created} "
                "refetched={refetched} refetch_failed={refetch_failed} "
                "recovered={recovered}".format(**counts)
            )
        )
        if not commit and counts["resolved"]:
            self.stdout.write(
                self.style.WARNING(
                    "Re-run with --commit to merge the "
                    f"{counts['resolved']} pending edge(s)."
                )
            )
        # Constitution §13: report the absence, every run. A clean summary here
        # does NOT mean the historical corpus has no statutory cites left to
        # link — it means none are visible to an offline pass.
        self.stdout.write(self.style.WARNING(RECALL_CAVEAT))

    async def _run_refetch(
        self, *, commit: bool, batch_size: int, limit: int | None
    ) -> tuple[StatuteBackfillStats, list[str]]:
        """Open a source client only for the pass that actually fetches."""
        from law_ai.ingestionapp.services.courtlistener import CourtListenerClient

        async with CourtListenerClient() as client:
            return await run_refetch(
                commit=commit, batch_size=batch_size, limit=limit, client=client
            )
