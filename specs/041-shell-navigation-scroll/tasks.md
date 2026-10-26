# Tasks: Application shell navigation & scroll contract

> Each task references `FR-*` / `NFR-*` / `AC-*` IDs from [spec.md](spec.md). CI's `spec_validator.py` enforces that every requirement is referenced by at least one task.

## Conventions

- Status: `[ ]` todo / `[~]` in-progress / `[x]` done.
- Owner: GitHub handle or `@copilot` / `@agent:<role>`.
- Each task lists exact files to touch and how to verify.

---

## T-001 — Layout token layer

- **Refs**: FR-9, NFR-A11Y-1, NFR-A11Y-2, NFR-SEC-1
- **Owner**: @agent:claude-code
- **Status**: `[x]`
- **Files**:
  - `frontend/ui/layout.css` (new), `frontend/ui/README.md` (new)
  - `frontend/app/globals.css`
- **Steps**:
  1. Shell metrics, the three-rung sticky stack, and the `--z-*` scale as custom properties.
  2. `.shell-scroll` / `.shell-panel-scroll` with contained overscroll and a stable gutter; `.focus-ring` / `.focus-ring-practice`; `.shell-motion`.
  3. Import from `globals.css`; catalogue every token and class in the README.
- **Verify**: `npm run build` compiles the import chain and prerenders every route.

## T-002 — Viewport-locked shell

- **Refs**: FR-1, FR-3, NFR-PERF-1
- **Owner**: @agent:claude-code
- **Status**: `[x]`
- **Files**:
  - `frontend/components/shell/AppShell.tsx`, `ShellScroll.tsx` (new), `BackToTop.tsx` (new)
  - `frontend/components/shell/{NavRail,ContextSidebar,InspectorPanel}.tsx`
  - `frontend/app/layout.tsx`, `frontend/lib/shell/scrollMemory.ts` (new)
- **Steps**:
  1. `h-dvh overflow-hidden` on the shell and the document; chrome becomes non-scrolling flex children.
  2. `<main class="shell-scroll">` becomes the only content scroller; panels take `.shell-panel-scroll`.
  3. `useMainScrollController` publishes scroll state through context, coalescing to one `requestAnimationFrame`; restore per-route offset before paint; move the UPL footer inside the scroll region.
- **Verify**: `ShellBehaviour.test.tsx` — chrome is outside `<main>`, footer inside it, remembered offset restored.

## T-003 — Page frame and the sticky stack

- **Refs**: FR-2, FR-10, AC-2
- **Owner**: @agent:claude-code
- **Status**: `[x]`
- **Files**:
  - `frontend/components/shell/PageLayout.tsx` (new)
  - `frontend/app/(app)/{agents,analysis,graph,lsat,settings}/page.tsx`
  - `frontend/components/{LsatLab,AgentDashboard,KnowledgeGraph}.tsx`
- **Steps**:
  1. `PageLayout` — sticky condensing header (title survives; eyebrow and description do not) plus a measured body container.
  2. `StickyToolbar` parks against `--shell-pageheader-h`.
  3. Migrate the five non-hero routes; pin the LSAT section switcher, the Agent Ops polling controls, the graph case picker, and the RC/LG passage.
- **Verify**: `data-condensed` flips with `scrolled`; `make test-frontend`.

## T-004 — Keyboard contract, palette, and masthead

- **Refs**: FR-4, FR-5, FR-7, AC-4, AC-5
- **Owner**: @agent:claude-code
- **Status**: `[x]`
- **Files**:
  - `frontend/lib/shell/{shortcuts,commands,panels}.ts` (new), `frontend/lib/modules/catalog.ts`
  - `frontend/components/shell/{CommandPalette,ShortcutsHelp,Masthead}.tsx`
- **Steps**:
  1. Pure `matchShortcut` with a typing guard; `⌘K` and `Esc` stay live inside a field.
  2. Palette generated from `MODULE_CATALOG` with alias-aware ranking and listbox semantics.
  3. Breadcrumbs from the catalog; panel toggles wired with `aria-expanded` + `aria-controls`.
- **Verify**: `[` typed into a textarea reaches the field; "graph" + Enter navigates to `/graph`.

## T-005 — Compact viewport and route states

- **Refs**: FR-6, FR-8, FR-12, NFR-A11Y-1
- **Owner**: @agent:claude-code
- **Status**: `[x]`
- **Files**:
  - `frontend/components/shell/{Overlay,MobileTabBar,useMediaQuery}.tsx`
  - `frontend/app/(app)/{loading,error}.tsx` (new), `frontend/app/not-found.tsx` (new)
  - `frontend/app/(app)/page.tsx`
- **Steps**:
  1. `useFocusTrap` + `Drawer` + `Scrim`; bottom tab bar from the same catalog; viewport-aware panel defaults.
  2. Route-level loading skeleton and an error boundary that keeps the shell alive.
  3. Homepage: one `contentinfo` (BL-20260830-06), honest stack copy and repo link (BL-20260830-03), no nested `<main>`.
- **Verify**: `make test-frontend`; `python3 scripts/ux_audit.py` R3/R6/R8 clean.

## T-006 — Focus indicator sweep

- **Refs**: NFR-A11Y-1
- **Owner**: @agent:claude-code
- **Status**: `[x]`
- **Files**: `frontend/components/{AgentDashboard,AnalysisStudio,KnowledgeGraph,LsatLab}.tsx`, `frontend/components/shell/CommandPalette.tsx`
- **Steps**: Replace the twelve `focus:outline-none` + 1px-border-tint controls with `.focus-ring` (`.focus-ring-practice` in LSAT amber contexts).
- **Verify**: `grep -rn "focus:outline-none" frontend/components frontend/app` returns nothing; `ux_audit.py` R5 clean.

## T-007 — The repeatable review loop

- **Refs**: FR-11, AC-6, NFR-DOCS-1
- **Owner**: @agent:claude-code
- **Status**: `[x]`
- **Files**:
  - `scripts/ux_audit.py` (new), `Makefile`, `.github/workflows/ci.yml`
  - `docs/ui-ux-review.md` (new), `.claude/skills/ux-review/SKILL.md` (new), `.claude/commands/ux-review.md` (new)
- **Steps**:
  1. Rules R1–R9, line-precise, with reasoned file-level and per-page exemption markers.
  2. `make ux-audit`, folded into `make lint-specs` and CI's Spec Drift Gate.
  3. The eight-dimension rubric, the one-fix-per-pass procedure, the "promote the fix into the floor" step, and the pass log.
- **Verify**: each rule fails against an injected violation and passes on a clean tree; `python3 scripts/ux_audit.py --list` prints the rules.

## T-008 — Tests, docs, gates, backlog

- **Refs**: AC-1, AC-3, AC-7, AC-8, NFR-AUDIT-1, NFR-HITL-1, NFR-DOCS-1
- **Owner**: @agent:claude-code
- **Status**: `[x]`
- **Files**: `frontend/__tests__/lib/shellLogic.test.ts` (new), `frontend/__tests__/shell/ShellBehaviour.test.tsx` (new), `frontend/.prettierrc` (new), `docs/ui-ux.md`, `BACKLOG.md`
- **Steps**: 40 new tests across the pure logic and the shell; refresh the inventory doc; mirror follow-ups. Pin the house style in `frontend/.prettierrc` (`semi: false`, `singleQuote: true`) — prettier had no config, so `make format` reformatted the whole tree away from the committed style.
- **Verify**: `make test-frontend` (109 tests), `make typecheck`, `make lint`, `make lint-specs`.

---

## Done-When (Definition of Done)

- All tasks `[x]`.
- All `AC-*` covered by passing tests or a reproducible command.
- `make lint && make typecheck && make test-frontend && make lint-specs` green.
- LegalBench delta: 0 pp (no LLM path touched).
- **`## Follow-ups Discovered` populated** and mirrored into [BACKLOG.md](../../BACKLOG.md).

---

## Follow-ups Discovered

- BL-20260831-01 — refactor, low — Delete `frontend/components/NavBar.tsx` (dead since spec 040, zero imports) and drop it from spec 039 FR-5's proof set.
- BL-20260831-02 — feature, med — Deep-link feature view state (LSAT Lab tab, Agent Ops run filters, graph selection) into the URL so Back and sharing work inside a screen the way they now do across the shell.
- BL-20260831-03 — feature, low — `prefers-reduced-motion` is still ignored by the homepage pulse animations and the Cytoscape layout.
- BL-20260831-04 — feature, low — `lsat-static` has no skip link and does not consume `frontend/ui/layout.css`; the two products' shells still diverge.
- BL-20260831-05 — test-gap, med — No real-layout coverage of the shell: jsdom cannot lay out `position: sticky`, so sticky/scroll behaviour is asserted by class name. Add a Playwright spec.
- BL-20260831-06 — feature, low — The nav rail is glyph-only; add a labelled expanded variant at `xl` with a persisted preference.
- BL-20260831-07 — refactor, med — `AgentDashboard`'s launch and trace-drill modals hand-roll a dialog with no focus trap; move them onto `useFocusTrap`.
