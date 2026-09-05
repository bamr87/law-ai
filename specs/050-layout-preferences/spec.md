# Spec: Layout preferences — show, hide, and move the shell's parts

- **ID**: 050-layout-preferences
- **Status**: shipped
- **Owner**: @bamr87
- **Created**: 2026-09-05
- **Roadmap Epic**: let a user choose what the screen shows — the bounded successor to spec 043's single dockable widget
- **Constitution Compliance**: confirmed against [docs/constitution.md](../../docs/constitution.md). No amendment needed — no dependency, no model call, no change to what the product claims about legal authority. The one piece of chrome with a legal job, the UPL disclaimer footer, is explicitly outside the preference model.

## 1. Problem & Motivation

The shell (spec 040) put a navigation rail, a contextual sidebar, an inspector, a masthead with a breadcrumb trail and a scope chip, a condensing page header, and a back-to-top button on every screen, and spec 043 let exactly one widget — the section timer — move between docks. Everything else was fixed. Two panel toggles existed, but their state lived only in the URL: a sidebar collapsed on the graph page sprang back on the next navigation, so the toggle read as a nuisance rather than a choice.

The people this costs most are at the two ends of the screen-size range. On a 13" laptop with both panels docked the library reader was left a few hundred pixels; a user who wanted a reading column and nothing else had no way to ask for one. On a 32" monitor a user who wanted the inspector beside the rail, or both panels on one edge, had no way to say so either. And for a screen-reader user every fixed panel is another landmark to page through on every route.

## 2. Origin & Background

- Requested directly: *"add options/capabilities to move, hide, toggle, etc the various UI components so users can choose what to show on the screen."*
- Backlog items claimed: none. Spec 043 NG3 ruled out "a general user-arrangeable dashboard"; this is the bounded version of that idea — a fixed set of named parts, each with one preference.
- Review question (constitution §13): this spec does not rank, score, or summarize legal authority. It decides what chrome renders.
- Who is the stronger here? A layout that cannot be simplified penalises low-vision and screen-reader users first, so *hide* is a first-class operation, every control is a menu rather than a drag, and the parts a user needs to recover from a bad layout — the home link, the palette, the Layout menu itself — can never be hidden.

## 3. Goals

- G1: Every part of the chrome except the UPL disclaimer can be hidden.
- G2: The two side panels can each be moved to either edge.
- G3: A panel choice survives a navigation.
- G4: One place to do all of it (the masthead's Layout menu), mirrored on `/settings` and in ⌘K.
- G5: A running section clock is never hidden (spec 043 FR-5 keeps holding).

## 4. Non-Goals

- NG1: Drag-and-drop or free-form arrangement (spec 043 NG1 applies: a menu is keyboard-operable by construction).
- NG2: Custom panel widths. The widths stay the shell metrics in `layout.css`.
- NG3: Server-side or per-user persistence. Preferences live in the spec 040 instance-scoped store until user accounts land (spec 036).
- NG4: Reordering two panels that share an edge. The sidebar is always outermost, the inspector always innermost.
- NG5: A density or spacing scale.
- NG6: The static site, which has no shell to arrange.

## 5. User Stories

- As a reader on a small laptop, I want to hide the rail, the inspector, and the library outline so the article gets the screen.
- As a user on a large monitor, I want the inspector on the left beside the rail, and my choice to still be there tomorrow.
- As a keyboard user, I want to collapse a panel once and not find it open again on the next page.
- As a screen-reader user, I want one named menu that tells me what is shown and lets me change it, rather than hunting for controls scattered around the chrome.
- As a student, I want the idle timer out of the way — and I want it back the instant a section is running, without asking.
- As a contributor, I want a new preference to be one catalog entry, not a new component.

## 6. Functional Requirements

- **FR-1**: Layout preferences are ordinary settings in the instance-scoped store, each defaulting to today's layout: `ui.rail.visible`, `ui.sidebar.default_open`, `ui.sidebar.side`, `ui.inspector.default_open` (existing), `ui.inspector.side`, `ui.masthead.breadcrumbs`, `ui.masthead.scope_switcher`, `ui.back_to_top`, `ui.page_header` (`auto` | `compact`), `lsat.timer.visible`, `lsat.library.contents`, `lsat.library.outline`. `lib/shell/layout.ts` lists them as `LAYOUT_SETTINGS`.
- **FR-2**: The masthead carries a Layout menu: `role="menu"` with `menuitemcheckbox` rows for show/hide, `menuitemradio` groups for each panel's edge and the page-header mode, and one `menuitem`, Reset. Toggles keep the menu open; Reset closes it. A module's rows (the timer, the library columns) appear only on that module's routes.
- **FR-3**: Every panel toggle — the masthead buttons, `[` and `]`, the palette, the menu rows — writes both the URL and the panel's `default_open` preference. The URL wins for the page it names; the preference carries the choice to the next page. A stored inspector preference beats the UPL-route auto-open; with none stored, a UPL route opens the inspector as before (spec 040 FR-2).
- **FR-4**: `resolvePanelSides` decides the render order from the two edge preferences — sidebar outermost, inspector innermost, on either edge — and both the docked columns and the compact drawers follow it.
- **FR-5**: With the rail hidden, `NavRail` is not rendered; the compact tab bar, the breadcrumb trail, and the palette are unaffected, so every module stays reachable.
- **FR-6**: The breadcrumb trail, the scope switcher, and the back-to-top button hide by preference. The home link, the palette button, the Layout menu, and the panel toggles never do.
- **FR-7**: `ui.page_header = compact` keeps `PageLayout`'s header in its condensed form from the first paint. The title stays; the eyebrow and description go, exactly as on scroll.
- **FR-8**: `lsat.timer.visible = false` hides the section timer only while no section is in progress. The widget's own Move menu carries the same choice as a "Show when idle" row.
- **FR-9**: `lsat.library.contents` and `lsat.library.outline` drop the library's side columns. With the contents rail hidden, the narrow-width "Browse contents" disclosure serves every width and an opened rail spans the row above the reader.
- **FR-10**: The palette gains `toggle-rail`, `toggle-breadcrumbs`, and `reset-layout`. Reset deletes every layout row (rather than writing defaults, so `/settings` reads them as inherited) and drops the URL's panel params.
- **FR-11**: `/settings` groups the catalog by key prefix under a heading each, and every layout preference is editable there.

## 7. Non-Functional Requirements

- **NFR-A11Y-1**: The Layout menu is named, is one tab stop (roving tabindex; Arrow, Home and End move inside it), closes on Escape with focus returned to its button, closes on outside click, and marks every toggle with `aria-checked`.
- **NFR-A11Y-2**: The popover sits on the `--z-popover` rung (`ux_audit.py` R4), never a literal z-index.
- **NFR-A11Y-3**: No preference removes the last keyboard route to a module or the UPL disclaimer: ⌘K and the breadcrumb trail's home link survive every combination, and the footer disclaimer inside `<main>` has no preference at all.
- **NFR-PERF-1**: Preferences are read through `useSetting` (`useSyncExternalStore`), never a mount effect — hydration-safe, and a change anywhere on the page is visible everywhere at once.
- **NFR-SEC-1**: No new runtime npm dependencies.
- **NFR-AUDIT-1**: No LLM, graph, or provenance changes.
- **NFR-HITL-1**: `human_approval_required` is false.
- **NFR-DOCS-1**: `docs/ui-ux.md` describes the preference model with visual evidence under `docs/images/`; `frontend/ui/README.md` lists the menu and the model.

## 8. Data Model Impact

None server-side. New rows in the existing browser key `law-ai.settings.v1`.

## 9. API Surface

None. No backend routes.

## 10. Agent / Crew Impact

None to `agents_runtime`.

## 11. LegalBench Impact

- Tasks affected: none.
- Expected delta: 0 pp.

## 12. Acceptance Criteria

- **AC-1**: Given a fresh profile, every route renders exactly as before this spec — each preference's default is the previous fixed layout.
- **AC-2**: Given the Layout menu, when "Navigation rail" is unchecked, then the rail is gone, the compact tab bar still renders below `md`, and ⌘K still reaches every module.
- **AC-3**: Given "Sidebar edge: Right", then the sidebar renders after the inspector on the right edge with a left border, and below `md` its drawer opens from the right.
- **AC-4**: Given the sidebar collapsed on `/graph`, when the user navigates to `/agents`, then it stays collapsed; a shared `?sidebar=1` link still opens it.
- **AC-5**: Given `/analysis` with no stored inspector choice, the inspector opens; with `ui.inspector.default_open = false` stored, it stays closed and the footer disclaimer remains in `<main>`.
- **AC-6**: Given a running section, when the timer is hidden from either menu, the clock stays on screen; when the section is reset, the clock goes.
- **AC-7**: Given `lsat.library.contents = false`, the "Browse contents" disclosure serves every width and opens the rail; given `lsat.library.outline = false`, no "On this page" navigation renders.
- **AC-8**: Given any set of layout rows, when Reset is chosen, then every layout row is deleted, `/settings` shows each as inherited, and the URL's panel params are gone.
- **AC-9**: `tsc --noEmit`, `eslint` (0 errors), `vitest`, `next build`, `python3 scripts/ux_audit.py`, and `make lint-specs` are clean, and the changed surfaces have screenshots under `docs/images/`.

## 13. Risks & Open Questions

- **R-1**: Hiding the rail leaves a mouse user who does not know ⌘K with the breadcrumb trail as the only navigation. Mitigated: the palette button and the Layout menu are in the masthead and cannot be hidden. A "Modules" menu that appears when the rail is hidden is recorded as a follow-up.
- **R-2**: The server render sees the defaults and the stored preferences apply after hydration, so a user with a non-default layout sees one reflow on a full load. The same trade spec 043 made for the dock preference; a cookie-backed server read is recorded as a follow-up.
- **R-3**: The menu decides which module rows to show from route prefixes, which bends the "the shell never learns a route name" rule. Bounded to one component; a module-declared registry is recorded as a follow-up.

## 14. Out of Scope / Follow-ups

Recorded in `tasks.md` ## Follow-ups Discovered and mirrored to BACKLOG.
