# Spec: Dockable LSAT section timer

- **ID**: 043-dockable-section-timer
- **Status**: shipped
- **Owner**: @bamr87
- **Created**: 2026-08-31
- **Roadmap Epic**: give the shell a place for persistent module widgets, starting with the section clock
- **Constitution Compliance**: confirmed against [docs/constitution.md](../../docs/constitution.md). No amendment needed — no dependency, no palette, no change to what the product claims about legal authority.

## 1. Problem & Motivation

The LSAT section timer lived inside the drill page's header, which made it a scroll-away decoration on the one surface where a clock is the point. It was also the wrong *place*: a 35-minute proctored-style section is context that belongs in the shell's persistent chrome, not in the middle of the content a student is reading.

Moving it to the sidebar is not a CSS change. The sidebar is a **parallel-route slot** (`app/(app)/@sidebar`), a different React subtree from the page — so a timer that kept its clock in `useState` would unmount and remount when it moved between docks, resetting a running section. The clock had to stop being component state before it could be dockable at all.

Two smaller defects fell out of the same work: the settings system could only render boolean and number controls, so a dock preference had nowhere to live; and `SettingsForm` read localStorage during its initial render, which produced a hydration mismatch the moment any setting actually had a stored value — latent since spec 040, and exposed here because a dock preference is the first setting users routinely change.

## 2. Origin & Background

- Backlog items claimed: none. Requested directly; related to BL-20260830-04 (unify the two timers), which this does **not** close.
- Review question (constitution §13): this spec does not rank, score, or summarize legal authority. It relocates a study-aid clock.
- Who is the stronger here? A clock that hides behind a scroll or resets when the layout changes penalises the student practising under time pressure — the user with the least slack. Durability across a move, a navigation, and a reload is the whole point.

## 3. Goals

- G1: The timer is docked in the sidebar by default.
- G2: The user can move it, from the widget itself, and the choice persists.
- G3: Moving, navigating, or reloading never costs a running section.
- G4: The dock mechanism is a shell capability, not an LSAT special case.

## 4. Non-Goals

- NG1: Drag-and-drop docking. A menu is keyboard-operable by construction; drag would need a full keyboard equivalent (WCAG 2.5.7) for no gain here.
- NG2: Unifying `frontend/components/LsatTimer.tsx` with `lsat-static/components/SectionTimer.tsx` (BL-20260830-04). `QuestionElapsed` still lives in the old file.
- NG3: A general user-arrangeable dashboard. One registry entry, one widget.
- NG4: Server-side persistence of the preference — it stays in the spec 040 instance-scoped store until user accounts land (spec 036).
- NG5: Shorter drill presets on the timer (BL-20260829-02).

## 5. User Stories

- As a student, I want the section clock in the sidebar so it is always visible without competing with the question I am reading.
- As a student who prefers it beside the questions, I want to move it to the page and have it stay there next time.
- As a student who opens a case on the graph mid-section, I want the clock to come with me and keep running.
- As a student who accidentally refreshes mid-section, I want my clock back — with the reload time counted, not refunded.
- As a contributor, I want to dock a second widget later without editing `AppShell`.

## 6. Functional Requirements

- **FR-1**: The clock lives in a module-level store (`lib/lsat/timerStore.ts`), not component state, so every dock is a view of one clock. Deadline-based, so a throttled background tab does not drift.
- **FR-2**: `lsat.timer.dock` is an instance-scoped enum setting (`sidebar` | `inspector` | `inline`) defaulting to `sidebar`, editable on `/settings`.
- **FR-3**: `SettingDefinition` supports `options`, and `SettingField` renders a labelled `<select>` for them. `parseEnum` rejects values outside the set so a stale key falls back to the default.
- **FR-4**: The widget carries its own "Move" menu (`role="menu"` with `menuitemradio` items marking the current dock), which writes the same preference.
- **FR-5**: `resolveDock` decides where a widget actually renders: honour the preference when that zone is on screen; otherwise fall back to any open zone; `inline` only on the widget's own route; `null` only when there is genuinely nowhere. A collapsed panel must never hide a running clock.
- **FR-6**: Off the LSAT routes the timer renders only while a section is in progress, and disappears on reset.
- **FR-7**: `DockZone` renders registered widgets into the shell's sidebar and inspector (docked columns and compact drawers alike); the LSAT page provides the `inline` zone. The shell never learns what LSAT is — each widget decides whether it belongs.
- **FR-8**: A running section persists to `sessionStorage` and is restored on load, with elapsed wall-clock time counted against it. sessionStorage, not localStorage: a section is a tab-lifetime thing.
- **FR-9**: The settings store notifies subscribers on write, and `useSetting` / `SettingsForm` read it through `useSyncExternalStore` — fixing the hydration mismatch and making a preference change visible everywhere at once.

## 7. Non-Functional Requirements

- **NFR-A11Y-1**: The timer is a named region with a `role="timer"` readout; the move menu is keyboard-operable, closes on Escape and outside click, and marks the current dock with `aria-checked`.
- **NFR-A11Y-2**: The dock popover takes the new `--z-popover` rung rather than a literal z-index (`ux_audit.py` R4).
- **NFR-PERF-1**: One interval for the whole app, owned by the store — previously each mounted timer ran its own.
- **NFR-SEC-1**: No new runtime npm dependencies.
- **NFR-AUDIT-1**: No LLM, graph, or provenance changes. Attempt counts still post through the existing `/api/lsat/*` path.
- **NFR-HITL-1**: `human_approval_required` is false.
- **NFR-DOCS-1**: `frontend/ui/README.md` documents the dock zones, the z-scale rung, and the widget registry.

## 8. Data Model Impact

None server-side. Two browser keys: `law-ai.settings.v1` (existing, one new row) and `law-ai.lsat.timer.v1` (new, sessionStorage).

## 9. API Surface

None. No backend routes.

## 10. Agent / Crew Impact

None to `agents_runtime`.

## 11. LegalBench Impact

- Tasks affected: none.
- Expected delta: 0 pp.

## 12. Acceptance Criteria

- **AC-1**: Given a fresh profile on `/lsat`, the timer renders in the sidebar and nowhere else, exactly once.
- **AC-2**: Given a running section, when the dock is changed from the widget's menu, then the clock continues from where it was — it does not reset — and exactly one timer remains.
- **AC-3**: Given a running section, when the user navigates to another module, the timer follows and keeps counting; when the section is reset, it disappears from non-LSAT routes.
- **AC-4**: Given a running section, when the page is reloaded, the clock resumes with the elapsed time deducted.
- **AC-5**: Given a preferred dock whose panel is closed, `resolveDock` returns an open zone rather than nothing; with nothing open and off-route it returns `null`.
- **AC-6**: Given `/settings`, the dock renders as a labelled select of the three docks, changing it persists, and the page hydrates with no console error.
- **AC-7**: `make test-frontend`, `tsc --noEmit`, `npm run lint` (0 errors), `npm run build`, and `python3 scripts/ux_audit.py` are all clean.

## 13. Risks & Open Questions

- **R-1**: A module-level store is shared across tests. Mitigated with `__resetTimerStore()` in `beforeEach` for every file that touches it.
- **R-2**: Persisting a running clock could resurrect a stale section. Mitigated by sessionStorage (tab lifetime) and by recomputing from the deadline, so an expired section restores as expired.
- **R-3**: `inline` is unavailable off-route, so the preference cannot always be honoured. Resolved by `resolveDock`'s documented fallback rather than by hiding the clock.
- **R-4**: One LsatLab grading assertion failed once during implementation and passed on three subsequent full runs. It asserts an MSW-backed result and is not timer-related, but it is not proven stable — recorded as a follow-up rather than dismissed.

## 14. Out of Scope / Follow-ups

Recorded in `tasks.md` ## Follow-ups Discovered and mirrored to BACKLOG.
