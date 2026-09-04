"""Deterministic library audit (spec 048 T-040: FR-14, AC-8).

The audit is the number behind "the library is being maintained", so the
central property under test is that it depends on nothing it measures: no
provider, no network, no model call.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from django.conf import settings

from law_ai.lsat.services.library import (
    STALE_AFTER_DAYS,
    THIN_ARTICLE_WORDS,
    library_audit,
    load_library,
    load_tracks,
)


@pytest.fixture()
def no_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    """Blank every credential so a stray model call would fail loudly."""
    for name in ("ANTHROPIC_API_KEY", "LLM_PROVIDER_CHAIN", "OLLAMA_BASE_URL"):
        monkeypatch.setattr(settings, name, "", raising=False)


def test_audit_runs_with_no_provider_configured(no_provider: None) -> None:
    report = library_audit()
    assert report["counts"]["articles"] == len(load_library())


def test_report_carries_every_category() -> None:
    report = library_audit()
    assert set(report) >= {
        "generated_at",
        "counts",
        "words",
        "coverage",
        "freshness",
        "graph",
    }
    assert set(report["counts"]) >= {
        "articles",
        "tracks",
        "by_kind",
        "by_section",
        "by_level",
        "by_status",
    }
    assert set(report["words"]) >= {"total", "mean", "min", "max", "thin_articles"}
    assert set(report["coverage"]) >= {
        "concepts_total",
        "concepts_taught",
        "concepts_untaught",
        "archetypes_total",
        "archetypes_covered",
        "archetypes_uncovered",
    }
    assert set(report["freshness"]) >= {"stale_after_days", "stale_articles"}
    assert set(report["graph"]) >= {
        "orphan_articles",
        "articles_in_no_track",
        "roots",
        "prerequisite_cycles",
        "broken_cross_references",
    }


def test_counts_match_the_loaders() -> None:
    report = library_audit()
    assert report["counts"]["articles"] == len(load_library())
    assert report["counts"]["tracks"] == len(load_tracks())
    assert sum(report["counts"]["by_kind"].values()) == len(load_library())


def test_thin_threshold_is_reported_and_applied() -> None:
    report = library_audit()
    assert report["words"]["thin_threshold"] == THIN_ARTICLE_WORDS
    for row in report["words"]["thin_articles"]:
        assert row["word_count"] < THIN_ARTICLE_WORDS


def test_staleness_is_relative_to_the_supplied_date() -> None:
    """Every article is fresh today and stale far enough in the future."""
    today = library_audit(today=date(2026, 9, 3))
    assert today["freshness"]["stale_articles"] == []

    later = library_audit(today=date(2026, 9, 3) + timedelta(days=STALE_AFTER_DAYS + 1))
    stale_ids = {row["id"] for row in later["freshness"]["stale_articles"]}
    assert stale_ids == set(load_library())


def test_stale_articles_are_ordered_oldest_first() -> None:
    report = library_audit(today=date(2027, 6, 1))
    ages = [row["days_since_review"] for row in report["freshness"]["stale_articles"]]
    assert ages == sorted(ages, reverse=True)


def test_untaught_concepts_are_reported_as_ids() -> None:
    report = library_audit()
    assert isinstance(report["coverage"]["concepts_untaught"], list)
    assert report["coverage"]["concepts_taught"] <= report["coverage"]["concepts_total"]
