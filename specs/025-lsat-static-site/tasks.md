# Tasks: LSAT Static Practice Site

> Each task references `FR-*` / `NFR-*` / `AC-*` IDs from `spec.md`; [spec_validator.py](../../scripts/spec_validator.py) enforces full coverage.

## Conventions

- Status: `[ ]` todo / `[~]` in-progress / `[x]` done.
- Verify commands run inside Docker per CLAUDE.md (root-suite test is host-stdlib by design).

---

## T-001 — Exporter command

- **Refs**: FR-1, FR-2, AC-1
- **Owner**: @bamr87 (+Claude Code)
- **Status**: `[x]`
- **Files**: `backend/lawgraph/lsat/management/commands/lsat_export.py`, `backend/tests/lsat/test_export_site.py`
- **Steps**: dump sections/concepts/passages/questions via the loaders with stable ordering; `schema_version`, `generated_at`, per-section `counts`; `--out`/`--pretty` options.
- **Verify**: `docker compose run --rm backend pytest tests/lsat/test_export_site.py -q --no-cov`

## T-002 — Static practice app

- **Refs**: FR-3, FR-4, FR-5, FR-6, NFR-PERF-1, NFR-SEC-1, NFR-A11Y-1, AC-2, AC-3
- **Owner**: @bamr87 (+Claude Code)
- **Status**: `[x]`
- **Files**: `frontend/public/lsat-practice/{index.html,styles.css,app.js,.nojekyll}`
- **Steps**: hash router; home/drill/passages/concepts/stats views; client-side grading with explanation + references; A–E/Enter keyboard (modifier-safe) + radiogroup + `aria-live`; localStorage attempts + stats + reset; relative URLs only.
- **Verify**: browser click-through over static serving (AC-2/AC-3); adversarial review pass.

## T-003 — Make target + drift gate

- **Refs**: FR-7, FR-8, AC-4
- **Owner**: @bamr87 (+Claude Code)
- **Status**: `[x]`
- **Files**: `Makefile`, `tests/test_lsat_site.py`
- **Steps**: `lsat-export` target (Docker run → host copy into `frontend/public/lsat-practice/data/`); stdlib root test for structure + bank↔artifact parity + integrity checks.
- **Verify**: `python3 -m pytest tests/test_lsat_site.py -q` (root suite convention) fails on a stale artifact, passes after `make lsat-export`.

## T-004 — GitHub Pages workflow

- **Refs**: FR-9, NFR-SEC-1, AC-5
- **Owner**: @bamr87 (+Claude Code)
- **Status**: `[x]`
- **Files**: `.github/workflows/deploy-lsat-pages.yml`
- **Steps**: trigger on `main` pushes touching the site/bank paths + `workflow_dispatch`; `configure-pages` → `upload-pages-artifact` (path: `frontend/public/lsat-practice`) → `deploy-pages`; minimal permissions.
- **Verify**: workflow YAML parses; paths + permissions reviewed; deployment exercised after merge (Pages source must be set to GitHub Actions once, manually).

## T-005 — Export, verify live, ship

- **Refs**: AC-1, AC-2, AC-3, NFR-TEST-1
- **Owner**: @bamr87 (+Claude Code)
- **Status**: `[x]`
- **Files**: `frontend/public/lsat-practice/data/content.json` (generated)
- **Steps**: run `make lsat-export`; serve the folder statically; keyboard-answer an LR item, grade an RC and LG item, check stats persistence; run backend + root suites.
- **Verify**: all suites green; screenshots of the running app.

---

## Done-When (Definition of Done)

- All FR/NFR/AC covered above; exporter + drift tests green; app verified in a real browser over static serving; workflow reviewed; BACKLOG mirrored.

## Follow-ups Discovered

_Mirrored to [BACKLOG.md](../../BACKLOG.md)._

- **BL-20260702-09** — *feature, low* — Timed-section simulation mode for the static app (35-minute section timer, per-question pacing readout) — spec 025 NG5.
- **BL-20260702-10** — *feature, low* — Progress export/import (JSON download/restore) in the static app; localStorage is device-bound and silently lost in private browsing.
- **BL-20260702-11** — *infra, low* — Auto-refresh the site artifact on content approval: extend `promote_to_bank` (or a CI job) to run `lsat_export` and commit `content.json`, removing the manual `make lsat-export` step the drift gate currently enforces.
- **BL-20260702-12** — *doc-gap, low* — Document the static-site delivery channel (exporter, drift gate, Pages one-time setup, `make lsat-export`) in `docs/architecture.md`.
- **BL-20260702-13** — *refactor, low* — `frontend/components/LsatLab.tsx` has the same radiogroup gap the static-app review confirmed here: `role="radio"` buttons without roving tabindex or Arrow-key selection (ARIA APG radio pattern), and Enter-with-selection submits even when a different choice is focused. Port the static app's fixed pattern (selection-follows-focus arrows, Enter-on-selected submits) back into the Lab.
