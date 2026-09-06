# Tasks: Backlog Zero

> Each task references `FR-*` / `NFR-*` / `AC-*` IDs from `spec.md`. One task per work package; the per-item dossiers (BACKLOG text, verified evidence, plan, files) are the task's step list.

## Conventions

- Status: `[ ]` todo / `[~]` in-progress / `[x]` done.
- Owner: `@agent:implementer` under Claude Code, verified by `@agent:verifier`.
- Each task lists the BACKLOG ids it resolves; the files are those items' files.

---

## T-001 — Package P01_lsat_static

- **Refs**: FR-P01, NFR-AUDIT-1, NFR-HITL-1, NFR-GATES-1, NFR-DOCKER-1, AC-1, AC-2, AC-3, AC-4
- **Owner**: @agent:implementer
- **Status**: `[ ]`
- **Files**: per item; see the ids below and their BACKLOG entries.
- **Items**: BL-20260831-18, BL-20260831-08, BL-20260901-07, BL-20260901-11, BL-20260831-26, BL-20260903-07, BL-20260905-03, BL-20260905-04, BL-20260831-22, BL-20260831-19, BL-20260831-20, BL-20260831-25, BL-20260901-05, BL-20260702-10, BL-20260831-24, BL-20260503-04
- **Steps**:
  1. For each id in order: re-read the BACKLOG text and the code it names, implement the smallest complete change, add or extend tests.
  2. Run the scoped gates for the touched files (ruff, black, mypy against the baseline; eslint, tsc, vitest).
  3. Record follow-ups.
- **Verify**:
  - Targeted tests for every touched area pass inside Docker.
  - The item's ask is demonstrably met (verifier pass with evidence).

## T-002 — Package P02_e2e

- **Refs**: FR-P02, NFR-AUDIT-1, NFR-HITL-1, NFR-GATES-1, NFR-DOCKER-1, AC-1, AC-2, AC-3, AC-4
- **Owner**: @agent:implementer
- **Status**: `[ ]`
- **Files**: per item; see the ids below and their BACKLOG entries.
- **Items**: BL-20260811-16, BL-20260429-27, BL-20260430-11, BL-20260831-05, BL-20260831-09, BL-20260503-17, BL-20260901-03
- **Steps**:
  1. For each id in order: re-read the BACKLOG text and the code it names, implement the smallest complete change, add or extend tests.
  2. Run the scoped gates for the touched files (ruff, black, mypy against the baseline; eslint, tsc, vitest).
  3. Record follow-ups.
- **Verify**:
  - Targeted tests for every touched area pass inside Docker.
  - The item's ask is demonstrably met (verifier pass with evidence).

## T-003 — Package P03_shell

- **Refs**: FR-P03, NFR-AUDIT-1, NFR-HITL-1, NFR-GATES-1, NFR-DOCKER-1, AC-1, AC-2, AC-3, AC-4
- **Owner**: @agent:implementer
- **Status**: `[ ]`
- **Files**: per item; see the ids below and their BACKLOG entries.
- **Items**: BL-20260831-01, BL-20260831-11, BL-20260905-07, BL-20260831-06, BL-20260831-14, BL-20260905-08, BL-20260905-09, BL-20260831-02, BL-20260430-07, BL-20260901-10
- **Steps**:
  1. For each id in order: re-read the BACKLOG text and the code it names, implement the smallest complete change, add or extend tests.
  2. Run the scoped gates for the touched files (ruff, black, mypy against the baseline; eslint, tsc, vitest).
  3. Record follow-ups.
- **Verify**:
  - Targeted tests for every touched area pass inside Docker.
  - The item's ask is demonstrably met (verifier pass with evidence).

## T-004 — Package P04a_lsat_lab_refactor

- **Refs**: FR-P04, NFR-AUDIT-1, NFR-HITL-1, NFR-GATES-1, NFR-DOCKER-1, AC-1, AC-2, AC-3, AC-4
- **Owner**: @agent:implementer
- **Status**: `[ ]`
- **Files**: per item; see the ids below and their BACKLOG entries.
- **Items**: BL-20260830-02, BL-20260831-15, BL-20260830-04, BL-20260829-01, BL-20260829-02, BL-20260831-13, BL-20260905-02, BL-20260503-07, BL-20260702-13
- **Steps**:
  1. For each id in order: re-read the BACKLOG text and the code it names, implement the smallest complete change, add or extend tests.
  2. Run the scoped gates for the touched files (ruff, black, mypy against the baseline; eslint, tsc, vitest).
  3. Record follow-ups.
- **Verify**:
  - Targeted tests for every touched area pass inside Docker.
  - The item's ask is demonstrably met (verifier pass with evidence).

## T-005 — Package P04b_lsat_lab_features

- **Refs**: FR-P04, NFR-AUDIT-1, NFR-HITL-1, NFR-GATES-1, NFR-DOCKER-1, AC-1, AC-2, AC-3, AC-4
- **Owner**: @agent:implementer
- **Status**: `[ ]`
- **Files**: per item; see the ids below and their BACKLOG entries.
- **Items**: BL-20260901-08, BL-20260901-06, BL-20260901-09, BL-20260905-01, BL-20260905-06, BL-20260903-05, BL-20260830-13, BL-20260831-27, BL-20260503-06, BL-20260702-06, BL-20260830-14
- **Steps**:
  1. For each id in order: re-read the BACKLOG text and the code it names, implement the smallest complete change, add or extend tests.
  2. Run the scoped gates for the touched files (ruff, black, mypy against the baseline; eslint, tsc, vitest).
  3. Record follow-ups.
- **Verify**:
  - Targeted tests for every touched area pass inside Docker.
  - The item's ask is demonstrably met (verifier pass with evidence).

## T-006 — Package P05a_lsat_factory

- **Refs**: FR-P05, NFR-AUDIT-1, NFR-HITL-1, NFR-GATES-1, NFR-DOCKER-1, AC-1, AC-2, AC-3
- **Owner**: @agent:implementer
- **Status**: `[ ]`
- **Files**: per item; see the ids below and their BACKLOG entries.
- **Items**: BL-20260702-08, BL-20260702-01, BL-20260702-02, BL-20260702-03, BL-20260702-04, BL-20260702-05, BL-20260901-04, BL-20260905-13, BL-20260831-28, BL-20260429-19
- **Steps**:
  1. For each id in order: re-read the BACKLOG text and the code it names, implement the smallest complete change, add or extend tests.
  2. Run the scoped gates for the touched files (ruff, black, mypy against the baseline; eslint, tsc, vitest).
  3. Record follow-ups.
- **Verify**:
  - Targeted tests for every touched area pass inside Docker.
  - The item's ask is demonstrably met (verifier pass with evidence).

## T-007 — Package P05b_lsat_library_data

- **Refs**: FR-P05, NFR-AUDIT-1, NFR-HITL-1, NFR-GATES-1, NFR-DOCKER-1, AC-1, AC-2, AC-3
- **Owner**: @agent:implementer
- **Status**: `[ ]`
- **Files**: per item; see the ids below and their BACKLOG entries.
- **Items**: BL-20260903-09, BL-20260903-06, BL-20260903-08, BL-20260901-02, BL-20260503-02, BL-20260901-01, BL-20260831-23
- **Steps**:
  1. For each id in order: re-read the BACKLOG text and the code it names, implement the smallest complete change, add or extend tests.
  2. Run the scoped gates for the touched files (ruff, black, mypy against the baseline; eslint, tsc, vitest).
  3. Record follow-ups.
- **Verify**:
  - Targeted tests for every touched area pass inside Docker.
  - The item's ask is demonstrably met (verifier pass with evidence).

## T-008 — Package P05c_lsat_proposals

- **Refs**: FR-P05, NFR-AUDIT-1, NFR-HITL-1, NFR-GATES-1, NFR-DOCKER-1, AC-1, AC-2, AC-3
- **Owner**: @agent:implementer
- **Status**: `[ ]`
- **Files**: per item; see the ids below and their BACKLOG entries.
- **Items**: BL-20260810-08, BL-20260527-06, BL-20260606-02, BL-20260702-07, BL-20260831-21, BL-20260527-05
- **Steps**:
  1. For each id in order: re-read the BACKLOG text and the code it names, implement the smallest complete change, add or extend tests.
  2. Run the scoped gates for the touched files (ruff, black, mypy against the baseline; eslint, tsc, vitest).
  3. Record follow-ups.
- **Verify**:
  - Targeted tests for every touched area pass inside Docker.
  - The item's ask is demonstrably met (verifier pass with evidence).

## T-009 — Package P05d_lsat_synth

- **Refs**: FR-P05, NFR-AUDIT-1, NFR-HITL-1, NFR-GATES-1, NFR-DOCKER-1, AC-1, AC-2, AC-3
- **Owner**: @agent:implementer
- **Status**: `[ ]`
- **Files**: per item; see the ids below and their BACKLOG entries.
- **Items**: BL-20260903-15, BL-20260903-17, BL-20260903-14, BL-20260903-16, BL-20260903-13, BL-20260606-01
- **Steps**:
  1. For each id in order: re-read the BACKLOG text and the code it names, implement the smallest complete change, add or extend tests.
  2. Run the scoped gates for the touched files (ruff, black, mypy against the baseline; eslint, tsc, vitest).
  3. Record follow-ups.
- **Verify**:
  - Targeted tests for every touched area pass inside Docker.
  - The item's ask is demonstrably met (verifier pass with evidence).

## T-010 — Package P06a_llm_core

- **Refs**: FR-P06, NFR-AUDIT-1, NFR-HITL-1, NFR-GATES-1, NFR-DOCKER-1, AC-1, AC-2, AC-3
- **Owner**: @agent:implementer
- **Status**: `[ ]`
- **Files**: per item; see the ids below and their BACKLOG entries.
- **Items**: BL-20260811-22, BL-20260905-12, BL-20260810-05, BL-20260810-15, BL-20260811-21, BL-20260811-23, BL-20260811-24, BL-20260904-04, BL-20260904-05, BL-20260904-06, BL-20260905-11
- **Steps**:
  1. For each id in order: re-read the BACKLOG text and the code it names, implement the smallest complete change, add or extend tests.
  2. Run the scoped gates for the touched files (ruff, black, mypy against the baseline; eslint, tsc, vitest).
  3. Record follow-ups.
- **Verify**:
  - Targeted tests for every touched area pass inside Docker.
  - The item's ask is demonstrably met (verifier pass with evidence).

## T-011 — Package P06b_streaming

- **Refs**: FR-P06, NFR-AUDIT-1, NFR-HITL-1, NFR-GATES-1, NFR-DOCKER-1, AC-1, AC-2, AC-3
- **Owner**: @agent:implementer
- **Status**: `[ ]`
- **Files**: per item; see the ids below and their BACKLOG entries.
- **Items**: BL-20260811-20, BL-20260811-26, BL-20260811-15, BL-20260429-16, BL-20260811-14, BL-20260503-03, BL-20260503-01, BL-20260429-18
- **Steps**:
  1. For each id in order: re-read the BACKLOG text and the code it names, implement the smallest complete change, add or extend tests.
  2. Run the scoped gates for the touched files (ruff, black, mypy against the baseline; eslint, tsc, vitest).
  3. Record follow-ups.
- **Verify**:
  - Targeted tests for every touched area pass inside Docker.
  - The item's ask is demonstrably met (verifier pass with evidence).

## T-012 — Package P07a_agents

- **Refs**: FR-P07, NFR-AUDIT-1, NFR-HITL-1, NFR-GATES-1, NFR-DOCKER-1, AC-1, AC-2, AC-3
- **Owner**: @agent:implementer
- **Status**: `[ ]`
- **Files**: per item; see the ids below and their BACKLOG entries.
- **Items**: BL-20260511-21, BL-20260511-31, BL-20260615-02, BL-20260811-28, BL-20260511-06, BL-20260615-03, BL-20260803-02, BL-20260810-18, BL-20260811-25, BL-20260811-27, BL-20260527-04, BL-20260803-04, BL-20260810-13, BL-20260830-15
- **Steps**:
  1. For each id in order: re-read the BACKLOG text and the code it names, implement the smallest complete change, add or extend tests.
  2. Run the scoped gates for the touched files (ruff, black, mypy against the baseline; eslint, tsc, vitest).
  3. Record follow-ups.
- **Verify**:
  - Targeted tests for every touched area pass inside Docker.
  - The item's ask is demonstrably met (verifier pass with evidence).

## T-013 — Package P07b_graph

- **Refs**: FR-P07, NFR-AUDIT-1, NFR-HITL-1, NFR-GATES-1, NFR-DOCKER-1, AC-1, AC-2, AC-3
- **Owner**: @agent:implementer
- **Status**: `[ ]`
- **Files**: per item; see the ids below and their BACKLOG entries.
- **Items**: BL-20260429-12, BL-20260526-01, BL-20260429-11, BL-20260429-22, BL-20260429-23, BL-20260509-02, BL-20260509-03, BL-20260810-17
- **Steps**:
  1. For each id in order: re-read the BACKLOG text and the code it names, implement the smallest complete change, add or extend tests.
  2. Run the scoped gates for the touched files (ruff, black, mypy against the baseline; eslint, tsc, vitest).
  3. Record follow-ups.
- **Verify**:
  - Targeted tests for every touched area pass inside Docker.
  - The item's ask is demonstrably met (verifier pass with evidence).

## T-014 — Package P07c_ingestion

- **Refs**: FR-P07, NFR-AUDIT-1, NFR-HITL-1, NFR-GATES-1, NFR-DOCKER-1, AC-1, AC-2, AC-3
- **Owner**: @agent:implementer
- **Status**: `[ ]`
- **Files**: per item; see the ids below and their BACKLOG entries.
- **Items**: BL-20260429-06, BL-20260503-10, BL-20260511-09, BL-20260602-01, BL-20260810-03, BL-20260429-03, BL-20260509-06, BL-20260511-07, BL-20260511-08, BL-20260602-07, BL-20260811-02, BL-20260811-03
- **Steps**:
  1. For each id in order: re-read the BACKLOG text and the code it names, implement the smallest complete change, add or extend tests.
  2. Run the scoped gates for the touched files (ruff, black, mypy against the baseline; eslint, tsc, vitest).
  3. Record follow-ups.
- **Verify**:
  - Targeted tests for every touched area pass inside Docker.
  - The item's ask is demonstrably met (verifier pass with evidence).

## T-015 — Package P07d_extraction

- **Refs**: FR-P07, NFR-AUDIT-1, NFR-HITL-1, NFR-GATES-1, NFR-DOCKER-1, AC-1, AC-2, AC-3
- **Owner**: @agent:implementer
- **Status**: `[ ]`
- **Files**: per item; see the ids below and their BACKLOG entries.
- **Items**: BL-20260803-01, BL-20260810-19, BL-20260509-07, BL-20260811-01, BL-20260509-05
- **Steps**:
  1. For each id in order: re-read the BACKLOG text and the code it names, implement the smallest complete change, add or extend tests.
  2. Run the scoped gates for the touched files (ruff, black, mypy against the baseline; eslint, tsc, vitest).
  3. Record follow-ups.
- **Verify**:
  - Targeted tests for every touched area pass inside Docker.
  - The item's ask is demonstrably met (verifier pass with evidence).

## T-016 — Package P08_accounts_core

- **Refs**: FR-P08, NFR-AUDIT-1, NFR-HITL-1, NFR-GATES-1, NFR-DOCKER-1, AC-1, AC-2, AC-3
- **Owner**: @agent:implementer
- **Status**: `[ ]`
- **Files**: per item; see the ids below and their BACKLOG entries.
- **Items**: BL-20260503-13, BL-20260429-25, BL-20260429-26, BL-20260811-06, BL-20260503-12, BL-20260430-12, BL-20260830-07, BL-20260503-23, BL-20260502-07, BL-20260811-07, BL-20260810-10
- **Steps**:
  1. For each id in order: re-read the BACKLOG text and the code it names, implement the smallest complete change, add or extend tests.
  2. Run the scoped gates for the touched files (ruff, black, mypy against the baseline; eslint, tsc, vitest).
  3. Record follow-ups.
- **Verify**:
  - Targeted tests for every touched area pass inside Docker.
  - The item's ask is demonstrably met (verifier pass with evidence).

## T-017 — Package P08w2_matters

- **Refs**: FR-P08, NFR-AUDIT-1, NFR-HITL-1, NFR-GATES-1, NFR-DOCKER-1, AC-1, AC-2, AC-3
- **Owner**: @agent:implementer
- **Status**: `[ ]`
- **Files**: per item; see the ids below and their BACKLOG entries.
- **Items**: BL-20260811-04, BL-20260503-05, BL-20260817-04, BL-20260817-05, BL-20260817-01, BL-20260817-02, BL-20260817-03, BL-20260830-08, BL-20260905-10
- **Steps**:
  1. For each id in order: re-read the BACKLOG text and the code it names, implement the smallest complete change, add or extend tests.
  2. Run the scoped gates for the touched files (ruff, black, mypy against the baseline; eslint, tsc, vitest).
  3. Record follow-ups.
- **Verify**:
  - Targeted tests for every touched area pass inside Docker.
  - The item's ask is demonstrably met (verifier pass with evidence).

## T-018 — Package P09a_autonomy

- **Refs**: FR-P09, NFR-AUDIT-1, NFR-HITL-1, NFR-GATES-1, NFR-DOCKER-1, AC-1, AC-2, AC-3
- **Owner**: @agent:implementer
- **Status**: `[ ]`
- **Files**: per item; see the ids below and their BACKLOG entries.
- **Items**: BL-20260511-11, BL-20260511-23, BL-20260511-05, BL-20260511-29, BL-20260511-03, BL-20260511-04, BL-20260511-19, BL-20260527-08, BL-20260511-14, BL-20260511-15, BL-20260526-02
- **Steps**:
  1. For each id in order: re-read the BACKLOG text and the code it names, implement the smallest complete change, add or extend tests.
  2. Run the scoped gates for the touched files (ruff, black, mypy against the baseline; eslint, tsc, vitest).
  3. Record follow-ups.
- **Verify**:
  - Targeted tests for every touched area pass inside Docker.
  - The item's ask is demonstrably met (verifier pass with evidence).

## T-019 — Package P09b_eval

- **Refs**: FR-P09, NFR-AUDIT-1, NFR-HITL-1, NFR-GATES-1, NFR-DOCKER-1, AC-1, AC-2, AC-3
- **Owner**: @agent:implementer
- **Status**: `[ ]`
- **Files**: per item; see the ids below and their BACKLOG entries.
- **Items**: BL-20260811-09, BL-20260811-10, BL-20260811-11, BL-20260811-12, BL-20260810-04
- **Steps**:
  1. For each id in order: re-read the BACKLOG text and the code it names, implement the smallest complete change, add or extend tests.
  2. Run the scoped gates for the touched files (ruff, black, mypy against the baseline; eslint, tsc, vitest).
  3. Record follow-ups.
- **Verify**:
  - Targeted tests for every touched area pass inside Docker.
  - The item's ask is demonstrably met (verifier pass with evidence).

## T-020 — Package P10a_infra

- **Refs**: FR-P10, NFR-AUDIT-1, NFR-HITL-1, NFR-GATES-1, NFR-DOCKER-1, AC-1, AC-2, AC-3
- **Owner**: @agent:implementer
- **Status**: `[ ]`
- **Files**: per item; see the ids below and their BACKLOG entries.
- **Items**: BL-20260502-08, BL-20260503-14, BL-20260503-25, BL-20260511-18, BL-20260511-26, BL-20260615-04, BL-20260811-17, BL-20260811-29, BL-20260815-01, BL-20260815-02, BL-20260815-04, BL-20260818-02, BL-20260818-03, BL-20260905-05, BL-20260702-11, BL-20260817-08
- **Steps**:
  1. For each id in order: re-read the BACKLOG text and the code it names, implement the smallest complete change, add or extend tests.
  2. Run the scoped gates for the touched files (ruff, black, mypy against the baseline; eslint, tsc, vitest).
  3. Record follow-ups.
- **Verify**:
  - Targeted tests for every touched area pass inside Docker.
  - The item's ask is demonstrably met (verifier pass with evidence).

## T-021 — Package P10b_local_ai

- **Refs**: FR-P10, NFR-AUDIT-1, NFR-HITL-1, NFR-GATES-1, NFR-DOCKER-1, AC-1, AC-2, AC-3
- **Owner**: @agent:implementer
- **Status**: `[ ]`
- **Files**: per item; see the ids below and their BACKLOG entries.
- **Items**: BL-20260502-01, BL-20260502-02, BL-20260502-06, BL-20260502-03
- **Steps**:
  1. For each id in order: re-read the BACKLOG text and the code it names, implement the smallest complete change, add or extend tests.
  2. Run the scoped gates for the touched files (ruff, black, mypy against the baseline; eslint, tsc, vitest).
  3. Record follow-ups.
- **Verify**:
  - Targeted tests for every touched area pass inside Docker.
  - The item's ask is demonstrably met (verifier pass with evidence).

## T-022 — Package P10c_docs

- **Refs**: FR-P10, NFR-AUDIT-1, NFR-HITL-1, NFR-GATES-1, NFR-DOCKER-1, AC-1, AC-2, AC-3
- **Owner**: @agent:implementer
- **Status**: `[ ]`
- **Files**: per item; see the ids below and their BACKLOG entries.
- **Items**: BL-20260602-02, BL-20260602-03, BL-20260702-12, BL-20260716-11, BL-20260811-19, BL-20260831-29, BL-20260904-07, BL-20260503-08, BL-20260803-05, BL-20260602-04, BL-20260904-03
- **Steps**:
  1. For each id in order: re-read the BACKLOG text and the code it names, implement the smallest complete change, add or extend tests.
  2. Run the scoped gates for the touched files (ruff, black, mypy against the baseline; eslint, tsc, vitest).
  3. Record follow-ups.
- **Verify**:
  - Targeted tests for every touched area pass inside Docker.
  - The item's ask is demonstrably met (verifier pass with evidence).

## T-023 — Package P11_frontend_other

- **Refs**: FR-P11, NFR-AUDIT-1, NFR-HITL-1, NFR-GATES-1, NFR-DOCKER-1, AC-1, AC-2, AC-3, AC-4
- **Owner**: @agent:implementer
- **Status**: `[ ]`
- **Files**: per item; see the ids below and their BACKLOG entries.
- **Items**: BL-20260527-07, BL-20260811-18, BL-20260830-01, BL-20260831-03, BL-20260831-07, BL-20260831-10, BL-20260511-17, BL-20260810-16, BL-20260831-12, BL-20260803-03
- **Steps**:
  1. For each id in order: re-read the BACKLOG text and the code it names, implement the smallest complete change, add or extend tests.
  2. Run the scoped gates for the touched files (ruff, black, mypy against the baseline; eslint, tsc, vitest).
  3. Record follow-ups.
- **Verify**:
  - Targeted tests for every touched area pass inside Docker.
  - The item's ask is demonstrably met (verifier pass with evidence).

## T-024 — Package P12_mypy

- **Refs**: FR-P12, NFR-AUDIT-1, NFR-HITL-1, NFR-GATES-1, NFR-DOCKER-1, AC-1, AC-2, AC-3
- **Owner**: @agent:implementer
- **Status**: `[ ]`
- **Files**: per item; see the ids below and their BACKLOG entries.
- **Items**: BL-20260429-04
- **Steps**:
  1. For each id in order: re-read the BACKLOG text and the code it names, implement the smallest complete change, add or extend tests.
  2. Run the scoped gates for the touched files (ruff, black, mypy against the baseline; eslint, tsc, vitest).
  3. Record follow-ups.
- **Verify**:
  - Targeted tests for every touched area pass inside Docker.
  - The item's ask is demonstrably met (verifier pass with evidence).

---

## Done-When (Definition of Done)

- All tasks `[x]`.
- All `AC-*` from `spec.md` covered by passing tests or recorded evidence.
- `make lint && make test` green; `make typecheck` reports no new mypy errors against the baseline.
- `make lint-specs` green.
- **`## Follow-ups Discovered` section below populated.**

---

## Follow-ups Discovered

> Append-only. Mirror each item into [BACKLOG.md](../../BACKLOG.md) with a `BL-YYYYMMDD-NN` id.

- _pending: populated as each package lands._
