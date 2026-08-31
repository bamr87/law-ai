# Spec: Static LSAT solving-aid parity

- **ID**: 046-static-lsat-feature-parity
- **Status**: shipped
- **Owner**: @bamr87
- **Created**: 2026-08-31
- **Roadmap Epic**: the published site teaches the same way the lab does
- **Constitution Compliance**: confirmed against [docs/constitution.md](../../docs/constitution.md). Spec 039 NFR-PERF-1 (Tailwind-free static export) preserved and verified on the built artifact.

## 1. Problem & Motivation

Spec 045 shipped the LSAT Lab's interactive solving aids — a progressive hint carousel, five typed diagram renderers, post-grade concept references — to `frontend/` and `backend/`, and **nothing** to `lsat-static/`. A user comparing the published GitHub Pages site to the Docker-run lab sees a different, poorer product.

Two things hid it. The Pages deploy *did* run for the spec 045 merge, because its path filter listed `backend/law_ai/lsat/services/data/**` as "belt-and-braces" — but that data never reaches the static site, which builds from `lsat-static/content.json`. The site was rebuilt without changing, which reads exactly like a successful update. And `scripts/ux_audit.py`, which had just been extended to both front ends by spec 044, checks *structure* — landmarks, focus, layout tokens — not whether a feature exists on both sides.

The guides are the frustrating part: all 40 are hand-authored static JSON that would work perfectly offline. They simply were not in the exporter's payload.

Spec 039 NG4 declared "merging the two LSAT products' feature sets" a non-goal. This spec deliberately narrows rather than reverses that: port what is *portable*, and make the rest an explicit, recorded decision.

## 2. Origin & Background

- Backlog items claimed: **BL-20260831-08** in part (the two products still keep separate roving-focus implementations; only the solving aids are shared here).
- Review question (constitution §13): no ranking, scoring, or summarising of legal authority. Spoiler discipline is *strengthened* — the answer step stays locked until the question is graded, on both surfaces.
- Who is the stronger here? The published site is what a prospective law student finds without an account, a Docker daemon, or a laptop that can run one. Shipping the teaching aids only to the surface that needs a dev environment inverts who gets the help.

## 3. Goals

- G1: The published site renders the same guides, carousel, and diagrams as the lab.
- G2: Spoiler discipline holds offline, with no server to withhold steps.
- G3: A feature landing on one LSAT surface and not the other becomes a build failure unless declared.
- G4: The deploy trigger tells the truth about what reaches the site.

## 4. Non-Goals

- NG1: AI cross-check, the AI tutor, HITL authoring, and the validation report. All need the provider chain or an API; a serverless site cannot host them at any effort.
- NG2: Live grading and server-side stats — the static site grades locally and stores progress in `localStorage` by design.
- NG3: Unifying the two roving-focus implementations (BL-20260831-08) or the two timers (BL-20260830-04).
- NG4: Giving the static site the platform's app shell (spec 044 NG2 still holds).
- NG5: Tailwind, or any build step, in the static export.

## 5. User Stories

- As a student on the public site, I want the same step-by-step hints the lab gives, so the free surface actually teaches.
- As a student, I want the answer step to stay shut until I have committed to an answer, even offline.
- As a student on a logic game, I want the board, the symbolised rules, and the elimination grid — not a wall of prose.
- As a contributor shipping an LSAT feature, I want the build to tell me the published site is about to fall behind.
- As a maintainer, I want a green Pages deploy to mean the site changed.

## 6. Functional Requirements

- **FR-1**: `lsat_export` emits `guides` — every solve guide whose question shipped, sorted for byte-stable re-exports — plus a `counts.guides` tally.
- **FR-2**: `lsat-static` types and data layer expose the spec 045 guide schema and a `guideFor(questionId)` lookup over the bundle.
- **FR-3**: A static `SolveAssist` renders the same carousel: one step per slide, back/next, step dots, progressive reveal, per-session revealed depth.
- **FR-4**: Spoiler steps ship in the bundle — as answer keys already do, since the site grades offline — and are locked **client-side** until the question is graded, mirroring `public_guide_view`. A locked step still shows its title and position.
- **FR-5**: All five typed representations render on the static site: sequence board, grouping grid, rule notation, argument map, passage map.
- **FR-6**: Post-grade `ConceptRefs` resolves tagged concepts against the bundled catalog rather than `/api/lsat/concepts`.
- **FR-7**: Static nav labels match the platform's tab labels.
- **FR-8**: `ux_audit.py` R13 fails the build for a component under `frontend/components/lsat/` with no same-named counterpart under `lsat-static/components/solve/` and no `static-parity: none — <reason>` marker.
- **FR-9**: The Pages deploy path filter lists only what actually reaches the site.

## 7. Non-Functional Requirements

- **NFR-PERF-1**: The export stays Tailwind-free. Verified on the artifact: 14 KB CSS, zero `tailwind` / `--tw-` occurrences.
- **NFR-PERF-2**: `content.json` grows with the guides. Measured at 339 KB for 126 questions + 40 guides — acceptable for a build-time bundle on a practice site, and it removes every per-hint network round trip the lab makes.
- **NFR-A11Y-1**: Ported diagrams keep the platform's accessibility properties: SVG boards carry a generated `aria-label` describing the board in words, grid marks pair a glyph with an `sr-only` word so meaning never rides on colour, and the notation legend is real text.
- **NFR-SEC-1**: No new dependencies in either app.
- **NFR-AUDIT-1**: No LLM, graph, or provenance changes. The static site makes no calls at all.
- **NFR-DOCS-1**: `docs/ui-ux.md`, `docs/ui-ux-review.md`, and the spec record which features are portable and which are structurally impossible offline.

## 8. Data Model Impact

None server-side. `content.json` gains a `guides` array and `counts.guides`, both optional in the TypeScript types so older artifacts still parse.

## 9. API Surface

None. The static site remains serverless.

## 10. Agent / Crew Impact

None to `agents_runtime`.

## 11. LegalBench Impact

- Tasks affected: none.
- Expected delta: 0 pp.

## 12. Acceptance Criteria

- **AC-1**: `make lsat-export` writes 40 guides into `lsat-static/content.json` with `counts.guides` set, and `tests/test_lsat_site.py` still passes.
- **AC-2**: On the built site, opening a Logic Games question and pressing Hint reveals step 1 with the method and step count; back/next and the dots move through revealed steps.
- **AC-3**: Before grading, the answer step renders locked with no way to reveal it; after grading it unlocks in place with its text.
- **AC-4**: All five representation types render on the built site — sequence and notation and grid on LG, argument map on LR, passage map on RC.
- **AC-5**: Reverting a port or dropping a marker makes `ux_audit.py` report R13; the fixed tree exits 0.
- **AC-6**: The emitted stylesheet contains no Tailwind runtime.
- **AC-7**: `make test-frontend`, `tsc --noEmit`, both builds, `pytest tests/lsat` and `tests/test_lsat_site.py`, `make lint-specs` are clean.

## 13. Risks & Open Questions

- **R-1**: Shipping spoiler steps to the browser means a determined user can read the answer in the bundle. Accepted: the answer key is already there — the site cannot grade offline otherwise — so this exposes nothing new. The UI honours the same discipline the API does.
- **R-2**: `content.json` more than doubled (150 KB → 339 KB). Accepted for a build-time bundle; if it keeps growing, per-question guide chunks are the fix.
- **R-3**: R13 keys on filename, so a rename on either side reads as a missing port. Preferred to a hand-maintained manifest, which drifts silently; a rename failing loudly is the correct bias.
- **R-4**: The static carousel is a second implementation of the platform's, so a behaviour change must be made twice. Bounded by R13 (the file must exist) but not by any test that the two behave alike — recorded as a follow-up.

## 14. Out of Scope / Follow-ups

Recorded in `tasks.md` ## Follow-ups Discovered and mirrored to BACKLOG.
