"""LSAT knowledge library — long-form, cross-linked study material (spec 048).

Everything else in this module is a *drill*: a keyed question, a solve guide
for one item, a writing prompt. The library is the layer that explains the
exam itself — how it is built and scored, what each section demands, what each
recurring question family rewards, which techniques work and why, how to pace a
section, how to review an error. It is the material a learner *studies*, as
opposed to the material they *practise against*.

Authoring format
----------------

Start a new article by copying ``data/library/_template.md`` — it carries every
frontmatter key with a placeholder value and one instance of every block and
span the parser accepts, and the corpus test keeps it parseable. Files whose
name starts with ``_`` are never loaded as articles.

One Markdown file per article under ``data/library/``, with frontmatter::

    ---
    id: lr-assumption-family
    title: The Assumption Family
    kind: question-type
    level: core
    sections: [LR]
    summary: One sentence a reader can scan in an index.
    concepts: [necessary-assumption, sufficient-assumption]
    prerequisites: [lr-argument-anatomy]
    related: [lr-strengthen-and-weaken]
    tags: [assumption, negation-test]
    status: reviewed
    last_reviewed: 2026-09-03
    revision: 1
    references:
      - title: LSAC — About the LSAT
        url: https://www.lsac.org/lsat
    ---

    ## A level-two heading

    A paragraph with **strong**, *emphasis*, ``code``, an
    [external link](https://example.org) and typed cross-references:
    [[concept:necessary-assumption]], [[article:lr-argument-anatomy]],
    [[question:lr-001|this drill]].

Markdown is what a human reviews in a diff and what an agent can patch one
section at a time — but *neither client ever sees Markdown*. The body is
compiled here into a list of typed blocks (:class:`HeadingBlock`,
:class:`ParagraphBlock`, :class:`ListBlock`, :class:`CalloutBlock`,
:class:`TableBlock`, :class:`NotationBlock`) carrying typed inline
:class:`Span` s. Both products render blocks, which means no Markdown
dependency in either frontend, no ``dangerouslySetInnerHTML`` anywhere, and one
rendering contract the two products cannot drift apart on (spec 048 FR-2/FR-11,
NFR-SAFETY-1).

The dialect is deliberately *closed*: a construct the parser does not
recognise is an error naming the file, never markup passed through to a client.

Follows the :mod:`law_ai.lsat.services.bank` pattern throughout — file-backed,
Pydantic-validated, lazy ``@lru_cache`` loaders that fail loudly on
cross-reference drift, and a public view that strips what an index does not
need.
"""

from __future__ import annotations

import json
import re
from datetime import UTC, date, datetime
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from law_ai.lsat.services import bank as _bank
from law_ai.lsat.services.bank import Reference, Section

LIBRARY_DIRNAME = "library"
TRACKS_FILE = "library_tracks.json"

#: Average adult reading speed for expository prose. Used to *compute*
#: ``reading_minutes``; declaring it in frontmatter is rejected, because a
#: declared value goes stale the moment anyone expands a section.
WORDS_PER_MINUTE = 200

#: An article below this word count is reported as thin by the audit. It is
#: not a load error: a short, sharp technique note is legitimate, but a whole
#: corpus of them means the library stopped being study material.
THIN_ARTICLE_WORDS = 350

#: An article whose ``last_reviewed`` is older than this is reported as stale.
#: Roughly one exam cycle: long enough that a real LSAC format change would
#: have landed, short enough that nothing sits unchecked for a year.
STALE_AFTER_DAYS = 120

ArticleKind = Literal[
    "orientation",  # what the exam is, how it is scored, how to plan for it
    "section-guide",  # a deep dive on one section as a whole
    "question-type",  # one recurring question family
    "technique",  # a repeatable method (diagramming, mapping, elimination)
    "strategy",  # pacing, guessing, section order, test-day conduct
    "foundation",  # the logic the sections rest on
    "review-method",  # how to learn from an attempt after it is over
]

#: Where an article sits in the reading order, independent of its kind.
ArticleLevel = Literal["foundation", "core", "advanced"]

ReviewStatus = Literal["draft", "reviewed", "needs-review"]

CalloutVariant = Literal["example", "trap", "tip", "note", "warning", "drill"]

SpanKind = Literal[
    "text", "strong", "em", "code", "link", "concept", "article", "question"
]

BlockType = Literal["heading", "paragraph", "list", "callout", "table", "notation"]


class LibraryError(ValueError):
    """Raised when an article cannot be parsed or fails an integrity rule.

    Always carries the file (or article id) it came from: a message that does
    not name the file turns a one-line fix into a search.
    """


# ---------------------------------------------------------------------------
# Inline spans
# ---------------------------------------------------------------------------


class Span(BaseModel):
    """One run of inline content.

    ``kind`` decides how it renders and what the other fields mean:

    ``text``/``strong``/``em``/``code``
        ``text`` is the content; ``href`` and ``ref_id`` are unset.
    ``link``
        ``href`` is an absolute external URL.
    ``concept``/``article``/``question``
        ``ref_id`` is the target id, resolved and validated at load time;
        ``text`` is the label to show.
    """

    kind: SpanKind
    text: str
    href: str | None = None
    ref_id: str | None = None


Cell = list[Span]


# ---------------------------------------------------------------------------
# Blocks
# ---------------------------------------------------------------------------


class HeadingBlock(BaseModel):
    block_type: Literal["heading"] = "heading"
    level: int = Field(ge=2, le=3)
    text: str
    anchor: str


class ParagraphBlock(BaseModel):
    block_type: Literal["paragraph"] = "paragraph"
    spans: list[Span] = Field(min_length=1)


class ListBlock(BaseModel):
    block_type: Literal["list"] = "list"
    ordered: bool = False
    items: list[Cell] = Field(min_length=1)


class NotationBlock(BaseModel):
    """A fenced block of symbolic notation or a worked board, rendered mono.

    Not a code block in the programming sense — it is where conditional
    chains, game boards and elimination traces live, which is exactly the
    content that must not be reflowed.
    """

    block_type: Literal["notation"] = "notation"
    lines: list[str] = Field(min_length=1)
    caption: str | None = None


class TableBlock(BaseModel):
    block_type: Literal["table"] = "table"
    headers: list[Cell] = Field(min_length=1)
    rows: list[list[Cell]] = Field(min_length=1)

    @model_validator(mode="after")
    def _rows_match_headers(self) -> TableBlock:
        width = len(self.headers)
        for i, row in enumerate(self.rows, start=1):
            if len(row) != width:
                raise ValueError(
                    f"table row {i} has {len(row)} cells, header has {width}"
                )
        return self


CalloutChild = Annotated[
    ParagraphBlock | ListBlock | NotationBlock,
    Field(discriminator="block_type"),
]


class CalloutBlock(BaseModel):
    """An aside pulled out of the flow: a worked example, a trap, a drill.

    ``example`` is load-bearing — every article must contain at least one
    (FR-4), because an explanation without a worked instance is a definition.
    """

    block_type: Literal["callout"] = "callout"
    variant: CalloutVariant
    title: str
    blocks: list[CalloutChild] = Field(min_length=1)


Block = Annotated[
    HeadingBlock
    | ParagraphBlock
    | ListBlock
    | CalloutBlock
    | TableBlock
    | NotationBlock,
    Field(discriminator="block_type"),
]


class OutlineEntry(BaseModel):
    """One row of an article's in-page outline, derived from its headings."""

    level: int
    text: str
    anchor: str


# ---------------------------------------------------------------------------
# Article + track
# ---------------------------------------------------------------------------


class Article(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    title: str
    kind: ArticleKind
    level: ArticleLevel
    summary: str = Field(min_length=1)
    sections: list[Section] = Field(
        default_factory=list,
        description="Exam sections this article serves. Empty = cross-cutting.",
    )
    concepts: list[str] = Field(
        default_factory=list,
        description="Concept catalog ids this article teaches. Resolved at load.",
    )
    archetypes: list[str] = Field(
        default_factory=list,
        description="Factory taxonomy archetype ids this article covers.",
    )
    prerequisites: list[str] = Field(
        default_factory=list,
        description="Article ids to read first. The graph must be acyclic.",
    )
    related: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    status: ReviewStatus = "draft"
    last_reviewed: date
    revision: int = Field(default=1, ge=1)
    source: str = "original (CC0)"
    references: list[Reference] = Field(default_factory=list)

    # Derived at parse time — never authored.
    blocks: list[Block] = Field(min_length=1)
    outline: list[OutlineEntry] = Field(default_factory=list)
    word_count: int = Field(ge=0)
    reading_minutes: int = Field(ge=1)


class ArticleSummary(BaseModel):
    """Index row: everything a contents rail needs, and no body.

    The index ships on first paint of both readers; sending 30 article bodies
    to render a list of 30 titles is the difference between a fast rail and a
    900 KB one (NFR-PERF-1).
    """

    id: str
    title: str
    kind: ArticleKind
    level: ArticleLevel
    summary: str
    sections: list[Section]
    concepts: list[str]
    prerequisites: list[str]
    related: list[str]
    tags: list[str]
    status: ReviewStatus
    last_reviewed: date
    reading_minutes: int
    word_count: int


class Track(BaseModel):
    """A curated reading order with a stated goal."""

    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    summary: str
    goal: str
    article_ids: list[str] = Field(min_length=1)
    tags: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Frontmatter parser
# ---------------------------------------------------------------------------

_FM_KEY_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*):\s*(.*)$")
_LIST_ITEM_RE = re.compile(r"^-\s+(.*)$")


def _scalar(raw: str) -> str:
    value = raw.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        return value[1:-1]
    return value


def _inline_list(raw: str) -> list[str]:
    inner = raw.strip()[1:-1].strip()
    if not inner:
        return []
    return [_scalar(part) for part in inner.split(",") if part.strip()]


def _parse_frontmatter_block(lines: list[str], *, where: str) -> Any:
    """Parse the indented body under a bare ``key:`` line.

    Two shapes only: a list of scalars, or a list of single-level mappings
    (which is how ``references`` is authored). Anything else is an error.
    """
    entries: list[Any] = []
    current: dict[str, str] | None = None
    for line in lines:
        stripped = line.strip()
        item = _LIST_ITEM_RE.match(stripped)
        if item:
            content = item.group(1)
            key_match = _FM_KEY_RE.match(content)
            if key_match and key_match.group(2):
                current = {key_match.group(1): _scalar(key_match.group(2))}
                entries.append(current)
            else:
                current = None
                entries.append(_scalar(content))
            continue
        key_match = _FM_KEY_RE.match(stripped)
        if key_match and current is not None:
            current[key_match.group(1)] = _scalar(key_match.group(2))
            continue
        raise LibraryError(f"{where}: cannot parse frontmatter line {line!r}")
    return entries


def parse_frontmatter(text: str, *, where: str) -> dict[str, Any]:
    """Parse the restricted frontmatter dialect into a plain dict.

    Supports ``key: scalar``, ``key: [a, b]``, and a bare ``key:`` followed by
    an indented list of scalars or of single-level mappings. No anchors, no
    nesting beyond that, no multi-line scalars — the schema does not need them
    and a general YAML parser is a dependency plus an attack surface for
    content that is compiled and rendered as typed blocks anyway.
    """
    out: dict[str, Any] = {}
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        if not line.strip():
            i += 1
            continue
        if line[:1].isspace():
            raise LibraryError(f"{where}: unexpected indentation at {line!r}")
        match = _FM_KEY_RE.match(line)
        if not match:
            raise LibraryError(f"{where}: cannot parse frontmatter line {line!r}")
        key, rest = match.group(1), match.group(2).strip()
        if key in out:
            raise LibraryError(f"{where}: duplicate frontmatter key {key!r}")
        if rest.startswith("[") and rest.endswith("]"):
            out[key] = _inline_list(rest)
            i += 1
            continue
        if rest:
            out[key] = _scalar(rest)
            i += 1
            continue
        block: list[str] = []
        j = i + 1
        while j < len(lines) and (not lines[j].strip() or lines[j][:1].isspace()):
            if lines[j].strip():
                block.append(lines[j])
            j += 1
        if not block:
            raise LibraryError(f"{where}: key {key!r} has no value")
        out[key] = _parse_frontmatter_block(block, where=where)
        i = j
    return out


def split_frontmatter(text: str, *, where: str) -> tuple[str, str]:
    """Split ``---``-delimited frontmatter from the body."""
    if not text.startswith("---\n"):
        raise LibraryError(f"{where}: file must start with a '---' frontmatter block")
    end = text.find("\n---\n", 3)
    if end == -1:
        raise LibraryError(f"{where}: unterminated frontmatter block")
    return text[4:end], text[end + 5 :]


# ---------------------------------------------------------------------------
# Inline parser
# ---------------------------------------------------------------------------

_INLINE_RE = re.compile(
    r"`(?P<code>[^`]+)`"
    r"|\[\[(?P<wiki>[^\]\[]+)\]\]"
    r"|\[(?P<ltext>[^\]\[]+)\]\((?P<lhref>[^)\s]+)\)"
    r"|\*\*(?P<strong>[^*]+)\*\*"
    r"|\*(?P<em>[^*]+)\*"
)

_WIKI_KINDS: dict[str, SpanKind] = {
    "concept": "concept",
    "article": "article",
    "question": "question",
}

_HTML_RE = re.compile(r"<[A-Za-z/!]")
_LEFTOVER_RE = re.compile(r"\*\*|\[\[|\]\]")


def _wiki_span(payload: str, *, where: str) -> Span:
    body, _, label = payload.partition("|")
    kind_name, sep, ref_id = body.partition(":")
    if not sep:
        raise LibraryError(
            f"{where}: cross-reference [[{payload}]] must be "
            "[[concept:id]], [[article:id]] or [[question:id]]"
        )
    kind = _WIKI_KINDS.get(kind_name.strip())
    if kind is None:
        raise LibraryError(
            f"{where}: unknown cross-reference kind {kind_name.strip()!r} "
            f"in [[{payload}]]"
        )
    ref = ref_id.strip()
    if not ref:
        raise LibraryError(f"{where}: cross-reference [[{payload}]] has no target id")
    return Span(kind=kind, text=(label.strip() or ref), ref_id=ref)


def parse_spans(text: str, *, where: str) -> list[Span]:
    """Compile one line of inline content into typed spans.

    Raw HTML is rejected outright rather than escaped: an article has no
    legitimate reason to contain a tag, and refusing it here means neither
    client needs a sanitiser (NFR-SAFETY-1).
    """
    if _HTML_RE.search(text):
        raise LibraryError(f"{where}: raw HTML is not allowed in article content")
    spans: list[Span] = []
    pos = 0
    for match in _INLINE_RE.finditer(text):
        if match.start() > pos:
            spans.append(Span(kind="text", text=text[pos : match.start()]))
        if (code := match.group("code")) is not None:
            spans.append(Span(kind="code", text=code))
        elif (wiki := match.group("wiki")) is not None:
            spans.append(_wiki_span(wiki, where=where))
        elif (ltext := match.group("ltext")) is not None:
            href = match.group("lhref")
            if not href.startswith(("http://", "https://", "#")):
                raise LibraryError(
                    f"{where}: link target {href!r} must be an absolute URL "
                    "or an in-page anchor"
                )
            spans.append(Span(kind="link", text=ltext, href=href))
        elif (strong := match.group("strong")) is not None:
            spans.append(Span(kind="strong", text=strong))
        elif (em := match.group("em")) is not None:
            spans.append(Span(kind="em", text=em))
        pos = match.end()
    if pos < len(text):
        spans.append(Span(kind="text", text=text[pos:]))

    leftover = "".join(s.text for s in spans if s.kind == "text")
    if _LEFTOVER_RE.search(leftover):
        raise LibraryError(
            f"{where}: unbalanced inline markup in {text.strip()[:60]!r} — "
            "check for an unclosed ** or [[ ]]"
        )
    return spans or [Span(kind="text", text=text)]


# ---------------------------------------------------------------------------
# Block parser
# ---------------------------------------------------------------------------

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")
_BULLET_RE = re.compile(r"^[-*]\s+(.*)$")
_ORDERED_RE = re.compile(r"^\d+\.\s+(.*)$")
_CALLOUT_RE = re.compile(r"^>\s*\[!([a-z]+)\]\s*(.*)$")
_FENCE_RE = re.compile(r"^```\s*(.*)$")
_TABLE_SEP_RE = re.compile(r"^\|[\s:|-]+\|$")


def slugify(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug or "section"


def _table_cells(line: str, *, where: str) -> list[Cell]:
    raw = line.strip()
    if not (raw.startswith("|") and raw.endswith("|")):
        raise LibraryError(f"{where}: malformed table row {line!r}")
    return [parse_spans(cell.strip(), where=where) for cell in raw[1:-1].split("|")]


def _flush_paragraph(buf: list[str], out: list[Any], *, where: str) -> None:
    if not buf:
        return
    text = " ".join(part.strip() for part in buf).strip()
    buf.clear()
    if text:
        out.append(ParagraphBlock(spans=parse_spans(text, where=where)))


def _parse_list(
    lines: list[str], start: int, *, ordered: bool, where: str
) -> tuple[ListBlock, int]:
    pattern = _ORDERED_RE if ordered else _BULLET_RE
    items: list[Cell] = []
    parts: list[str] = []
    i = start
    while i < len(lines):
        line = lines[i]
        match = pattern.match(line)
        if match:
            if parts:
                items.append(parse_spans(" ".join(parts), where=where))
            parts = [match.group(1).strip()]
            i += 1
            continue
        if line[:1].isspace() and line.strip():
            parts.append(line.strip())
            i += 1
            continue
        break
    if parts:
        items.append(parse_spans(" ".join(parts), where=where))
    if not items:
        raise LibraryError(f"{where}: empty list at line {start + 1}")
    return ListBlock(ordered=ordered, items=items), i


def _parse_fence(
    lines: list[str], start: int, *, where: str
) -> tuple[NotationBlock, int]:
    fence = _FENCE_RE.match(lines[start])
    assert fence is not None  # caller checked
    caption = fence.group(1).strip()
    body: list[str] = []
    i = start + 1
    while i < len(lines) and not lines[i].startswith("```"):
        body.append(lines[i].rstrip())
        i += 1
    if i >= len(lines):
        raise LibraryError(
            f"{where}: unterminated ``` block opened at line {start + 1}"
        )
    if not any(line.strip() for line in body):
        raise LibraryError(f"{where}: empty ``` block at line {start + 1}")
    return NotationBlock(lines=body, caption=caption or None), i + 1


def _parse_callout(
    lines: list[str], start: int, *, where: str
) -> tuple[CalloutBlock, int]:
    match = _CALLOUT_RE.match(lines[start])
    assert match is not None  # caller checked
    variant_name, title = match.group(1), match.group(2).strip()
    if variant_name not in (
        "example",
        "trap",
        "tip",
        "note",
        "warning",
        "drill",
    ):
        raise LibraryError(
            f"{where}: unknown callout variant {variant_name!r} at line {start + 1}"
        )
    inner: list[str] = []
    i = start + 1
    while i < len(lines) and lines[i].startswith(">"):
        inner.append(lines[i][1:].lstrip(" "))
        i += 1
    children = parse_blocks_from_lines(inner, where=where, allow_headings=False)
    child_blocks: list[Any] = []
    for block in children:
        if isinstance(block, ParagraphBlock | ListBlock | NotationBlock):
            child_blocks.append(block)
        else:  # pragma: no cover - defended by allow_headings=False
            raise LibraryError(
                f"{where}: a callout cannot contain a {block.block_type}"
            )
    if not child_blocks:
        raise LibraryError(f"{where}: empty callout at line {start + 1}")
    variant: CalloutVariant = variant_name  # type: ignore[assignment]
    return (
        CalloutBlock(
            variant=variant,
            title=title or variant_name.title(),
            blocks=child_blocks,
        ),
        i,
    )


def _parse_heading(line: str, *, allow_headings: bool, where: str) -> HeadingBlock:
    heading = _HEADING_RE.match(line)
    assert heading is not None  # caller checked
    level = len(heading.group(1))
    if not allow_headings:
        raise LibraryError(f"{where}: a callout cannot contain a heading")
    if level == 1:
        raise LibraryError(
            f"{where}: '# ' is reserved for the frontmatter title — "
            "start article sections at '## '"
        )
    if level > 3:
        raise LibraryError(
            f"{where}: heading depth {level} is not supported (use ## or ###)"
        )
    text = heading.group(2).strip()
    return HeadingBlock(level=level, text=text, anchor=slugify(text))


def _parse_table(lines: list[str], start: int, *, where: str) -> tuple[TableBlock, int]:
    if start + 1 >= len(lines) or not _TABLE_SEP_RE.match(lines[start + 1].strip()):
        raise LibraryError(
            f"{where}: table at line {start + 1} needs a '|---|---|' "
            "separator row under its header"
        )
    headers = _table_cells(lines[start], where=where)
    rows: list[list[Cell]] = []
    i = start + 2
    while i < len(lines) and lines[i].lstrip().startswith("|"):
        rows.append(_table_cells(lines[i], where=where))
        i += 1
    if not rows:
        raise LibraryError(f"{where}: table has a header but no rows")
    return TableBlock(headers=headers, rows=rows), i


def parse_blocks_from_lines(
    lines: list[str], *, where: str, allow_headings: bool = True
) -> list[Any]:
    out: list[Any] = []
    buf: list[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if not line.strip():
            _flush_paragraph(buf, out, where=where)
            i += 1
            continue
        if _HEADING_RE.match(line):
            _flush_paragraph(buf, out, where=where)
            out.append(_parse_heading(line, allow_headings=allow_headings, where=where))
            i += 1
            continue
        if _CALLOUT_RE.match(line):
            _flush_paragraph(buf, out, where=where)
            callout, i = _parse_callout(lines, i, where=where)
            out.append(callout)
            continue
        if line.startswith(">"):
            raise LibraryError(
                f"{where}: a '>' block must open with a variant marker, "
                "e.g. '> [!example] Title'"
            )
        if _FENCE_RE.match(line):
            _flush_paragraph(buf, out, where=where)
            notation, i = _parse_fence(lines, i, where=where)
            out.append(notation)
            continue
        if _BULLET_RE.match(line):
            _flush_paragraph(buf, out, where=where)
            bullets, i = _parse_list(lines, i, ordered=False, where=where)
            out.append(bullets)
            continue
        if _ORDERED_RE.match(line):
            _flush_paragraph(buf, out, where=where)
            numbered, i = _parse_list(lines, i, ordered=True, where=where)
            out.append(numbered)
            continue
        if line.lstrip().startswith("|"):
            _flush_paragraph(buf, out, where=where)
            table, i = _parse_table(lines, i, where=where)
            out.append(table)
            continue
        buf.append(line)
        i += 1
    _flush_paragraph(buf, out, where=where)
    return out


def parse_blocks(body: str, *, where: str) -> list[Any]:
    """Compile an article body into typed blocks."""
    blocks = parse_blocks_from_lines(body.splitlines(), where=where)
    if not blocks:
        raise LibraryError(f"{where}: article body is empty")
    return blocks


# ---------------------------------------------------------------------------
# Derived values + structural gates
# ---------------------------------------------------------------------------


def _spans_text(spans: list[Span]) -> str:
    return " ".join(s.text for s in spans)


def block_text(block: Any) -> str:
    """Flatten one block to plain text (search index, word count)."""
    if isinstance(block, HeadingBlock):
        return block.text
    if isinstance(block, ParagraphBlock):
        return _spans_text(block.spans)
    if isinstance(block, ListBlock):
        return " ".join(_spans_text(item) for item in block.items)
    if isinstance(block, NotationBlock):
        return " ".join(block.lines)
    if isinstance(block, TableBlock):
        cells = [_spans_text(c) for c in block.headers]
        cells += [_spans_text(c) for row in block.rows for c in row]
        return " ".join(cells)
    if isinstance(block, CalloutBlock):
        return " ".join([block.title, *(block_text(b) for b in block.blocks)])
    raise LibraryError(f"unknown block type {type(block).__name__}")  # pragma: no cover


def article_text(article: Article) -> str:
    """Full plain-text body — what search matches against."""
    return " ".join(block_text(b) for b in article.blocks)


def _iter_spans(blocks: list[Any]) -> list[Span]:
    out: list[Span] = []
    for block in blocks:
        if isinstance(block, ParagraphBlock):
            out.extend(block.spans)
        elif isinstance(block, ListBlock):
            for item in block.items:
                out.extend(item)
        elif isinstance(block, TableBlock):
            for cell in block.headers:
                out.extend(cell)
            for row in block.rows:
                for cell in row:
                    out.extend(cell)
        elif isinstance(block, CalloutBlock):
            out.extend(_iter_spans(list(block.blocks)))
    return out


def _check_structure(blocks: list[Any], *, where: str) -> None:
    """The four gates every published article must pass (FR-4).

    Enforced here rather than by convention because "we always include a
    worked example" is exactly the kind of rule that survives until the first
    agent-drafted expansion.
    """
    h2 = [b for b in blocks if isinstance(b, HeadingBlock) and b.level == 2]
    if len(h2) < 3:
        raise LibraryError(f"{where}: needs at least 3 '## ' sections, found {len(h2)}")
    if not any(isinstance(b, CalloutBlock) and b.variant == "example" for b in blocks):
        raise LibraryError(
            f"{where}: needs at least one worked example — add a "
            "'> [!example] …' callout"
        )
    takeaway_at = next(
        (
            i
            for i, b in enumerate(blocks)
            if isinstance(b, HeadingBlock) and b.anchor == "key-takeaways"
        ),
        None,
    )
    if takeaway_at is None:
        raise LibraryError(f"{where}: needs a '## Key takeaways' section")
    if not any(isinstance(b, ListBlock) for b in blocks[takeaway_at:]):
        raise LibraryError(f"{where}: 'Key takeaways' must be followed by a list")


def _outline(blocks: list[Any]) -> list[OutlineEntry]:
    return [
        OutlineEntry(level=b.level, text=b.text, anchor=b.anchor)
        for b in blocks
        if isinstance(b, HeadingBlock)
    ]


# ---------------------------------------------------------------------------
# Article construction
# ---------------------------------------------------------------------------

_DERIVED_FIELDS = ("blocks", "outline", "word_count", "reading_minutes")


def parse_article(text: str, *, article_id: str, where: str) -> Article:
    """Parse one article file into a validated :class:`Article`."""
    front_text, body = split_frontmatter(text, where=where)
    meta = parse_frontmatter(front_text, where=where)

    for field in _DERIVED_FIELDS:
        if field in meta:
            raise LibraryError(
                f"{where}: {field!r} is computed from the body — remove it from "
                "the frontmatter"
            )
    declared_id = meta.get("id")
    if declared_id != article_id:
        raise LibraryError(
            f"{where}: frontmatter id {declared_id!r} does not match the "
            f"file name (expected {article_id!r})"
        )

    blocks = parse_blocks(body, where=where)
    _check_structure(blocks, where=where)
    words = len(" ".join(block_text(b) for b in blocks).split())
    try:
        return Article(
            **meta,
            blocks=blocks,
            outline=_outline(blocks),
            word_count=words,
            reading_minutes=max(1, round(words / WORDS_PER_MINUTE)),
        )
    except LibraryError:
        raise
    except Exception as exc:  # pydantic ValidationError and friends
        raise LibraryError(f"{where}: {exc}") from exc


# ---------------------------------------------------------------------------
# Loaders (lazy + cached, mirrors bank.py)
# ---------------------------------------------------------------------------


def _library_dir() -> Path:
    # Resolved through the bank module so a test sandbox that monkeypatches
    # ``bank.DATA_DIR`` redirects this loader too (same trick as guides.py).
    return _bank.DATA_DIR / LIBRARY_DIRNAME


def _detect_cycle(graph: dict[str, list[str]]) -> list[str] | None:
    """Return one prerequisite cycle as a path, or None. Iterative DFS."""
    WHITE, GREY, BLACK = 0, 1, 2
    colour = dict.fromkeys(graph, WHITE)
    for root in sorted(graph):
        if colour[root] != WHITE:
            continue
        stack: list[tuple[str, int]] = [(root, 0)]
        path: list[str] = []
        colour[root] = GREY
        path.append(root)
        while stack:
            node, index = stack.pop()
            deps = graph.get(node, [])
            if index < len(deps):
                stack.append((node, index + 1))
                nxt = deps[index]
                if colour.get(nxt, BLACK) == GREY:
                    return [*path[path.index(nxt) :], nxt]
                if colour.get(nxt, BLACK) == WHITE:
                    colour[nxt] = GREY
                    path.append(nxt)
                    stack.append((nxt, 0))
            else:
                colour[node] = BLACK
                if path and path[-1] == node:
                    path.pop()
    return None


def _parse_all_articles() -> dict[str, Article]:
    """Parse every ``*.md`` under the library dir. ``_``-prefixed files skipped."""
    directory = _library_dir()
    if not directory.is_dir():
        return {}
    articles: dict[str, Article] = {}
    for path in sorted(directory.glob("*.md")):
        if path.name.startswith("_"):
            continue
        article = parse_article(
            path.read_text(encoding="utf-8"),
            article_id=path.stem,
            where=f"library/{path.name}",
        )
        if article.id in articles:
            raise LibraryError(f"duplicate article id {article.id!r}")
        articles[article.id] = article
    return articles


def _check_article_metadata(
    article: Article,
    *,
    articles: dict[str, Article],
    known_concepts: set[str],
    known_archetypes: set[str],
) -> None:
    """Frontmatter ids: concepts, archetypes, prerequisites and related."""
    where = f"library/{article.id}.md"
    for concept_id in article.concepts:
        if concept_id not in known_concepts:
            raise LibraryError(f"{where}: unknown concept {concept_id!r}")
    if known_archetypes:
        for archetype_id in article.archetypes:
            if archetype_id not in known_archetypes:
                raise LibraryError(f"{where}: unknown archetype {archetype_id!r}")
    for field in ("prerequisites", "related"):
        for ref in getattr(article, field):
            if ref not in articles:
                raise LibraryError(f"{where}: {field} names unknown article {ref!r}")
            if ref == article.id:
                raise LibraryError(f"{where}: {field} names the article itself")


def _check_article_spans(
    article: Article,
    *,
    articles: dict[str, Article],
    known_concepts: set[str],
    known_questions: set[str],
) -> None:
    """Inline ``[[kind:id]]`` cross-references in the compiled body."""
    where = f"library/{article.id}.md"
    for span in _iter_spans(article.blocks):
        if span.kind == "concept" and span.ref_id not in known_concepts:
            raise LibraryError(f"{where}: [[concept:{span.ref_id}]] does not exist")
        if span.kind == "article" and span.ref_id not in articles:
            raise LibraryError(f"{where}: [[article:{span.ref_id}]] does not exist")
        if span.kind == "question" and span.ref_id not in known_questions:
            raise LibraryError(
                f"{where}: [[question:{span.ref_id}]] is not in the bank"
            )


def _short_title(title: str) -> str:
    """The part of a title that reads well mid-sentence.

    Article titles carry a subtitle after an em-dash — "Conditional Logic —
    Necessary, Sufficient, and the Contrapositive" — which is right at the head
    of a page and far too long inside a paragraph. The name before the dash is
    what a reader would actually say.
    """
    return title.split(" — ", 1)[0].strip() or title


def _label_cross_references(articles: dict[str, Article]) -> None:
    """Give unlabelled ``[[article:…]]`` / ``[[concept:…]]`` spans real names.

    Authors write ``[[article:lg-section-guide]]`` far more often than they
    write out a label, and rendering the bare id mid-sentence reads like a
    broken link. Resolving it here — once, at load, where the target is already
    in hand — fixes every occurrence at the same time and keeps both readers
    free of any lookup logic.

    A span the author *did* label is left alone: ``span.text == span.ref_id``
    is exactly the "no label was given" case.
    """
    concepts = _bank.load_concepts()
    for article in articles.values():
        for span in _iter_spans(article.blocks):
            if span.text != span.ref_id:
                continue
            if span.kind == "article" and span.ref_id in articles:
                span.text = _short_title(articles[span.ref_id].title)
            elif span.kind == "concept" and span.ref_id in concepts:
                span.text = concepts[span.ref_id].name


def _check_cross_references(articles: dict[str, Article]) -> None:
    """Resolve every id an article names, and reject prerequisite cycles.

    Split out of :func:`load_library` so the parse step and the integrity step
    fail with clearly different messages, and so this is callable on its own
    when a promoted draft has to be validated against the whole corpus.
    """
    known_concepts = set(_bank.load_concepts())
    known_questions = set(_bank.load_bank())
    # The taxonomy is optional to the library (it lives in the factory
    # package), so an empty set means "cannot check" rather than "nothing
    # is valid" — never fail a content load on a missing optional module.
    known_archetypes = _archetype_ids()
    for article in articles.values():
        _check_article_metadata(
            article,
            articles=articles,
            known_concepts=known_concepts,
            known_archetypes=known_archetypes,
        )
        _check_article_spans(
            article,
            articles=articles,
            known_concepts=known_concepts,
            known_questions=known_questions,
        )

    graph = {a.id: list(a.prerequisites) for a in articles.values()}
    if cycle := _detect_cycle(graph):
        raise LibraryError("prerequisite cycle: " + " → ".join(cycle))


@lru_cache(maxsize=1)
def load_library() -> dict[str, Article]:
    """Load every article, keyed by id, with full cross-reference integrity.

    Every failure mode here is a load-time error rather than a render-time
    surprise: a renamed concept id, a prerequisite cycle or a link to a
    question that left the bank breaks CI, not a reader's page.
    """
    articles = _parse_all_articles()
    if articles:
        _check_cross_references(articles)
        _label_cross_references(articles)
    return articles


@lru_cache(maxsize=1)
def load_tracks() -> dict[str, Track]:
    """Load the curated reading paths, validated against the library."""
    path = _bank.DATA_DIR / TRACKS_FILE
    if not path.is_file():
        return {}
    raw: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    articles = load_library()
    tracks: dict[str, Track] = {}
    for entry in raw.get("items", []):
        track = Track.model_validate(entry)
        if track.id in tracks:
            raise LibraryError(f"duplicate track id {track.id!r}")
        seen: set[str] = set()
        for article_id in track.article_ids:
            article = articles.get(article_id)
            if article is None:
                raise LibraryError(
                    f"track {track.id!r} names unknown article {article_id!r}"
                )
            # A track that puts an article before its own prerequisite reads
            # as a syllabus and teaches out of order.
            missing = [
                p
                for p in article.prerequisites
                if p in track.article_ids and p not in seen
            ]
            if missing:
                raise LibraryError(
                    f"track {track.id!r} lists {article_id!r} before its "
                    f"prerequisite(s): {', '.join(sorted(missing))}"
                )
            seen.add(article_id)
        tracks[track.id] = track
    return tracks


def reset_library_caches() -> None:
    """Drop every library loader cache. Tests and promotion use this."""
    load_library.cache_clear()
    load_tracks.cache_clear()


# ---------------------------------------------------------------------------
# Views + derived queries
# ---------------------------------------------------------------------------


def public_article_view(article: Article) -> ArticleSummary:
    """Index row — everything a contents rail needs and no body (NFR-PERF-1)."""
    return ArticleSummary(
        id=article.id,
        title=article.title,
        kind=article.kind,
        level=article.level,
        summary=article.summary,
        sections=list(article.sections),
        concepts=list(article.concepts),
        prerequisites=list(article.prerequisites),
        related=list(article.related),
        tags=list(article.tags),
        status=article.status,
        last_reviewed=article.last_reviewed,
        reading_minutes=article.reading_minutes,
        word_count=article.word_count,
    )


def public_track_view(track: Track) -> dict[str, Any]:
    """Serialize a track with its duration *computed* from its members."""
    articles = load_library()
    members = [articles[a] for a in track.article_ids if a in articles]
    return {
        **track.model_dump(),
        "article_count": len(members),
        "estimated_minutes": sum(a.reading_minutes for a in members),
    }


def articles_teaching(concept_id: str) -> list[str]:
    """Article ids that teach a concept — the inverse of ``Article.concepts``.

    Spec 048 FR-7: a learner who misses a concept-tagged question needs a way
    from the tag to the material, not just from the material to the tag.
    """
    return sorted(
        a.id
        for a in load_library().values()
        if concept_id in a.concepts
        or any(
            s.kind == "concept" and s.ref_id == concept_id
            for s in _iter_spans(a.blocks)
        )
    )


def inbound_links(article_id: str) -> list[str]:
    """Article ids that point at this one (prerequisite, related or inline)."""
    out: set[str] = set()
    for other in load_library().values():
        if other.id == article_id:
            continue
        if article_id in other.prerequisites or article_id in other.related:
            out.add(other.id)
            continue
        if any(
            s.kind == "article" and s.ref_id == article_id
            for s in _iter_spans(other.blocks)
        ):
            out.add(other.id)
    return sorted(out)


# ---------------------------------------------------------------------------
# Search (FR-9)
# ---------------------------------------------------------------------------

#: Field weights. A title match is worth far more than a body match: the
#: corpus is small enough that body hits are common and titles are not.
_WEIGHTS = {"title": 8, "summary": 4, "tag": 3, "heading": 3, "body": 1}
_SNIPPET_RADIUS = 90

#: Query-side synonyms. A query token listed here also matches any of its
#: alternates, each of which may be a phrase (every word of the phrase must
#: then be present in the field). Section abbreviations are the reason the
#: table exists at all — a learner types "LG" far more often than "logic
#: games" — and the rest are the pairs the corpus itself uses interchangeably.
#: Mirrored verbatim in ``lsat-static/lib/search.ts``; the parity fixture under
#: ``backend/tests/lsat/fixtures/search_parity.json`` pins both copies.
_SYNONYMS: dict[str, tuple[str, ...]] = {
    "lr": ("logical reasoning",),
    "rc": ("reading comprehension",),
    "lg": ("logic games", "analytical reasoning"),
    "ws": ("writing sample", "writing"),
    "games": ("logic games",),
    "game": ("logic games",),
    "flaw": ("fallacy",),
    "flaws": ("fallacy",),
    "fallacy": ("flaw",),
    "fallacies": ("flaw",),
    "premise": ("evidence",),
    "conclusion": ("main point",),
    "diagram": ("notation",),
    "diagramming": ("notation",),
    "timing": ("pacing",),
    "pacing": ("timing",),
    "inference": ("must be true",),
    "necessary": ("required",),
    "sufficient": ("guarantee",),
    "contrapositive": ("conditional",),
}

_TOKEN_RE = re.compile(r"[a-z0-9]+")

#: Dropped from the *query* only. "the assumption family" must not hand +8 to
#: every article whose title happens to start with "The". Field text keeps
#: them so a synonym phrase such as "must be true" still resolves.
_STOPWORDS = frozenset(
    [
        "a",
        "an",
        "and",
        "are",
        "as",
        "at",
        "be",
        "by",
        "does",
        "do",
        "for",
        "from",
        "how",
        "in",
        "is",
        "it",
        "of",
        "on",
        "or",
        "that",
        "the",
        "this",
        "to",
        "vs",
        "what",
        "when",
        "why",
        "with",
    ]
)

#: Stems this short are left alone: stripping "s" from "bus" or "ing" from
#: "ring" produces garbage, and short words are already matched by prefix.
_MIN_STEM = 4

#: Shortest stem a typo is forgiven on. Below five characters a single edit
#: turns one real word into another ("gam" → "game", "ram", "gap"), so the
#: tolerance is worth less than the false hits it buys.
_MIN_FUZZY = 5


def _strip_double_consonant(stem: str) -> str:
    """``diagramm`` → ``diagram``: undo the doubling ``-ing``/``-ed`` adds."""
    if (
        len(stem) >= 3
        and stem[-1] == stem[-2]
        and stem[-1] not in "aeiou"
        and stem[-1] not in "lsz"
    ):
        return stem[:-1]
    return stem


def stem(word: str) -> str:
    """A small, dependency-free suffix stemmer for the library's vocabulary.

    Deliberately far short of Porter: the rules cover plurals, ``-ing``,
    ``-ed``, ``-ly`` and ``-ness`` and then drop a trailing ``e``, which is
    enough for "assumptions" to meet "assumption" and "sequencing" to meet
    "sequence" and "timed" to meet "time" without conflating "premise" with
    "premium". The same rules, in the same order, live in
    ``lsat-static/lib/search.ts``.

    >>> stem("assumptions"), stem("fallacies"), stem("sequencing"), stem("timed")
    ('assumption', 'fallacy', 'sequenc', 'tim')
    """
    w = word.lower()
    if len(w) < _MIN_STEM:
        return w
    if w.endswith("ies") and len(w) > 4:
        w = w[:-3] + "y"
    elif w.endswith("sses"):
        w = w[:-2]
    elif w.endswith("s") and not w.endswith(("ss", "us", "is")):
        w = w[:-1]
    if w.endswith("ness") and len(w) > 6:
        w = w[:-4]
    if w.endswith("ing") and len(w) > 5:
        w = _strip_double_consonant(w[:-3])
    elif w.endswith("ed") and len(w) > 4:
        w = _strip_double_consonant(w[:-2])
    elif w.endswith("ly") and len(w) > 4:
        w = w[:-2]
    if w.endswith("e") and len(w) > 3:
        w = w[:-1]
    return w


def tokenize(text: str) -> list[str]:
    """Lower-case alphanumeric tokens, in order, duplicates kept."""
    return _TOKEN_RE.findall(text.lower())


def query_tokens(query: str) -> list[str]:
    """The tokens a query is matched on: ≥2 characters, stopwords dropped.

    >>> query_tokens("the Assumption family")
    ['assumption', 'family']
    """
    return [t for t in tokenize(query) if len(t) >= 2 and t not in _STOPWORDS]


def _field_stems(text: str) -> list[str]:
    return [stem(t) for t in tokenize(text)]


def _alternates(token: str) -> list[list[str]]:
    """Every stem-sequence a query token may match: itself, then synonyms."""
    out = [[stem(token)]]
    for phrase in _SYNONYMS.get(token, ()):
        out.append(_field_stems(phrase))
    return out


def _count_matches(field_stems: list[str], token: str) -> int:
    """How many times a query token is present in a tokenised field.

    A field word matches when its stem equals the token's stem or when the
    word begins with the raw token — the latter keeps search-as-you-type
    working, so "assu" still finds "assumption" before the word is finished.
    A synonym phrase counts once when every word of it is present.
    """
    target = stem(token)
    count = sum(1 for s in field_stems if s == target or s.startswith(token))
    field_set = set(field_stems)
    for phrase in _alternates(token)[1:]:
        if all(part in field_set for part in phrase):
            count += 1
    return count


def _same_length_typo(a: str, b: str) -> bool:
    """One substitution, or one transposition of adjacent letters."""
    diffs = [i for i in range(len(a)) if a[i] != b[i]]
    if len(diffs) == 1:
        return True
    if len(diffs) == 2 and diffs[1] == diffs[0] + 1:
        i, j = diffs
        return a[i] == b[j] and a[j] == b[i]
    return False


def _off_by_one_typo(short: str, long: str) -> bool:
    """One inserted or dropped letter: ``long`` with one character removed."""
    i = j = 0
    skipped = False
    while i < len(short) and j < len(long):
        if short[i] == long[j]:
            i += 1
            j += 1
        elif skipped:
            return False
        else:
            skipped = True
            j += 1
    return True


def is_typo(a: str, b: str) -> bool:
    """Whether two stems are within one edit — substitute, insert, drop, swap.

    A hand-rolled Damerau-Levenshtein *bound* rather than a distance: the
    answer is only ever "≤ 1 or not", which needs no matrix and stays trivial
    to mirror in TypeScript.

    >>> is_typo("assumption", "assumtion"), is_typo("premis", "premium")
    (True, False)
    """
    if a == b:
        return True
    if abs(len(a) - len(b)) > 1:
        return False
    if len(a) == len(b):
        return _same_length_typo(a, b)
    short, long = (a, b) if len(a) < len(b) else (b, a)
    return _off_by_one_typo(short, long)


def _fuzzy_matches(field_stems: list[str], token: str) -> bool:
    """Whether a *mistyped* query token is present in a tokenised field.

    The last resort, tried only when a token matches nothing exactly: it lets
    "assumtion" and "seqencing" find their articles instead of returning the
    empty state. Deliberately bounded — one edit, on stems of at least
    :data:`_MIN_FUZZY` characters — so it forgives typing, not meaning.
    """
    target = stem(token)
    if len(target) < _MIN_FUZZY:
        return False
    return any(
        len(s) >= _MIN_FUZZY and is_typo(s, target)
        for s in field_stems
        if abs(len(s) - len(target)) <= 1
    )


def _fuzzy_weight(weight: int) -> int:
    """A typo hit is worth half a real one, and never nothing."""
    return max(1, weight // 2)


def _score_field(field_stems: list[str], token: str, weight: int, cap: int) -> int:
    """One field's contribution for one token: exact first, typo as a fallback."""
    occurrences = _count_matches(field_stems, token)
    if occurrences:
        return weight * min(occurrences, cap)
    if _fuzzy_matches(field_stems, token):
        return _fuzzy_weight(weight)
    return 0


def _score_headings(
    headings: list[tuple[str, list[str]]], token: str
) -> tuple[int, str | None]:
    """Heading contribution for one token, plus the anchor to jump to."""
    exact = [a for a, stems in headings if _count_matches(stems, token)]
    if exact:
        return _WEIGHTS["heading"] * len(exact), exact[0]
    fuzzy = [a for a, stems in headings if _fuzzy_matches(stems, token)]
    if fuzzy:
        return _fuzzy_weight(_WEIGHTS["heading"]) * len(fuzzy), fuzzy[0]
    return 0, None


def _first_match_offset(text: str, tokens: list[str]) -> tuple[int, int] | None:
    """Character span of the first body word any query token matches."""
    targets = {stem(t) for t in tokens}
    fuzzy: tuple[int, int] | None = None
    for match in _TOKEN_RE.finditer(text.lower()):
        word = stem(match.group(0))
        if word in targets or any(match.group(0).startswith(t) for t in tokens):
            return match.start(), match.end()
        if fuzzy is None and any(_fuzzy_matches([word], t) for t in tokens):
            fuzzy = (match.start(), match.end())
    return fuzzy


def _snippet(text: str, tokens: list[str]) -> str | None:
    span = _first_match_offset(text, tokens)
    if span is None:
        return None
    at, stop = span
    start = max(0, at - _SNIPPET_RADIUS)
    end = min(len(text), stop + _SNIPPET_RADIUS)
    return (
        ("…" if start else "")
        + text[start:end].strip()
        + ("…" if end < len(text) else "")
    )


def _score_article(
    article: Article, tokens: list[str], body: str
) -> tuple[int, list[str], str | None]:
    """Field-weighted token score; ``0`` unless every token matches somewhere."""
    fields = {
        "title": _field_stems(article.title),
        "summary": _field_stems(article.summary),
        "tag": _field_stems(" ".join(article.tags)),
        "body": _field_stems(body),
    }
    headings = [(e.anchor, _field_stems(e.text)) for e in article.outline]
    score = 0
    where: list[str] = []
    anchor: str | None = None
    for token in tokens:
        gained = 0
        for name in ("title", "summary", "tag"):
            field_score = _score_field(fields[name], token, _WEIGHTS[name], 1)
            if field_score:
                gained += field_score
                if name not in where:
                    where.append(name)
        heading_score, heading_anchor = _score_headings(headings, token)
        if heading_score:
            gained += heading_score
            if "heading" not in where:
                where.append("heading")
            anchor = anchor or heading_anchor
        body_score = _score_field(fields["body"], token, _WEIGHTS["body"], 5)
        if body_score:
            gained += body_score
            if "body" not in where:
                where.append("body")
        if not gained:
            return 0, [], None
        score += gained
    return score, where, anchor


def search_library(query: str, *, limit: int = 20) -> list[dict[str, Any]]:
    """Rank articles against a query, with a matched-context snippet.

    A token + field-weight ranker, not an index: at the library's size it is
    instant on both products and needs no build step, which is what lets the
    offline site search with zero network calls (NFR-OFFLINE-1). Each query
    token is stemmed (:func:`stem`) and expanded through ``_SYNONYMS``, so
    "assumptions" meets "assumption" and "LG" meets "logic games"; a field
    word also matches by prefix so search-as-you-type keeps working. A token
    that matches nothing exactly is retried within one edit (:func:`is_typo`,
    stems of ≥ 5 characters only), scored at half weight, so "assumtion"
    still lands on the assumption family rather than the empty state. Every
    token must match somewhere in an article for it to be a hit.

    ``lsat-static/lib/search.ts`` mirrors this function rule for rule.
    """
    tokens = query_tokens(query)
    if not tokens:
        return []
    hits: list[dict[str, Any]] = []
    for article in load_library().values():
        body = article_text(article)
        score, where, anchor = _score_article(article, tokens, body)
        if not score:
            continue
        hits.append(
            {
                "id": article.id,
                "title": article.title,
                "kind": article.kind,
                "sections": list(article.sections),
                "reading_minutes": article.reading_minutes,
                "score": score,
                "matched_in": where,
                "snippet": _snippet(body, tokens) or article.summary,
                "anchor": anchor,
            }
        )
    hits.sort(key=lambda h: (-int(h["score"]), str(h["id"])))
    return hits[:limit]


# ---------------------------------------------------------------------------
# Health audit (FR-14) — deterministic, no model call
# ---------------------------------------------------------------------------


def _archetype_ids() -> set[str]:
    try:
        from law_ai.lsat.factory import taxonomy

        return set(taxonomy.by_id())
    except Exception:  # pragma: no cover - taxonomy is optional to the library
        return set()


def library_audit(*, today: date | None = None) -> dict[str, Any]:
    """Deterministic health report for the corpus.

    Runs with no LLM provider configured (AC-8) — it is the number behind the
    claim that the library is being maintained, so it must never depend on the
    thing it is measuring.
    """
    now = today or datetime.now(UTC).date()
    articles = load_library()
    tracks = load_tracks()

    by_kind: dict[str, int] = {}
    by_section: dict[str, int] = {}
    by_level: dict[str, int] = {}
    by_status: dict[str, int] = {}
    thin: list[dict[str, Any]] = []
    stale: list[dict[str, Any]] = []
    for article in articles.values():
        by_kind[article.kind] = by_kind.get(article.kind, 0) + 1
        by_level[article.level] = by_level.get(article.level, 0) + 1
        by_status[article.status] = by_status.get(article.status, 0) + 1
        # "cross-cutting" is a reporting bucket, not a Section — an article
        # serving no single section still has to appear in the breakdown.
        section_keys: list[str] = list(article.sections) or ["cross-cutting"]
        for section_key in section_keys:
            by_section[section_key] = by_section.get(section_key, 0) + 1
        if article.word_count < THIN_ARTICLE_WORDS:
            thin.append({"id": article.id, "word_count": article.word_count})
        age = (now - article.last_reviewed).days
        if age > STALE_AFTER_DAYS or article.status == "needs-review":
            stale.append(
                {"id": article.id, "days_since_review": age, "status": article.status}
            )

    taught = {c for a in articles.values() for c in a.concepts}
    all_concepts = set(_bank.load_concepts())
    covered_archetypes = {x for a in articles.values() for x in a.archetypes}
    all_archetypes = _archetype_ids()

    tracked = {a for t in tracks.values() for a in t.article_ids}
    orphans = sorted(
        a.id
        for a in articles.values()
        if not inbound_links(a.id) and a.id not in tracked
    )

    words = [a.word_count for a in articles.values()]
    graph = {a.id: list(a.prerequisites) for a in articles.values()}
    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "counts": {
            "articles": len(articles),
            "tracks": len(tracks),
            "by_kind": dict(sorted(by_kind.items())),
            "by_section": dict(sorted(by_section.items())),
            "by_level": dict(sorted(by_level.items())),
            "by_status": dict(sorted(by_status.items())),
        },
        "words": {
            "total": sum(words),
            "mean": round(sum(words) / len(words)) if words else 0,
            "min": min(words) if words else 0,
            "max": max(words) if words else 0,
            "thin_threshold": THIN_ARTICLE_WORDS,
            "thin_articles": sorted(thin, key=lambda t: int(t["word_count"])),
        },
        "coverage": {
            "concepts_total": len(all_concepts),
            "concepts_taught": len(taught & all_concepts),
            "concepts_untaught": sorted(all_concepts - taught),
            "archetypes_total": len(all_archetypes),
            "archetypes_covered": len(covered_archetypes & all_archetypes),
            "archetypes_uncovered": sorted(all_archetypes - covered_archetypes),
        },
        "freshness": {
            "stale_after_days": STALE_AFTER_DAYS,
            "stale_articles": sorted(stale, key=lambda s: -int(s["days_since_review"])),
        },
        "graph": {
            "orphan_articles": orphans,
            "articles_in_no_track": sorted(set(articles) - tracked),
            "roots": sorted(a for a, deps in graph.items() if not deps),
            "prerequisite_cycles": [],
            "broken_cross_references": [],
        },
    }


# ---------------------------------------------------------------------------
# Target picker (BL-20260903-08) — deterministic, no model call
# ---------------------------------------------------------------------------

#: How many gap-driven expansions the picker will ever emit in one run,
#: however many gaps the audit reports. Expansions are the noisier half of the
#: librarian's work — a review reports, an expansion drafts prose a human then
#: has to read line by line — so a cycle stays mostly review even when the
#: coverage report is long.
MAX_EXPANSIONS_PER_RUN = 2


class LibrarianRequest(BaseModel):
    """One target the picker hands :class:`LSATLibrarian`.

    ``reason`` is the audit signal that selected it, and is carried onto the
    proposal so a reviewer sees *why* the cycle chose this article rather than
    having to reconstruct it from the report.
    """

    model_config = ConfigDict(frozen=True)

    action: Literal["review", "expand"] = "review"
    article_id: str
    gap: str | None = None
    reason: str

    def to_input(self) -> dict[str, Any]:
        """The ``run()`` payload for :class:`LSATLibrarian`."""
        payload: dict[str, Any] = {"action": self.action, "article_id": self.article_id}
        if self.gap:
            payload["gap"] = self.gap
        return payload


_ID_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


def scaffold_article(
    article_id: str,
    *,
    title: str,
    summary: str,
    kind: ArticleKind = "technique",
    level: ArticleLevel = "core",
    sections: list[str] | None = None,
    concepts: list[str] | None = None,
    archetypes: list[str] | None = None,
) -> Path:
    """Create a new article file with valid frontmatter and a stub body.

    BL-20260905-53. ``expand`` drafts a body and cannot write the frontmatter
    that gives an article its id, level and review status, so a section with
    no article at all was unreachable by the autonomous cycle
    (:func:`_host_article` dropped the gap). This is the missing half: it
    writes the frontmatter, and the librarian's ``expand`` pass then has
    somewhere to draft into.

    The file is written, the whole library re-loaded, and the file removed
    again if that load fails — the corpus never keeps an article that breaks
    it. Raises ``ValueError`` for a malformed id or an id that already exists.
    """
    if not _ID_RE.match(article_id):
        raise ValueError(
            f"article id {article_id!r} must be lower-case words joined by "
            "hyphens (it becomes the file name and the link target)"
        )
    path = _library_dir() / f"{article_id}.md"
    if path.exists():
        raise ValueError(f"article {article_id!r} already exists at {path}")

    def _seq(values: list[str] | None) -> str:
        return "[" + ", ".join(values or []) + "]"

    body = (
        "---\n"
        f"id: {article_id}\n"
        f"title: {title}\n"
        f"kind: {kind}\n"
        f"level: {level}\n"
        f"sections: {_seq(sections)}\n"
        f"summary: {summary}\n"
        f"concepts: {_seq(concepts)}\n"
        f"archetypes: {_seq(archetypes)}\n"
        "prerequisites: []\n"
        "related: []\n"
        "tags: [scaffold]\n"
        "status: draft\n"
        f"last_reviewed: {date.today().isoformat()}\n"
        "revision: 1\n"
        "---\n"
        "\n"
        "## Overview\n"
        "\n"
        f"{summary}\n"
        "\n"
        "This article is a scaffold: its frontmatter is complete and the "
        "library loads it, but the body is a stub. The next librarian "
        "`expand` pass drafts the first real section into it, and a reviewer "
        "approves that draft in the usual queue.\n"
        "\n"
        "## Worked example\n"
        "\n"
        "> [!example] Not yet written\n"
        "> Replace this callout with a worked instance of what this article "
        "teaches.\n"
        "\n"
        "## Key takeaways\n"
        "\n"
        "- This article is a scaffold and has not been written yet.\n"
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    reset_library_caches()
    try:
        load_library()
    except Exception:
        path.unlink(missing_ok=True)
        reset_library_caches()
        raise
    return path


def article_source(article_id: str) -> str:
    """The article's on-disk Markdown — what an expansion is appended to."""
    path = _library_dir() / f"{article_id}.md"
    if not path.is_file():
        raise KeyError(f"no source file for article {article_id!r}")
    return path.read_text(encoding="utf-8")


def merge_expansion(article_id: str, proposed_markdown: str) -> str:
    """The whole revised article: its source with the drafted section appended.

    ``expand`` returns a new ``##`` section, but a promoted draft is written
    whole (:func:`law_ai.lsat.services.proposals.promote_library_article`), so
    the merge happens here — before a reviewer ever sees the draft — and what
    they approve is exactly the file that lands.
    """
    return (
        article_source(article_id).rstrip() + "\n\n" + proposed_markdown.strip() + "\n"
    )


def _host_article(section: str, articles: dict[str, Article]) -> str | None:
    """The article a gap in ``section`` should be expanded into.

    The section's hub: among the articles serving it, the one already teaching
    the most concepts, ties broken by id. A section with no article at all
    returns ``None`` and the gap is dropped — ``expand`` drafts a body and
    cannot write the frontmatter that gives an article its id, level and
    review status. :func:`scaffold_article` (``manage.py lsat_library
    scaffold``) writes that frontmatter, after which the section has a host
    and the gap becomes reachable by the cycle again (BL-20260905-53).
    """
    candidates = [a for a in articles.values() if section in a.sections]
    if not candidates:
        return None
    return min(candidates, key=lambda a: (-len(a.concepts), a.id)).id


def _concept_gaps(
    report: dict[str, Any], articles: dict[str, Article]
) -> list[LibrarianRequest]:
    """One expansion per untaught concept, hosted in that concept's section."""
    catalog = _bank.load_concepts()
    out: list[LibrarianRequest] = []
    for concept_id in report["coverage"]["concepts_untaught"]:
        concept = catalog.get(concept_id)
        if concept is None:
            continue
        for section in concept.sections:
            host = _host_article(section, articles)
            if host is None:
                continue
            out.append(
                LibrarianRequest(
                    action="expand",
                    article_id=host,
                    gap=(
                        f"The concept catalog defines '{concept.name}' "
                        f"({concept_id}) — {concept.summary} — but no library "
                        f"article teaches it. Draft a section for this article "
                        f"that does, tagged [[concept:{concept_id}]]."
                    ),
                    reason=f"untaught concept {concept_id}",
                )
            )
            break
    return out


def _archetype_gaps(
    report: dict[str, Any], articles: dict[str, Article]
) -> list[LibrarianRequest]:
    """One expansion per uncovered archetype, hosted in that archetype's section."""
    try:
        from law_ai.lsat.factory import taxonomy

        catalog = taxonomy.by_id()
    except Exception:  # pragma: no cover - taxonomy is optional to the library
        return []
    out: list[LibrarianRequest] = []
    for archetype_id in report["coverage"]["archetypes_uncovered"]:
        archetype = catalog.get(archetype_id)
        if archetype is None:
            continue
        host = _host_article(archetype.section, articles)
        if host is None:
            continue
        out.append(
            LibrarianRequest(
                action="expand",
                article_id=host,
                gap=(
                    f"No library article covers the '{archetype.name}' question "
                    f"archetype ({archetype_id}), which the item factory already "
                    f"generates. Draft a section for this article that explains "
                    f"how the pattern is recognised and solved."
                ),
                reason=f"uncovered archetype {archetype_id}",
            )
        )
    return out


def _review_targets(
    report: dict[str, Any], articles: dict[str, Article]
) -> list[LibrarianRequest]:
    """Reviews, worst first: unreviewed, then thin, then unreachable."""
    out: list[LibrarianRequest] = []
    for row in report["freshness"]["stale_articles"]:
        out.append(
            LibrarianRequest(
                article_id=str(row["id"]),
                reason=(
                    f"{row['status']}, {row['days_since_review']} days since review"
                ),
            )
        )
    floor = report["words"]["thin_threshold"]
    for row in report["words"]["thin_articles"]:
        out.append(
            LibrarianRequest(
                article_id=str(row["id"]),
                reason=f"thin — {row['word_count']} words, under the {floor} floor",
            )
        )
    graph = report["graph"]
    for article_id in graph["orphan_articles"]:
        out.append(
            LibrarianRequest(
                article_id=str(article_id),
                reason="orphan — nothing links to it and no track reaches it",
            )
        )
    for article_id in graph["articles_in_no_track"]:
        out.append(
            LibrarianRequest(article_id=str(article_id), reason="in no reading track")
        )
    return out


def pick_librarian_targets(
    report: dict[str, Any], *, limit: int = 3
) -> list[LibrarianRequest]:
    """Choose what the librarian works on next, from the audit alone.

    The corpus-wide pass the scheduled cycle used to need a human target list
    for (BL-20260903-08). Deterministic and provider-free: the same report
    always yields the same targets, in one order —

    1. **reviews** of articles the audit flags: never-reviewed or stale first
       (the audit orders them by days-since-review), then thin ones, then
       articles nothing links to and no track reaches;
    2. **expansions** for coverage gaps — an untaught concept or an uncovered
       archetype — hosted in that section's hub article and capped at
       :data:`MAX_EXPANSIONS_PER_RUN`, because a draft costs a reviewer far
       more than a report does;
    3. a **review of everything else**, in id order, so a healthy corpus keeps
       the cycle useful instead of idling.

    Each article appears at most once, under the first signal that named it.
    ``limit`` is the number of targets returned, not the number considered.
    """
    articles = load_library()
    gaps = (_concept_gaps(report, articles) + _archetype_gaps(report, articles))[
        :MAX_EXPANSIONS_PER_RUN
    ]
    # A scaffolded stub exists to be written into, and it is thin and orphaned
    # by construction — so the review signals would claim it first and it
    # would be reviewed forever instead of filled (BL-20260905-53). When a gap
    # names one, the expansion wins.
    scaffolds = {
        request.article_id
        for request in gaps
        if "scaffold" in articles[request.article_id].tags
    }
    ranked = [
        request
        for request in _review_targets(report, articles)
        if request.article_id not in scaffolds
    ]
    ranked += gaps
    ranked += [
        LibrarianRequest(article_id=article_id, reason="routine sweep")
        for article_id in sorted(articles)
    ]

    picked: list[LibrarianRequest] = []
    seen: set[str] = set()
    for request in ranked:
        if request.article_id in seen or request.article_id not in articles:
            continue
        seen.add(request.article_id)
        picked.append(request)
        if len(picked) >= max(1, limit):
            break
    return picked
