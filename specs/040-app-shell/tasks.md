# Tasks: App shell + scoped settings

## T-001 — Settings resolver (no React)

- **Refs**: FR-1, AC-1
- **Owner**: @copilot
- **Status**: `[x]`
- **Files**: `frontend/lib/scope/types.ts`, `resolver.ts`, `frontend/__tests__/lib/resolver.test.ts`
- **Steps**: Implement `resolveEffective` + exhaustive truth table.
- **Verify**: `make test-frontend` includes resolver tests.

## T-002 — Setting catalog + store

- **Refs**: FR-2, FR-3
- **Owner**: @copilot
- **Status**: `[x]`
- **Files**: `frontend/lib/settings/define.ts`, `catalog.ts`, `frontend/lib/scope/store.ts`, `instance.ts`
- **Steps**: `defineSetting` + three v1 keys; memory/localStorage store.
- **Verify**: catalog keys match spec FR-2.

## T-003 — Module catalog

- **Refs**: FR-4, AC-2
- **Owner**: @copilot
- **Status**: `[x]`
- **Files**: `frontend/lib/modules/define.ts`, `catalog.ts`
- **Steps**: Register home/agents/analysis/graph/lsat/settings.
- **Verify**: catalog test asserts NavRail would see six modules.

## T-004 — Shell components + (app) routes

- **Refs**: FR-5, FR-6, FR-8, AC-4, NFR-A11Y-1
- **Owner**: @copilot
- **Status**: `[x]`
- **Files**: `frontend/components/shell/*`, `frontend/app/(app)/*`, `frontend/app/layout.tsx`, `frontend/components/NavBar.tsx`
- **Steps**: Grid shell, parallel routes, move pages, searchParams panels, keep NavBar export.
- **Verify**: URLs unchanged; skip link present.

## T-005 — Settings page + SettingField

- **Refs**: FR-6, FR-7, AC-3, NFR-A11Y-1
- **Owner**: @copilot
- **Status**: `[x]`
- **Files**: `SettingField.tsx`, `InheritanceBadge.tsx`, `app/(app)/settings/page.tsx`
- **Steps**: Provenance + explicit override/reset; analysis inspector UPL.
- **Verify**: RTL override/reset.

## T-006 — Tests + docs + backlog

- **Refs**: AC-5, NFR-DOCS-1, NFR-PERF-1, NFR-SEC-1, NFR-AUDIT-1, NFR-HITL-1
- **Owner**: @copilot
- **Status**: `[x]`
- **Files**: tests, `docs/ui-ux.md`, `docs/architecture.md`, `BACKLOG.md`
- **Steps**: Coverage-safe tests; docs; follow-ups.
- **Verify**: `make test-frontend`; `python3 scripts/spec_validator.py specs/040-app-shell`; `python3 scripts/backlog_lint.py`.

---

## Done-When (Definition of Done)

- All tasks `[x]`.
- All `AC-*` covered.
- `make test-frontend` green.
- LegalBench delta: 0 pp.
- **`## Follow-ups Discovered` populated.**

---

## Follow-ups Discovered

- BL-20260830-07 — feature, med — Persist `setting_value` in Django once spec 036 user accounts land; keep the TS resolver as the engine.
- BL-20260830-08 — feature, low — Bind spec 036 Matter as the `project` scope in ScopeSwitcher.
- BL-20260830-09 — feature, low — Command palette (⌘K) over modules + settings.
