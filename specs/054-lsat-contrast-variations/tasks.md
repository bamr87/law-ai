# Tasks: LSAT Contrast Variations and the Agent Quality Loop

> Each task must reference one or more `FR-*` / `NFR-*` / `AC-*` IDs from `spec.md`. CI's [spec_validator.py](../../scripts/spec_validator.py) enforces that every requirement in `spec.md` is referenced by at least one task.

## Conventions

- Status: `[ ]` todo / `[~]` in-progress / `[x]` done.
- Owner: GitHub handle or `@copilot` / `@agent:<role>`.
- Each task lists exact files to touch and how to verify.

---

## T-001 — Contrast sets as bank data

- **Refs**: FR-1, FR-2, NFR-SPOILER-1, AC-1, AC-2
- **Owner**: @agent:claude
- **Status**: `[x]`
- **Files**: `backend/law_ai/lsat/services/bank.py`, `backend/law_ai/lsat/services/data/lr_bank.json`, `backend/law_ai/lsat/services/contrast.py` (new)
- **Steps**: add the two fields; hand-author `lr-097`..`lr-099`; write `stimulus_of`, `contrast_set`, `pivot_targets`, `public_contrast_view`.
- **Verify**: `docker compose run --rm backend pytest tests/lsat/test_contrast.py -k "Shape" -q --no-cov`

## T-002 — Deterministic variation gates

- **Refs**: FR-3, AC-1, AC-5
- **Owner**: @agent:claude
- **Status**: `[x]`
- **Files**: `backend/law_ai/lsat/services/contrast.py`
- **Steps**: `validate_variation` and its helpers.
- **Verify**: `pytest tests/lsat/test_contrast.py -k Gates`

## T-003 — Contrast author crew

- **Refs**: FR-4, NFR-AUDIT-1, NFR-HITL-1, NFR-DEGRADE-1
- **Owner**: @agent:claude
- **Status**: `[x]`
- **Files**: `backend/law_ai/agents_runtime/crews/lsat_contrast_author.py` (new), `prompts/lsat_contrast_author.v1.md` (new), `registry.py`
- **Verify**: `pytest tests/agents/test_lsat_contrast_author.py`

## T-004 — Revise loop and draft-and-file

- **Refs**: FR-5, FR-6, FR-7, AC-3, AC-4, AC-5, AC-8
- **Owner**: @agent:claude
- **Status**: `[x]`
- **Files**: `backend/law_ai/lsat/factory/revise.py` (new), `services/contrast.py`, `services/proposals.py`, `services/bank.py`
- **Verify**: `pytest tests/lsat/test_revise.py tests/lsat/test_contrast.py -k "Revise or DraftAndFile"`

## T-005 — Type reviewer crew, typecheck kind, sweeps

- **Refs**: FR-8, FR-9, NFR-AUDIT-1, NFR-DEGRADE-1, AC-7
- **Owner**: @agent:claude
- **Status**: `[x]`
- **Files**: `crews/lsat_type_reviewer.py` (new), `prompts/lsat_type_reviewer.v1.md` (new), `services/proposals.py`, `management/commands/lsat_type_review_sweep.py` (new), `management/commands/lsat_contrast_sweep.py` (new), `Makefile`
- **Verify**: `pytest tests/agents/test_lsat_type_reviewer.py tests/lsat/test_contrast_sweeps.py tests/lsat/test_contrast.py -k Typecheck`

## T-006 — API endpoints

- **Refs**: FR-7, AC-2, AC-6
- **Owner**: @agent:claude
- **Status**: `[x]`
- **Files**: `backend/law_ai/lsat/urls.py`, `backend/tests/api/test_lsat_contrast.py` (new)
- **Verify**: `pytest tests/api/test_lsat_contrast.py`

## T-007 — Frontend: contrast panel, deep link, authoring

- **Refs**: FR-10, AC-9
- **Owner**: @agent:claude
- **Status**: `[x]`
- **Files**: `frontend/components/lsat/ContrastPanel.tsx` (new), `QuestionCard.tsx`, `LrPanel.tsx`, `LsatLab.tsx`, `AuthoringPanel.tsx`, `lib/api.ts`, `lib/shell/viewState.ts`, `mocks/server.ts`, tests
- **Verify**: `docker compose run --rm frontend npx vitest run __tests__/components/lsat/ContrastPanel.test.tsx __tests__/components/lsat/AuthoringPanel.test.tsx`

## T-009 — Judge-driven rewrites of existing items

- **Refs**: FR-11, NFR-AUDIT-1, NFR-HITL-1, NFR-DEGRADE-1, AC-10, AC-11
- **Owner**: @agent:claude
- **Status**: `[x]`
- **Files**: `crews/lsat_question_editor.py` (new), `prompts/lsat_question_editor.v1.md` (new), `services/rewrite.py` (new), `services/proposals.py` (`rewrite` kind, `promote_rewrite`), `management/commands/lsat_question_review_sweep.py` (new), `urls.py`, `Makefile`, `frontend/lib/api.ts`, `frontend/components/lsat/AuthoringPanel.tsx`
- **Verify**: `pytest tests/lsat/test_rewrite.py tests/agents/test_lsat_question_editor.py tests/api/test_lsat_contrast.py`

## T-010 — Final review by Fable

- **Refs**: FR-12, AC-12
- **Owner**: @agent:claude
- **Status**: `[x]`
- **Files**: `crews/lsat_draft_judge.py` (`model_override`), `factory/revise.py` (`final_reviewer`), `services/contrast.py` (`final_review`), `services/rewrite.py`, `.env.example`
- **Verify**: `pytest tests/lsat/test_revise.py tests/lsat/test_contrast.py -k final`

## T-008 — Docs, gates, backlog loop

- **Refs**: FR-9, NFR-HITL-1
- **Owner**: @agent:claude
- **Status**: `[x]`
- **Files**: `docs/agent-roles.md`, `docs/lsat-playbooks.md`, `BACKLOG.md`, `lsat-static/content.json`
- **Verify**: `make lint-specs`

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

> Append-only. Mirror each item into [BACKLOG.md](../../BACKLOG.md) with a `BL-YYYYMMDD-NN` id. CI ([scripts/spec_validator.py](../../scripts/spec_validator.py)) checks this section exists. CI ([scripts/backlog_lint.py](../../scripts/backlog_lint.py)) checks the BACKLOG mirror.

- BL-20260908-01 — feature, med — `lsat-static` parity for the contrast panel (the bundle now carries `variation_of` and `contrast_note`; the static drill does not render them).
- BL-20260908-02 — feature, med — Wire the revise loop into the main content factory: give `LSATContentAuthor` a `critique` input and call `author_with_review` from `factory/judge.py` behind a `FactoryConfig.revise_enabled` flag.
- BL-20260908-03 — feature, low — Contrast variations for RC and LG (re-ask a passage or game question as another task on the same context); `pivot_targets` returns none for them today.
- BL-20260908-04 — infra, low — Autonomy beats for `lsat_contrast_sweep` and `lsat_type_review_sweep`, like the weekly cross-check beat, under the `AUTONOMY_ENABLED` kill-switch.
- BL-20260908-06 — feature, med — Human review of the full-bank sweep output: the `typecheck`, `rewrite` and variation rows the 2026-09-08 runs queued need a reviewer to approve or reject on the Authoring tab; the bank does not change until they do.
- BL-20260908-05 — tech-debt, low — `AgentListView` (`/api/agents`) does not surface `human_approval_required`, though every LSAT crew docstring says the registry does; expose it so the dashboard can show the HITL gate.
