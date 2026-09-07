"""The shipped corpus — coverage floors that make it a library, not a stub.

Spec 048 T-010 (FR-5, NFR-UPL-1). These assert properties of the *real*
content under `data/library/`, so a future edit that thins it out or drops a
section's coverage fails CI rather than degrading quietly.
"""

from __future__ import annotations

import pytest

from law_ai.lsat.services import bank as bank_mod
from law_ai.lsat.services.library import (
    THIN_ARTICLE_WORDS,
    article_text,
    load_library,
    load_tracks,
)

#: Spec 048 FR-5. Not the current count — the floor the spec commits to.
MIN_ARTICLES = 30


@pytest.fixture(scope="module")
def articles() -> dict:
    return load_library()


def test_corpus_meets_the_article_floor(articles: dict) -> None:
    assert len(articles) >= MIN_ARTICLES


def test_every_required_kind_is_represented(articles: dict) -> None:
    kinds = {a.kind for a in articles.values()}
    assert kinds >= {
        "orientation",
        "foundation",
        "section-guide",
        "question-type",
        "technique",
        "strategy",
        "review-method",
    }


@pytest.mark.parametrize("section", ["LR", "RC", "LG", "WS"])
def test_every_section_has_a_guide_and_supporting_articles(
    articles: dict, section: str
) -> None:
    serving = [a for a in articles.values() if section in a.sections]
    assert any(
        a.kind == "section-guide" for a in serving
    ), f"{section} has no section guide"
    assert len(serving) >= 2, f"{section} is served by only {len(serving)} article(s)"


def test_no_article_is_thin(articles: dict) -> None:
    thin = {
        a.id: a.word_count
        for a in articles.values()
        if a.word_count < THIN_ARTICLE_WORDS
    }
    assert thin == {}


def test_every_concept_is_taught_somewhere(articles: dict) -> None:
    taught = {c for a in articles.values() for c in a.concepts}
    untaught = sorted(set(bank_mod.load_concepts()) - taught)
    assert untaught == [], f"concepts no article teaches: {untaught}"


def test_every_archetype_is_covered(articles: dict) -> None:
    from law_ai.lsat.factory import taxonomy

    covered = {x for a in articles.values() for x in a.archetypes}
    uncovered = sorted(set(taxonomy.by_id()) - covered)
    assert uncovered == [], f"archetypes no article covers: {uncovered}"


def test_every_article_belongs_to_a_track(articles: dict) -> None:
    tracked = {a for t in load_tracks().values() for a in t.article_ids}
    assert sorted(set(articles) - tracked) == []


def test_every_article_carries_a_worked_example_and_takeaways(articles: dict) -> None:
    # The loader enforces this, but asserting it here means the *corpus* test
    # fails with a readable message rather than the whole module erroring out.
    for article in articles.values():
        anchors = {e.anchor for e in article.outline}
        assert "key-takeaways" in anchors, article.id
        assert any(
            b.block_type == "callout" and b.variant == "example" for b in article.blocks
        ), article.id


def test_content_is_original_and_framed_as_a_study_aid(articles: dict) -> None:
    """NFR-UPL-1 / NG1: original (CC0), and no outcome claims."""
    banned = ("guaranteed score", "score guarantee", "will raise your score")
    for article in articles.values():
        assert article.source == "original (CC0)", article.id
        body = article_text(article).lower()
        for phrase in banned:
            assert phrase not in body, f"{article.id} claims an outcome: {phrase!r}"


def test_structural_claims_about_the_exam_carry_a_reference(articles: dict) -> None:
    """Spec 048 R3: an article describing the exam's format cites a source."""
    for article in articles.values():
        if article.kind in ("orientation", "section-guide"):
            assert (
                article.references
            ), f"{article.id} describes exam structure with no reference"


# ---------------------------------------------------------------------------
# The authoring template (BL-20260903-09)
# ---------------------------------------------------------------------------


def _template_path():
    from law_ai.lsat.services.library import LIBRARY_DIRNAME

    return bank_mod.DATA_DIR / LIBRARY_DIRNAME / "_template.md"


def test_authoring_template_exists_and_is_not_an_article(articles: dict) -> None:
    """``_template.md`` is where a new author starts — never a published entry."""
    assert _template_path().is_file()
    assert "_template" not in articles


def test_authoring_template_parses_and_uses_every_construct(articles: dict) -> None:
    """The template must stay a valid article and exercise the whole dialect.

    Parsed under its own ``_template`` id and cross-checked against the real
    corpus, so a construct the parser stops accepting, or a placeholder id
    that drifts out of the catalog, fails here rather than in an author's
    first copy.
    """
    from law_ai.lsat.services import library as lib

    text = _template_path().read_text(encoding="utf-8")
    template = lib.parse_article(
        text, article_id="_template", where="library/_template.md"
    )
    lib._check_cross_references({**articles, "_template": template})

    block_types = {b.block_type for b in template.blocks}
    assert block_types == {
        "heading",
        "paragraph",
        "list",
        "callout",
        "table",
        "notation",
    }
    variants = {b.variant for b in template.blocks if b.block_type == "callout"}
    assert variants == {"example", "trap", "tip", "note", "warning", "drill"}
    assert {b.ordered for b in template.blocks if b.block_type == "list"} == {
        True,
        False,
    }
    assert any(b.level == 3 for b in template.outline)
    span_kinds = {s.kind for s in lib._iter_spans(template.blocks)}
    assert span_kinds >= {
        "text",
        "strong",
        "em",
        "code",
        "link",
        "concept",
        "article",
        "question",
    }
    # Every frontmatter key the docstring documents is present as a placeholder.
    front, _ = lib.split_frontmatter(text, where="library/_template.md")
    keys = set(lib.parse_frontmatter(front, where="library/_template.md"))
    assert keys >= {
        "id",
        "title",
        "kind",
        "level",
        "sections",
        "summary",
        "concepts",
        "archetypes",
        "prerequisites",
        "related",
        "tags",
        "status",
        "last_reviewed",
        "revision",
        "references",
    }


def test_authoring_template_survives_a_rename() -> None:
    """Copy, rename, swap the id: the documented workflow yields a valid article."""
    from law_ai.lsat.services import library as lib

    text = _template_path().read_text(encoding="utf-8")
    renamed = text.replace("id: _template", "id: my-new-article", 1)
    article = lib.parse_article(
        renamed, article_id="my-new-article", where="library/my-new-article.md"
    )
    assert article.id == "my-new-article"
    assert article.word_count > 0
