# Law AI UI / UX

> Current-state inventory of every user-facing surface, the two styling
> idioms that actually ship, and the governance target for a maintainable
> design system. Constitution §2 still lists `shadcn/ui` as the locked
> frontend kit; **it is not installed**. Spec
> [039](../specs/039-design-system/spec.md) +
> [ADR 0006](adr/0006-first-party-design-system.md) propose replacing that
> lock with a first-party system owned in-repo.

This file is the source of truth for **what the UI is today**. The spec is the source of truth for **what we will build**. Do not treat `.design-sync/` as either.

---

## Surfaces

| Surface | App | Route / deploy | Stack | Components |
|---------|-----|----------------|-------|------------|
| Platform | `frontend/` | `make dev` → `:3000` | Next 16, React 19, Tailwind v4 | 10 files under `frontend/components/` |
| LSAT practice (static) | `lsat-static/` | GitHub Pages, `make lsat-export` | Next 16 static export, **no Tailwind** | 7 files under `lsat-static/components/` |
| Design-sync snapshot | `.design-sync/` | converter bundle only | Synthetic `law-ai-ui` package | Re-exports the 16 above |

`frontend/` pages: `/` (home), `/agents`, `/analysis`, `/graph`, `/lsat`, `/settings`. Chrome is the spec 040 **app shell** (`frontend/components/shell/`): masthead, nav rail, contextual sidebar, inspector. Modules register in `frontend/lib/modules/catalog.ts` — adding a surface must not edit `AppShell.tsx`. Settings resolve through `frontend/lib/scope/resolver.ts` (instance-only live scope; org/team wait on spec 036). There is no Case Library UI despite [docs/architecture.md](architecture.md) naming one.

`lsat-static/` is a single-page tab router (`Overview`, `LR`, `RC`, `LG`, `Concepts`, `Stats`) driven by a HITL-approved `content.json`. It is **not** on the `make dev` compose network.

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
| `NavBar.tsx` | Chrome | Sticky, mobile drawer. Brand mark is **"LG"**. Status pill is hardcoded `v0.1.1 · Local` and always green. |
| `LegalDisclaimer.tsx` | Guardrail | `Banner` + `Footer`. UPL copy (BL-20260810-07). Required beside generated analysis. |
| `HomeStats.tsx` | Widget | Fetches agent/backlog/spec counts. |
| `AgentDashboard.tsx` | Screen (~1460 lines) | God component: registry, runs, backlog, specs, health, launch modal. |
| `AgentTrace.tsx` | Primitive-ish | Numbered steps + optional confidence badge. Confidence is shown as a percentage with no authority label (watch constitution §13 if this is ever wired to citation volume). |
| `AnalysisStudio.tsx` | Screen | IRAC form, live WS trace, coverage envelope, citation verified badges, UPL banner. |
| `KnowledgeGraph.tsx` | Screen | Case search + neighborhood fetch. |
| `GraphViewer.tsx` | Widget | Cytoscape canvas. Open: [BL-20260803-03](../BACKLOG.md) (do not label centrality as correctness). |
| `LsatLab.tsx` | Screen (~1611 lines) | God component: overview, LR/RC/LG drills, concepts, stats, HITL authoring. Parallel to `lsat-static/`, not shared. |
| `LsatTimer.tsx` | Primitive | Section clock + per-question elapsed. Parallel to `lsat-static/components/SectionTimer.tsx`. |

`frontend/app/page.tsx` inlines its own `Card` and `SectionHeading` instead of extracting them. It also renders a marketing footer **in addition to** the layout's `LegalDisclaimerFooter` (double footer). The STACK blurb still says "FastAPI · Next.js 15".

### Static LSAT (`lsat-static/components/`)

| File | Kind | Notes |
|------|------|-------|
| `Overview.tsx` | Screen | Section cards, `.btn-primary` amber CTA. |
| `Drill.tsx` | Screen | Section timer + question nav + optional passage column. |
| `QuestionCard.tsx` | Primitive-ish | Accessible radiogroup (roving tabindex, arrows, Space/Enter). The strongest a11y implementation in the repo. |
| `PassagePanel.tsx` | Widget | Sticky RC/LG passage. |
| `SectionTimer.tsx` | Primitive | Warn / urgent / expired states via semantic classes. |
| `Concepts.tsx` | Screen | Filterable concept catalog. |
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
4. **Homepage STACK copy is stale** (FastAPI, Next 15, Ollama-as-the-runtime).
   Marketing pages that lie about the stack train users (and agents) wrong.

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

9. **Focus rings exist only on the static site** (`:focus-visible` → amber
outline). Platform components rely on browser defaults and often `focus:outline-none` (e.g. KnowledgeGraph search).
10. **No skip link** on either app.
11. **No `prefers-reduced-motion`.** NavBar ping animation, homepage pulses,
    and Cytoscape layout ignore it.
12. **QuestionCard keyboard pattern is the gold standard** — port it into
    the shared `Choice` primitive; do not regress it when unifying styles.

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

The maintainable shape, to be built under [specs/039-design-system](../specs/039-design-system/spec.md):

```
frontend/ui/
  tokens.css          # CSS custom properties — the only palette
  semantic.css        # .btn, .card, .choice, .pill, .empty, …
  README.md           # catalog: when to use which primitive
  components/         # React primitives (Button, Card, Input, …)
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
