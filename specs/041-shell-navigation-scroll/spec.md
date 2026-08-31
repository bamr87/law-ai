# Spec: Application shell navigation & scroll contract

- **ID**: 041-shell-navigation-scroll
- **Status**: shipped
- **Owner**: @bamr87
- **Created**: 2026-08-31
- **Roadmap Epic**: make the shell a contract new surfaces inherit, not a layout each screen re-invents
- **Constitution Compliance**: confirmed against [docs/constitution.md](../../docs/constitution.md). No amendment needed — §2's frontend-kit question is spec 039's, and this spec adds no dependency and no palette.

## 1. Problem & Motivation

Spec 040 landed the app shell's *structure* — masthead, nav rail, contextual sidebar, inspector, module catalog — but not its *behaviour under scroll*. `AppShell` rendered `min-h-screen` and let the document scroll, so:

- The nav rail, contextual sidebar, and inspector scrolled out of view with the content. On `/agents` (a ~1460-line dashboard) and `/lsat` (~1611 lines), a user two screens down had no navigation at all.
- `<main>` carried `overflow-auto` but had auto height, so it never actually scrolled; the body did. The class was decorative.
- The masthead was `position: sticky`, which survives normal scrolling but not overscroll, and only worked because the document scrolled.
- Nothing inside a screen stayed put: the LSAT section switcher, the Agent Ops polling controls, and the Knowledge Graph case picker all scrolled away from the content they controlled.

Around that, the chrome was missing the things a user of any comparable app expects and gets no warning about: no scroll restoration on Back, no command palette, no keyboard shortcuts, no `loading` or `error` route states, no compact-viewport story for the two side panels, a double `contentinfo` landmark on the homepage, nested `<main>` elements on four routes, and twelve form controls that removed the focus outline and put back a 1px border tint.

The deeper problem is that none of this failed anything. It degraded quietly, in a place nobody owned, and would have kept degrading as modules were added — which is why the deliverable is a repeatable review with a mechanical gate, not only a fix.

## 2. Origin & Background

- Backlog items claimed: **BL-20260830-09** (⌘K palette), **BL-20260830-06** (double footer), **BL-20260830-03** (stale homepage stack copy, in part — the GitHub chip href and STACK table).
- Review question (constitution §13): this spec does **not** rank, score, or summarize legal authority. It moves existing surfaces; it does not change what any of them claims.
- Who is the stronger here? A shell that hides its navigation under a long generated brief advantages the reader who already knows the product over the first-time user — typically the layperson the UPL guardrails exist for. Pinning the chrome, keeping the disclaimer reachable, and making every destination reachable by keyboard and on a phone all move in the same direction.

## 3. Goals

- G1: Chrome is structurally incapable of scrolling away; exactly one element scrolls page content.
- G2: A page frame every route composes, so a new module inherits the sticky header, gutters, and reading width rather than re-deriving them.
- G3: The navigation and keyboard affordances a user expects: breadcrumbs, palette, shortcuts, scroll memory, drawers, route states.
- G4: The contract is machine-checked and the review is repeatable, so this does not have to be rediscovered.

## 4. Non-Goals

- NG1: The colour palette, semantic classes, and React primitives — spec 039 owns those.
- NG2: Decomposing `LsatLab.tsx` / `AgentDashboard.tsx` (BL-20260830-02).
- NG3: Light theme, i18n, or a marketing redesign.
- NG4: Deep-linking feature-internal view state (LSAT tab, dashboard filters) — recorded as a follow-up.
- NG5: Bringing `lsat-static` onto the layout layer.
- NG6: Wiring unused deps (TanStack Query, framer-motion, lucide, xyflow).

## 5. User Stories

- As a reader halfway through a generated IRAC brief, I want the navigation and the "not legal advice" banner still on screen, so I can leave or check myself without scrolling back.
- As an operator reading the run trail, I want the pause control and "last updated" pinned, so I can stop polling without hunting for the button.
- As an LSAT student mid-passage, I want the section switcher pinned and the passage beside its questions.
- As a keyboard user, I want to reach any module without the mouse — and never to have a bare `[` swallowed out of a fact pattern I am typing.
- As a phone user, I want the real sidebar and inspector, not a stub, and primary navigation in thumb reach.
- As someone who hit Back, I want to land where I was in the list, not at the top.
- As the next contributor, I want adding a module to be one catalog edit, and I want CI to tell me when I have broken the shell contract.

## 6. Functional Requirements

- **FR-1**: `AppShell` locks the viewport (`h-dvh` + `overflow-hidden`, document `overflow-hidden`). Masthead, nav rail, sidebar, inspector, and compact tab bar are non-scrolling flex children. Exactly one element scrolls page content (`<main class="shell-scroll">`); panels that scroll use `.shell-panel-scroll`, which contains overscroll.
- **FR-2**: `PageLayout` provides the page frame for every route: a sticky page header that condenses once the main region scrolls (title survives; eyebrow and description do not), plus a measured body container with a named `width`. `StickyToolbar` parks a control bar against `--shell-pageheader-h`.
- **FR-3**: Main-region scroll offset is remembered per route in `sessionStorage` and restored before paint. A back-to-top control appears past 480px. Opening or closing a panel must not scroll the reader.
- **FR-4**: Keyboard contract — `[` sidebar, `]` inspector, `?` shortcut sheet, `⌘K`/`Ctrl K` palette, `Esc` dismiss. Bare keys never fire from a text field; `⌘K` and `Esc` stay live inside one. A `?` sheet documents the bindings.
- **FR-5**: The masthead carries a catalog-derived breadcrumb trail, panel toggles wired with `aria-expanded` + `aria-controls`, and a palette trigger.
- **FR-6**: Below `md` the sidebar and inspector render as focus-trapped drawers (Escape-dismissed, focus restored) and the rail is replaced by a bottom tab bar carrying the same catalog. Panel defaults are viewport-aware so no drawer auto-opens over content on first paint; an explicit `?sidebar=1` still wins.
- **FR-7**: A ⌘K command palette generated from `MODULE_CATALOG` plus the shell's layout actions, with substring ranking, arrow-key selection, and `role="listbox"` semantics. Registering a module is the only edit needed to make it reachable. Closes BL-20260830-09.
- **FR-8**: The `(app)` route group ships `loading.tsx` and `error.tsx`; the app ships `not-found.tsx`. The error boundary keeps the shell alive and offers `reset()`.
- **FR-9**: `frontend/ui/layout.css` holds the layout tokens — shell metrics, the sticky stack, the `--z-*` scale, `.shell-scroll` / `.shell-panel-scroll`, `.focus-ring` / `.focus-ring-practice`, `.shell-motion` — imported by `app/globals.css` and catalogued in `frontend/ui/README.md`. No colours beyond the scrollbar and focus-ring hooks spec 039 will re-point.
- **FR-10**: Apply the sticky stack in the feature screens: LSAT section switcher, Agent Ops polling controls, Knowledge Graph case picker (pinned column with its own scroll), and the RC/LG passage reader.
- **FR-11**: A repeatable review: `scripts/ux_audit.py` (rules R1–R9, host stdlib) wired into `make ux-audit`, `make lint-specs`, and CI's Spec Drift Gate; the rubric and pass log in `docs/ui-ux-review.md`; the `/ux-review` skill and command.
- **FR-12**: Landmark and content fixes — one `<main>` per page (four routes nested a second one), one `contentinfo` on the homepage with the UPL footer moved inside the shell's scroll region (BL-20260830-06), and the homepage GitHub chip and STACK table telling the truth about the stack (BL-20260830-03).

## 7. Non-Functional Requirements

- **NFR-A11Y-1**: `.focus-ring` / `.focus-ring-practice` are the app-wide `:focus-visible` indicator; no control removes the outline without one. Every `<nav>` / `<aside>` has an accessible name. Overlays trap focus and restore it. The skip link renders above the chrome.
- **NFR-A11Y-2**: Smooth scrolling is gated on `prefers-reduced-motion: no-preference` and `.shell-motion` disables shell transitions under `reduce`. Zoom is not capped (`maximumScale: 5`).
- **NFR-PERF-1**: Scroll handling is coalesced to one `requestAnimationFrame` per frame; scroll memory writes are bounded by the same. `h-dvh` rather than `h-screen`, so mobile browser chrome does not hide the bottom bar.
- **NFR-SEC-1**: No new runtime npm dependencies.
- **NFR-AUDIT-1**: No LLM, graph, or provenance changes. UPL chrome stays user-visible and is not an audit event.
- **NFR-HITL-1**: `human_approval_required` is false. Visual acceptance is the PR review (constitution Level 2).
- **NFR-DOCS-1**: `docs/ui-ux.md`, `docs/ui-ux-review.md`, and `frontend/ui/README.md` describe the shipped shell; `make help` names the new targets.

## 8. Data Model Impact

None.

## 9. API Surface

None. No backend routes.

## 10. Agent / Crew Impact

None to `agents_runtime`. Dev agents gain `/ux-review` plus `frontend/ui/README.md` as the layout catalog.

## 11. LegalBench Impact

- Tasks affected: none.
- Expected delta: 0 pp.

## 12. Acceptance Criteria

- **AC-1**: Given any route, when the content is scrolled to the bottom, then the masthead, nav rail, sidebar, inspector, and tab bar are still on screen, and the document itself has not scrolled.
- **AC-2**: Given a page with a `PageLayout` header, when the main region scrolls past the condense threshold, then the header stays pinned with its title and reports `data-condensed="true"`, and a `StickyToolbar` parks beneath it.
- **AC-3**: Given a route with a remembered offset, when it is rendered, then `main.scrollTop` is that offset; and toggling a panel does not change it.
- **AC-4**: Given focus in a textarea, when `[` is typed, then the character reaches the field and no panel toggles; given focus outside one, `[` toggles the sidebar and `⌘K` opens the palette from either.
- **AC-5**: Given the palette, when "graph" is typed and Enter pressed, then the router navigates to the Knowledge Graph module (not one of its sub-links); a layout command runs its action instead of navigating.
- **AC-6**: Given `python3 scripts/ux_audit.py`, when the tree satisfies R1–R9, then it exits 0; when any rule is violated it exits 1 naming file, line, and rule.
- **AC-7**: Given `make test-frontend`, when the shell suites run, then they pass, including the pre-existing spec 040 assertions.
- **AC-8**: Given `python3 scripts/spec_validator.py` and `python3 scripts/backlog_lint.py`, then both exit 0; and `npm run build` prerenders every route.

## 13. Risks & Open Questions

- **R-1**: A viewport-locked shell breaks anything that assumed `window.scrollY`. Mitigation: `useShellScroll` is the single reader, and audit rule R2 fails a screen that tries to claim the viewport itself.
- **R-2**: jsdom cannot lay out sticky positioning, so the tests assert contract (class names, `data-condensed`, ancestry) rather than pixels. Mitigation: recorded as a follow-up for Playwright coverage; the class-to-behaviour mapping lives in one CSS file.
- **R-3**: A new audit rule with false positives gets bypassed and then deleted. Mitigation: rules are line-precise, every one was verified against an injected violation, and file-level exemptions require a written reason.
- **R-4**: The condensed-header height is a constant, so a header taller than `--shell-pageheader-h` would let a sticky toolbar slide under it mid-transition. Mitigation: the toolbar sits below the header on the z-scale, so the overlap reads as intended layering rather than as a bug.

## 14. Out of Scope / Follow-ups

Recorded in `tasks.md` ## Follow-ups Discovered and mirrored to BACKLOG: NavBar deletion, deep-linkable feature view state, remaining reduced-motion gaps, `lsat-static` parity, Playwright shell coverage, an expanded nav rail, and moving the dashboard's hand-rolled modals onto `useFocusTrap`.
