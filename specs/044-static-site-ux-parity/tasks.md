# Tasks: Static LSAT site UI/UX parity

> Each task references `FR-*` / `NFR-*` / `AC-*` IDs from [spec.md](spec.md). CI's `spec_validator.py` enforces that every requirement is referenced by at least one task.

## Conventions

- Status: `[ ]` todo / `[~]` in-progress / `[x]` done.
- Owner: GitHub handle or `@copilot` / `@agent:<role>`.
- Each task lists exact files to touch and how to verify.

---

## T-001 — Extract the shared primitives

- **Refs**: FR-1, FR-2, NFR-SEC-1
- **Owner**: @agent:claude-code
- **Status**: `[x]`
- **Files**: `frontend/ui/base.css` (new), `frontend/ui/layout.css`, `lsat-static/app/base.css` (new, mirrored), `lsat-static/app/globals.css`, `Makefile`
- **Steps**: Move the z-scale, focus ring, and motion opt-out into `base.css`; have `layout.css` import it; mirror it into the static app because Next cannot resolve a cross-root CSS import; add `make ui-sync`.
- **Verify**: Platform build and 135 tests still pass; static export builds.

## T-002 — Gate the mirror and both surfaces

- **Refs**: FR-3, FR-8, FR-9, NFR-TEST-1, AC-5, AC-6
- **Owner**: @agent:claude-code
- **Status**: `[x]`
- **Files**: `scripts/ux_audit.py`
- **Steps**: R12 mirror-drift check; scan `lsat-static/{app,components}` with the universal rules only; scan stylesheets for R4/R9; fix the R3 and R11 false positives the second surface exposed.
- **Verify**: Each rule fails against an injected violation and passes on the fixed tree.

## T-003 — Landmarks and the skip link

- **Refs**: FR-4, FR-5, AC-1, AC-2
- **Owner**: @agent:claude-code
- **Status**: `[x]`
- **Files**: `lsat-static/app/layout.tsx`, `lsat-static/app/page.tsx`, `lsat-static/app/globals.css`
- **Steps**: Skip link as the first body child targeting `main#view`, revealed on focus; demote the page's information strip so the UPL disclaimer is the only `contentinfo`.
- **Verify**: Built `out/index.html` has one `<main>` and one `contentinfo`; in-browser the skip link is the first tab stop and moves into view on focus.

## T-004 — The sticky stack

- **Refs**: FR-6, FR-7, NFR-A11Y-1, NFR-A11Y-2, AC-3, AC-4
- **Owner**: @agent:claude-code
- **Status**: `[x]`
- **Files**: `lsat-static/app/globals.css`
- **Steps**: Tokens for the site header and drill-head heights; `z-index` off the shared scale; pin the drill head and passage at ≥820px only; `align-self: start` so the passage's sticky can travel; point the global `:focus-visible` at the shared token.
- **Verify**: At 1440px the drill head pins with a −1px tuck and the clock stays visible; at 390px neither is sticky and the header is 16% of the viewport.

## T-005 — Prove the constraints still hold

- **Refs**: NFR-PERF-1, AC-7, AC-8
- **Owner**: @agent:claude-code
- **Status**: `[x]`
- **Files**: build artifacts only
- **Steps**: Build the static export and inspect the emitted CSS.
- **Verify**: 9.6 KB stylesheet, shared tokens present, zero `tailwind` / `--tw-` occurrences.

## T-006 — Docs and backlog

- **Refs**: NFR-DOCS-1
- **Owner**: @agent:claude-code
- **Status**: `[x]`
- **Files**: `docs/ui-ux.md`, `docs/ui-ux-review.md`, `frontend/ui/README.md`, `BACKLOG.md`
- **Steps**: Record the two-surface contract, the rule table additions, the pass-log row, and the follow-ups; close BL-20260831-04.
- **Verify**: `make lint-specs`; `python3 tools/unwrap-prose.py --check`.

---

## Done-When (Definition of Done)

- All tasks `[x]`.
- All `AC-*` covered by a passing check or a reproducible command.
- `make test-frontend`, `tsc --noEmit`, both `npm run build`s, `make lint-specs` green.
- LegalBench delta: 0 pp.
- **`## Follow-ups Discovered` populated** and mirrored into [BACKLOG.md](../../BACKLOG.md).

---

## Follow-ups Discovered

- BL-20260831-18 — test-gap, med — `lsat-static` has no test runner at all, so its behaviour is verified only by the audit and by hand. Add Vitest + RTL there, starting with the `QuestionCard` radiogroup keyboard pattern that the platform now has covered and the static site does not.
- BL-20260831-19 — feature, low — A passage taller than the viewport gets no benefit from top-stickiness; browsers only pin such an element once its bottom is reached. Give the passage column its own scroll region, or anchor it with `bottom`, so long RC passages actually stay beside their questions.
- BL-20260831-20 — refactor, low — `--site-header-h` and `--drill-head-h` are measured constants. A container query or a small `ResizeObserver` would let the sticky stack track the real header height instead of a number that has to be re-measured whenever the header's content changes.
