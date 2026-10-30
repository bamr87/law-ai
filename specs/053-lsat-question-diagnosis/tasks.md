# Tasks: LSAT Question-Type Diagnosis

> Each task must reference one or more `FR-*` / `NFR-*` / `AC-*` IDs from `spec.md`. CI's `spec_validator.py` enforces that every requirement in `spec.md` is referenced by at least one task.

## Conventions

- Status: `[ ]` todo / `[~]` in-progress / `[x]` done.
- Owner: GitHub handle or `@copilot` / `@agent:<role>`.
- Each task lists exact files to touch and how to verify.

---

## T-001 — Author the playbook catalog

- **Refs**: FR-1, FR-6, NFR-PROV-1, AC-1
- **Owner**: @agent:claude
- **Status**: `[x]`
- **Files**:
  - `backend/law_ai/lsat/services/data/playbooks.json` (new)
- **Steps**:
  1. Write the shared strategy and trap catalogs.
  2. Write one playbook per question archetype: family, priority, cues, cue patterns, concept requirements, task, strategies, method, traps, look-alikes.
- **Verify**:
  - `docker compose run --rm backend pytest tests/lsat/test_playbooks.py -k Catalog -q --no-cov`

## T-002 — Playbook service and stem-cue classifier

- **Refs**: FR-3, FR-4, FR-5, FR-6, NFR-DETERMINISM-1, NFR-SPOILER-1, AC-3, AC-5
- **Owner**: @agent:claude
- **Status**: `[x]`
- **Files**:
  - `backend/law_ai/lsat/services/playbooks.py` (new)
  - `backend/tests/lsat/test_playbooks.py` (new)
- **Steps**:
  1. Pydantic models and cached loaders that fail loudly on dangling references.
  2. `classify` over the question sentence with priority, concept-requirement and overlap tie-breaks; stamp wins; concept fallback; none rather than a guess.
  3. `diagnosis_options` (seeded, key never marked) and `grade_diagnosis` (family partial credit, any key strategy counts, quoted cue).
- **Verify**:
  - `docker compose run --rm backend pytest tests/lsat/test_playbooks.py -q --no-cov`

## T-003 — Stamp the bank

- **Refs**: FR-2, AC-2
- **Owner**: @agent:claude
- **Status**: `[x]`
- **Files**:
  - `backend/law_ai/lsat/management/commands/lsat_archetype_backfill.py` (new)
  - `backend/law_ai/lsat/services/data/{lr,rc,lg}_bank.json`
  - `lsat-static/content.json` (regenerated)
- **Steps**:
  1. Command with `--check` / `--force`; run it; review the diff (208 stamps, nothing else).
  2. `make lsat-export` so the static bundle carries the stamps.
- **Verify**:
  - `make manage CMD='lsat_archetype_backfill --check'` reports every item stamped.
  - `test_every_bank_item_is_stamped_and_the_stem_agrees` passes.

## T-004 — Diagnosis attempts table and stats

- **Refs**: FR-7, NFR-SEP-1, NFR-AUDIT-1, AC-6
- **Owner**: @agent:claude
- **Status**: `[x]`
- **Files**:
  - `backend/law_ai/lsat/models.py`, `backend/law_ai/lsat/migrations/0005_lsat_diagnosis_attempt.py`
  - `backend/law_ai/lsat/services/attempts.py`
- **Steps**:
  1. `LsatDiagnosisAttempt` sibling table; migration.
  2. `record_diagnosis_attempt`, `diagnosis_summary` (weakest-first, confusions), `diagnosis_stats`.
- **Verify**:
  - `docker compose run --rm backend pytest tests/lsat/test_playbooks.py -k Summary tests/api/test_lsat_diagnose.py -k signed_in -q --no-cov`

## T-005 — API endpoints

- **Refs**: FR-4, FR-5, FR-7, FR-8, FR-9, NFR-AUDIT-1, NFR-SPOILER-1, AC-3, AC-4, AC-6, AC-7
- **Owner**: @agent:claude
- **Status**: `[x]`
- **Files**:
  - `backend/law_ai/lsat/urls.py`
  - `backend/tests/api/test_lsat_diagnose.py` (new)
- **Steps**:
  1. `DiagnoseView` (GET/POST, audit event, signed-in row), `PlaybooksView`, `PlaybookDetailView` (taught_in, question_count, weights).
  2. `_fold_diagnosis` into both stats readings; `archetype` filter on `QuestionsView`.
- **Verify**:
  - `docker compose run --rm backend pytest tests/api/test_lsat_diagnose.py -q --no-cov`

## T-006 — Diagnose-first in the drill

- **Refs**: FR-10, FR-11, AC-8, AC-9
- **Owner**: @agent:claude
- **Status**: `[x]`
- **Files**:
  - `frontend/lib/api.ts`, `frontend/lib/lsat/diagnoseMode.ts` (new), `frontend/lib/shell/viewState.ts`
  - `frontend/components/lsat/DiagnoseStep.tsx` (new), `frontend/components/lsat/QuestionCard.tsx`
  - `frontend/components/LsatLab.tsx`, `frontend/components/lsat/LrPanel.tsx`
  - `frontend/__tests__/components/lsat/DiagnoseStep.test.tsx` (new), `frontend/__tests__/lib/lsatDiagnoseMode.test.ts` (new), `frontend/__tests__/components/lsat/QuestionCard.test.tsx`
- **Steps**:
  1. Types and fetchers; persisted setting store; header toggle.
  2. `DiagnoseStep` with two radiogroups, skip, feedback, continue; gate the card's choices, guide, keys and submit; header chip; `?archetype=` deep link into LR.
- **Verify**:
  - `docker compose run --rm frontend npx vitest run __tests__/components/lsat/DiagnoseStep.test.tsx __tests__/components/lsat/QuestionCard.test.tsx __tests__/lib/lsatDiagnoseMode.test.ts`

## T-007 — Playbooks page and recognition stats

- **Refs**: FR-9, FR-12, AC-10, AC-11
- **Owner**: @agent:claude
- **Status**: `[x]`
- **Files**:
  - `frontend/components/lsat/PlaybookBrowser.tsx` (new), `frontend/app/(app)/lsat/playbooks/page.tsx` (new)
  - `frontend/components/lsat/StatsPanel.tsx`, `frontend/components/lsat/OverviewPanel.tsx`
  - `frontend/__tests__/components/lsat/PlaybookBrowser.test.tsx` (new), `frontend/__tests__/components/lsat/StatsPanel.test.tsx`
- **Steps**:
  1. Section tabs, per-type cards with drill links, trap glossary, hash deep links.
  2. `DiagnosisProgress` card; Overview link.
- **Verify**:
  - `docker compose run --rm frontend npx vitest run __tests__/components/lsat/PlaybookBrowser.test.tsx __tests__/components/lsat/StatsPanel.test.tsx`

## T-008 — Runbook, gates, backlog loop

- **Refs**: FR-2, AC-2
- **Owner**: @agent:claude
- **Status**: `[x]`
- **Files**:
  - `docs/lsat-playbooks.md` (new), `BACKLOG.md`
- **Steps**:
  1. Write the runbook (where things live, how to add a playbook, how to re-stamp).
  2. `make lint`, `make typecheck`, `make test`, `make lint-specs`; mirror follow-ups.
- **Verify**:
  - `make lint-specs` passes.

---

## Done-When (Definition of Done)

- All tasks `[x]`.
- All `AC-*` from `spec.md` covered by passing tests.
- `make lint && make test` green.
- LegalBench delta recorded in PR description (if §11 of spec applies).
- Provenance logging verified manually for new agent paths.
- **`## Follow-ups Discovered` section below populated** — at minimum, every implementer must record one of: a new BACKLOG entry, a refactor candidate, a missing test, or `_none_` (must be justified in the PR).

---

## Follow-ups Discovered

> Append-only. Mirror each item into [BACKLOG.md](../../BACKLOG.md) with a `BL-YYYYMMDD-NN` id. CI (`scripts/spec_validator.py`) checks this section exists. CI (`scripts/backlog_lint.py`) checks the BACKLOG mirror.

- BL-20260907-16 — feature, med — `lsat-static` parity for the diagnosis exercise and the playbooks page: export the playbook catalog into `content.json`, mirror `DiagnoseStep` and `PlaybookBrowser` under `lsat-static/components/`, and extend the drift gate.
- BL-20260907-17 — feature, med — Per-choice trap tagging: when spec 047 FR-17's per-choice rationales land, tag each distractor with a trap id from `playbooks.json` so post-grade feedback can say which trap a wrong answer fell for, and the stats can rank traps as well as types.
- BL-20260907-18 — feature, low — Adaptive sequencing by weakest type: deal the next LR question from the archetype the learner misreads most (`diagnosis.weakest`). Spec 047 NG3 fences this off; it needs its own spec.
- BL-20260907-19 — feature, low — Server-side `archetype` filter for the passages endpoint so RC/LG "drill this type" links land on the type rather than on its primary concept.
- BL-20260907-20 — tech-debt, low — The factory coverage census now counts by stamp, which drops the LG game-type archetypes (`lg-grouping`, `lg-hybrid`, `lg-in-out-selection`) to one item each because task cues win classification. Decide whether the planner should treat game-type archetypes as passage-set targets rather than item deficits.
