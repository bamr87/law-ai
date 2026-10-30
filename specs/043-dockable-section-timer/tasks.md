# Tasks: Dockable LSAT section timer

> Each task references `FR-*` / `NFR-*` / `AC-*` IDs from [spec.md](spec.md). CI's `spec_validator.py` enforces that every requirement is referenced by at least one task.

## Conventions

- Status: `[ ]` todo / `[~]` in-progress / `[x]` done.
- Owner: GitHub handle or `@copilot` / `@agent:<role>`.
- Each task lists exact files to touch and how to verify.

---

## T-001 — The clock becomes a store

- **Refs**: FR-1, FR-8, NFR-PERF-1, AC-4
- **Owner**: @agent:claude-code
- **Status**: `[x]`
- **Files**: `frontend/lib/lsat/timerStore.ts` (new)
- **Steps**: Deadline-based countdown, one interval for the app, start/pause/reset/duration/pace actions, `isSectionInProgress`, sessionStorage persistence keyed on the deadline, `__resetTimerStore` test seam.
- **Verify**: Fake-timer cases for deadline arithmetic and pause-holds; in-browser reload resumes with elapsed time deducted.

## T-002 — Enum settings + a live settings store

- **Refs**: FR-2, FR-3, FR-9, AC-6
- **Owner**: @agent:claude-code
- **Status**: `[x]`
- **Files**: `frontend/lib/scope/{types,store}.ts`, `frontend/lib/settings/{define,catalog}.ts`, `frontend/components/shell/{SettingField,SettingsForm,useSetting}.tsx`
- **Steps**: `options` on `SettingDefinition`; `parseEnum`; the `lsat.timer.dock` setting; a select control; subscribable store with a cached snapshot; `useSetting`; move `SettingsForm` onto `useSyncExternalStore`.
- **Verify**: `/settings` renders the labelled select, changing it persists, and the page hydrates with no console error.

## T-003 — Dock resolution and zones

- **Refs**: FR-5, FR-6, FR-7, AC-1, AC-3, AC-5
- **Owner**: @agent:claude-code
- **Status**: `[x]`
- **Files**: `frontend/lib/shell/docks.ts` (new), `frontend/components/shell/DockZone.tsx` (new), `frontend/components/shell/AppShell.tsx`, `frontend/components/LsatLab.tsx`
- **Steps**: Pure `resolveDock` with documented fallbacks; zones in both panels and both drawers; the inline zone on the LSAT page; route policy inside the widget so the shell stays generic.
- **Verify**: Default is sidebar, exactly one instance; timer follows a client-side navigation while running and leaves on reset.

## T-004 — The widget and its move menu

- **Refs**: FR-4, NFR-A11Y-1, NFR-A11Y-2, NFR-SEC-1, AC-2
- **Owner**: @agent:claude-code
- **Status**: `[x]`
- **Files**: `frontend/components/lsat/SectionTimerWidget.tsx` (new), `frontend/ui/layout.css`
- **Steps**: Store-backed readouts, compact and inline layouts, a `role="menu"` dock picker with `menuitemradio` state, Escape/outside-click dismissal, the `--z-popover` rung.
- **Verify**: In-browser move sidebar → inspector → in page with the clock running and never resetting.

## T-005 — Tests, gates, docs, backlog

- **Refs**: NFR-DOCS-1, NFR-AUDIT-1, NFR-HITL-1, AC-7
- **Owner**: @agent:claude-code
- **Status**: `[x]`
- **Files**: `frontend/__tests__/shell/lsatTimerDock.test.tsx` (new), `frontend/__tests__/{lib/modules,components/LsatLab}.test.*`, `frontend/ui/README.md`, `docs/ui-ux.md`, `BACKLOG.md`
- **Steps**: Dock and store coverage; update the two suites the behaviour change invalidated; document the zones, the registry, and the new z rung.
- **Verify**: `make test-frontend` 135 tests; `tsc`; `npm run lint` 0 errors; `npm run build`; `python3 scripts/ux_audit.py`; `make lint-specs`.

---

## Done-When (Definition of Done)

- All tasks `[x]`.
- All `AC-*` covered by a passing test or a reproducible command.
- `make test-frontend`, `tsc --noEmit`, `npm run lint`, `make lint-specs` green.
- LegalBench delta: 0 pp.
- **`## Follow-ups Discovered` populated** and mirrored into [BACKLOG.md](../../BACKLOG.md).

---

## Follow-ups Discovered

- BL-20260831-13 — test-gap, med — One LsatLab grading assertion (`Incorrect — answer was C`, MSW-backed) failed once during spec 043 implementation and passed on three subsequent full runs. Not timer-related and not reproduced, but not proven stable either — instrument or harden the await rather than leaving a known-once-flaky assertion in the suite.
- BL-20260831-14 — feature, med — The dock mechanism has one registered widget. Generalise `DOCKED_WIDGETS` into the module catalog so a module can contribute a dock widget as data, the way it already contributes nav and sidebar entries.
- BL-20260831-15 — feature, low — `frontend/components/LsatTimer.tsx` now only exports `QuestionElapsed`; fold it into the LSAT component folder and close the naming confusion with the dockable widget. Related to BL-20260830-04 (unify with `lsat-static`'s SectionTimer).
- BL-20260831-16 — feature, low — The timer's remaining-per-question readout still needs a section bank size to be meaningful off the RC/LG stacks (carries BL-20260829-01); the store now has a natural home for it.
- BL-20260831-17 — feature, low — A dock preference is instance-scoped, so every user of an instance shares it. Move it to the `user` scope when accounts land (spec 036).
