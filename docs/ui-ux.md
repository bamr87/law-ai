# Law AI UI / UX

> Current-state inventory of every user-facing surface, the two styling
> idioms that actually ship, and the governance target for a maintainable
> design system. Constitution §2 still lists `shadcn/ui` as the locked
> frontend kit; **it is not installed**. Spec
> [039](../specs/039-design-system/spec.md) +
> [ADR 0006](adr/0006-first-party-design-system.md) propose replacing that
> lock with a first-party system owned in-repo.

This file is the source of truth for **what the UI is today**. The spec is the source of truth for **what we will build**. [docs/ui-ux-review.md](ui-ux-review.md) is the source of truth for **how we keep it good** — the repeatable `/ux-review` loop and the nine structural rules `scripts/ux_audit.py` enforces in CI. Do not treat `.design-sync/` as either.

**Update, 2026-08-31 (spec 041):** the *layout* half of the first-party design system shipped as [frontend/ui/layout.css](../frontend/ui/layout.css) — shell metrics, the sticky stack, the z-scale, the scroll primitives, and the app-wide focus ring, catalogued in [frontend/ui/README.md](../frontend/ui/README.md). The *palette* half (`tokens.css`, `semantic.css`, React primitives) is still spec 039's to build.

---

## Surfaces

| Surface | App | Route / deploy | Stack | Components |
|---------|-----|----------------|-------|------------|
| Platform | `frontend/` | `make dev` → `:3000` | Next 16, React 19, Tailwind v4 | 10 files under `frontend/components/` |
| LSAT practice (static) | `lsat-static/` | GitHub Pages, `make lsat-export` | Next 16 static export, **no Tailwind** | 7 files under `lsat-static/components/` |
| Design-sync snapshot | `.design-sync/` | converter bundle only | Synthetic `law-ai-ui` package | Re-exports the 16 above |

**Both front ends share one UI contract as of spec 044.** `frontend/ui/base.css` (z-scale, focus ring, motion opt-out) is mirrored byte-for-byte into `lsat-static/app/base.css` — Next refuses to resolve a CSS `@import` outside an app root, so `make ui-sync` copies it and `ux_audit.py` R12 fails the build on drift. The audit itself now covers both apps and their stylesheets.

`frontend/` pages: `/` (home), `/agents`, `/analysis`, `/graph`, `/lsat`, `/settings`, plus route-level `loading` / `error` / `not-found` states. Chrome is the spec 040 **app shell** (`frontend/components/shell/`), reworked by spec 041 into a **viewport-locked** shell: masthead, nav rail, contextual sidebar, inspector, compact tab bar, and a ⌘K command palette. Modules register in `frontend/lib/modules/catalog.ts` — adding a surface must not edit `AppShell.tsx`. Settings resolve through `frontend/lib/scope/resolver.ts` (instance-only live scope; org/team wait on spec 036). There is no Case Library UI despite [docs/architecture.md](architecture.md) naming one.

### The layout contract (spec 041)

The document does not scroll. `AppShell` is `h-dvh overflow-hidden`, so the masthead, rail, sidebar, inspector, and compact tab bar are flex children of a viewport-height row and are structurally incapable of scrolling away. Exactly one element scrolls page content — `<main class="shell-scroll">` — and panels that need to scroll use `.shell-panel-scroll`. Inside main, `PageLayout` pins a page header that condenses once the region scrolls, and `StickyToolbar` parks control bars directly beneath it against `--shell-pageheader-h`. Scroll position is remembered per route in `sessionStorage`, because a locked viewport means the browser's own restoration has nothing to restore. Below `md`, the sidebar and inspector become focus-trapped drawers and the rail becomes a bottom tab bar.

### Layout preferences (spec 051)

What the shell shows, and where, is the user's to choose. Every part of the chrome except the UPL disclaimer footer has a preference behind it — an ordinary setting in the instance-scoped store, so it persists like the timer's dock does, appears on `/settings` under a "Layout" heading, and can be reset as a group. The masthead's **Layout** menu is the one place to do it: `menuitemcheckbox` rows show or hide the navigation rail, the contextual sidebar, the inspector, the breadcrumb trail, the scope switcher, the back-to-top button, and — on their own routes — the section timer and the library's contents rail and outline; `menuitemradio` groups put each side panel on either edge (the sidebar is always outermost, the inspector always innermost) and pick whether the page header condenses on scroll or is always compact; one `menuitem` resets everything. The palette mirrors the rail and breadcrumb toggles and the reset. Panel toggles now write the preference as well as the URL, so a collapsed panel stays collapsed across a navigation; the URL still wins for the page it names, and a stored inspector choice beats the UPL-route auto-open. A running section clock is never hidden by anything (spec 043 FR-5). Defaults reproduce the previous fixed layout, so a fresh profile cannot tell the feature shipped.

| | |
|---|---|
| The Layout menu, open on the library — module rows appear only on their routes | ![Layout menu](images/shell-layout-menu.png) |
| A moved and thinned shell: rail and breadcrumbs hidden, sidebar docked on the right beside the inspector, page header compact | ![Moved and hidden](images/shell-layout-moved.png) |
| `/settings`, grouped by key prefix — every preference editable with provenance | ![Settings, Layout group](images/shell-settings-layout.png) |

The default layout, for comparison, is the first capture in the entry-template table above.

**Feature parity (spec 046).** The published site renders the same solve guides, hint carousel, five diagram types, and post-grade concept references as the lab — the guides are hand-authored static data, so they ship in `content.json` and are locked client-side until a question is graded. What it will never have, because a serverless site cannot: the AI tutor, answer cross-check, HITL authoring, the validation report, and server-side stats. `ux_audit.py` R13 fails the build when a `frontend/components/lsat/` component gains no counterpart and no `static-parity: none — <reason>`.

`lsat-static/` is a single-page tab router (`Overview`, `LR`, `RC`, `LG`, `Writing`, `Library`, `Stats`) driven by a HITL-approved `content.json`. It is **not** on the `make dev` compose network. `Library` carries two views, `Articles` and `Concepts` — the catalog was its own destination until the concepts merge moved it next to the material that teaches it, on both products.

### The library, both products

| | |
|---|---|
| Platform, Concepts view — a concept naming the articles that teach it | ![Concepts view](images/lsat-library-concepts-view.png) |
| Platform, an article's glossary — each name opens that concept in the catalog | ![Article glossary](images/lsat-library-article-glossary.png) |
| Practice lab, with no concept catalog of its own | ![LSAT Lab tabs](images/lsat-lab-without-concepts-tab.png) |
| Offline site, same two views | ![Static library](images/lsat-static-library-concepts.png) |

Page measures at 2560px, before and after the large-screen step (`PageLayout`'s `WIDTH` map). The shell's docked chrome eats 36.5rem, so the caps only bind past ~1900px — and there they were leaving ~350px of dead gutter down each side:

| Before | After |
|---|---|
| ![2560px before](images/lsat-library-width-before.png) | ![2560px after](images/lsat-library-width-after.png) |

The entry template ([lsat-library.md](lsat-library.md) § "The entry template") at 1440px with both panels docked. Before, an article and a concept were two unrelated shapes — different heading levels, a different section order (`Concepts in this article` → `References` → `Related` on one, `Where to learn it` → `See also` → `References` on the other), a drill link on one and a drill button on the other — and the reader was squeezed to a ~230px column because the grid keyed off the viewport rather than the region it actually sits in. After, both readers render the same header → actions → body → cross-references sequence with fixed `#entry-*` anchors, one read-state store, and a grid driven by container queries:

| | Before | After |
|---|---|---|
| Article header | ![article header before](images/lsat-library-entry-article-header-before.png) | ![article header after](images/lsat-library-entry-article-header.png) |
| Article cross-references | ![article sections before](images/lsat-library-entry-article-sections-before.png) | ![article sections after](images/lsat-library-entry-article-sections.png) |
| Concept header | ![concept before](images/lsat-library-entry-concept-before.png) | ![concept after](images/lsat-library-entry-concept.png) |
| Concept cross-references | ![concept sections before](images/lsat-library-entry-concept-sections-before.png) | ![concept sections after](images/lsat-library-entry-concept-sections.png) |
| Offline site, concept card | ![static concept before](images/lsat-static-library-concepts-before.png) | ![static concept after](images/lsat-static-library-concepts.png) |

---

## What actually ships (vs what docs claim)

| Claim (constitution §2 / AGENTS.md / PRD) | On disk |
|-------------------------------------------|---------|
| Next.js 15 | Next `^16.3` in both apps |
| shadcn/ui | No `components.json`, no `components/ui/`, no Radix |
| TanStack Query | Declared in `frontend/package.json`, **zero imports** |
| React Flow (`@xyflow/react`) | Declared, **zero imports** (Cytoscape only) |
| Recharts (PRD only) | Not a dependency |
| framer-motion, lucide-react | Declared, **zero imports** |
| One design system | Two styling idioms, no shared package |

The platform styles with **Tailwind utility classes** and two CSS variables (`--background`, `--foreground`). The static LSAT site styles with a **hand-written semantic CSS design system** (`lsat-static/app/globals.css`, ~600 lines, 11 tokens). `.design-sync/conventions.md` already documents this split and forbids blending the idioms.

---

## Token inventory (lsat-static — the only real palette)

| Token | Value | Role |
|-------|-------|------|
| `--bg` | `#0f172a` | Page canvas (slate-900) |
| `--bg-elev` | `#1e293b` | Cards, header, raised surfaces |
| `--bg-elev-2` | `#273449` | Hover / nested elevation |
| `--border` | `#334155` | Hairline borders |
| `--text` | `#e2e8f0` | Body |
| `--text-muted` | `#94a3b8` | Secondary copy |
| `--accent` | `#fbbf24` | LSAT amber (links, pills, primary button) |
| `--accent-dim` | `rgba(251, 191, 36, 0.15)` | Selected / tinted fill |
| `--ok` | `#34d399` | Correct / success |
| `--no` | `#f87171` | Incorrect / danger |
| `--radius` | `12px` | Card radius |

The platform app does **not** use these tokens. It inlines Tailwind ramps (`slate` / `blue` / `indigo` / `emerald` / `amber` / `red`) with a **blue** primary (`bg-blue-600`, `from-blue-500 to-indigo-600`) and amber reserved for the UPL disclaimer. Both apps are dark-only; there is no `prefers-color-scheme` path and no theme toggle.

Shared hex coincidence: both canvases are `#0f172a` / `#e2e8f0`. That is the entire overlap.

---

## Component map

### Platform (`frontend/components/`)

| File | Kind | Notes |
|------|------|-------|
| `shell/` | Chrome | The app shell: `AppShell`, `Masthead`, `NavRail`, `ContextSidebar`, `InspectorPanel`, `MobileTabBar`, `PageLayout` + `StickyToolbar`, `Overlay` (`Drawer` + `useFocusTrap`), `CommandPalette`, `ShortcutsHelp`, `BackToTop`, `ShellScroll`, `useMediaQuery`. Catalogued in [frontend/ui/README.md](../frontend/ui/README.md). |
| `NavBar.tsx` | **Dead code** | Superseded by `shell/` in spec 040; zero imports. Kept only because spec 039 FR-5 names it in its proof set. Marked `ux-audit: exempt`; deletion tracked as BL-20260831-01. |
| `LegalDisclaimer.tsx` | Guardrail | `Banner` + `Footer`. UPL copy (BL-20260810-07). Required beside generated analysis. |
| `HomeStats.tsx` | Widget | Fetches agent/backlog/spec counts. |
| `AgentDashboard.tsx` | Screen (~1460 lines) | God component: registry, runs, backlog, specs, health, launch modal. |
| `AgentTrace.tsx` | Primitive-ish | Numbered steps + optional confidence badge. Confidence is shown as a percentage with no authority label (watch constitution §13 if this is ever wired to citation volume). |
| `AnalysisStudio.tsx` | Screen | IRAC form, live WS trace, coverage envelope, citation verified badges, UPL banner. |
| `KnowledgeGraph.tsx` | Screen | Case search + neighborhood fetch. |
| `GraphViewer.tsx` | Widget | Cytoscape canvas. Open: [BL-20260803-03](../BACKLOG.md) (do not label centrality as correctness). |
| `LsatLab.tsx` | Screen (~1750 lines) | God component: overview, LR/RC/LG drills, stats, HITL authoring. The concept catalog left for the library. Parallel to `lsat-static/`, not shared. |
| `LsatLibrary.tsx` | Screen | The study surface: `Articles` and `Concepts` as two views of one shelf, both rendered through one entry template (header · actions · body · concepts/articles · related · reading tracks · references · provenance, fixed anchors, shared card component) — see [docs/lsat-library.md](lsat-library.md) § "The entry template". Same three-column grid, same rail row shape, one read-state store for both. |
| `lsat/SectionTimerWidget.tsx` | Docked widget | The section clock. Docks in the sidebar (default), inspector, or in page — moved from its own menu or `/settings`, persisted per instance. A view over `lib/lsat/timerStore.ts`, so moving it never resets a running section; it follows you to other modules while a section is in progress and survives a reload with the elapsed time counted (spec 043). |
| `LsatTimer.tsx` | Primitive | Now only `QuestionElapsed` (per-question clock). Section timing moved to the docked widget above; the file is a leftover name (BL-20260831-15). |

`frontend/app/(app)/page.tsx` still inlines its own `Card` and `SectionHeading` instead of extracting them (spec 039's job). Spec 041 fixed its two content bugs: the marketing footer became a labelled `<nav>`, so the page no longer renders two `contentinfo` landmarks alongside the shell's `LegalDisclaimerFooter` (BL-20260830-06), and the STACK blurb now names the real stack — Django 5 / Next 16, and the Claude→Ollama provider chain rather than Ollama-as-the-runtime (BL-20260830-03). It is the one route deliberately exempt from `PageLayout` (`ux-audit: bare-page`), because a condensing header would sit on top of its full-bleed hero.

### Static LSAT (`lsat-static/components/`)

| File | Kind | Notes |
|------|------|-------|
| `Overview.tsx` | Screen | Section cards, `.btn-primary` amber CTA. |
| `Drill.tsx` | Screen | Section timer + question nav + optional passage column. |
| `QuestionCard.tsx` | Primitive-ish | Accessible radiogroup (roving tabindex, arrows, Space/Enter). The strongest a11y implementation in the repo. |
| `PassagePanel.tsx` | Widget | Sticky RC/LG passage. |
| `SectionTimer.tsx` | Primitive | Warn / urgent / expired states via semantic classes. |
| `Library.tsx` | Screen | Reading surface, two views: contents rail + block-rendered article, or the concept catalog. |
| `Concepts.tsx` | View | Filterable concept catalog, rendered by `Library.tsx` as its Concepts view. |
| `Stats.tsx` | Screen | `localStorage` attempt history. |

---

## UX findings (priority)

### Correctness / trust (constitution §13, UPL)

1. **UPL disclaimer is global and good.** Both apps mount it. Analysis Studio
additionally shows `LegalDisclaimerBanner` next to generated IRAC. Keep this as a primitive, not a one-off.
2. **NavBar "Local" pill is decorative.** It does not read backend health;
it always looks online. That is a trust bug on a product that otherwise refuses to fabricate.
3. **Confidence badges have no provenance.** `AgentTrace` paints a green
percentage. Fine for model self-score if labelled; dangerous if a future change feeds citation counts into it ([BL-20260803-03](../BACKLOG.md)).
4. ~~**Homepage STACK copy is stale**~~ — **fixed in spec 041.** It now names
Django 5 / Next 16 and the Claude→Ollama provider chain. Marketing pages that lie about the stack train users (and agents) wrong, so this is a `/ux-review` D8 check, not a one-off.

### Consistency

5. **Two accents, undocumented.** Platform = blue/indigo. LSAT static = amber.
Keep both as *named* tokens (`--accent-brand`, `--accent-practice`); do not silently pick one.
6. **Two max-widths.** Platform content is `max-w-7xl`; LSAT is `.wrap` at
   960px. Different jobs — document them as `--page-max` / `--prose-max`.
7. **Two LSAT products.** `LsatLab` (API-backed, authoring, tutor) vs
`lsat-static` (offline, `content.json`). Visual language should converge; feature sets should not be merged in the design-system spec.
8. **Two timers.** `LsatTimer` (utilities) and `SectionTimer` (semantic CSS)
   implement the same control.

### Accessibility

8b. **Placeholder-only controls** — ~~three inputs were named only by their placeholder~~ (graph case search, Agent Ops run filter, LSAT tutor follow-up); **fixed in spec 042** and gated by `ux_audit.py` R11. The Cytoscape canvas is now a named `role="img"` region pointing at the case list as its accessible equivalent, instead of three anonymous `<canvas>` elements.
9. ~~**Focus rings exist only on the static site**~~ — **fixed in spec 041.**
`.focus-ring` / `.focus-ring-practice` in [layout.css](../frontend/ui/layout.css) are the app-wide `:focus-visible` indicator; the twelve controls that paired `focus:outline-none` with a 1px `focus:border-*` were migrated onto them, and `ux_audit.py` R5 fails the build on a regression.
10. ~~**No skip link**~~ — **both apps have one.** The platform shell since
spec 040, `lsat-static` since spec 044 (first tab stop, revealed on focus, targeting the `main#view` that had always been a ready focus target with nothing pointing at it). Spec 044 also gave the static site a single `contentinfo` landmark and a tokenised sticky stack that keeps the section clock visible during a drill at ≥820px — pinning it on a phone would have cost 37% of the viewport.
11. **`prefers-reduced-motion` is partial.** Spec 041 gated smooth scrolling
and added `.shell-motion` for shell transitions, but the homepage pulses and the Cytoscape layout still ignore the preference.
12. ~~**QuestionCard keyboard pattern is the gold standard**~~ — **ported in
spec 042.** The platform LSAT Lab had a `role="tablist"` with dead arrow keys, seven tab stops, and no `aria-controls`/`tabpanel`, plus a `role="radiogroup"` with no name and no roving tabindex — strictly worse keyboard access than the static export of the same widget. Both now compose `useRovingTabIndex` (one tab stop, arrows move and select). `ux_audit.py` R10 gates the ARIA half; `__tests__/shell/rovingFocus.test.tsx` gates the keyboard half. A shared `Choice` *component* is still spec 039's.

### Maintainability

13. **No primitive layer.** Every screen re-implements buttons, cards,
    inputs, pills, empty states as one-off `className` strings.
14. **God components.** `LsatLab.tsx` and `AgentDashboard.tsx` are each
    >1.4k lines. A design system cannot form while screens own every atom.
15. **`.design-sync/` is a snapshot, not a system.** Hand-maintained
    `entry.tsx` / `componentSrcMap` / `dtsPropsFor`; compiled
    `styles.css` (~915 KB) does not regenerate in CI; Tailwind safelist
    silently drops any ramp not pre-enumerated. Previews are useful;
    they must *consume* the future package, not define it.
16. **Unused dependencies** add install/CVE surface for libraries the UI
    does not call (TanStack Query, framer-motion, lucide-react, xyflow).
17. **Docs/code drift on the kit itself** (shadcn listed, not present)
    causes agents to import components that do not exist.

---

## Governance target (spec 039)

The maintainable shape. `layout.css` and `README.md` shipped in spec 041; the rest is [specs/039-design-system](../specs/039-design-system/spec.md):

```
frontend/ui/
  layout.css          # SHIPPED (041) — shell metrics, sticky stack, z-scale, scroll + focus
  README.md           # SHIPPED (041) — catalog: when to use which token/class/primitive
  tokens.css          # 039 — CSS custom properties, the only palette
  semantic.css        # 039 — .btn, .card, .choice, .pill, .empty, …
  components/         # 039 — React primitives (Button, Card, Input, …)
```

- **Tokens are the source of truth.** `lsat-static/app/globals.css` imports
  them; `frontend/app/globals.css` maps them into Tailwind v4 `@theme`.
- **Primitives, not screens.** Nav, disclaimer, choice, timer, card — not
  Analysis Studio.
- **No shadcn, no Storybook, no new top-level `packages/`.** First-party,
MIT-compatible, lives under `frontend/ui/` so AGENTS.md's layout stays canonical. Storybook would be a new framework (constitution §2 + ADR).
- **Lint the contract.** A structural test fails on raw hex / non-token
palette classes in feature components once migration of a file is marked done.
- **`.design-sync` becomes a consumer** of `frontend/ui/`, not a second
palette. The compiled 915 KB stylesheet is regenerated from tokens + primitives, or dropped.

Dark-only remains the v1 theme. Light mode is a follow-up, not a requirement of 039.

---

## How to change the UI after 039

1. **Token change** — edit `frontend/ui/tokens.css`, update the table in
   this file, run `make test-frontend`.
2. **New primitive** — add `frontend/ui/components/<Name>.tsx` + a Vitest
file under `frontend/__tests__/ui/`. Do not put one-off variants in screen files.
3. **Screen work** — compose primitives. No new hex, no new semantic class
   that isn't in `semantic.css`.
4. **UPL** — any surface that shows model-generated legal analysis must
   render `LegalDisclaimerBanner`; every page keeps the footer.
5. **Authority labelling** — if a control sizes, ranks, or colors nodes by
citation count or centrality, the legend must say what the number measures (constitution §13). Never "importance."
6. **Shell work** — compose `PageLayout`, `StickyToolbar`, `Drawer`, and the
`.shell-*` classes from [frontend/ui/README.md](../frontend/ui/README.md). Register new destinations in `frontend/lib/modules/catalog.ts`; never teach `AppShell.tsx` a route name. Run `make ux-audit` before you push.
7. **Periodic review** — run `/ux-review` (see
[docs/ui-ux-review.md](ui-ux-review.md)) rather than waiting for someone to notice the shell has drifted. Each pass scores eight dimensions, fixes the single worst one, and promotes the fix into `scripts/ux_audit.py` or `frontend/__tests__/shell/`.
