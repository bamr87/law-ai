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

from law_ai.ingestionapp.services.colorado_statutes import (
    ColoradoStatutesClient,
    parse_title_pdf,
)
from law_ai.ingestionapp.services.courtlistener import CourtListenerClient
from law_ai.ingestionapp.services.denver_municipal_code import (
    DenverMunicipalCodeClient,
    parse_chapter_html,
)
from law_ai.ingestionapp.services.ordinance_scout import OrdinanceScout
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

    per_title_cap = args.limit if args.limit and args.limit > 0 else None
    if args.pdf_dir:
        return await _run_colorado_pdfs(args, titles, per_title_cap)

    scout = StatuteScout()
    summary: dict[str, int] = {"committed": 0, "pending": 0, "skipped": 0}
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


async def _run_colorado_pdfs(
    args: argparse.Namespace, titles: list[str], per_title_cap: int | None
) -> dict[str, int]:
    """Parse local CRS title PDFs instead of fetching HTML (BL-20260509-06).

    Reads ``<pdf-dir>/title-<N>.pdf`` for each requested title. Sections
    parsed from a PDF carry a confidence penalty, so in commit mode they
    normally land in the HITL queue rather than the graph — that is the
    intended posture for column-laid-out publications.
    """
    scout = StatuteScout()
    summary: dict[str, int] = {"committed": 0, "pending": 0, "skipped": 0}
    pdf_dir = Path(args.pdf_dir)
    for title_id in titles:
        path = pdf_dir / f"title-{title_id}.pdf"
        try:
            extraction = parse_title_pdf(
                f"us-co/crs/title-{title_id}",
                path.read_bytes(),
                source_url=path.as_uri(),
            )
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
            logger.warning("skipped PDF title %s: %s", title_id, exc)
            summary["skipped"] += 1
    return summary


async def _run_denver(args: argparse.Namespace) -> dict[str, int]:
    """Run the Denver municipal-code ingestion path (BL-20260509-05).

    ``--limit`` is a per-chapter section cap, exactly as ``--titles`` +
    ``--limit`` behave for Colorado statutes.

    Two modes, and the offline one is the default posture:

    * ``--chapter-dir DIR`` parses ``DIR/chapter-<N>.html`` — checked-in or
      operator-supplied HTML, no network at all. This is what the tests and
      the documented workflow use, because the upstream host's terms prohibit
      systematic downloading.
    * Without it, the client fetches from ``DENVER_MUNICIPAL_CODE_BASE_URL``.
      Only point that at a mirror you are permitted to crawl.

    Either way ``OrdinanceScout.requires_human_approval`` is True, so in
    commit mode every section lands in the HITL queue rather than the graph;
    the "committed" column stays 0 by design.
    """
    chapters = [c.strip() for c in (args.chapters or "").split(",") if c.strip()]
    discover = chapters == ["all"]
    if discover and args.chapter_dir:
        # Offline discovery: whatever chapter files the operator actually has.
        chapters = sorted(
            (
                p.stem.removeprefix("chapter-")
                for p in Path(args.chapter_dir).glob("chapter-*.html")
            ),
            key=lambda c: (int(c) if c.isdigit() else 0, c),
        )
        discover = False
    if not chapters:
        raise SystemExit(
            "--source denver_municipal_code requires --chapters 38[,24,...] "
            "(or --chapters all to read them from the code's table of contents)"
        )
    per_chapter_cap = args.limit if args.limit and args.limit > 0 else None
    scout = OrdinanceScout()
    summary: dict[str, int] = {"committed": 0, "pending": 0, "skipped": 0}

    async def _handle(chapter: str, html: str, source_url: str | None) -> None:
        extraction = parse_chapter_html(chapter, html, source_url=source_url)
        extraction.agent_version = scout.agent_version
        if per_chapter_cap is not None:
            extraction.sections = extraction.sections[:per_chapter_cap]
        if args.dry_run:
            # Dry run reports what the *parser* found, so an operator can see
            # the parse quality before deciding to ingest. The HITL routing
            # that would send all of it to review is applied in commit mode.
            summary["committed"] += len(extraction.high_confidence_sections())
            summary["pending"] += len(extraction.low_confidence_sections())
            return
        res = await scout.commit(extraction)
        summary["committed"] += int(res["committed"])
        summary["pending"] += int(res["pending"])

    if args.chapter_dir:
        chapter_dir = Path(args.chapter_dir)
        for chapter in chapters:
            path = chapter_dir / f"chapter-{chapter}.html"
            try:
                await _handle(chapter, path.read_text(encoding="utf-8"), path.as_uri())
            except Exception as exc:
                logger.warning("skipped chapter %s: %s", chapter, exc)
                summary["skipped"] += 1
        return summary

    async with DenverMunicipalCodeClient() as client:
        if discover:
            # BL-20260906-06: one fetch of the table of contents instead of a
            # hand-typed list that silently misses chapters.
            chapters = await client.list_chapters()
            logger.info("discovered %d chapter(s) from the code index", len(chapters))
        async for chapter, html in client.iter_chapters(chapters):
            try:
                await _handle(chapter, html, client.url_for_chapter(chapter))
            except Exception as exc:
                logger.warning("skipped chapter %s: %s", chapter, exc)
                summary["skipped"] += 1
    return summary


async def _run(args: argparse.Namespace) -> dict[str, int]:
    start = time.time()
    if args.source == "colorado_statutes":
        summary = await _run_colorado(args)
    elif args.source == "denver_municipal_code":
        summary = await _run_denver(args)
    else:
        summary = await _run_courtlistener(args)
    summary["elapsed_s"] = int(time.time() - start)
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Ingest sample legal data into Neo4j.")
    parser.add_argument(
        "--source",
        choices=["courtlistener", "colorado_statutes", "denver_municipal_code"],
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
        "--chapters",
        type=str,
        default=None,
        help=(
            "Comma-separated Denver municipal-code chapter numbers "
            "(denver_municipal_code only), e.g. 38,24. Pass `all` to read the "
            "chapter list from the code's table of contents, or from the "
            "chapter-*.html files in --chapter-dir (BL-20260906-06)."
        ),
    )
    parser.add_argument(
        "--chapter-dir",
        type=str,
        default=None,
        help=(
            "Parse local municipal-code HTML (<dir>/chapter-N.html) instead of "
            "fetching (denver_municipal_code only; the documented default "
            "workflow — see docs/data-sources.md)"
        ),
    )
    parser.add_argument(
        "--pdf-dir",
        type=str,
        default=None,
        help=(
            "Parse local CRS title PDFs (<dir>/title-N.pdf) instead of "
            "fetching HTML (colorado_statutes only, BL-20260509-06)"
        ),
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
