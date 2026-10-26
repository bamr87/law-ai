# Tasks: Static LSAT solving-aid parity

> Each task references `FR-*` / `NFR-*` / `AC-*` IDs from [spec.md](spec.md). CI's `spec_validator.py` enforces that every requirement is referenced by at least one task.

## Conventions

- Status: `[ ]` todo / `[~]` in-progress / `[x]` done.
- Owner: GitHub handle or `@copilot` / `@agent:<role>`.
- Each task lists exact files to touch and how to verify.

---

## T-001 — Ship the guides in the export

- **Refs**: FR-1, FR-2, NFR-PERF-2, AC-1
- **Owner**: @agent:claude-code
- **Status**: `[x]`
- **Files**: `backend/law_ai/lsat/management/commands/lsat_export.py`, `lsat-static/content.json`, `lsat-static/lib/{types,data}.ts`
- **Steps**: Emit guides for shipped questions, sorted; add `counts.guides`; type the spec 045 guide schema on the static side; add `guideFor` / `conceptById`.
- **Verify**: `make lsat-export` writes 40 guides; `pytest tests/lsat` and `tests/test_lsat_site.py` pass.

## T-002 — The carousel, offline

- **Refs**: FR-3, FR-4, AC-2, AC-3
- **Owner**: @agent:claude-code
- **Status**: `[x]`
- **Files**: `lsat-static/components/solve/SolveAssist.tsx` (new), `lsat-static/components/QuestionCard.tsx`
- **Steps**: One step per slide with back/next, dots, progressive reveal and per-session depth; lock spoiler steps client-side until graded, keeping title and position visible.
- **Verify**: In-browser — Hint reveals step 1 with method and count; the answer step is locked with no reveal control pre-grade and unlocks in place after.

## T-003 — The five diagram renderers

- **Refs**: FR-5, NFR-A11Y-1, NFR-SEC-1
- **Owner**: @agent:claude-code
- **Status**: `[x]`
- **Files**: `lsat-static/components/solve/diagrams/*.tsx` (new), `lsat-static/app/globals.css`
- **Steps**: Port sequence board, grouping grid, rule notation, argument map, passage map plus the exhaustive dispatcher onto semantic CSS; keep the generated SVG `aria-label`, the glyph+`sr-only` marks, and the text legend.
- **Verify**: In-browser — all five render (grid only after grading, since it sits on a spoiler step).

## T-004 — Concept references and naming

- **Refs**: FR-6, FR-7
- **Owner**: @agent:claude-code
- **Status**: `[x]`
- **Files**: `lsat-static/components/solve/ConceptRefs.tsx` (new), `lsat-static/app/page.tsx`, `lsat-static/app/globals.css`
- **Steps**: Resolve tagged concepts from the bundle instead of the API; align nav labels with the platform's tabs.
- **Verify**: Nav reads Overview / Logical Reasoning / Reading Comprehension / Logic Games / Concepts / Stats.

## T-005 — Gate the drift and tell the truth about deploys

- **Refs**: FR-8, FR-9, AC-5
- **Owner**: @agent:claude-code
- **Status**: `[x]`
- **Files**: `scripts/ux_audit.py`, `.github/workflows/deploy-lsat-pages.yml`, `frontend/components/lsat/{CrossCheckPanel,ValidationReport,SectionTimerWidget}.tsx`
- **Steps**: R13 requires a static counterpart or a `static-parity: none — <reason>`; declare the three that cannot port; drop the source-bank paths that produced no-op deploys.
- **Verify**: R13 flags exactly the undeclared components and passes once each is ported or declared.

## T-006 — Prove the constraints and document

- **Refs**: NFR-PERF-1, NFR-AUDIT-1, NFR-DOCS-1, AC-4, AC-6, AC-7
- **Owner**: @agent:claude-code
- **Status**: `[x]`
- **Files**: `docs/ui-ux.md`, `docs/ui-ux-review.md`, `BACKLOG.md`
- **Steps**: Build the export and inspect the artifact; record the portable/impossible split and the pass-log row.
- **Verify**: 14 KB CSS with zero Tailwind; `make test-frontend` 157 tests; `tsc`; `make lint-specs`.

---

## Done-When (Definition of Done)

- All tasks `[x]`.
- All `AC-*` covered by a passing check or a reproducible command.
- `make test-frontend`, `tsc --noEmit`, both builds, `pytest tests/lsat`, `make lint-specs` green.
- LegalBench delta: 0 pp.
- **`## Follow-ups Discovered` populated** and mirrored into [BACKLOG.md](../../BACKLOG.md).

---

## Follow-ups Discovered

- BL-20260831-22 — test-gap, high — The hint carousel now exists twice with no test that the two behave alike. R13 gates existence only. Once `lsat-static` has a test runner (BL-20260831-18), add a shared behavioural contract — reveal order, spoiler locking, dot navigation — exercised against both implementations.
- BL-20260831-23 — feature, med — 86 of 126 questions still have no solve guide, so most of the published site shows "No step-by-step guide for this question yet." Run the `lsat_guide_backfill` drafting command through the HITL queue to close the gap.
- BL-20260831-24 — refactor, low — `content.json` more than doubled to 339 KB now that guides ship. If it keeps growing, split guides into per-question chunks fetched on demand rather than bundling all of them at build time.
- BL-20260831-25 — doc-gap, low — The published site does not say which features it lacks relative to the full lab (AI tutor, cross-check, live stats). A short honest note would set expectations rather than leaving the difference to be discovered.
