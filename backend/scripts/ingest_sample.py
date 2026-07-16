#!/usr/bin/env python3
"""Sample-data ingestion CLI (T-004 in specs/001).

Usage::

    python scripts/ingest_sample.py --source courtlistener --limit 500
    python scripts/ingest_sample.py --source courtlistener --limit 5 --dry-run

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

# Allow ``python scripts/ingest_sample.py`` from backend/ without install.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from law_ai.ingestionapp.services.colorado_statutes import ColoradoStatutesClient
from law_ai.ingestionapp.services.courtlistener import CourtListenerClient
from law_ai.ingestionapp.services.scout import IngestionScout
from law_ai.ingestionapp.services.statute_scout import StatuteScout

logger = logging.getLogger("law_ai.cli.ingest")


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


async def _run(args: argparse.Namespace) -> dict[str, int]:
    start = time.time()
    if args.source == "colorado_statutes":
        summary = await _run_colorado(args)
    else:
        summary = await _run_courtlistener(args)
    summary["elapsed_s"] = int(time.time() - start)
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Ingest sample legal data into Neo4j.")
    parser.add_argument(
        "--source",
        choices=["courtlistener", "colorado_statutes"],
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
