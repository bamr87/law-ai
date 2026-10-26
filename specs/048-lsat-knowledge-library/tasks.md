# Tasks: LSAT Knowledge Library

> Each task references one or more `FR-*` / `NFR-*` / `AC-*` IDs from `spec.md`. CI's `spec_validator.py` enforces that every requirement is referenced by at least one task.

## Conventions

- Status: `[ ]` todo / `[~]` in-progress / `[x]` done.
- Owner: GitHub handle or `@copilot` / `@agent:<role>`.
- Each task lists exact files to touch and how to verify.
- Tasks are grouped into **slices**; one slice = one PR.

---

# Slice 1 — Content model and parser

## T-001 — Article model, frontmatter parser, typed-block Markdown parser

- **Refs**: FR-1, FR-2, NFR-SAFETY-1, AC-2
- **Owner**: @bamr87
- **Status**: `[x]`
- **Files**:
  - `backend/law_ai/lsat/services/library.py` (new)
- **Steps**:
  1. Model `Article`, `ArticleKind`, `ArticleLevel`, `ReviewStatus`, `Track`, the `Block`
     discriminated union and `Span`.
  2. Write the restricted frontmatter parser (scalars, inline lists, block lists, nested
     reference objects) — no YAML dependency, strict on anything else.
  3. Write the block parser: `##`/`###` headings, paragraphs, bullet and ordered lists,
     `> [!variant]` callouts, pipe tables, fenced notation blocks.
  4. Write the inline parser: strong, emphasis, code, external link, `[[concept:…]]`,
     `[[article:…]]`, `[[question:…]]`.
  5. Reject a declared `reading_minutes`; compute it from the body word count.
- **Verify**:
  - `docker compose run --rm backend pytest tests/lsat/test_library_parser.py -q --no-cov` passes.
  - `make typecheck` clean.

## T-002 — Loader, cross-reference integrity, structural quality gates

- **Refs**: FR-3, FR-4, AC-1
- **Owner**: @bamr87
- **Status**: `[x]`
- **Files**:
  - `backend/law_ai/lsat/services/library.py` (edit)
  - `backend/tests/lsat/test_library.py` (new)
- **Steps**:
  1. `load_library()` / `load_tracks()` as lazy `lru_cache` loaders resolving `bank.DATA_DIR`
     through the bank module so test sandboxes redirect them.
  2. Enforce: unique ids matching filenames; every concept/article/question reference resolves;
     acyclic prerequisites; ≥3 `##` sections; ≥1 worked-example callout; a key-takeaways list;
     non-empty summary.
  3. Add `public_article_view()` (index rows carry no body) and `reset_library_caches()`.
  4. One failing-case test per rule, each asserting the file name appears in the message.
- **Verify**: `docker compose run --rm backend pytest tests/lsat/test_library.py -q --no-cov` passes.

---

# Slice 2 — The corpus

## T-010 — Author the article corpus

- **Refs**: FR-5, NFR-UPL-1
- **Owner**: @bamr87
- **Status**: `[x]`
- **Files**:
  - `backend/law_ai/lsat/services/data/library/*.md` (new)
- **Steps**:
  1. Orientation and scoring; a deep dive per section; the LR question families; RC technique;
     LG board technique; the writing method; pacing/guessing/strategy; blind review and error
     logging; logic foundations.
  2. Every article: original (CC0), study-aid framing, worked example, key takeaways, concept
     links, and a reference on any structural claim about the exam.
- **Verify**: `docker compose run --rm backend pytest tests/lsat/test_library_corpus.py -q --no-cov` passes.

## T-011 — Curated reading tracks

- **Refs**: FR-6
- **Owner**: @bamr87
- **Status**: `[x]`
- **Files**:
  - `backend/law_ai/lsat/services/data/library_tracks.json` (new)
  - `backend/law_ai/lsat/services/library.py` (edit — `load_tracks`, computed durations)
- **Steps**: author the tracks, validate every id against the library, compute durations from the
  member articles, and reject a track that lists an article before its prerequisite.
- **Verify**: covered by `tests/lsat/test_library.py::TestTracks`.

## T-012 — Concept ↔ article linkage

- **Refs**: FR-7
- **Owner**: @bamr87
- **Status**: `[x]`
- **Files**:
  - `backend/law_ai/lsat/services/library.py` (edit — `articles_teaching()`)
  - `backend/law_ai/lsat/urls.py` (edit — `ConceptDetailView` gains `taught_in`)
- **Verify**: `tests/lsat/test_library_api.py::TestConceptLinkage`.

---

# Slice 3 — API and export

## T-020 — Library API surface

- **Refs**: FR-12, AC-3, AC-4
- **Owner**: @bamr87
- **Status**: `[x]`
- **Files**:
  - `backend/law_ai/lsat/urls.py` (edit)
  - `backend/law_ai/lsat/services/library.py` (edit — `search_library()`)
  - `backend/tests/lsat/test_library_api.py` (new)
- **Steps**: index with filters, detail with resolved cross-references, tracks, ranked search with
  snippets and a 422 on a too-short query, and the health endpoint.
- **Verify**: `docker compose run --rm backend pytest tests/lsat/test_library_api.py -q --no-cov` passes.

## T-021 — Export the library into the static artifact

- **Refs**: FR-13, NFR-DETERMINISM-1, NFR-PERF-1, AC-5
- **Owner**: @bamr87
- **Status**: `[x]`
- **Files**:
  - `backend/law_ai/lsat/management/commands/lsat_export.py` (edit)
  - `backend/tests/lsat/test_export_site.py` (edit)
  - `tests/test_lsat_site.py` (edit — library drift gate, bundle budget)
- **Verify**: `make lsat-export` twice produces files differing only in `generated_at`.

---

# Slice 4 — Reading surfaces

## T-030 — Shared block-rendering contract + platform reader

- **Refs**: FR-8, FR-11, NFR-A11Y-1, AC-6, AC-7
- **Owner**: @bamr87
- **Status**: `[x]`
- **Files**:
  - `frontend/lib/api.ts` (edit), `frontend/lib/lsat/library.ts` (new)
  - `frontend/components/lsat/library/*` (new)
  - `frontend/app/(app)/lsat/library/page.tsx` (new)
  - `frontend/lib/modules/catalog.ts` (edit)
- **Steps**: contents rail with filters, article reader, in-page outline, cross-reference
navigation, reading-position persistence, and a block renderer covering every block type with no raw-HTML path.
- **Verify**: `make test-frontend`; `frontend/__tests__/components/LsatLibrary.test.tsx`.

## T-031 — Search on both products

- **Refs**: FR-9
- **Owner**: @bamr87
- **Status**: `[x]`
- **Files**:
  - `frontend/lib/lsat/library.ts` (edit), `lsat-static/lib/search.ts` (new)
- **Verify**: search tests in both suites; the static one makes no network call.

## T-032 — Static-site Library view at parity

- **Refs**: FR-10, NFR-OFFLINE-1
- **Owner**: @bamr87
- **Status**: `[x]`
- **Files**:
  - `lsat-static/lib/types.ts`, `lsat-static/lib/data.ts` (edit)
  - `lsat-static/components/Library.tsx`, `lsat-static/components/library/*` (new)
  - `lsat-static/app/page.tsx`, `lsat-static/app/globals.css` (edit)
- **Verify**: `make lsat-static-build`; `tests/test_lsat_site.py` structure + parity gates.

---

# Slice 5 — Agent maintenance loop

## T-040 — Deterministic library health audit

- **Refs**: FR-14, AC-8
- **Owner**: @bamr87
- **Status**: `[x]`
- **Files**:
  - `backend/law_ai/lsat/services/library.py` (edit — `library_audit()`)
  - `backend/tests/lsat/test_library_audit.py` (new)
- **Verify**: audit runs with no provider configured and reports every FR-14 category.

## T-041 — `LSATLibrarian` agent

- **Refs**: FR-15, AC-9
- **Owner**: @bamr87
- **Status**: `[x]`
- **Files**:
  - `backend/law_ai/agents_runtime/crews/lsat_librarian.py` (new)
  - `backend/law_ai/agents_runtime/prompts/lsat_librarian.v1.md` (new)
  - `backend/tests/agents/test_lsat_librarian.py` (new)
- **Verify**: each action returns a validated output; degraded path returns confidence 0.0 and
  still writes a provenance event.

## T-042 — HITL gate + `lsat_library` command + schedule

- **Refs**: FR-16, FR-17, AC-10, AC-11
- **Owner**: @bamr87
- **Status**: `[x]`
- **Files**:
  - `backend/law_ai/lsat/management/commands/lsat_library.py` (new)
  - `backend/law_ai/lsat/services/proposals.py` (edit — library proposal kinds + promotion)
  - `Makefile` (edit), `backend/law_ai/settings/base.py` (edit — beat entry)
  - `docs/lsat-library.md` (new)
- **Verify**: `make lint`, `make typecheck`, `make test`, `make lint-specs` all pass; `review`
  writes nothing under `data/library/`.

---

## Done-When (Definition of Done)

- Every task above is `[x]`.
- The four gates pass: `make lint`, `make typecheck`, `make test`, `make lint-specs`.
- `make lsat-export` is current — the committed `lsat-static/content.json` carries the library.
- Follow-ups below are mirrored into [BACKLOG.md](../../BACKLOG.md) and copied into the PR body.

## Follow-ups Discovered

- **BL-20260903-05** — *feature, med* — Reading progress is per-browser `localStorage` on both
products; there is no cross-device sync and no fold-in to `/api/lsat/stats`, so "articles read" is invisible next to drill accuracy.
- **BL-20260903-06** — *feature, med* — Library search is a substring + field-weight ranker with no
stemming, synonym handling or fuzzy matching; "assumptions" does not match "assumption" in body text. Good enough for a 30-article corpus, visibly weak by 100.
- **BL-20260903-07** — *test-gap, med* — The static Library view ships with no component test
because `lsat-static` still has no test runner (BL-20260831-18); its reader, outline and search are covered only structurally by the root suite. Same gap as BL-20260831-26.
- **BL-20260903-08** — *feature, low* — `LSATLibrarian` reviews one article per run. There is no
corpus-wide pass that reads the audit and picks its own targets, so the scheduled cycle needs a human-chosen target list until a picker exists.
- **BL-20260903-09** — *doc-gap, low* — The article dialect is documented in `library.py`'s
docstring and `docs/lsat-library.md`, but there is no authoring template under `data/library/_template.md`, so a new author copies an existing article and edits it.
