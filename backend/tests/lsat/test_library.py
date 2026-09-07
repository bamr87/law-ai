"""Library loader — cross-reference integrity, tracks, and views.

Spec 048 T-002/T-011/T-012 (FR-3, FR-4, FR-6, FR-7, AC-1).
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path

import pytest

from law_ai.lsat.services import bank as bank_mod
from law_ai.lsat.services import library as lib

MINIMAL = """---
id: {id}
title: {title}
kind: technique
level: core
sections: [LR]
summary: A sandbox article.
concepts: [{concepts}]
prerequisites: [{prerequisites}]
related: []
tags: []
status: draft
last_reviewed: 2026-09-03
revision: 1
references: []
---

## One

Body text. {extra}

## Two

More body.

> [!example] Worked example
> An instance.

## Key takeaways

- a takeaway
"""


def _write(directory: Path, article_id: str, **kw: str) -> None:
    (directory / f"{article_id}.md").write_text(
        MINIMAL.format(
            id=article_id,
            title=kw.get("title", article_id.replace("-", " ").title()),
            concepts=kw.get("concepts", ""),
            prerequisites=kw.get("prerequisites", ""),
            extra=kw.get("extra", ""),
        ),
        encoding="utf-8",
    )


@pytest.fixture()
def sandbox(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    """A data dir with the real bank + concepts and an empty library."""
    real = bank_mod.DATA_DIR
    box = tmp_path / "lsat_data"
    box.mkdir()
    for name in ("lr_bank.json", "rc_bank.json", "lg_bank.json", "concepts.json"):
        src = real / name
        if src.is_file():
            (box / name).write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
    (box / "library").mkdir()
    monkeypatch.setattr(bank_mod, "DATA_DIR", box)
    bank_mod.load_bank.cache_clear()
    bank_mod.load_concepts.cache_clear()
    lib.reset_library_caches()
    yield box / "library"
    bank_mod.load_bank.cache_clear()
    bank_mod.load_concepts.cache_clear()
    lib.reset_library_caches()


class TestLoad:
    def test_empty_directory_loads_as_empty(self, sandbox: Path) -> None:
        assert lib.load_library() == {}

    def test_underscore_prefixed_files_are_skipped(self, sandbox: Path) -> None:
        _write(sandbox, "real-one")
        (sandbox / "_template.md").write_text("not an article", encoding="utf-8")
        assert set(lib.load_library()) == {"real-one"}

    def test_unknown_concept_fails_the_load(self, sandbox: Path) -> None:
        _write(sandbox, "bad-concept", concepts="no-such-concept")
        with pytest.raises(lib.LibraryError, match="unknown concept"):
            lib.load_library()

    def test_unknown_prerequisite_fails_the_load(self, sandbox: Path) -> None:
        _write(sandbox, "orphan-prereq", prerequisites="missing-article")
        with pytest.raises(lib.LibraryError, match="unknown article"):
            lib.load_library()

    def test_self_reference_fails_the_load(self, sandbox: Path) -> None:
        _write(sandbox, "selfy", prerequisites="selfy")
        with pytest.raises(lib.LibraryError, match="names the article itself"):
            lib.load_library()

    def test_dead_inline_concept_reference_fails_the_load(self, sandbox: Path) -> None:
        _write(sandbox, "dead-inline", extra="See [[concept:not-a-concept]].")
        with pytest.raises(lib.LibraryError, match=r"\[\[concept:not-a-concept\]\]"):
            lib.load_library()

    def test_dead_inline_article_reference_fails_the_load(self, sandbox: Path) -> None:
        _write(sandbox, "dead-link", extra="See [[article:nowhere]].")
        with pytest.raises(lib.LibraryError, match=r"\[\[article:nowhere\]\]"):
            lib.load_library()

    def test_dead_question_reference_fails_the_load(self, sandbox: Path) -> None:
        _write(sandbox, "dead-drill", extra="Try [[question:lr-99999]].")
        with pytest.raises(lib.LibraryError, match="not in the bank"):
            lib.load_library()

    def test_prerequisite_cycle_is_detected(self, sandbox: Path) -> None:
        _write(sandbox, "cycle-a", prerequisites="cycle-b")
        _write(sandbox, "cycle-b", prerequisites="cycle-a")
        with pytest.raises(lib.LibraryError, match="prerequisite cycle"):
            lib.load_library()

    def test_valid_cross_references_load(self, sandbox: Path) -> None:
        _write(sandbox, "base", concepts="weaken")
        _write(
            sandbox,
            "derived",
            prerequisites="base",
            extra="See [[article:base]] and [[concept:strengthen]].",
        )
        articles = lib.load_library()
        assert set(articles) == {"base", "derived"}
        assert articles["derived"].prerequisites == ["base"]


class TestTracks:
    def _tracks(self, box: Path, items: list[dict[str, object]]) -> None:
        (box.parent / lib.TRACKS_FILE).write_text(
            json.dumps({"items": items}), encoding="utf-8"
        )

    def test_unknown_article_in_a_track_fails(self, sandbox: Path) -> None:
        _write(sandbox, "known")
        self._tracks(
            sandbox,
            [
                {
                    "id": "t1",
                    "name": "T",
                    "summary": "s",
                    "goal": "g",
                    "article_ids": ["known", "missing"],
                }
            ],
        )
        with pytest.raises(lib.LibraryError, match="unknown article"):
            lib.load_tracks()

    def test_article_before_its_prerequisite_fails(self, sandbox: Path) -> None:
        _write(sandbox, "first")
        _write(sandbox, "second", prerequisites="first")
        self._tracks(
            sandbox,
            [
                {
                    "id": "t1",
                    "name": "T",
                    "summary": "s",
                    "goal": "g",
                    "article_ids": ["second", "first"],
                }
            ],
        )
        with pytest.raises(lib.LibraryError, match="before its prerequisite"):
            lib.load_tracks()

    def test_duration_is_computed_from_members(self, sandbox: Path) -> None:
        _write(sandbox, "first")
        _write(sandbox, "second", prerequisites="first")
        self._tracks(
            sandbox,
            [
                {
                    "id": "t1",
                    "name": "T",
                    "summary": "s",
                    "goal": "g",
                    "article_ids": ["first", "second"],
                }
            ],
        )
        view = lib.public_track_view(lib.load_tracks()["t1"])
        articles = lib.load_library()
        assert view["article_count"] == 2
        assert view["estimated_minutes"] == sum(
            articles[a].reading_minutes for a in ("first", "second")
        )

    def test_declared_duration_is_rejected(self, sandbox: Path) -> None:
        _write(sandbox, "first")
        self._tracks(
            sandbox,
            [
                {
                    "id": "t1",
                    "name": "T",
                    "summary": "s",
                    "goal": "g",
                    "article_ids": ["first"],
                    "estimated_minutes": 999,
                }
            ],
        )
        with pytest.raises(Exception, match="estimated_minutes"):
            lib.load_tracks()


class TestViews:
    def test_index_row_carries_no_body(self, sandbox: Path) -> None:
        _write(sandbox, "solo")
        row = lib.public_article_view(lib.load_library()["solo"])
        assert not hasattr(row, "blocks")
        assert row.reading_minutes >= 1

    def test_articles_teaching_covers_tags_and_inline_references(
        self, sandbox: Path
    ) -> None:
        _write(sandbox, "tagged", concepts="weaken")
        _write(sandbox, "inline", extra="See [[concept:weaken]].")
        assert lib.articles_teaching("weaken") == ["inline", "tagged"]

    def test_inbound_links(self, sandbox: Path) -> None:
        _write(sandbox, "target")
        _write(sandbox, "pointer", prerequisites="target")
        _write(sandbox, "mentioner", extra="See [[article:target]].")
        assert lib.inbound_links("target") == ["mentioner", "pointer"]


class TestSearch:
    def test_short_queries_return_nothing(self, sandbox: Path) -> None:
        _write(sandbox, "solo")
        assert lib.search_library("a") == []

    def test_title_matches_outrank_body_matches(self, sandbox: Path) -> None:
        _write(sandbox, "widget-technique", title="Widget Technique")
        _write(sandbox, "other-one", title="Other One", extra="A widget appears here.")
        hits = lib.search_library("widget")
        assert [h["id"] for h in hits] == ["widget-technique", "other-one"]
        assert hits[0]["score"] > hits[1]["score"]

    def test_hits_carry_a_snippet(self, sandbox: Path) -> None:
        _write(sandbox, "solo", extra="The negation test settles it.")
        hit = lib.search_library("negation")[0]
        assert "negation" in hit["snippet"].lower()

    # BL-20260903-06: stemming, synonyms, multi-token queries.

    def test_plural_query_matches_singular_body(self, sandbox: Path) -> None:
        _write(sandbox, "solo", extra="The assumption is unstated.")
        hits = lib.search_library("assumptions")
        assert [h["id"] for h in hits] == ["solo"]
        assert "body" in hits[0]["matched_in"]
        assert "assumption" in hits[0]["snippet"].lower()

    def test_singular_query_matches_plural_title(self, sandbox: Path) -> None:
        _write(sandbox, "many", title="Formal Fallacies")
        assert [h["id"] for h in lib.search_library("fallacy")] == ["many"]

    def test_prefix_keeps_search_as_you_type_working(self, sandbox: Path) -> None:
        _write(sandbox, "solo", extra="An assumption, unstated.")
        assert [h["id"] for h in lib.search_library("assu")] == ["solo"]

    def test_every_token_must_match_somewhere(self, sandbox: Path) -> None:
        _write(sandbox, "both", extra="Sequencing games reward frames.")
        _write(sandbox, "one", extra="Sequencing only, no second word.")
        assert [h["id"] for h in lib.search_library("sequencing games")] == ["both"]

    def test_section_abbreviation_expands_to_its_name(self, sandbox: Path) -> None:
        _write(sandbox, "lg-guide", title="Logic Games Section Guide")
        _write(sandbox, "other", title="Something Else")
        hits = lib.search_library("LG")
        assert [h["id"] for h in hits] == ["lg-guide"]
        assert "title" in hits[0]["matched_in"]

    def test_stopwords_do_not_score(self, sandbox: Path) -> None:
        _write(sandbox, "the-one", title="The One")
        _write(sandbox, "widget", title="Widget", extra="A widget.")
        assert [h["id"] for h in lib.search_library("the widget")] == ["widget"]
        assert lib.search_library("the") == []

    def test_anchor_points_at_the_first_matching_heading(self, sandbox: Path) -> None:
        _write(sandbox, "solo")
        assert lib.search_library("two")[0]["anchor"] == "two"

    # BL-20260903-06: one-edit typo tolerance, the last resort after exact.

    def test_a_mistyped_token_still_finds_its_article(self, sandbox: Path) -> None:
        _write(sandbox, "solo", extra="The assumption is unstated.")
        hits = lib.search_library("assumtion")
        assert [h["id"] for h in hits] == ["solo"]
        assert "assumption" in hits[0]["snippet"].lower()

    def test_an_exact_hit_outranks_a_mistyped_one(self, sandbox: Path) -> None:
        _write(sandbox, "right", title="Notation Habits")
        _write(sandbox, "close", title="Rotation Habits")
        hits = lib.search_library("notation")
        assert [h["id"] for h in hits] == ["right", "close"]
        assert hits[0]["score"] > hits[1]["score"]

    def test_short_words_are_not_typo_matched(self, sandbox: Path) -> None:
        """One edit on a four-letter stem is a different word, not a typo."""
        _write(sandbox, "solo", extra="Games reward frames.")
        assert lib.search_library("gapes") == []

    def test_two_edits_are_too_many(self, sandbox: Path) -> None:
        _write(sandbox, "solo", title="Parallel Reasoning")
        assert lib.search_library("parralel") == []

    def test_is_typo_covers_the_four_single_edits(self) -> None:
        assert lib.is_typo("assumption", "assumtion")  # dropped letter
        assert lib.is_typo("assumption", "assumpttion")  # inserted letter
        assert lib.is_typo("notation", "rotation")  # substituted letter
        assert lib.is_typo("fallacy", "falalcy")  # transposed letters
        assert not lib.is_typo("premis", "premium")


class TestCrossReferenceLabels:
    """Unlabelled references resolve to a readable name, not a raw id."""

    def test_article_reference_gets_the_short_title(self, sandbox: Path) -> None:
        (sandbox / "target-piece.md").write_text(
            MINIMAL.format(
                id="target-piece",
                title="Conditional Logic — Necessary and Sufficient",
                concepts="",
                prerequisites="",
                extra="",
            ),
            encoding="utf-8",
        )
        _write(sandbox, "pointer", extra="See [[article:target-piece]].")
        spans = lib._iter_spans(lib.load_library()["pointer"].blocks)
        ref = next(s for s in spans if s.kind == "article")
        # The subtitle after the em-dash is right at the head of a page and
        # unreadable mid-sentence.
        assert ref.text == "Conditional Logic"
        assert ref.ref_id == "target-piece"

    def test_concept_reference_gets_the_concept_name(self, sandbox: Path) -> None:
        _write(sandbox, "pointer", extra="See [[concept:weaken]].")
        spans = lib._iter_spans(lib.load_library()["pointer"].blocks)
        ref = next(s for s in spans if s.kind == "concept")
        assert ref.text == "Weaken Question"

    def test_an_authored_label_is_left_alone(self, sandbox: Path) -> None:
        _write(sandbox, "pointer", extra="See [[concept:weaken|the weaken family]].")
        spans = lib._iter_spans(lib.load_library()["pointer"].blocks)
        ref = next(s for s in spans if s.kind == "concept")
        assert ref.text == "the weaken family"

    def test_question_references_keep_their_id(self, sandbox: Path) -> None:
        """A drill id reads fine as a chip; a title would be wrong there."""
        _write(sandbox, "pointer", extra="Try [[question:lr-001]].")
        spans = lib._iter_spans(lib.load_library()["pointer"].blocks)
        ref = next(s for s in spans if s.kind == "question")
        assert ref.text == "lr-001"


class TestScaffold:
    """BL-20260905-53 — a section with no article at all is now reachable.

    ``expand`` drafts a body and cannot write frontmatter, so
    :func:`_host_article` dropped every gap in a section that had no article
    yet: the autonomous cycle could improve the library but never widen it.
    :func:`scaffold_article` writes that frontmatter.
    """

    #: A concept the catalog files under RC only, so an LR-only library has
    #: nowhere to host it.
    RC_ONLY_CONCEPT = "main-point"

    @staticmethod
    def _report_with_rc_gap(concept_id: str) -> dict:
        report = lib.library_audit()
        report["coverage"]["concepts_untaught"] = [concept_id]
        return report

    def test_an_uncovered_section_is_unreachable_until_it_is_scaffolded(
        self, sandbox: Path
    ) -> None:
        _write(sandbox, "lr-hub")  # LR only
        concept = bank_mod.load_concepts()[self.RC_ONLY_CONCEPT]
        assert concept.sections == ["RC"]

        before = lib.pick_librarian_targets(
            self._report_with_rc_gap(self.RC_ONLY_CONCEPT), limit=5
        )
        assert not [
            r for r in before if r.action == "expand"
        ], "with no RC article the gap has no host and is dropped"

        path = lib.scaffold_article(
            "rc-hub",
            title="Reading Comprehension — Where To Start",
            summary="An orientation to the RC section.",
            kind="section-guide",
            sections=["RC"],
        )
        assert path == sandbox / "rc-hub.md"

        article = lib.load_library()["rc-hub"]
        assert article.sections == ["RC"]
        # The frontmatter the agent cannot write: id, level and review status.
        assert article.id == "rc-hub"
        assert article.level == "core"
        assert article.status == "draft"

        after = lib.pick_librarian_targets(
            self._report_with_rc_gap(self.RC_ONLY_CONCEPT), limit=5
        )
        expansions = [r for r in after if r.action == "expand"]
        assert [r.article_id for r in expansions] == ["rc-hub"]
        assert self.RC_ONLY_CONCEPT in (expansions[0].gap or "")

    def test_a_malformed_or_duplicate_id_is_refused(self, sandbox: Path) -> None:
        with pytest.raises(ValueError, match="lower-case words"):
            lib.scaffold_article("Not An Id", title="T", summary="S", sections=["LR"])
        lib.scaffold_article("rc-hub", title="T", summary="S", sections=["RC"])
        with pytest.raises(ValueError, match="already exists"):
            lib.scaffold_article("rc-hub", title="T", summary="S", sections=["RC"])

    def test_a_scaffold_that_breaks_the_load_is_rolled_back(
        self, sandbox: Path
    ) -> None:
        """The corpus never keeps an article that fails cross-reference checks."""
        with pytest.raises(lib.LibraryError, match="no-such-concept"):
            lib.scaffold_article(
                "bad-hub",
                title="T",
                summary="S",
                sections=["RC"],
                concepts=["no-such-concept"],
            )
        assert not (sandbox / "bad-hub.md").exists()
        assert "bad-hub" not in lib.load_library()

    def test_the_command_scaffolds_and_says_what_to_run_next(
        self, sandbox: Path
    ) -> None:
        from io import StringIO

        from django.core.management import call_command

        out = StringIO()
        call_command(
            "lsat_library",
            "scaffold",
            "--article",
            "rc-hub",
            "--title",
            "Reading Comprehension",
            "--summary",
            "An orientation to the RC section.",
            "--section",
            "RC",
            stdout=out,
        )
        assert (sandbox / "rc-hub.md").is_file()
        assert "rc-hub" in lib.load_library()
        assert "lsat_library review --article rc-hub" in out.getvalue()
