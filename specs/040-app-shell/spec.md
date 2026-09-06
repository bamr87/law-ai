# Spec: App shell + scoped settings (instance-only)

- **ID**: 040-app-shell
- **Status**: shipped
- **Owner**: @bamr87
- **Created**: 2026-08-30
- **Roadmap Epic**: [nextjs-scoped-app-shell-architecture.md](../../nextjs-scoped-app-shell-architecture.md) adapted to Law AI; PRD §8.1 dashboard chrome
- **Constitution Compliance**: confirmed against [docs/constitution.md](../../docs/constitution.md). No Drizzle/Prisma, no Radix/shadcn, no org/team tables (spec 036 NG3). Settings engine is pure TypeScript (no React). Shell is Next.js App Router + Tailwind, first-party components.

## 1. Problem & Motivation

The platform has four product surfaces plus a marketing home, all sharing a single `NavBar`. Adding a surface requires editing chrome. There is no rail / contextual sidebar / inspector, no module registry, and no settings model with inheritance provenance.

The architecture note at repo root describes an enterprise shell + hierarchical settings engine. Law AI cannot adopt that note's stack (Drizzle, shadcn, org/tenant RBAC) without constitution + spec 036 violations. This spec implements the **same split** (shell vs engine vs modules) on the locked stack, with a **single live scope** (the local instance) and a resolver tested against a multi-level fixture so Matter (036) / future org scopes can plug in without rewriting the engine.

## 2. Origin & Background

- Backlog items claimed: none. Related open: BL-20260830-05 (NavBar honesty), BL-20260817-01… (036 follow-ups).
- Constitution §13: the shell does not rank authority. Any setting that toggles citation-count display must label the number as litigation-frequency, never correctness (`graph.show_citation_counts` help text). SettingField never shows a value without provenance (architecture trap #2/#3).
- Who is the stronger? A chrome that hides *why* a control is off (inherited, locked, no permission) advantages operators. Provenance on every effective value is the obligation.

## 3. Goals

- G1: App shell owns layout, navigation, panel orchestration, URL ↔ panel state. It does not import AnalysisStudio / GraphViewer / LsatLab.
- G2: Settings engine owns hierarchy, inheritance, locks, `Effective<T>`. It does not import React.
- G3: A module is added by registering one catalog entry (nav, sidebar, inspector copy, settings). Existing four surfaces plus Settings become modules.
- G4: Resolver is exhaustively unit-tested (inherit / override / lock-above / lock-below / default / type-drift).

## 4. Non-Goals

- NG1: Org / team / project Postgres tables or RBAC (spec 036 NG3). Types exist; only `instance` is seeded in the UI.
- NG2: Django persistence of `setting_value` (follow-up once 036 users land).
- NG3: shadcn, Radix, Zod, react-hook-form, Drizzle, Storybook, command palette.
- NG4: Rewriting Analysis Studio / LsatLab / AgentDashboard internals.
- NG5: Light theme.

## 5. User Stories

- As a contributor, I add a module by editing the catalog, not `AppShell`.
- As an operator, I see whether a setting is default, inherited, overridden, or locked — never a bare toggle.
- As a keyboard user, I can skip to main, tab the rail with `aria-current`, and collapse panels via the URL.

## 6. Functional Requirements

- **FR-1**: Pure-TS scope types (`instance|org|team|project|user`) + `resolveEffective(def, chain, values, canWrite)` returning `Effective<T>` with `value`, `source`, `isInherited`, `locked`, `lockedBy`, `canOverride`. Deepest unlocked value wins unless a locked ancestor exists; deepest lock wins among locks; unparsable stored values fall back to default.
- **FR-2**: `defineSetting` catalog in code (not DB). v1 keys: `analysis.hitl_threshold` (number, instance), `graph.show_citation_counts` (boolean, instance, §13-labelled), `ui.inspector.default_open` (boolean, instance).
- **FR-3**: In-memory setting store with `localStorage` persistence keyed by `scopeId+key`. No backend route.
- **FR-4**: `defineModule` catalog: `home`, `agents`, `analysis`, `graph`, `lsat`, `settings`. Each declares nav label/href/permission stub, optional sidebar links, inspector help. Shell folds the list; adding a module does not edit `AppShell.tsx`.
- **FR-5**: Next.js `(app)` route group with parallel routes `@sidebar` and `@inspector`. `AppShell` CSS grid: masthead / rail / sidebar / main / inspector. Panel open state in `searchParams` (`sidebar`, `inspector` = `0|1`).
- **FR-6**: Components: `AppShell`, `Masthead`, `NavRail`, `ContextSidebar`, `InspectorPanel`, `ScopeSwitcher` (instance-only, full path), `SettingField`, `InheritanceBadge`, `OverrideControl`. Override is an explicit action; focusing an inherited field does not write.
- **FR-7**: `/settings` page generated from the setting catalog + `SettingField`. UPL footer remains global (root layout). Analysis inspector includes `LegalDisclaimerBanner`.
- **FR-8**: Existing URLs (`/`, `/agents`, `/analysis`, `/graph`, `/lsat`) keep working. `NavBar.tsx` remains a horizontal registry-driven bar for `.design-sync` but is not mounted in root layout.
  - *Amendment 2026-09-05 (BL-20260831-01, spec 051):* `NavBar.tsx` and its `.design-sync` preview were deleted; the design-sync catalog has no chrome preview until `Masthead`/`NavRail` are registered there. The URL clause stands.

## 7. Non-Functional Requirements

- **NFR-A11Y-1**: Skip link; rail `aria-current="page"`; inspector/sidebar toggles are buttons with labels; `:focus-visible` rings; `prefers-reduced-motion` disables ping animations in the shell.
- **NFR-PERF-1**: No new runtime npm dependencies.
- **NFR-SEC-1**: ScopeSwitcher does not trust a client-supplied scope id for authorization (v1 has one instance scope; document the IDOR rule for when 036 lands).
- **NFR-AUDIT-1**: No LLM/graph writes. Setting changes are local-only; not `AuditEvent`s.
- **NFR-HITL-1**: `human_approval_required` false (no schema migration, no new agent path).
- **NFR-DOCS-1**: [docs/ui-ux.md](../../docs/ui-ux.md) and [docs/architecture.md](../../docs/architecture.md) describe the shell. Root architecture note stays as the generic essay; this spec is the Law AI adaptation.

## 8. Data Model Impact

None in Postgres/Neo4j. Frontend-only `ScopeNode` + `SettingValue` types.

## 9. API Surface

None.

## 10. Agent / Crew Impact

None.

## 11. LegalBench Impact

- Tasks affected: none.
- Expected delta: 0 pp.

## 12. Acceptance Criteria

- **AC-1**: Resolver tests cover inherit, override, lock-above-override, lock-below-lock, missing default, type-drift → default.
- **AC-2**: Adding a module to the catalog surfaces it in NavRail without editing `AppShell.tsx`.
- **AC-3**: `/settings` renders each catalog key with provenance; Override then Reset restores inherited/default.
- **AC-4**: `?inspector=1` opens the inspector on reload; `?sidebar=0` collapses the sidebar. Analysis route inspector includes the UPL banner.
- **AC-5**: `make test-frontend` green; `python3 scripts/spec_validator.py specs/040-app-shell` exits 0.

## 13. Risks & Open Questions

- **R-1**: Parallel routes can 404 without `default.tsx` — both slots ship `default.tsx`.
- **R-2**: Coverage thresholds (70% lines) — new shell files must be tested so the suite does not drop.
- **R-3**: `.design-sync` NavBar preview — keep `NavBar.tsx` export working.
  - *Amendment 2026-09-05 (BL-20260831-01):* retired with the file; the `next/navigation` shim in `.design-sync/ds/shims/` stays for the next route-aware export.

## 14. Out of Scope / Follow-ups

Django `setting_value` persistence, Matter-as-project scope (036), command palette, org/team RBAC.
