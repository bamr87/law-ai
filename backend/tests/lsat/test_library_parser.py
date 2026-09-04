"""Article dialect parser — every construct, and one failure per rule.

Spec 048 T-001 (FR-1, FR-2, NFR-SAFETY-1, AC-2). These tests exercise
`parse_article` directly rather than through `load_library`, so a dialect
regression is located at the parser rather than blamed on the corpus.
"""

from __future__ import annotations

import pytest

from law_ai.lsat.services.library import (
    CalloutBlock,
    HeadingBlock,
    LibraryError,
    ListBlock,
    NotationBlock,
    ParagraphBlock,
    TableBlock,
    parse_article,
    parse_frontmatter,
    parse_spans,
    slugify,
    split_frontmatter,
)

FRONTMATTER = """---
id: sample-article
title: Sample Article
kind: technique
level: core
sections: [LR]
summary: A sample used by the parser tests.
concepts: []
prerequisites: []
related: []
tags: [sample]
status: draft
last_reviewed: 2026-09-03
revision: 1
references:
  - title: A source
    url: https://example.org/source
---
"""

BODY = """
## First section

A paragraph with **strong**, *emphasis*, `code`, an
[external link](https://example.org) and a plain sentence.

- bullet one
- bullet two

1. step one
2. step two

| Column A | Column B |
|---|---|
| a1 | b1 |
| a2 | b2 |

```a caption
A → B
¬B → ¬A
```

## Second section

> [!example] A worked example
> The example body.
>
> - with a list
> - inside it

### A subsection

More prose.

## Key takeaways

- one takeaway
- another takeaway
"""


def _article(body: str = BODY, frontmatter: str = FRONTMATTER):
    return parse_article(
        frontmatter + body, article_id="sample-article", where="library/sample.md"
    )


class TestFrontmatter:
    def test_scalars_inline_lists_and_reference_blocks(self) -> None:
        meta = parse_frontmatter(
            split_frontmatter(FRONTMATTER + BODY, where="x")[0], where="x"
        )
        assert meta["id"] == "sample-article"
        assert meta["sections"] == ["LR"]
        assert meta["concepts"] == []
        assert meta["references"] == [
            {"title": "A source", "url": "https://example.org/source"}
        ]

    def test_missing_delimiter_is_an_error_naming_the_file(self) -> None:
        with pytest.raises(LibraryError, match=r"library/sample\.md"):
            parse_article(
                "no frontmatter here", article_id="x", where="library/sample.md"
            )

    def test_unterminated_frontmatter_is_an_error(self) -> None:
        with pytest.raises(LibraryError, match="unterminated"):
            split_frontmatter("---\nid: x\n", where="library/sample.md")

    def test_duplicate_key_is_an_error(self) -> None:
        with pytest.raises(LibraryError, match="duplicate"):
            parse_frontmatter("id: a\nid: b\n", where="x")

    def test_id_must_match_the_file_name(self) -> None:
        with pytest.raises(LibraryError, match="does not match the file name"):
            parse_article(
                FRONTMATTER + BODY, article_id="other-id", where="library/other-id.md"
            )


class TestBlocks:
    def test_every_block_type_is_produced(self) -> None:
        kinds = {b.block_type for b in _article().blocks}
        assert kinds == {"heading", "paragraph", "list", "table", "notation", "callout"}

    def test_headings_carry_levels_and_anchors(self) -> None:
        headings = [b for b in _article().blocks if isinstance(b, HeadingBlock)]
        assert [h.level for h in headings] == [2, 2, 3, 2]
        assert headings[0].anchor == "first-section"
        assert headings[-1].anchor == "key-takeaways"

    def test_ordered_and_unordered_lists_are_distinguished(self) -> None:
        lists = [b for b in _article().blocks if isinstance(b, ListBlock)]
        assert lists[0].ordered is False
        assert lists[1].ordered is True
        assert len(lists[1].items) == 2

    def test_table_headers_and_rows(self) -> None:
        table = next(b for b in _article().blocks if isinstance(b, TableBlock))
        assert len(table.headers) == 2
        assert len(table.rows) == 2

    def test_table_without_separator_row_is_an_error(self) -> None:
        body = BODY.replace("|---|---|\n", "")
        with pytest.raises(LibraryError, match="separator row"):
            _article(body)

    def test_notation_keeps_its_lines_and_caption(self) -> None:
        notation = next(b for b in _article().blocks if isinstance(b, NotationBlock))
        assert notation.caption == "a caption"
        assert notation.lines == ["A → B", "¬B → ¬A"]

    def test_unterminated_fence_is_an_error(self) -> None:
        with pytest.raises(LibraryError, match="unterminated"):
            _article(BODY.replace("¬B → ¬A\n```", "¬B → ¬A"))

    def test_callout_carries_variant_title_and_children(self) -> None:
        callout = next(b for b in _article().blocks if isinstance(b, CalloutBlock))
        assert callout.variant == "example"
        assert callout.title == "A worked example"
        assert [c.block_type for c in callout.blocks] == ["paragraph", "list"]

    def test_unknown_callout_variant_is_an_error(self) -> None:
        with pytest.raises(LibraryError, match="unknown callout variant"):
            _article(BODY.replace("> [!example]", "> [!aside]"))

    def test_bare_quote_block_is_an_error(self) -> None:
        with pytest.raises(LibraryError, match="variant marker"):
            _article(BODY.replace("> [!example] A worked example", "> just a quote"))

    def test_h1_is_reserved_for_the_title(self) -> None:
        with pytest.raises(LibraryError, match="reserved for the frontmatter title"):
            _article(BODY.replace("## First section", "# First section"))

    def test_heading_deeper_than_h3_is_rejected(self) -> None:
        with pytest.raises(LibraryError, match="heading depth"):
            _article(BODY.replace("### A subsection", "#### A subsection"))


class TestSpans:
    def test_inline_kinds(self) -> None:
        spans = parse_spans(
            "plain **bold** *italic* `code` [link](https://x.test) "
            "[[concept:weaken]] [[article:other|Other]] [[question:lr-001]]",
            where="x",
        )
        kinds = [s.kind for s in spans if s.kind != "text"]
        assert kinds == [
            "strong",
            "em",
            "code",
            "link",
            "concept",
            "article",
            "question",
        ]

    def test_wiki_label_overrides_the_id(self) -> None:
        span = next(
            s
            for s in parse_spans("[[article:other|Other]]", where="x")
            if s.kind == "article"
        )
        assert span.ref_id == "other"
        assert span.text == "Other"

    def test_raw_html_is_rejected(self) -> None:
        with pytest.raises(LibraryError, match="raw HTML"):
            parse_spans("a <script>alert(1)</script> b", where="x")

    def test_unknown_cross_reference_kind_is_rejected(self) -> None:
        with pytest.raises(LibraryError, match="unknown cross-reference kind"):
            parse_spans("[[passage:rc-01]]", where="x")

    def test_cross_reference_without_a_kind_is_rejected(self) -> None:
        with pytest.raises(LibraryError, match="must be"):
            parse_spans("[[weaken]]", where="x")

    def test_relative_link_target_is_rejected(self) -> None:
        with pytest.raises(LibraryError, match="absolute URL"):
            parse_spans("[text](/local/path)", where="x")

    def test_unbalanced_markup_is_rejected(self) -> None:
        with pytest.raises(LibraryError, match="unbalanced"):
            parse_spans("an **unclosed bold run", where="x")


class TestStructuralGates:
    def test_fewer_than_three_sections_fails(self) -> None:
        body = BODY.replace("## Second section", "Second section")
        with pytest.raises(LibraryError, match="at least 3"):
            _article(body)

    def test_missing_worked_example_fails(self) -> None:
        body = BODY.replace("[!example]", "[!note]")
        with pytest.raises(LibraryError, match="worked example"):
            _article(body)

    def test_missing_key_takeaways_fails(self) -> None:
        body = BODY.replace("## Key takeaways", "## Wrapping up")
        with pytest.raises(LibraryError, match="Key takeaways"):
            _article(body)

    def test_key_takeaways_without_a_list_fails(self) -> None:
        body = BODY.replace(
            "- one takeaway\n- another takeaway\n", "Just a closing paragraph.\n"
        )
        with pytest.raises(LibraryError, match="followed by a list"):
            _article(body)


class TestDerivedValues:
    def test_reading_minutes_is_computed_not_declared(self) -> None:
        article = _article()
        assert article.word_count > 0
        assert article.reading_minutes >= 1

    def test_declaring_a_derived_field_is_rejected(self) -> None:
        frontmatter = FRONTMATTER.replace(
            "revision: 1\n", "revision: 1\nreading_minutes: 99\n"
        )
        with pytest.raises(LibraryError, match="computed from the body"):
            _article(frontmatter=frontmatter)

    def test_outline_mirrors_the_headings(self) -> None:
        article = _article()
        assert [e.anchor for e in article.outline] == [
            "first-section",
            "second-section",
            "a-subsection",
            "key-takeaways",
        ]

    def test_slugify(self) -> None:
        assert slugify("Key takeaways") == "key-takeaways"
        assert slugify("All, some & most!") == "all-some-most"
        assert slugify("!!!") == "section"


class TestParagraphAssembly:
    def test_wrapped_lines_join_into_one_paragraph(self) -> None:
        paragraphs = [b for b in _article().blocks if isinstance(b, ParagraphBlock)]
        text = "".join(s.text for s in paragraphs[0].spans)
        assert "an\n" not in text
        assert "and a plain sentence." in text
