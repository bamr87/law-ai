# Tasks: Layout preferences

> Each task references `FR-*` / `NFR-*` / `AC-*` IDs from [spec.md](spec.md). CI's `spec_validator.py` enforces that every requirement is referenced by at least one task.

## Conventions

- Status: `[ ]` todo / `[~]` in-progress / `[x]` done.
- Owner: GitHub handle or `@copilot` / `@agent:<role>`.
- Each task lists exact files to touch and how to verify.

---

## T-001 — The preferences and the pure model

- **Refs**: FR-1, FR-4, FR-10, NFR-PERF-1, AC-1, AC-8
- **Owner**: @agent:claude-code
- **Status**: `[x]`
- **Files**: `frontend/lib/settings/catalog.ts`, `frontend/lib/shell/layout.ts` (new), `frontend/lib/shell/panels.ts`, `frontend/lib/shell/commands.ts`, `frontend/components/shell/useSetting.ts`
- **Steps**: Eleven settings with today's layout as their defaults, ordered by key prefix; `LAYOUT_SETTINGS`, `resetLayout` (deletes rows), `resolvePanelSides` (sidebar outer, inspector inner); `withoutPanels`; three palette actions; `useSetting` returns the `Effective` row.
- **Verify**: `__tests__/lib/shellLogic.test.ts` — the four edge combinations, a reset that leaves non-layout rows alone, the palette actions.

## T-002 — The Layout menu and the shell that honours it

- **Refs**: FR-2, FR-3, FR-5, FR-6, FR-7, FR-11, NFR-A11Y-1, NFR-A11Y-2, NFR-A11Y-3, AC-2, AC-3, AC-4, AC-5
- **Owner**: @agent:claude-code
- **Status**: `[x]`
- **Files**: `frontend/components/shell/LayoutMenu.tsx` (new), `frontend/components/shell/{AppShell,Masthead,PageLayout,SettingsForm}.tsx`
- **Steps**: A `role="menu"` of checkbox and radio rows with roving focus, Escape-to-button, outside-click dismissal, on the `--z-popover` rung; the shell reads every preference through `useSetting`, maps `resolvePanelSides` on both sides of `<main>`, writes panel toggles to the URL and the preference, lets a stored inspector choice beat the UPL auto-open; the masthead hides its trail and scope chip on request; the page header takes `ui.page_header`; `/settings` heads each key prefix.
- **Verify**: `__tests__/shell/{LayoutMenu,AppShell,ShellBehaviour}.test.tsx`; in-browser: hide the rail, move the sidebar right, collapse a panel and navigate.

## T-003 — Per-widget hide: the timer and the library columns

- **Refs**: FR-8, FR-9, AC-6, AC-7
- **Owner**: @agent:claude-code
- **Status**: `[x]`
- **Files**: `frontend/components/lsat/SectionTimerWidget.tsx`, `frontend/components/LsatLibrary.tsx`
- **Steps**: `lsat.timer.visible` applies only while idle and the Move menu gains "Show when idle"; the library picks its grid from the four column combinations and lets the narrow-width disclosure serve every width when the rail is hidden.
- **Verify**: `__tests__/shell/lsatTimerDock.test.tsx`, `__tests__/components/lsat/LsatLibrary.test.tsx`.

## T-004 — Tests, gates, docs, evidence, backlog

- **Refs**: NFR-SEC-1, NFR-AUDIT-1, NFR-HITL-1, NFR-DOCS-1, AC-9
- **Owner**: @agent:claude-code
- **Status**: `[x]`
- **Files**: `frontend/__tests__/**`, `docs/ui-ux.md`, `docs/images/shell-layout-*.png`, `frontend/ui/README.md`, `BACKLOG.md`
- **Steps**: The suites above; `tsc`, `eslint`, `vitest`, `next build`, `ux_audit.py`, `make lint-specs`; Playwright captures of the menu, a moved-and-hidden arrangement, and the grouped settings page; the follow-ups below mirrored to BACKLOG.
- **Verify**: every gate clean; the images referenced from `docs/ui-ux.md` and the PR.

---

## Done-When (Definition of Done)

- All tasks `[x]`.
- All `AC-*` covered by a passing test or a reproducible command.
- `make test-frontend`, `tsc --noEmit`, `npm run lint`, `make lint-specs` green.
- LegalBench delta: 0 pp.
- **`## Follow-ups Discovered` populated** and mirrored into [BACKLOG.md](../../BACKLOG.md).

---

## Follow-ups Discovered

> Append-only. Mirror each item into [BACKLOG.md](../../BACKLOG.md) with a `BL-YYYYMMDD-NN` id.

- BL-20260905-07 — feature, low — `LayoutMenu` decides which module rows to show from route prefixes (`/lsat`, `/lsat/library`); let a module declare its own layout rows in `lib/modules/catalog.ts` so the shell stops knowing route names (spec 040's rule).
- BL-20260905-08 — feature, med — with the rail hidden, a mouse user who does not know ⌘K navigates by breadcrumbs alone; show a compact "Modules" menu in the masthead whenever `ui.rail.visible` is false.
- BL-20260905-09 — feature, low — layout preferences are read after hydration, so a non-default layout reflows once on every full load; read the settings rows server-side (a cookie mirror of `law-ai.settings.v1`) and render the chosen layout on the first paint.
- BL-20260905-10 — feature, low — layout preferences are instance-scoped until user accounts land (spec 036); once a `user` scope exists, `LAYOUT_SETTINGS` should move to `settableAt: ['user']` so two people on one instance stop sharing a layout.
