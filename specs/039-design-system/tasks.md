# Tasks: First-party design system

> Each task must reference one or more `FR-*` / `NFR-*` / `AC-*` IDs from `spec.md`. CI's [spec_validator.py](../../scripts/spec_validator.py) enforces that every requirement in `spec.md` is referenced by at least one task.

## Conventions

- Status: `[ ]` todo / `[~]` in-progress / `[x]` done.
- Owner: GitHub handle or `@copilot` / `@agent:<role>`.
- Each task lists exact files to touch and how to verify.

---

## T-001 — Land CSS tokens

- **Refs**: FR-1, FR-2, NFR-A11Y-1, AC-1
- **Owner**: @copilot
- **Status**: `[ ]`
- **Files**:
  - `frontend/ui/tokens.css` (new)
  - `frontend/app/globals.css`
  - `frontend/__tests__/ui/tokens.test.ts` (new)
- **Steps**:
  1. Create `frontend/ui/tokens.css` with the locked table in plan §2 (including `--accent` alias → `--accent-practice`).
  2. Import it from `frontend/app/globals.css` and map variables through `@theme`. Keep `@import "tailwindcss"` and existing `--background`/`--foreground` as aliases of `--bg`/`--text` so unmigrated screens do not flash.
  3. Assert required names in `tokens.test.ts`.
- **Verify**:
  - `make test-frontend` includes the new test.
  - Contrast of `--text` / `--text-muted` on `--bg` meets AA (document ratios in the test or README).

## T-002 — Extract semantic CSS and wire lsat-static

- **Refs**: FR-3, NFR-PERF-1, AC-1, AC-2
- **Owner**: @copilot
- **Status**: `[ ]`
- **Files**:
  - `frontend/ui/semantic.css` (new)
  - `lsat-static/app/globals.css`
  - `Makefile` (only if the copy fallback is required)
- **Steps**:
  1. Move atoms (`.btn*`, `.card*`, `.choice*`, `.pill*`, `.empty`, `.wrap`, `.sr-only`, `:focus-visible`) into `semantic.css`, referencing tokens not hex.
  2. Import tokens + semantic from `lsat-static/app/globals.css`; delete duplicated `:root` hex.
  3. Leave template CSS (drill, passage, stats, header layout) in the static app.
  4. If Next rejects the cross-app `@import`, add the copy fallback from the plan (R-2).
- **Verify**:
  - `lsat-static` production build succeeds inside Docker (or the existing make target) and the output CSS has no Tailwind runtime.
  - Overview/Drill still show amber primary buttons.

## T-003 — React primitives

- **Refs**: FR-4, NFR-A11Y-1, NFR-SEC-1
- **Owner**: @copilot
- **Status**: `[ ]`
- **Files**:
  - `frontend/ui/components/Button.tsx` (new)
  - `frontend/ui/components/Card.tsx` (new)
  - `frontend/ui/components/Input.tsx` (new)
  - `frontend/ui/components/Badge.tsx` (new)
  - `frontend/ui/components/Pill.tsx` (new)
  - `frontend/ui/components/Empty.tsx` (new)
  - `frontend/ui/index.ts` (new barrel)
- **Steps**:
  1. Implement primitives on tokens / semantic classes. `Button` variants: `default` | `primary` | `danger`. `Badge` variants: `ok` | `warn` | `no` | `muted`.
  2. `className` merge via a tiny local helper (no `clsx`/`cva` unless already a dependency — they are not; keep it to template strings).
  3. Focus ring on every interactive primitive.
- **Verify**:
  - `npx tsc --noEmit` via `make typecheck`.
  - No new runtime npm dependencies in `frontend/package.json`.

## T-004 — Choice primitive (keyboard radiogroup)

- **Refs**: FR-4, NFR-A11Y-2, AC-3
- **Owner**: @copilot
- **Status**: `[ ]`
- **Files**:
  - `frontend/ui/components/Choice.tsx` (new)
  - `frontend/__tests__/ui/Choice.test.tsx` (new)
- **Steps**:
  1. Port the radiogroup behavior from `lsat-static/components/QuestionCard.tsx` into `Choice` (list of `{label, text}`, selected, submitted, correct label).
  2. Visual states use `.choice` / `.choice-selected` / `.choice-correct` / `.choice-wrong`.
- **Verify**:
  - RTL: arrow keys move, Enter submits, correct/incorrect classes appear.

## T-005 — Disclaimer primitives + proof migration

- **Refs**: FR-4, FR-5, FR-9, AC-4, NFR-A11Y-1
- **Owner**: @copilot
- **Status**: `[ ]`
- **Files**:
  - `frontend/ui/components/LegalDisclaimer.tsx` (new)
  - `frontend/components/LegalDisclaimer.tsx` (re-export)
  - `frontend/components/NavBar.tsx`
  - `lsat-static/components/QuestionCard.tsx`
  - `frontend/__tests__/ui/LegalDisclaimer.test.tsx` (new)
  - `tests/test_ui_tokens.py` (new — AC-4 grep on proof files)
- **Steps**:
  1. Move Banner/Footer into `frontend/ui`; keep existing import paths working.
  2. NavBar: token utilities / Button; no raw hex; keep behavior (mobile drawer, active route). Do not "fix" the Local pill here (follow-up).
  3. QuestionCard: render `Choice`; keep attempt recording and announcements.
  4. Structural test: proof files contain no `#rrggbb` / `rgb(`.
- **Verify**:
  - Existing `frontend/__tests__/LsatLab.test.tsx` and NavBar-related tests still pass if present.
  - `make test-frontend` + `python3 tests/test_ui_tokens.py` (or pytest via the repo smoke suite).

## T-006 — Catalog + design-sync consumer

- **Refs**: FR-6, FR-8
- **Owner**: @copilot
- **Status**: `[ ]`
- **Files**:
  - `frontend/ui/README.md` (new)
  - `docs/ui-ux.md`
  - `.design-sync/ds/styles.src.css`
  - `.design-sync/NOTES.md`
  - `.design-sync/conventions.md`
- **Steps**:
  1. Catalog every primitive, accent role, and "do not import shadcn".
  2. Update `docs/ui-ux.md` "Governance target" to "Current layout" once files exist.
  3. Point design-sync stylesheet at `frontend/ui/tokens.css` + `semantic.css`; drop duplicated `:root`.
  4. NOTES: DS consumes `frontend/ui/`; do not hand-edit compiled colors.
- **Verify**:
  - Links in README resolve (case-exact; `tests/test_docs.py` scan).

## T-007 — Accept ADR 0006 and align locked docs

- **Refs**: FR-7, NFR-DOCS-1, NFR-AUDIT-1, NFR-HITL-1, AC-6
- **Owner**: @bamr87 (human) + @copilot
- **Status**: `[ ]`
- **Files**:
  - `docs/adr/0006-first-party-design-system.md` (status → accepted)
  - `docs/adr/README.md`
  - `docs/constitution.md` §2, §9
  - `AGENTS.md` (frontend stack + Important Context Files + `frontend/ui/` in the tree)
  - `README.md` stack line
  - `PRD.md` frontend bullet (pointer, not a rewrite)
  - `tests/test_docs.py` (`docs/ui-ux.md` in `REQUIRED_DOCS`)
- **Steps**:
  1. Human accepts ADR 0006.
  2. Amend constitution §2 frontend line per the ADR; add §9 bullet for `docs/ui-ux.md`.
  3. Align AGENTS.md / README; do not claim Next 15 or shadcn.
- **Verify**:
  - `rg -n shadcn AGENTS.md docs/constitution.md README.md` is empty (PRD/Proposal historical text may keep a pointer).
  - `python3 tests/test_docs.py` equivalent via `make test` smoke.

## T-008 — Primitive test suite gate

- **Refs**: FR-9, AC-5, NFR-A11Y-1
- **Owner**: @copilot
- **Status**: `[ ]`
- **Files**:
  - `frontend/__tests__/ui/*.test.tsx`
- **Steps**:
  1. Fill remaining primitive tests (Button variants, Empty, Banner heading).
  2. Run the full frontend suite in Docker.
- **Verify**:
  - `make test-frontend`
  - `make lint` / `make typecheck`
  - `python3 scripts/spec_validator.py specs/039-design-system`
  - `python3 scripts/backlog_lint.py`

---

## Done-When (Definition of Done)

- All tasks `[x]`.
- All `AC-*` from `spec.md` covered by passing tests.
- `make lint && make typecheck && make test-frontend` green.
- LegalBench delta: 0 pp (N/A — no reasoning change).
- ADR 0006 accepted; constitution §2 no longer lists shadcn/ui.
- **`## Follow-ups Discovered` section below populated.**

---

## Follow-ups Discovered

> Append-only. Mirror each item into [BACKLOG.md](../../BACKLOG.md) with a `BL-YYYYMMDD-NN` id.

- BL-20260830-01 — tech-debt, med — Unused frontend deps (`@tanstack/react-query`, `framer-motion`, `lucide-react`, `@xyflow/react`) declared with zero imports.
- BL-20260830-02 — refactor, med — Decompose `LsatLab.tsx` (~1611 lines) and `AgentDashboard.tsx` (~1460 lines) onto `frontend/ui` primitives.
- BL-20260830-03 — doc-gap, low — Homepage STACK copy still says FastAPI · Next.js 15; hero GitHub chip href is `https://github.com` not the repo.
- BL-20260830-04 — feature, low — Unify `LsatTimer` and `lsat-static` `SectionTimer` onto a shared Timer primitive.
- BL-20260830-05 — feature, low — NavBar status pill is hardcoded `v0.1.1 · Local` (always green) and the brand mark reads "LG".
- BL-20260830-06 — tech-debt, low — Homepage renders a marketing footer in addition to `LegalDisclaimerFooter` (double footer).
