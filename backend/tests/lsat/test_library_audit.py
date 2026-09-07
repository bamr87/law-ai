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
    MAX_EXPANSIONS_PER_RUN,
    STALE_AFTER_DAYS,
    THIN_ARTICLE_WORDS,
    LibrarianRequest,
    library_audit,
    load_library,
    load_tracks,
    merge_expansion,
    parse_article,
    pick_librarian_targets,
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


class TestTargetPicker:
    """BL-20260903-08 — the corpus-wide pass that picks its own targets."""

    @staticmethod
    def _report(**overrides: object) -> dict:
        """The real audit with one or two signals forced on."""
        report = library_audit()
        for path, value in overrides.items():
            group, key = path.split("__", 1)
            report[group][key] = value
        return report

    def test_a_healthy_corpus_still_yields_reviews(self) -> None:
        """No signal at all must not idle the cycle."""
        picked = pick_librarian_targets(library_audit(), limit=3)
        assert len(picked) == 3
        assert {r.action for r in picked} == {"review"}
        assert [r.article_id for r in picked] == sorted(load_library())[:3]
        assert all(r.reason for r in picked)

    def test_stale_articles_come_first_in_audit_order(self) -> None:
        ids = sorted(load_library())
        report = self._report(
            freshness__stale_articles=[
                {"id": ids[5], "days_since_review": 400, "status": "reviewed"},
                {"id": ids[2], "days_since_review": 130, "status": "needs-review"},
            ]
        )
        picked = pick_librarian_targets(report, limit=3)
        assert [r.article_id for r in picked[:2]] == [ids[5], ids[2]]
        assert "400 days" in picked[0].reason
        assert "needs-review" in picked[1].reason

    def test_thin_then_unreachable_articles_follow(self) -> None:
        ids = sorted(load_library())
        report = self._report(
            words__thin_articles=[{"id": ids[7], "word_count": 120}],
            graph__orphan_articles=[ids[9]],
        )
        picked = pick_librarian_targets(report, limit=2)
        assert [r.article_id for r in picked] == [ids[7], ids[9]]
        assert "thin" in picked[0].reason
        assert "orphan" in picked[1].reason

    def test_an_article_is_picked_once_under_its_first_signal(self) -> None:
        ids = sorted(load_library())
        report = self._report(
            freshness__stale_articles=[
                {"id": ids[0], "days_since_review": 200, "status": "reviewed"}
            ],
            words__thin_articles=[{"id": ids[0], "word_count": 40}],
        )
        picked = pick_librarian_targets(report, limit=4)
        assert [r.article_id for r in picked].count(ids[0]) == 1
        assert "days since review" in picked[0].reason

    def test_unknown_ids_in_the_report_are_dropped(self) -> None:
        report = self._report(graph__orphan_articles=["no-such-article"])
        picked = pick_librarian_targets(report, limit=2)
        assert "no-such-article" not in [r.article_id for r in picked]

    def test_coverage_gaps_become_capped_expansions(self) -> None:
        from law_ai.lsat.services.bank import load_concepts

        concept_ids = sorted(load_concepts())[:4]
        report = self._report(coverage__concepts_untaught=concept_ids)
        picked = pick_librarian_targets(report, limit=20)
        expansions = [r for r in picked if r.action == "expand"]
        assert 0 < len(expansions) <= MAX_EXPANSIONS_PER_RUN
        gap_concepts = concept_ids[: len(expansions)]
        for request, concept_id in zip(expansions, gap_concepts, strict=True):
            concept = load_concepts()[concept_id]
            assert request.gap and concept_id in request.gap
            assert concept_id in request.reason
            host = load_library()[request.article_id]
            assert set(host.sections) & set(concept.sections)

    def test_expansions_rank_below_every_review(self) -> None:
        from law_ai.lsat.services.bank import load_concepts

        ids = sorted(load_library())
        report = self._report(
            coverage__concepts_untaught=sorted(load_concepts())[:2],
            words__thin_articles=[{"id": ids[3], "word_count": 90}],
        )
        picked = pick_librarian_targets(report, limit=3)
        assert picked[0].action == "review" and picked[0].article_id == ids[3]
        assert [r.action for r in picked[1:]] == ["expand", "expand"]

    def test_limit_is_the_number_returned_not_considered(self) -> None:
        report = library_audit()
        assert len(pick_librarian_targets(report, limit=1)) == 1
        assert len(pick_librarian_targets(report, limit=0)) == 1
        assert len(pick_librarian_targets(report, limit=7)) == 7

    def test_request_renders_the_agent_payload(self) -> None:
        review, expand = LibrarianRequest(article_id="a", reason="r"), LibrarianRequest(
            action="expand", article_id="a", gap="g", reason="r"
        )
        assert review.to_input() == {"action": "review", "article_id": "a"}
        assert expand.to_input() == {
            "action": "expand",
            "article_id": "a",
            "gap": "g",
        }

    def test_merged_expansion_is_a_whole_parseable_article(self) -> None:
        article_id = sorted(load_library())[0]
        merged = merge_expansion(article_id, "## A New Section\n\nOne paragraph.\n")
        assert merged.startswith("---")
        assert merged.rstrip().endswith("One paragraph.")
        parsed = parse_article(merged, article_id=article_id, where="merged")
        assert any(
            b.block_type == "heading" and b.text == "A New Section"
            for b in parsed.blocks
        )
