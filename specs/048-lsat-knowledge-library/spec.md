# Spec: LSAT Knowledge Library

- **ID**: 048-lsat-knowledge-library
- **Status**: shipped
- **Owner**: @bamr87
- **Created**: 2026-09-03
- **Roadmap Epic**: BACKLOG BL-20260903-01, BL-20260903-02, BL-20260903-03, BL-20260903-04
- **Constitution Compliance**: confirmed against [docs/constitution.md](../../docs/constitution.md)

## 1. Problem & Motivation

Everything the LSAT module ships today is a *drill*. As of 2026-09-03 the bank holds 148 keyed questions, 40 solve guides, 13 passages, 4 writing prompts and 52 concepts — and every one of those artifacts answers the question "how do I solve **this item**?"

Nothing answers "how does this **exam** work?" A learner arriving at either product can practise but cannot study:

- **Section metadata is four paragraphs.** `sections.json` gives each section a description,
a format line, a timing line and a bullet list of tips. That is a table of contents, not a guide — there is no explanation of *why* the assumption family rewards the negation test, what distinguishes a necessary from a sufficient assumption in practice, or how to build a pacing plan that survives a hard first passage.
- **Concepts are a glossary.** A `Concept` is `summary` + optional `detail` + a couple of
examples. The median concept body is under 60 words. It is enough to tag a question with and nowhere near enough to learn from.
- **There is no prose layer at all.** No article, tutorial, deep dive or technique walkthrough
exists anywhere in the repo. A learner who wants the *method* has to reverse-engineer it from 40 solve guides.
- **No reading surface.** Both products are drill-shaped: tab bars, question cards, timers. There
is no reading/research layout — no table of contents, no article view, no cross-reference navigation, no search over explanatory text, no curated reading order.
- **Nothing maintains explanatory content.** The factory (spec 024) grows the *question* bank and
the librarian loop that spec 047 slice 7 introduced judges *drafts*. No agent reviews, corrects, expands or re-verifies a body of explanatory knowledge on a schedule.

The goal is a knowledgebase: a first-class, versioned, cross-linked library of long-form LSAT material — exam architecture, per-section deep dives, every recurring question family, technique walkthroughs, strategy and pacing, review methodology — presented in a reading/research layout on both products, and kept current by an agent loop that audits, reviews, corrects and expands it.

## 2. Goals

- **G1**: Ship a substantive corpus of long-form LSAT material — at minimum 30 articles spanning
orientation, all four sections, every major question family, technique, strategy and review method — authored as reviewable Markdown, not as JSON string blobs.
- **G2**: Make the corpus *structured* knowledge rather than free text: typed blocks, typed inline
spans, first-class cross-references to concepts, archetypes, questions and other articles, and a prerequisite ordering that can be walked as a syllabus.
- **G3**: Give both products a real reading/research layout — table of contents, filterable index,
article reader with an in-page outline, cross-reference navigation, full-text search, and curated reading tracks — with the offline product losing no capability.
- **G4**: Make the library maintainable by agents on a schedule: a deterministic health audit, an
`LSATLibrarian` agent that reviews / corrects / expands articles, and an HITL gate so nothing an agent writes reaches a learner unreviewed.
- **G5**: Keep the whole library available offline in the static bundle and byte-stable across re-exports, so the existing drift gate extends to it unchanged.

## 3. Non-Goals

- **NG1**: Reproducing copyrighted LSAT preparation material, LSAC explanations, or real exam items. Every article is original (CC0) and pattern-derived, like the rest of the module.
- **NG2**: Claiming score improvement, score equivalence, or any outcome guarantee.
- **NG3**: Per-learner adaptive sequencing. Tracks are curated and static; learner modelling stays out of scope exactly as it is in spec 047 NG3.
- **NG4**: A rich-text authoring UI. Articles are authored as Markdown files in the repo and reviewed through the existing proposal/HITL path.
- **NG5**: Replacing the concept catalog. `concepts.json` remains the tagging vocabulary; articles reference concepts, they do not absorb them.
- **NG6**: Rendering arbitrary third-party Markdown. The parser accepts one documented dialect and fails loudly on anything else, so no untrusted HTML can ever reach either client.

## 4. User Stories

- As a **test taker new to the LSAT**, I want an orientation article explaining what the exam
measures, how it is scored, what each section demands and how long I should plan to prepare, so I can start studying with an accurate model of the test.
- As a **test taker working on a weakness**, I want a deep dive on one question family — what the
stem looks like, what the credited answer must do, the traps, a worked example, and the bank questions that drill it — so I can convert a diagnosed weakness into a method.
- As a **test taker**, I want to read in a layout built for reading: a contents rail, an in-page
outline, comfortable measure, and links that take me from an article to the concepts and drills it references and back, so studying does not mean scrolling one long page.
- As a **test taker preparing offline**, I want the whole library in the static bundle with working search and cross-links, so the offline product is a study tool and not just a drill tool.
- As a **test taker who does not know where to start**, I want curated reading tracks with an ordering and an honest time estimate, so I can follow a path rather than pick at random.
- As a **content reviewer**, I want the librarian agent to hand me specific, located findings with a proposed replacement, so reviewing is a decision rather than a rewrite.
- As a **maintainer**, I want a deterministic library health report — coverage, staleness, dead
cross-references, orphans, prerequisite cycles, thin articles — so "the library is being maintained" is a number and not a claim.

## 5. Functional Requirements

### Content model and parser (slice 1)

- **FR-1**: A `library.py` service defining an `Article` content type loaded from one Markdown
file per article under `services/data/library/`, with YAML-style frontmatter carrying `id`, `title`, `kind`, `level`, `sections`, `summary`, `concepts`, `archetypes`, `prerequisites`, `related`, `tags`, `status`, `last_reviewed`, `revision`, `source` and `references`. Loading follows the established `bank.py` pattern: file-backed, Pydantic-validated, lazy `lru_cache`, failing loudly on drift.
- **FR-2**: A restricted Markdown parser that converts an article body into a typed block list —
heading, paragraph, list, callout, table, notation — with typed inline spans (text, strong, emphasis, code, external link, concept reference, article reference). The dialect is closed: any construct the parser does not recognise is an error at load time, never silently-passed-through markup. No client ever renders raw HTML.
- **FR-3**: Cross-reference integrity is enforced at load: every `concepts` entry and every
`[[concept:…]]` span resolves against `concepts.json`; every `prerequisites`/`related` entry and every `[[article:…]]` span resolves against the library; every `[[question:…]]` span resolves against the bank; the prerequisite graph is acyclic; article ids are unique and match filenames.
- **FR-4**: Structural quality gates enforced by the loader, not by convention: an article carries
a non-empty summary, at least three `##` sections, at least one worked-example callout, and a key-takeaways list. `reading_minutes` is *computed* from the body word count, never declared.

### Corpus (slice 2)

- **FR-5**: At least 30 published articles covering: exam architecture and scoring; a deep dive per
section (LR, RC, LG, Writing); the recurring LR question families; RC passage-type and question-type technique; LG board technique; the argumentative-writing method; pacing, guessing and section strategy; blind review and error-log methodology; and the logic foundations (conditional, causal, quantifier, formal-logic) the sections rest on.
- **FR-6**: Curated reading tracks (`library_tracks.json`): an ordered list of article ids with a
goal statement, validated against the library and against the prerequisite graph, with the time estimate computed rather than declared.
- **FR-7**: Every concept in `concepts.json` that an article teaches is linked from that article, and the API exposes the inverse mapping so a concept page can list the articles that teach it.

### Reading surfaces (slice 3)

- **FR-8**: The platform app gains a `/lsat/library` route with a reading/research layout:
a filterable contents rail (by kind, section, level, track, tag), an article reader rendering the typed blocks, an in-page outline built from the article's headings, cross-reference navigation, and reading-position persistence.
- **FR-9**: Client-side full-text search across article titles, summaries, headings and body text,
with matched-context snippets — working identically on both products and with no network call on the static one.
- **FR-10**: The static site gains a Library view at parity: same blocks, same outline, same
search, same tracks, same cross-links, bundled offline, and reachable from the existing keyboard scheme.
- **FR-11**: A shared block-rendering contract, so an article renders identically on both products and a new block type cannot ship to one and not the other.

### API and export (slice 4)

- **FR-12**: API surface: `GET /api/lsat/library` (index, filterable), `GET /api/lsat/library/<id>`
(full article + resolved cross-references), `GET /api/lsat/library/tracks`, `GET /api/lsat/library/search?q=`, and `GET /api/lsat/library/health` (the deterministic audit).
- **FR-13**: `lsat_export` ships `library` and `library_tracks` into `content.json` under stable
ordering, bumping `schema_version`, and the root-suite drift gate covers them the way it covers questions and guides.

### Agent maintenance loop (slice 5)

- **FR-14**: A deterministic, model-free `library_audit()` reporting: article counts by kind /
section / level, concept coverage (concepts no article teaches), archetype coverage, stale articles (unreviewed beyond a threshold), orphans (no inbound cross-reference), dead references, thin articles (below a word floor), and prerequisite-graph health.
- **FR-15**: An `LSATLibrarian` agent implementing `run(input: dict) -> Pydantic` with three
actions — `review` (locate defects in an existing article), `correct` (propose replacement text for a located defect), `expand` (draft a new section or a new article for a declared gap) — routed through `law_ai.core.llm`, never a provider transport, with a deterministic degraded fallback at confidence 0.0 and one `provenance.log_agent_call` per run.
- **FR-16**: Everything the librarian produces is HITL-gated: findings and drafts land in the
existing proposal store under library-specific proposal kinds, and nothing reaches a learner without explicit promotion. `human_approval_required = True` on the agent class.
- **FR-17**: An `lsat_library` management command exposing `audit`, `review` and `promote`, runnable Docker-first via `make`, plus a scheduled entry so the review loop runs without a human starting it.

## 6. Non-Functional Requirements

- **NFR-OFFLINE-1**: The static Library view makes zero network calls — content, search index and cross-links all come from the bundle.
- **NFR-DETERMINISM-1**: `build_content()` output is byte-identical across runs for unchanged content apart from `generated_at`, library included.
- **NFR-SAFETY-1**: No article renders as HTML on either client; only typed blocks are rendered, so a malicious or malformed article cannot inject markup.
- **NFR-A11Y-1**: The reading layout meets the shell's existing bar: landmark structure, a heading
hierarchy that matches the article outline, visible focus, keyboard-reachable navigation, and respect for `prefers-reduced-motion`.
- **NFR-PERF-1**: The exported bundle stays under 1.5 MB and the library index renders without parsing every article body on the client.
- **NFR-UPL-1**: Every article carries the study-aid disclaimer posture the module already uses — this is LSAT preparation material, not legal advice.

## 7. Data Model Impact

New files under `backend/law_ai/lsat/services/`:

- `library.py` — `Article`, `ArticleKind`, `ArticleLevel`, `ReviewStatus`, `Block` union
(`HeadingBlock`, `ParagraphBlock`, `ListBlock`, `CalloutBlock`, `TableBlock`, `NotationBlock`), `Span`, `Track`, the frontmatter + Markdown parsers, `load_library()`, `load_tracks()`, `library_audit()`, `search_library()`, `public_article_view()`.
- `data/library/*.md` — one file per article.
- `data/library_tracks.json` — curated reading paths.

No Django migration and no Neo4j change: the library is file-backed content like the rest of the LSAT module. `content.json` gains `library` and `library_tracks` and bumps `schema_version` to 3.

## 8. API Surface

| Method | Path | Auth | Notes |
| ------ | ---- | ---- | ----- |
| GET | `/api/lsat/library` | `RequireLsat` | Index; filters `kind`, `section`, `level`, `tag`, `track`, `concept`. |
| GET | `/api/lsat/library/<article_id>` | `RequireLsat` | Full article + resolved concepts, prerequisites, related, and the bank questions that drill its concepts. |
| GET | `/api/lsat/library/tracks` | `RequireLsat` | Curated reading paths with computed durations. |
| GET | `/api/lsat/library/search` | `RequireLsat` | `q` (2–100 chars); returns ranked hits with snippets. |
| GET | `/api/lsat/library/health` | `RequireLsat` | Deterministic audit (FR-14). No model call. |

`GET /api/lsat/concepts/<id>` gains a `taught_in` list (FR-7). No endpoint in this spec invokes an LLM, so none carries the `llm` throttle scope.

## 9. Agent / Crew Impact

- New `LSATLibrarian` crew member (`agents_runtime/crews/lsat_librarian.py`) + versioned prompt
`agents_runtime/prompts/lsat_librarian.v1.md`. Registered like every other crew member; `human_approval_required = True`.
- Reuses `law_ai.lsat.services.proposals` with new proposal kinds (`library_finding`, `library_article`), so the existing HITL review, audit trail and promotion path apply unchanged.
- Every run writes one `provenance.log_agent_call` parent event; the underlying model call is logged by `law_ai.core.llm` as it already is.

## 10. Acceptance Criteria

- **AC-1**: `load_library()` returns ≥30 articles; a file with a dead `[[concept:…]]`,
a prerequisite cycle, a missing key-takeaways list, no worked example, fewer than three `##` sections, or an unparseable construct fails the load with a message naming the file.
- **AC-2**: `reading_minutes` is computed; declaring it in frontmatter is rejected.
- **AC-3**: `GET /api/lsat/library` returns the index without article bodies; `GET /api/lsat/library/<id>` returns typed blocks plus resolved cross-references; an unknown id 404s.
- **AC-4**: `GET /api/lsat/library/search?q=negation` returns ranked hits with snippets; `q` shorter than 2 characters is a 422.
- **AC-5**: `make lsat-export` writes `library` + `library_tracks` into `content.json`; re-running
it on unchanged content produces a byte-identical file apart from `generated_at`; the root drift gate fails when a library file changes without a re-export.
- **AC-6**: The platform app renders `/lsat/library` with contents rail, reader, outline and search; the static site renders the same library offline with the same blocks and the same search.
- **AC-7**: Neither client passes article content to `dangerouslySetInnerHTML`; a root-suite test asserts it.
- **AC-8**: `library_audit()` reports every category in FR-14 and is model-free — it runs with no provider configured.
- **AC-9**: `LSATLibrarian.run()` returns a validated Pydantic output for each of `review`,
`correct` and `expand`; with every provider unreachable it returns a degraded result at confidence 0.0 and still writes a provenance event.
- **AC-10**: Nothing the librarian produces mutates `data/library/` directly; promotion is a separate, explicit, audited step.
- **AC-11**: `make lint`, `make typecheck`, `make test` and `make lint-specs` all pass.

## 11. LegalBench Impact

None. The LSAT module is disjoint from the LegalBench harness, which stays pinned to Ollama (constitution §1). No eval task changes.

## 12. Risks & Open Questions

- **R1 — Bundle size.** 30+ articles of prose in `content.json` grows the static bundle. Mitigated
by NFR-PERF-1 and by the export profiles spec 047 FR-15 already introduced; if the full profile crosses the budget the library ships as its own shard.
- **R2 — A hand-rolled Markdown parser.** Rolling our own dialect avoids a new dependency and
guarantees no raw HTML reaches a client, at the cost of owning the parser. Mitigated by keeping the dialect closed, failing loudly, and testing the parser directly.
- **R3 — Agent-written prose drifting from fact.** An LLM confidently describing a section format
that LSAC changed is the failure mode that matters. Mitigated by HITL promotion (FR-16), by `last_reviewed` staleness surfacing in the audit, and by requiring a reference on factual claims about exam structure.
- **R4 — Two renderers drifting.** The platform and static block renderers can diverge. Mitigated by FR-11 and a root-suite test asserting both implement the same block-type set.

## 13. Out of Scope / Follow-ups

- Per-learner reading progress synced across devices (local persistence only here).
- Adaptive "read this next" recommendations driven by drill accuracy.
- Translating the library into the knowledge graph as `Concept`/`Article` nodes.
- An in-browser authoring or editing surface for reviewers.
