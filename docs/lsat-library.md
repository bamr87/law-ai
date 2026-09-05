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
