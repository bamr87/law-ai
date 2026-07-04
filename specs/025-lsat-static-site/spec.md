# Spec: LSAT Static Practice Site — Serverless Delivery on GitHub Pages

- **ID**: 025-lsat-static-site
- **Status**: shipped
- **Owner**: @bamr87
- **Created**: 2026-07-02
- **Roadmap Epic**: extends spec 005 (LSAT Lab) / spec 024 (content factory) — public, serverless delivery channel for the approved question bank
- **Constitution Compliance**: confirmed against [docs/constitution.md](../../docs/constitution.md) — no runtime LLM at all (the static site is pure content, §1 trivially satisfied); only HITL-approved bank content is exported (§5); the exporter runs Docker-first and is deterministic; no audit-layer bypass because no agent/LLM/retrieval calls occur.

## 1. Problem & Motivation

The LSAT Lab lives behind the full Docker stack (Django API + Next.js + Neo4j/Postgres/Redis). Learners can't touch it without running six containers. The question bank itself, however, is plain approved JSON — nothing about *practicing* (read question → pick answer → see explanation → track accuracy) needs a server. Publishing the module as a static site gives end-users a zero-install practice app at a public URL, hosted free on GitHub Pages, always in sync with the HITL-approved bank.

## 2. Goals

- **G1**: A Docker-first exporter that snapshots the entire LSAT content module (sections, concepts, passages, questions **including answer keys + explanations**) into a single versioned static artifact, validated through the existing Pydantic loaders.
- **G2**: A zero-build static web app (plain HTML/CSS/JS, no framework, no bundler) that renders that artifact: section overview, LR drill, RC/LG passage+game practice, concept catalog, and localStorage-backed progress stats with client-side grading.
- **G3**: Serverless deployment to GitHub Pages via a GitHub Actions workflow that uploads the committed site directory as-is (no CI build step).
- **G4**: A drift gate: CI fails when the bank changes without re-exporting, so the published site can never silently lag the approved content.
- **G5**: Interaction parity with the LSAT Lab where it matters: A–E/Enter keyboard drilling (modifier-safe), radiogroup semantics, `aria-live` result announcements, explanation + references after grading.

## 3. Non-Goals

- **NG1**: No AI tutor, authoring, or proposals surface — those require the runtime stack and stay in the Lab. The static app is practice-only.
- **NG2**: No user accounts or cross-device sync; progress lives in `localStorage` only.
- **NG3**: No answer-key obfuscation. Keys and explanations are already public in this repository (CC0 content); the practice app grades client-side by design.
- **NG4**: No new frontend framework or npm dependency — the site must stay buildless.
- **NG5**: No timed-section simulation mode in v1 (recorded as a follow-up).

## 4. User Stories

- As a **learner without the dev stack**, I want a public URL where I can drill LSAT questions and see explanations, so I can practice from any browser.
- As a **content maintainer**, I want `make lsat-export` to regenerate the site data from the approved bank, and CI to fail if I forget, so the published app never drifts from the source of truth.
- As a **keyboard-first user**, I want A–E/Enter drilling and screen-reader announcements, matching the Lab's accessibility affordances.

## 5. Functional Requirements

- **FR-1**: `python manage.py lsat_export [--out DIR] [--pretty]` (backend, Docker-first) writes `content.json` containing `{schema_version, generated_at, counts, sections, concepts, passages, questions}` where `questions` are full `Question` model dumps (id, section, difficulty, stem, choices, **correct**, **explanation**, concepts, references, passage_id, source). Content loads through `load_bank()/load_passages()/load_concepts()/load_sections()` so only loader-valid data can ship. Default out dir: `var/lsat_site` (in-container).
- **FR-2**: The export is deterministic for a fixed bank (stable ordering: sections LR/RC/LG, questions by id, concepts/passages by id) apart from the `generated_at` timestamp; `counts` summarizes totals per section for the drift gate and the site footer.
- **FR-3**: The static app lives at `frontend/public/lsat-practice/` (`index.html`, `styles.css`, `app.js`, `.nojekyll`, `data/content.json`) using **relative** URLs only, so it works at any base path (GitHub Pages project sites serve under `/<repo>/`) and is also served verbatim by the existing Next dev server at `/lsat-practice/` for local verification.
- **FR-4**: The app provides hash-routed views: `#/home` (section cards + data-version footer), `#/drill/LR` (question drill with difficulty filter + shuffle), `#/passages/RC` and `#/passages/LG` (context list → reader + linked question stack), `#/concepts` (searchable catalog with expandable detail), `#/stats` (attempts, accuracy, per-section table, reset).
- **FR-5**: Question cards grade client-side: A–E radio choices, Submit, correct/incorrect verdict, explanation + reference links, Next. Keyboard: unmodified A–E selects, Enter submits (Ctrl/⌘/Alt combos pass through); `role="radiogroup"`/`role="radio"` semantics and a visually hidden `aria-live="polite"` region announcing results.
- **FR-6**: Attempts persist to `localStorage` (`lsat-practice.attempts.v1`): `{qid, section, choice, correct, ts}`; the stats view aggregates all-time and per-section accuracy and offers a destructive-confirmed reset.
- **FR-7**: `make lsat-export` runs the exporter in Docker and copies the artifact into `frontend/public/lsat-practice/data/` (host-side copy inside the make target).
- **FR-8**: Root-suite drift + structure test (`tests/test_lsat_site.py`, stdlib-only): site files exist; committed `content.json` question ids/keys/counts exactly match the bank JSON under `backend/lawgraph/lsat/services/data/`; every question's `correct` label exists among its choices; every `passage_id` resolves.
- **FR-9**: `.github/workflows/deploy-lsat-pages.yml` deploys `frontend/public/lsat-practice/` as the Pages artifact on pushes to `main` touching the site or LSAT data (plus `workflow_dispatch`), using `actions/configure-pages` → `upload-pages-artifact` → `deploy-pages` with the standard `pages: write` / `id-token: write` permissions. No build step.

## 6. Non-Functional Requirements

- **NFR-PERF-1**: One data fetch per session (`content.json`, currently ~150 KB); the app renders on a single HTML/JS/CSS load with no external assets (self-contained, CSP-friendly).
- **NFR-SEC-1**: No secrets, tokens, or API calls anywhere in the site; the workflow uses only the built-in `GITHUB_TOKEN` via the official Pages actions.
- **NFR-TEST-1**: Exporter covered by backend tests (Docker); site structure + data drift covered by the stdlib root suite; interactive behavior verified in a real browser before ship.
- **NFR-A11Y-1**: Keyboard-only operation possible end-to-end; results announced via `aria-live`; focus states visible.

## 7. Data Model Impact

None (read-only export of existing JSON fixtures). New committed artifact: `frontend/public/lsat-practice/data/content.json` (generated, drift-gated).

## 8. API Surface

No HTTP API changes. New CLI: `manage.py lsat_export`. New make target: `lsat-export`.

## 9. Agent / Crew Impact

None — no agents, no LLM, no provenance events (nothing to audit: static content publishing).

## 10. Acceptance Criteria

- **AC-1**: `make lsat-export` (Docker) regenerates `content.json`; running it twice yields identical files apart from `generated_at`.
- **AC-2**: Opening the site over plain static file serving (no backend) allows: pick LR drill → answer with keyboard A+Enter → see verdict + explanation → stats view shows the attempt.
- **AC-3**: RC and LG views render the passage/game text with its linked questions; grading works against them.
- **AC-4**: With a bank question edited and no re-export, the root drift test fails; after `make lsat-export` it passes.
- **AC-5**: The Pages workflow validates (actionlint-clean structure) and uploads only `frontend/public/lsat-practice`; the app works under a non-root base path (all URLs relative).
