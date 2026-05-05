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

from lawgraph.ingestionapp.services.courtlistener import CourtListenerClient
from lawgraph.ingestionapp.services.scout import IngestionScout

logger = logging.getLogger("lawgraph.cli.ingest")


async def _run(args: argparse.Namespace) -> dict[str, int]:
    scout = IngestionScout()
    summary = {"committed": 0, "pending": 0, "skipped": 0}
    start = time.time()
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
    summary["elapsed_s"] = int(time.time() - start)  # type: ignore[assignment]
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Ingest sample case data into Neo4j.")
    parser.add_argument("--source", choices=["courtlistener"], default="courtlistener")
    parser.add_argument("--limit", type=int, default=500)
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
        f"committed={summary['committed']} pending={summary['pending']} "
        f"skipped={summary['skipped']} elapsed_s={summary['elapsed_s']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
