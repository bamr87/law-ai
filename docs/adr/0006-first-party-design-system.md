# ADR 0006 — First-party design system (replace the shadcn/ui lock)

- **Status**: proposed
- **Date**: 2026-08-30
- **Spec**: [specs/039-design-system](../../specs/039-design-system/spec.md)
- **Constitution clauses amended**: [§2 Tech Stack (Locked)](../constitution.md#2-tech-stack-locked), [§9 Documentation](../constitution.md#9-documentation)

## Context

Constitution §2 locks the frontend kit to "Next.js 15 App Router, TypeScript strict, Tailwind, shadcn/ui, Cytoscape.js, TanStack Query." On disk:

- Both UI apps run **Next.js 16**.
- **shadcn/ui is not installed** — no `components.json`, no Radix, no `components/ui/`.
- **TanStack Query is declared and unused.**
- Styling is split across two idioms: Tailwind utilities in `frontend/`
(blue/indigo accent, almost no CSS variables) and a hand-written semantic CSS system in `lsat-static/` (amber accent, 11 tokens). See [docs/ui-ux.md](../ui-ux.md).

Agents following §2 try to import shadcn primitives that do not exist. Installing shadcn now would add Radix + a third styling idiom on top of two that already disagree, and would not serve `lsat-static/` (static export, no Tailwind, GitHub Pages).

## Decision

Replace the fictional shadcn/ui lock with a **first-party design system** owned at `frontend/ui/`:

1. **CSS custom properties** (`tokens.css`) are the only palette. Both apps
import them. Tailwind v4 `@theme` in `frontend/app/globals.css` maps tokens to utilities; `lsat-static` stays Tailwind-free and consumes `semantic.css`.
2. **React primitives** (Button, Card, Input, Badge, Banner, Empty, Choice,
Pill) live under `frontend/ui/components/`. Feature screens compose them. No new top-level `packages/` directory.
3. **Do not add shadcn, Storybook, or a third CSS-in-JS runtime.** Catalog
is `frontend/ui/README.md` plus Vitest. `.design-sync/` is retargeted as a consumer, not a source of truth.
4. **Named dual accents.** `--accent-brand` (blue, platform) and `--accent-practice` (amber, LSAT). Dark-only for v1.
5. **Documentation.** [docs/ui-ux.md](../ui-ux.md) is the UI source of
record. Constitution §9 gains a bullet: UI/token/primitive changes update that file.

Constitution §2 frontend line becomes:

> Frontend: Next.js App Router (16), TypeScript strict, Tailwind v4,
> first-party design system (`frontend/ui/`), Cytoscape.js.

TanStack Query remains allowed (already listed) but is not required by this ADR; unused-dep cleanup is a follow-up, not a constitution change. React Flow stays listed only if it is actually used; until then Cytoscape is the graph viewer.

## Consequences

**Positive**

- Docs match the repo. Agents stop generating shadcn imports.
- One token file, two renderers (utilities + semantic classes) — the static LSAT export stays small.
- Legal-specific primitives (Choice radiogroup, UPL Banner, authority labels) have a home that shadcn would not have given us.
- Visual drift becomes a testable contract (no raw hex in migrated files).

**Negative / Risks**

- We forgo shadcn's prebuilt a11y patterns and must own focus/keyboard
ourselves. Mitigated by lifting `QuestionCard`'s radiogroup as the `Choice` primitive and requiring `:focus-visible` on every primitive (spec 039 NFR-A11Y-1).
- Migrating ~3k lines of god components in one spec would stall. Spec 039
extracts tokens + primitives and migrates a proof set (NavBar, LegalDisclaimer, QuestionCard); remaining screens are follow-ups.
- `.design-sync/` compiled CSS will go stale during the cutover. Spec 039 retargets it or documents it as preview-only.

## Alternatives Considered

| Alternative | Why not |
|-------------|---------|
| Install shadcn/ui and migrate both apps onto it | Adds Radix + a third idiom; `lsat-static` cannot take Tailwind/Radix without blowing the static export; constitution would still be describing a future, not a present. |
| Keep documenting shadcn and do nothing | Agents and contributors keep importing ghosts; the two palettes keep drifting. |
| New top-level `packages/ui` workspace | Violates AGENTS.md's canonical layout ("do not invent new top-level locations") without a stronger reason than a folder name. `frontend/ui/` is enough. |
| Storybook as the catalog | New framework → needs its own ADR. Vitest + `frontend/ui/README.md` + existing design-sync previews cover review. |

## Supersedes / Superseded by

- Supersedes the shadcn/ui clause of constitution §2 (as written since the
FastAPI-era stack lock). Does not touch §1 (LLM chain), §4 (provenance), or §13 (jurisprudential honesty).
- Superseded by: none.
