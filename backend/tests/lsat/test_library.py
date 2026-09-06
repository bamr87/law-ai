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
