# Spec: First-party design system

- **ID**: 039-design-system
- **Status**: planned
- **Owner**: @bamr87
- **Created**: 2026-08-30
- **Roadmap Epic**: make the UI a managed, testable contract instead of two drifting idioms
- **Constitution Compliance**: confirmed against [docs/constitution.md](../../docs/constitution.md); §2 frontend-kit lock is amended by [ADR 0006](../../docs/adr/0006-first-party-design-system.md) (proposed — human maintainer must accept)

## 1. Problem & Motivation

Law AI ships two Next.js apps that look related and are styled independently:

- `frontend/` — Tailwind utility soup, blue/indigo accent, two CSS variables, no primitive components.
- `lsat-static/` — a real (if unnamed) design system: 11 tokens + semantic classes in `app/globals.css`.

Constitution §2, AGENTS.md, README, and the PRD all list **shadcn/ui**. It has never been installed. Agents following those docs import components that do not exist. `.design-sync/` snapshots both apps into a 915 KB compiled stylesheet that does not regenerate in CI and is not a source of truth.

There is no way to change a color, a focus ring, or a button once and have both products follow. Screens the size of `LsatLab.tsx` (~1611 lines) and `AgentDashboard.tsx` (~1460 lines) re-implement atoms inline. The static LSAT `QuestionCard` is the only robust accessible radiogroup.

Inventory and findings: [docs/ui-ux.md](../../docs/ui-ux.md).

## 2. Origin & Background

- Backlog items claimed: none (no existing BL covered "build a design system").
- Review question (constitution §13): this spec does **not** rank, score, or summarize legal authority. It does require that primitives used next to authority signals (confidence badges, graph node size) stay label-only — they must not imply correctness. UPL chrome (`LegalDisclaimerBanner` / footer) is in scope as a primitive.
- Who is the stronger here? A polished, confident UI without shared disclaimer/focus/empty-state primitives advantages the system operator (looks finished) over the under-resourced user (cannot tell advice from study aid, cannot tab through choices). The design system exists to make those obligations cheap to keep, not to make output look more authoritative.

## 3. Goals

- G1: One token file is the only palette; both apps consume it.
- G2: A small primitive set (not screens) that feature work must compose.
- G3: Docs, constitution §2, and the repo agree; agents have a catalog to follow.
- G4: The contract is testable (contrast, focus, no raw hex in migrated files).

## 4. Non-Goals

- NG1: Installing shadcn/ui, Radix, Storybook, or a CSS-in-JS runtime.
- NG2: A new top-level `packages/` workspace.
- NG3: Rewriting `LsatLab.tsx` / `AgentDashboard.tsx` / Analysis Studio (follow-ups).
- NG4: Merging the two LSAT products' feature sets (API lab vs static export).
- NG5: Light theme, i18n, or a marketing redesign of the homepage.
- NG6: Wiring unused deps (TanStack Query, framer-motion, lucide, xyflow).

## 5. User Stories

- As a contributor, I want to change `--accent-brand` once and see it on NavBar and platform buttons, so palette drift stops.
- As a contributor on `lsat-static`, I want semantic classes that already map to those tokens, so the GitHub Pages export stays Tailwind-free.
- As a prospective LSAT student, I want the same keyboard-accessible choices and visible focus I have on the static site, on every new control.
- As a reviewer of generated IRAC, I want the UPL banner to be a primitive that screens cannot forget.
- As an agent, I want `docs/ui-ux.md` + `frontend/ui/README.md` to list real import paths, so I stop scaffolding shadcn.

## 6. Functional Requirements

- **FR-1**: Add `frontend/ui/tokens.css` with named custom properties covering canvas, elevation, border, text, `--accent-brand` (blue), `--accent-practice` (amber), `--ok`, `--warn`, `--no`, radius, font-sans, font-mono, `--page-max`, `--prose-max`. Values lift from the current dark palette in [docs/ui-ux.md](../../docs/ui-ux.md).
- **FR-2**: `frontend/app/globals.css` imports the tokens and maps them through Tailwind v4 `@theme` so utilities like `bg-canvas`, `text-fg`, `border-line`, `bg-accent-brand` exist. Existing utility-class screens keep compiling.
- **FR-3**: `lsat-static/app/globals.css` imports `tokens.css` + `frontend/ui/semantic.css` (relative or copied-at-build — implementation in plan) and deletes duplicated `:root` hex. Semantic class names (`.btn`, `.card`, `.choice`, …) remain the public API of the static app.
- **FR-4**: Ship React primitives under `frontend/ui/components/`: `Button`, `Card`, `Input`, `Badge`, `Pill`, `Empty`, `Choice` (radiogroup, porting `lsat-static` QuestionCard keyboard behavior), `LegalDisclaimerBanner`, `LegalDisclaimerFooter`. Each accepts a `className` merge and uses tokens/semantic classes only.
- **FR-5**: Migrate a proof set onto primitives + tokens: `NavBar`, `LegalDisclaimer.tsx` (become re-exports or thin wrappers), `lsat-static/components/QuestionCard.tsx`. No raw hex in those files after migration.
  - *Amendment 2026-09-05 (BL-20260831-01, spec 051):* `NavBar.tsx` was deleted — dead since the spec 040 shell replaced it. The proof set is now `LegalDisclaimer.tsx` + `QuestionCard.tsx`; the shipped migration is unchanged.
- **FR-6**: Catalog at `frontend/ui/README.md` listing every primitive, when to use it, and the two accent roles. [docs/ui-ux.md](../../docs/ui-ux.md) stays the narrative inventory and is updated to describe the new layout as current once primitives land.
- **FR-7**: Accept [ADR 0006](../../docs/adr/0006-first-party-design-system.md) in the same PR that amends constitution §2 (drop shadcn/ui; name `frontend/ui/`) and §9 (UI changes update `docs/ui-ux.md`). Update AGENTS.md, README, and the ADR index. PRD/Proposal get a one-line pointer rather than a stack rewrite.
- **FR-8**: Retarget `.design-sync/ds/styles.src.css` to import `frontend/ui/tokens.css` + `semantic.css` instead of duplicating `:root`. Document in `.design-sync/NOTES.md` that the DS consumes `frontend/ui/`. Do not treat design-sync as a second palette.
- **FR-9**: Every primitive ships a Vitest + RTL test under `frontend/__tests__/ui/`. `Choice` covers arrow-key movement and submit. `LegalDisclaimerBanner` asserts the UPL heading is present.

## 7. Non-Functional Requirements

- **NFR-A11Y-1**: Primitives expose a visible `:focus-visible` ring using `--accent-brand` (platform) or `--accent-practice` (LSAT context). No primitive uses `outline-none` without a replacement ring. Contrast of `--text` and `--text-muted` on `--bg` / `--bg-elev` meets WCAG 2.2 AA.
- **NFR-A11Y-2**: `Choice` preserves the static site's radiogroup pattern (roving tabindex, Arrow selection-follows-focus, Space selects, Enter submits).
- **NFR-PERF-1**: `lsat-static` remains a Tailwind-free static export. Design-system CSS imported into it must not pull the Tailwind runtime or the 915 KB safelist build.
- **NFR-SEC-1**: No new runtime npm dependencies. Dev-only test helpers already in `frontend/package.json` are fine.
- **NFR-AUDIT-1**: No LLM, graph, or provenance changes. UPL chrome stays user-visible, not an audit event.
- **NFR-HITL-1**: `human_approval_required` is false for this spec. Visual acceptance is the PR review (constitution Level 2). ADR 0006 itself requires a human maintainer (constitution last line).
- **NFR-DOCS-1**: After implementation, constitution §2, AGENTS.md frontend bullets, README stack line, and `docs/ui-ux.md` describe the same kit.

## 8. Data Model Impact

None.

## 9. API Surface

None. No backend routes.

## 10. Agent / Crew Impact

None to `agents_runtime`. Dev agents gain `docs/ui-ux.md` + `frontend/ui/README.md` as the UI catalog (AGENTS.md Important Context Files).

## 11. LegalBench Impact

- Tasks affected: none.
- Expected delta: 0 pp.

## 12. Acceptance Criteria

- **AC-1**: Given both apps' `globals.css`, when tokens.css changes `--bg`, then both canvases pick up the new value without editing screen files.
- **AC-2**: Given `lsat-static` production build, when the design system is imported, then the export still contains no Tailwind runtime and existing semantic class names still style Overview/Drill/QuestionCard.
- **AC-3**: Given `Choice`, when the user arrows through options and presses Enter, then the selected label is submitted and the correct/incorrect classes apply — matching today's QuestionCard.
- **AC-4**: Given the migrated proof files (NavBar, LegalDisclaimer, QuestionCard), when grepped for raw `#rrggbb` / `rgb(`, then there are zero matches outside `frontend/ui/tokens.css`.
  - *Amendment 2026-09-05 (BL-20260831-01):* the grep now covers LegalDisclaimer + QuestionCard only; NavBar no longer exists.
- **AC-5**: Given `make test-frontend`, when the new `__tests__/ui/` files run, then they pass. `python3 scripts/spec_validator.py specs/039-design-system` and `python3 scripts/backlog_lint.py` exit 0.
- **AC-6**: Given constitution §2 after ADR 0006 is accepted, when an agent reads the locked stack, then it names `frontend/ui/` and does not name shadcn/ui.

## 13. Risks & Open Questions

- **R-1**: Tailwind `@theme` token names colliding with default color ramps (`blue-600` still used by unmigrated screens). Mitigation: add token utilities alongside existing ramps; do not delete `slate`/`blue` until follow-up migrations.
- **R-2**: Relative import of `frontend/ui/*.css` from `lsat-static` may break Next static export path resolution. Mitigation: plan records a copy-or-import decision; AC-2 is the gate.
- **R-3**: Focus-ring change on NavBar could look "unfinished" next to unmigrated screens. Mitigation: proof set is chrome + disclaimer + one LSAT control, not a mixed form.
- **R-4**: Human maintainer rejects ADR 0006 and wants shadcn instead. Mitigation: implementation of FR-7 is gated on ADR acceptance; tokens/primitives (FR-1–FR-5) are valuable either way.

## 14. Out of Scope / Follow-ups

Recorded in `tasks.md` ## Follow-ups Discovered and mirrored to BACKLOG: unused frontend deps, god-component decomposition, timer unification, homepage copy/footer drift, NavBar honesty ("Local" pill / "LG" mark).
