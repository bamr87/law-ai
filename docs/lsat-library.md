# LSAT Knowledge Library

The library is the LSAT module's **prose layer**: long-form, cross-linked study material on how the exam is built, what each section demands, how each recurring question family is solved, and how to pace and review. It sits beside the question bank, the solve guides and the writing prompts, and it is what a learner *studies* as opposed to what they *practise against*.

Introduced by [specs/048-lsat-knowledge-library](../specs/048-lsat-knowledge-library/spec.md).

**Two views, one surface.** The library reads in two modes on both products — **Articles** (the reader) and **Concepts** (the catalog of recurring reasoning patterns that `concepts.json` defines and every article and bank question is tagged with). The catalog used to be a tab in the practice lab and a separate destination on the static site, which meant an article could name a concept but a concept named nothing. In the library it carries `taught_in` — the concept → article inverse `/api/lsat/concepts/<id>` has always returned — so a learner who misses a concept-tagged question can go tag → material in one hop. This does not merge the *data*: `concepts.json` is still the tagging vocabulary and articles reference concepts rather than absorbing them (spec 048 NG5).

## Where it lives

| Thing | Path |
| ----- | ---- |
| Articles | `backend/law_ai/lsat/services/data/library/*.md` |
| Reading tracks | `backend/law_ai/lsat/services/data/library_tracks.json` |
| Models, parser, loaders, search, audit | `backend/law_ai/lsat/services/library.py` |
| API | `backend/law_ai/lsat/urls.py` → `/api/lsat/library/*` |
| Platform reader | `frontend/components/LsatLibrary.tsx` + `components/lsat/library/` |
| Offline reader | `lsat-static/components/Library.tsx` + `components/library/` |
| Concept catalog | `frontend/components/LsatLibrary.tsx` (Concepts view) · `lsat-static/components/Concepts.tsx` |
| Maintenance agent | `backend/law_ai/agents_runtime/crews/lsat_librarian.py` |
| Command | `backend/law_ai/lsat/management/commands/lsat_library.py` |

## The entry template

An article and a concept are different data but the same kind of thing to a reader: an entry on a shelf. Both readers on both products therefore render through one template, in one order, and every cross-reference section carries a fixed anchor (`#entry-<section>`) so the outline column lists it whichever view is open. A section with nothing to show is omitted rather than rendered empty — with one exception, noted below.

| Step | Article | Concept |
| ---- | ------- | ------- |
| Header | kind · level · reading time · word count · sections; title; summary; tag and archetype chips | "Concept" · example count · articles taught in · sections; title; summary |
| Actions | Mark as read · Drill this (N questions) | Mark as read · Drill this (N questions) |
| Read first | prerequisites | — |
| Body | the typed blocks | the detail paragraph |
| Schema & examples | — | `#entry-examples` |
| Concepts in this article | `#entry-concepts` — cards, each also the `#concept-<id>` landing spot for inline references | — |
| Articles on this concept | — | `#entry-articles` — `taught_in`, resolved against the index. **Always rendered**: a learner who missed a tagged question arrives here needing the material, so "no article covers this concept yet" is an answer where an omitted section is not |
| Related | `#entry-related` — `related` articles | `#entry-related` — `see_also`, resolved against the catalog; an id the catalog no longer holds is shown as text, not a dead button |
| Reading tracks | `#entry-tracks` — tracks containing the article | `#entry-tracks` — tracks reaching any article that teaches it |
| References | `#entry-references` | `#entry-references` |
| Provenance | source · revision · last reviewed · status | concept catalog · sections |

The two cross-reference directions use the same card component, so an article's concepts and a concept's articles look alike and open alike. Read state is one `localStorage` set for both kinds of entry — articles under their bare id (what every existing entry already holds), concepts under `concept:<id>` — and each rail reports its own "N of M read". The rails share one row shape too: read-state dot, title, and a second line that says what you get (reading time for an article, "taught in N articles" for a concept).

The static site renders the same template with its own layout: the article reader section for section, and the concept catalog as cards that carry the same header facts and the same cross-reference blocks in the same order.

## Markdown in, typed blocks out

Articles are authored as Markdown because that is what a human reviews in a diff and what an agent can patch one section at a time. **Neither client ever sees Markdown.** `library.py` compiles each body into a typed block tree at load time, and both readers render blocks.

That single decision buys three things:

- no Markdown dependency in either frontend (`lsat-static/` has three
  dependencies in total, and it stays that way);
- no `dangerouslySetInnerHTML` anywhere, so no sanitiser is needed
  (`tests/test_lsat_site.py` asserts it);
- one rendering contract, so a block type cannot ship to the platform app and
  silently vanish from the offline site.

The dialect is **closed**. Anything the parser does not recognise is an error naming the file, never markup passed through to a client.

### Starting a new article

Copy `backend/law_ai/lsat/services/data/library/_template.md` to `<your-id>.md` in the same directory, set `id` to the file name, and replace the placeholders. The template carries every frontmatter key, one instance of every block construct and every typed span, and a body table explaining each key. Files whose name starts with `_` are skipped by the loader and by the export drift gate, so the template is never published — but `tests/lsat/test_library_corpus.py` parses it against the live corpus, so it cannot fall behind the dialect.

### Frontmatter

```markdown
---
id: lr-assumption-family          # must equal the file name
title: The Assumption Family
kind: question-type               # orientation | section-guide | question-type |
                                  # technique | strategy | foundation | review-method
level: core                       # foundation | core | advanced
sections: [LR]                    # LR, RC, LG, WS — empty for cross-cutting
summary: One sentence a reader can scan in an index.
concepts: [necessary-assumption]  # ids in concepts.json
archetypes: [lr-necessary-assumption]   # ids in the factory taxonomy
prerequisites: [argument-anatomy] # article ids; the graph must stay acyclic
related: [lr-strengthen-and-weaken]
tags: [assumption, negation-test]
status: reviewed                  # draft | reviewed | needs-review
last_reviewed: 2026-09-03
revision: 1
references:
  - title: LSAC — About the LSAT
    url: https://www.lsac.org/lsat
---
```

`reading_minutes`, `word_count`, `blocks` and `outline` are **computed**. Declaring any of them is rejected — a declared reading time goes stale the moment anyone expands a section.

The frontmatter parser is a small restricted reader, not YAML: `key: scalar`, `key: [a, b]`, and a bare `key:` followed by an indented list of scalars or of single-level mappings. That is the whole schema, and it needs no dependency.

### Body constructs

| Construct | Syntax |
| --------- | ------ |
| Section heading | `## Heading`, `### Subheading` (never `#`) |
| Paragraph | Plain lines; wrapped lines join |
| Bullet list | `- item` |
| Ordered list | `1. item` |
| Callout | `> [!example] Title`, then `> ` on every line |
| Table | Pipe rows, **with** a `\|---\|---\|` separator under the header |
| Notation | Triple-backtick fence; the fence line's text becomes the caption |

Callout variants: `example`, `trap`, `tip`, `note`, `warning`, `drill`.

Inline: `**strong**`, `*emphasis*`, `` `code` ``, `[text](https://…)`, and typed cross-references `[[concept:id]]`, `[[article:id]]`, `[[question:id]]`, each
optionally labelled as `[[kind:id|Label]]`.

### The four structural gates

Enforced by the loader, not by convention — "we always include a worked example" is exactly the rule that survives until the first agent-drafted expansion:

1. a non-empty `summary`;
2. at least three `##` sections;
3. at least one `> [!example]` callout;
4. a `## Key takeaways` section followed by a list.

### Cross-reference integrity

Every id resolves at load: concepts against `concepts.json`, articles against the library, questions against the bank, archetypes against the factory taxonomy. The prerequisite graph is checked for cycles, and a reading track that lists an article before its own prerequisite fails to load.

A renamed concept therefore breaks CI, not a reader's page.

## Working on it

```bash
# Health report — deterministic, no model call, no provider needed.
make lsat-library-audit
make lsat-library-audit ARGS='--json'

# Agent review pass. Files pending proposals; writes nothing under data/library/.
make lsat-library-review ARGS='--limit 3'
make lsat-library-review ARGS='--article lr-flaw-family --dry-run'

# Promote one approved draft — the only path that writes an article file.
make manage CMD='lsat_library promote --proposal prop-abc123 --reviewer you'

# Ship it to the offline site. Required whenever any library file changes.
make lsat-export
```

**After editing any article or the tracks file, run `make lsat-export`.** `tests/test_lsat_site.py` fails CI when the committed `lsat-static/content.json` lags the source.

## The maintenance loop

`LSATLibrarian` (`human_approval_required = True`) does one of three jobs per run — `review`, `correct`, `expand` — through the provider chain in `law_ai.core.llm`, never a direct transport, with a deterministic offline fallback at confidence 0.0 and one `provenance.log_agent_call` per run.

Its confidence ceiling is 0.6, below the solve-guide author's 0.7: prose about exam structure is harder to verify mechanically than a walkthrough that can be checked against an answer key.

Everything it produces lands in the existing proposal store under `library_finding` (a review report — read and closed by a human, never promoted) or `library_article` (a draft). `promote_library_article` re-parses the draft **and** reloads the whole library before keeping the write, rolling back if the new text dangles a cross-reference or introduces a cycle.

A Celery beat entry (`autonomy-lsat-library`, Mondays 05:00 UTC) runs `review` only, gated by `AUTONOMY_ENABLED`. Weekly rather than daily: prose about exam structure does not change on a daily cadence, and each review is a full-article model call.

## Guardrails

- **Original (CC0) only.** No real LSAT items, LSAC explanations, or commercial
  preparation material — reproduced, quoted, or closely paraphrased.
- **Study aid, not legal advice**, and no article may claim a score outcome.
  `tests/lsat/test_library_corpus.py` asserts both.
- **Structural claims cite a source.** An `orientation` or `section-guide`
article without a reference fails the corpus test — the failure mode that matters is an agent confidently describing a format LSAC changed.
- **Nothing an agent writes reaches a learner** without a human promoting a
  specific proposal id.
