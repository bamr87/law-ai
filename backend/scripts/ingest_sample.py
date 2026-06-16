#!/usr/bin/env python3
"""Sample-data ingestion CLI (T-004 in specs/001).

Usage::

    python scripts/ingest_sample.py --source courtlistener --limit 500
    python scripts/ingest_sample.py --source courtlistener --limit 5 --dry-run
    python scripts/ingest_sample.py --source sample        # offline landmark seed

``--source sample`` writes a few landmark Supreme Court cases + citations
directly to Neo4j with no network call or API token — it backs ``make
ingest-sample`` and the Knowledge Graph explorer's empty-state CTA.

In ``--dry-run`` mode no Neo4j writes occur — extractions are run and
counted but the final ``run_and_commit`` step is skipped, which makes
the CLI safe for use against ``respx`` cassettes in tests.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
import time
from pathlib import Path
from typing import Any

# Allow ``python scripts/ingest_sample.py`` from backend/ without install.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lawgraph.ingestionapp.services.colorado_statutes import ColoradoStatutesClient
from lawgraph.ingestionapp.services.courtlistener import CourtListenerClient
from lawgraph.ingestionapp.services.scout import IngestionScout
from lawgraph.ingestionapp.services.statute_scout import StatuteScout

logger = logging.getLogger("lawgraph.cli.ingest")


async def _run_courtlistener(args: argparse.Namespace) -> dict[str, int]:
    scout = IngestionScout()
    summary: dict[str, int] = {"committed": 0, "pending": 0, "skipped": 0}
    async with CourtListenerClient() as client:
        async for opinion in client.list_opinions(limit=args.limit):
            try:
                if args.dry_run:
                    result = scout.extract(opinion)
                    if result.is_high_confidence():
                        summary["committed"] += 1  # would-commit
                    else:
                        summary["pending"] += 1
                else:
                    res = await scout.run_and_commit(opinion)
                    if res["committed"]:
                        summary["committed"] += 1
                    else:
                        summary["pending"] += 1
            except Exception as exc:
                logger.warning("skipped opinion: %s", exc)
                summary["skipped"] += 1
    return summary


async def _run_colorado(args: argparse.Namespace) -> dict[str, int]:
    """Run the Colorado statute ingestion path (spec 016 FR-7).

    ``--limit`` is interpreted as a *per-title section cap* (spec 016 FR-7):
    when set, only the first ``args.limit`` parsed sections of each title are
    committed (or counted, in dry-run mode). The cap is applied identically
    in dry-run and commit modes; titles are processed independently and the
    cap does not span across titles.
    """
    titles = [t.strip() for t in (args.titles or "").split(",") if t.strip()]
    if not titles:
        raise SystemExit("--source colorado_statutes requires --titles 18[,42,...]")

    scout = StatuteScout()
    summary: dict[str, int] = {"committed": 0, "pending": 0, "skipped": 0}
    per_title_cap = args.limit if args.limit and args.limit > 0 else None
    async with ColoradoStatutesClient() as client:
        async for title_id, html in client.iter_titles(titles):
            payload: dict[str, object] = {
                "title_id": f"us-co/crs/title-{title_id}",
                "html": html,
                "source_url": client.url_for_title(title_id),
            }
            try:
                extraction = scout.extract(payload)
                if per_title_cap is not None:
                    extraction.sections = extraction.sections[:per_title_cap]

                if args.dry_run:
                    summary["committed"] += len(extraction.high_confidence_sections())
                    summary["pending"] += len(extraction.low_confidence_sections())
                else:
                    res = await scout.commit(extraction)
                    summary["committed"] += int(res["committed"])
                    summary["pending"] += int(res["pending"])
            except Exception as exc:
                logger.warning("skipped title %s: %s", title_id, exc)
                summary["skipped"] += 1
    return summary


# A tiny, fully-offline seed of landmark U.S. Supreme Court cases + their
# citations and a few CITES edges. Powers ``--source sample`` (and the
# Knowledge Graph explorer's "make ingest-sample" empty-state CTA) without any
# network call or API token — unlike the courtlistener/colorado_statutes paths.
# Edges are deliberately conservative: every case CITES Marbury (the canonical
# judicial-review authority) plus the two well-known direct relationships
# (Brown→Plessy, Miranda→Gideon), giving a connected graph to explore.
_SAMPLE_CASES: list[dict[str, Any]] = [
    {
        "id": "scotus-marbury-1803",
        "title": "Marbury v. Madison",
        "decided_at": "1803-02-24",
        "url": "https://supreme.justia.com/cases/federal/us/5/137/",
        "citation": "5 U.S. 137",
    },
    {
        "id": "scotus-plessy-1896",
        "title": "Plessy v. Ferguson",
        "decided_at": "1896-05-18",
        "url": "https://supreme.justia.com/cases/federal/us/163/537/",
        "citation": "163 U.S. 537",
    },
    {
        "id": "scotus-brown-1954",
        "title": "Brown v. Board of Education",
        "decided_at": "1954-05-17",
        "url": "https://supreme.justia.com/cases/federal/us/347/483/",
        "citation": "347 U.S. 483",
    },
    {
        "id": "scotus-gideon-1963",
        "title": "Gideon v. Wainwright",
        "decided_at": "1963-03-18",
        "url": "https://supreme.justia.com/cases/federal/us/372/335/",
        "citation": "372 U.S. 335",
    },
    {
        "id": "scotus-miranda-1966",
        "title": "Miranda v. Arizona",
        "decided_at": "1966-06-13",
        "url": "https://supreme.justia.com/cases/federal/us/384/436/",
        "citation": "384 U.S. 436",
    },
]
_SAMPLE_CITES: list[tuple[str, str]] = [
    ("scotus-plessy-1896", "scotus-marbury-1803"),
    ("scotus-brown-1954", "scotus-marbury-1803"),
    ("scotus-gideon-1963", "scotus-marbury-1803"),
    ("scotus-miranda-1966", "scotus-marbury-1803"),
    ("scotus-brown-1954", "scotus-plessy-1896"),
    ("scotus-miranda-1966", "scotus-gideon-1963"),
]


async def _run_sample(args: argparse.Namespace) -> dict[str, int]:
    """Seed a few landmark cases + citations directly into Neo4j — no network.

    Reuses the canonical ``MERGE_*`` write queries so the seeded nodes carry the
    same provenance fields (``source``/``confidence``, constitution §4) and stay
    idempotent (re-running is a no-op via ``MERGE``).
    """
    from datetime import UTC, datetime

    from lawgraph.core.neo4j.driver import get_neo4j_driver
    from lawgraph.core.neo4j.queries import (
        MERGE_CASE_CYPHER,
        MERGE_CITATION_CYPHER,
        MERGE_CITES_CYPHER,
    )

    summary: dict[str, int] = {"committed": 0, "pending": 0, "skipped": 0}
    if args.dry_run:
        summary["committed"] = len(_SAMPLE_CASES)
        return summary

    now = datetime.now(UTC).isoformat()
    driver = get_neo4j_driver()
    async with driver.session() as session:
        for case in _SAMPLE_CASES:
            await session.run(
                MERGE_CASE_CYPHER,
                {
                    "id": case["id"],
                    "title": case["title"],
                    "court": "Supreme Court of the United States",
                    "decided_at": case["decided_at"],
                    "source": "seed",
                    "source_url": case["url"],
                    "ingest_timestamp": now,
                    "agent_version": "ingest-sample",
                    "confidence": 1.0,
                    "aliases": [case["citation"]],
                },
            )
            await session.run(
                MERGE_CITATION_CYPHER,
                {
                    "normalized": case["citation"],
                    "text": f"{case['citation']} ({case['decided_at'][:4]})",
                    "case_id": case["id"],
                    "ingest_timestamp": now,
                    "confidence": 1.0,
                },
            )
            summary["committed"] += 1
        for src_id, dst_id in _SAMPLE_CITES:
            await session.run(
                MERGE_CITES_CYPHER,
                {
                    "src_id": src_id,
                    "dst_id": dst_id,
                    "confidence": 1.0,
                    "ingest_timestamp": now,
                },
            )
    return summary


async def _run(args: argparse.Namespace) -> dict[str, int]:
    start = time.time()
    if args.source == "colorado_statutes":
        summary = await _run_colorado(args)
    elif args.source == "sample":
        summary = await _run_sample(args)
    else:
        summary = await _run_courtlistener(args)
    summary["elapsed_s"] = int(time.time() - start)
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Ingest sample legal data into Neo4j.")
    parser.add_argument(
        "--source",
        choices=["courtlistener", "colorado_statutes", "sample"],
        default="courtlistener",
    )
    parser.add_argument("--limit", type=int, default=500)
    parser.add_argument(
        "--titles",
        type=str,
        default=None,
        help="Comma-separated CRS title numbers (colorado_statutes only), e.g. 18,42",
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Extract but do not commit"
    )
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    summary = asyncio.run(_run(args))
    print(
        "ingest summary: "
        f"source={args.source} committed={summary['committed']} "
        f"pending={summary['pending']} skipped={summary['skipped']} "
        f"elapsed_s={summary['elapsed_s']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
