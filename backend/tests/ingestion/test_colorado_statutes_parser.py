"""Unit tests for the Colorado statutes HTML parser (spec 016 T-002, AC-1)."""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from law_ai.core.schemas.statute_extraction import StatuteExtraction
from law_ai.ingestionapp.services.colorado_statutes import (
    JURISDICTION_CODE,
    parse_title_html,
)

FIXTURE = Path(__file__).parent / "fixtures" / "co" / "title_18_article_3.html"


@pytest.fixture(scope="module")
def fixture_html() -> str:
    return FIXTURE.read_text(encoding="utf-8")


def test_parse_title_returns_statute_extraction(fixture_html: str) -> None:
    extraction = parse_title_html(
        title_id="us-co/crs/title-18",
        html=fixture_html,
        source_url="https://example.test/title-18/",
    )
    assert isinstance(extraction, StatuteExtraction)
    assert extraction.jurisdiction_code == JURISDICTION_CODE
    assert extraction.code_id == "us-co/crs"
    assert extraction.statute_id == "us-co/crs/title-18"
    assert extraction.statute_citation == "C.R.S. Title 18"
    assert extraction.source_url == "https://example.test/title-18/"
    assert extraction.source == "colorado_statutes"


def test_parse_extracts_all_six_fixture_sections(fixture_html: str) -> None:
    extraction = parse_title_html("us-co/crs/title-18", fixture_html)
    ids = [s.id for s in extraction.sections]
    assert ids == [
        "us-co/crs/18-3-101",
        "us-co/crs/18-3-102",
        "us-co/crs/18-3-103",
        "us-co/crs/18-3-104",
        "us-co/crs/18-3-105",
        "us-co/crs/18-3-106",
    ]


def test_section_citation_and_heading_shape(fixture_html: str) -> None:
    extraction = parse_title_html("us-co/crs/title-18", fixture_html)
    sec = extraction.sections[1]  # 18-3-102
    assert sec.citation == "C.R.S. § 18-3-102"
    assert "Murder in the first degree" in sec.heading
    assert sec.text  # body extracted
    assert sec.confidence >= 0.7  # substantive section -> high confidence


def test_low_quality_section_quarantines(fixture_html: str) -> None:
    """The deliberately-malformed § 18-3-106 fixture must score below 0.7."""
    extraction = parse_title_html("us-co/crs/title-18", fixture_html)
    bad = next(s for s in extraction.sections if s.id == "us-co/crs/18-3-106")
    assert bad.confidence < 0.7
    high = extraction.high_confidence_sections()
    low = extraction.low_confidence_sections()
    assert bad in low
    assert bad not in high
    assert len(high) >= 5


def test_parser_strips_script_and_style(fixture_html: str) -> None:
    """NFR-SEC-1: parsed text must not carry executable markup."""
    extraction = parse_title_html("us-co/crs/title-18", fixture_html)
    for sec in extraction.sections:
        assert "<script" not in sec.text.lower()
        assert "console.log" not in sec.text


def test_parse_effective_date(fixture_html: str) -> None:
    extraction = parse_title_html("us-co/crs/title-18", fixture_html)
    sec_101 = next(s for s in extraction.sections if s.id == "us-co/crs/18-3-101")
    assert sec_101.effective_from is not None
    assert sec_101.effective_from.year == 2024
    assert sec_101.effective_from.month == 7


def test_parser_is_fast(fixture_html: str) -> None:
    """NFR-PERF-1: < 500 ms per title on the fixture."""
    start = time.time()
    parse_title_html("us-co/crs/title-18", fixture_html)
    elapsed_ms = (time.time() - start) * 1000
    assert elapsed_ms < 500, f"parser took {elapsed_ms:.0f} ms"


def test_parser_aggregate_confidence_in_bounds(fixture_html: str) -> None:
    extraction = parse_title_html("us-co/crs/title-18", fixture_html)
    assert 0.0 <= extraction.confidence <= 1.0


# ---------------------------------------------------------------------------
# Decimal articles (BL-20260511-07). Colorado numbers whole articles with a
# decimal — 18-1.3 (sentencing), 18-1.4 (death penalty). The old section-number
# regex stopped at the decimal, so "§ 18-1.3-401" became "18-1.3": a wrong
# node id, a wrong citation, and a false drift signal from the live smoke test.
# ---------------------------------------------------------------------------

DECIMAL_ARTICLE_HTML = """
<html><body>
<h1 class="codes-title">Title 18 - Criminal Code</h1>
<article class="codes-section" id="18-1.3-401">
  <h3 class="section-heading">§ 18-1.3-401. Felonies classified - presumptive penalties</h3>
  <div class="section-text">As to any person sentenced for a felony committed
  on or after July 1, 1993, the presumptive ranges apply.</div>
</article>
<article class="codes-section" id="18-3-102">
  <h3 class="section-heading">§ 18-3-102. Murder in the first degree</h3>
  <div class="section-text">A person commits the crime of murder in the first
  degree if, after deliberation, that person causes the death of a person.</div>
</article>
</body></html>
"""


def test_decimal_article_section_number_survives_intact() -> None:
    extraction = parse_title_html("us-co/crs/title-18", DECIMAL_ARTICLE_HTML)
    assert [s.id for s in extraction.sections] == [
        "us-co/crs/18-1.3-401",
        "us-co/crs/18-3-102",
    ]
    assert extraction.sections[0].citation == "C.R.S. § 18-1.3-401"


def test_decimal_article_section_is_not_penalised_for_its_number() -> None:
    """A decimal article is a normal, high-confidence section, not a parse fault."""
    extraction = parse_title_html("us-co/crs/title-18", DECIMAL_ARTICLE_HTML)
    assert extraction.sections[0].confidence >= 0.7
