---
id: _template
title: Article Title — Optional Subtitle After an Em-Dash
kind: technique
level: core
sections: [LR]
summary: One sentence a reader can scan in the index — what this article teaches and why it matters.
concepts: [necessary-assumption, conditional-reasoning]
archetypes: [lr-necessary-assumption]
prerequisites: [argument-anatomy]
related: [lr-assumption-family, conditional-logic-foundations]
tags: [template, authoring]
status: draft
last_reviewed: 2026-09-05
revision: 1
references:
  - title: LSAC — About the LSAT
    url: https://www.lsac.org/lsat
---

## How to use this template

Copy this file to `data/library/YOUR-ARTICLE-ID.md`, set `id` to the new file name, replace every placeholder, and delete this section. The loader skips any file whose name starts with `_`, so the template itself is never published — but it is parsed by the corpus tests, which means every construct below is guaranteed to be one the parser accepts today.

The dialect is closed: a construct the parser does not recognise fails the load with an error naming the file. Nothing is passed through to a client as raw markup, and raw HTML is rejected outright.

## Frontmatter keys

Every key in the block at the top of this file, what it means, and what it must resolve against. `reading_minutes`, `word_count`, `blocks` and `outline` are computed from the body — declaring any of them is an error.

| Key | Required | Meaning |
|---|---|---|
| `id` | yes | Must equal the file name without `.md`. |
| `title` | yes | Shown at the head of the page. Text after ` — ` is a subtitle; the part before it is what an unlabelled `[[article:…]]` link renders as. |
| `kind` | yes | One of `orientation`, `section-guide`, `question-type`, `technique`, `strategy`, `foundation`, `review-method`. |
| `level` | yes | Reading-order tier: `foundation`, `core` or `advanced`. |
| `sections` | no | Exam sections served: any of `LR`, `RC`, `LG`, `WS`. Empty means cross-cutting. |
| `summary` | yes | One non-empty sentence for the index row. |
| `concepts` | no | Ids from `concepts.json` this article teaches. Each must exist. |
| `archetypes` | no | Ids from the factory taxonomy this article covers. Each must exist. |
| `prerequisites` | no | Article ids to read first. The graph must stay acyclic. |
| `related` | no | Article ids to show as further reading. |
| `tags` | no | Free-form chips; searched at weight 3. |
| `status` | no | `draft` (default), `reviewed` or `needs-review`. |
| `last_reviewed` | yes | ISO date. Older than 120 days is reported as stale by the audit. |
| `revision` | no | Integer starting at 1; bump it on every substantive edit. |
| `source` | no | Defaults to `original (CC0)`, which is the only value the corpus test accepts. |
| `references` | no | List of `title` + `url` mappings. Required in practice for `orientation` and `section-guide` articles. |

## Inline markup

A paragraph is one or more plain lines; wrapped lines are joined with a space. Inside a paragraph you can use **strong**, *emphasis*, `code`, and an [external link](https://www.lsac.org/lsat) — link targets must be absolute `http(s)` URLs or in-page `#anchors`.

Cross-references are typed. An unlabelled concept link such as [[concept:necessary-assumption]] renders the concept's catalog name; an unlabelled article link such as [[article:argument-anatomy]] renders the target's short title; a question link needs a label, as in [[question:lr-001|this warm-up drill]]. Every target is resolved at load time, so a renamed id breaks CI rather than a reader's page.

## Block constructs

Section headings use `##`; subheadings use `###`. A `#` heading is reserved for the title and rejected, and depth four and beyond is not supported.

### Lists

- A bullet list item.
- A second item with **strong** text and a [[concept:conditional-reasoning]] reference.
  A continuation line indented under the item joins it.

1. An ordered list item.
2. A second ordered item.

### Callouts

A callout opens with `> [!variant] Title` and continues with `> ` on every line. Variants: `example`, `trap`, `tip`, `note`, `warning`, `drill`. A callout may hold paragraphs, lists and notation, but not headings or tables. Every article must contain at least one `example` callout.

> [!example] A worked example
> *If the museum extends its hours, attendance will rise. Attendance did not rise. Therefore the museum did not extend its hours.*
>
> This is the contrapositive applied cleanly: the necessary condition failed, so the sufficient condition cannot have held.
>
> - Sufficient: extended hours
> - Necessary: attendance rises

> [!trap] A common mistake
> Reading a conditional backwards — treating the necessary condition as if it were sufficient — is the single most frequent error in this family.

> [!tip] A shortcut
> Diagram before you evaluate the choices.

> [!note] Background
> This template is not study material; it exists so authors and agents share one starting point.

> [!warning] Scope
> No real LSAT items, LSAC explanations or commercial preparation material — reproduced, quoted or closely paraphrased.

> [!drill] Try it
> Attempt [[question:lr-001|the first bank item]] before reading the next section.

### Tables

A table needs a header row, a `|---|---|` separator, and at least one body row. Every row must have the same number of cells as the header.

| Column A | Column B |
|---|---|
| A cell with *emphasis* | A cell with a [[concept:conditional-reasoning]] reference |
| Plain text | `code` |

### Notation

A fenced block is rendered monospace and never reflowed. Text on the fence line becomes the caption.

```Conditional chain
Extended hours → Attendance rises
Attendance did not rise → Hours not extended
```

## Structural gates

The loader enforces four rules on every article, template included: a non-empty `summary`, at least three `##` sections, at least one `> [!example]` callout, and a `## Key takeaways` section followed by a list. Keep the last section exactly as below.

## Key takeaways

- Copy this file, rename it, set `id` to the file name, and delete the how-to sections.
- Use only the constructs shown here; the parser rejects everything else.
- Run `make lsat-export` after saving so the offline site stays in lockstep.
