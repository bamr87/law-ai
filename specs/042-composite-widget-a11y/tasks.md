# Tasks: Composite-widget keyboard accessibility

> Each task references `FR-*` / `NFR-*` / `AC-*` IDs from [spec.md](spec.md). CI's [spec_validator.py](../../scripts/spec_validator.py) enforces that every requirement is referenced by at least one task.

## Conventions

- Status: `[ ]` todo / `[~]` in-progress / `[x]` done.
- Owner: GitHub handle or `@copilot` / `@agent:<role>`.
- Each task lists exact files to touch and how to verify.

---

## T-001 — Roving-focus mechanism

- **Refs**: FR-1, FR-2, NFR-A11Y-2, NFR-SEC-1, AC-4
- **Owner**: @agent:claude-code
- **Status**: `[x]`
- **Files**: `frontend/lib/shell/rovingFocus.ts` (new), `frontend/components/shell/useRovingTabIndex.ts` (new)
- **Steps**:
  1. Pure `nextRovingIndex` — orientation, wrap, Home/End, null for modified chords and foreign keys.
  2. `useRovingTabIndex` — exactly one `tabIndex=0`, arrows move focus and activate, group reachable when nothing is selected.
- **Verify**: `rovingFocus.test.tsx` unit cases pass.

## T-002 — LSAT tab bar onto the tabs pattern

- **Refs**: FR-3, NFR-A11Y-1, AC-1, AC-2
- **Owner**: @agent:claude-code
- **Status**: `[x]`
- **Files**: `frontend/components/LsatLab.tsx`
- **Steps**: `aria-controls` per tab, a `role="tabpanel"` labelled by its tab at `tabIndex=0`, roving tab stop, selection follows focus.
- **Verify**: In-browser — 1 tab stop (was 7), 7 `aria-controls` (was 0), ArrowRight moves focus + selection, End/wrap work.

## T-003 — LSAT answer list onto the radiogroup pattern

- **Refs**: FR-4, NFR-A11Y-1, AC-3
- **Owner**: @agent:claude-code
- **Status**: `[x]`
- **Files**: `frontend/components/LsatLab.tsx`
- **Steps**: Name the group, vertical orientation, roving tabindex, arrows move and select; keep the choice letter in the accessible name.
- **Verify**: In-browser — group named, 1 tab stop of 5, ArrowDown moves and checks, ArrowRight inert, letter retained.

## T-004 — Name every control and the graph region

- **Refs**: FR-5, FR-6, FR-7
- **Owner**: @agent:claude-code
- **Status**: `[x]`
- **Files**: `frontend/components/{KnowledgeGraph,AgentDashboard,LsatLab,GraphViewer}.tsx`, `frontend/app/icon.svg` (new), `frontend/app/layout.tsx`
- **Steps**: Label the three placeholder-only controls; make the canvas a named `role="img"` region citing the case list; serve `app/icon.svg` and drop the dead `/favicon.ico` reference.
- **Verify**: Browser console reports 0 errors (AC-7); no unlabelled visible control remains.

## T-005 — Gate both halves

- **Refs**: FR-8, NFR-TEST-1, AC-5, AC-6
- **Owner**: @agent:claude-code
- **Status**: `[x]`
- **Files**: `scripts/ux_audit.py`, `frontend/__tests__/shell/rovingFocus.test.tsx` (new)
- **Steps**: R10 and R11 with a brace-aware JSX tag scanner; RTL coverage for the behavioural half.
- **Verify**: Each rule fails against the reverted markup (R10: 2 findings, R11: 3) and passes on the fixed tree; `make test-frontend` 119 tests.

## T-006 — Docs, gates, backlog

- **Refs**: NFR-DOCS-1, NFR-AUDIT-1, NFR-HITL-1, AC-7
- **Owner**: @agent:claude-code
- **Status**: `[x]`
- **Files**: `docs/ui-ux.md`, `docs/ui-ux-review.md`, `frontend/ui/README.md`, `BACKLOG.md`
- **Steps**: Rule table, pass-log row, resolved findings, catalog entry, follow-ups.
- **Verify**: `make lint-specs`; `python3 tools/unwrap-prose.py --check`.

---

## Done-When (Definition of Done)

- All tasks `[x]`.
- All `AC-*` covered by a passing test or a reproducible command.
- `make test-frontend`, `tsc --noEmit`, `npm run lint` (0 errors), `make lint-specs` green.
- LegalBench delta: 0 pp.
- **`## Follow-ups Discovered` populated** and mirrored into [BACKLOG.md](../../BACKLOG.md).

---

## Follow-ups Discovered

- BL-20260831-08 — feature, med — Port `lsat-static/components/QuestionCard.tsx` onto the shared roving-focus mechanism so the two products stop maintaining the same keyboard pattern twice; today only the platform side is gated.
- BL-20260831-09 — test-gap, med — The UX audit's browser half is manual. Wire a Playwright a11y smoke (axe-core or equivalent) over the six routes into CI so contrast, name-role-value, and focus order are checked on every PR rather than once per review pass.
- BL-20260831-10 — feature, low — `AnalysisStudio.tsx` silently truncates pasted input at 20,000 characters (`value.slice(0, MAX_LEN)`); warn on truncation instead of dropping text without telling the user.
- BL-20260831-11 — refactor, low — 27 interactive targets are under 44×44 CSS px at a 390px viewport (all clear the 24px WCAG 2.5.8 AA floor); raise the masthead controls and LSAT tabs toward the 44px AAA/HIG guideline.
- BL-20260831-12 — feature, low — The graph canvas is named but still has no keyboard-operable equivalent for node selection; the case list covers reading, not traversal of `CITES` edges.
