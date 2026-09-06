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

- **BL-20260905-14** — *tech-debt, med* — lsat-static/components/solve/SolveAssist.tsx renders a "Show final step" button under `graded && hasLockedVisible`, but `isLocked(s)` is `s.spoiler && !graded` — so the moment `graded` is true nothing is locked and the button can never appear. It is unreachable dead code. The platform's equivalent is reachable because `locked` comes from the server payload and survives until a refetch. Either delete the branch (the static site unlocks the spoiler in place, which the shared contract now asserts) or make the static lock latch on first render so the affordance means something. _Surfaced in:_ specs/051-backlog-zero (while closing BL-20260831-22).
- **BL-20260905-15** — *test-gap, low* — lsat-static has no eslint config — `npx eslint` fails with "couldn't find an eslint.config.*" and `npm run lint` is an unconfigured `next lint` — so the CI lsat-static job effectively gates on `tsc --noEmit` and vitest only. Add a flat config mirroring frontend/'s and run it in the job. _Surfaced in:_ specs/051-backlog-zero (while closing BL-20260901-07).
- **BL-20260905-16** — *refactor, low* — The static site now has two persisted UI preferences (lsat-practice.header-pinned.v1 in app/page.tsx, plus the reading marks and drafts in lib/deviceState.ts) while the platform keeps its own in frontend/lib/settings/. Neither knows about the other, and lib/backup.ts deliberately excludes the pin because it is a preference rather than progress. Decide whether preferences belong in the export snapshot and whether the two products should share a preference key shape. _Surfaced in:_ specs/051-backlog-zero (while closing BL-20260901-05).
- **BL-20260905-17** — *feature, low* — lsat-static/components/Library.tsx now writes `#article-<id>` on every article change via history.replaceState, but the Concepts view leaves whatever fragment was last written in place until a permalink is clicked. Consider writing `#catalog-<id>` for the concept nearest the top of the viewport (IntersectionObserver) so the catalog's URL is as copyable as the reader's. _Surfaced in:_ specs/051-backlog-zero (while closing BL-20260905-04).
- **BL-20260905-18** — *tech-debt, med* — axe-core reports colour-contrast failures on all six app routes (7-13 nodes each, recorded in frontend/e2e/a11y-baseline.json) — `text-slate-500` and `text-[10px]/[11px]` on `bg-slate-950`/`bg-slate-900/40` do not clear WCAG AA. Raise the muted-text token (or restrict it to larger sizes) across frontend/components and frontend/ui, then re-record the baseline downwards; the ratchet in frontend/e2e/a11y.spec.ts will hold the gain. _Surfaced in:_ specs/051-backlog-zero (while closing BL-20260831-09).
- **BL-20260905-19** — *feature, low* — At 390px the lsat-static skip link measures 40.8px tall, under the 44px floor globals.css sets for `.btn`/`.nav-link`/`.choice`, and inline prose links and `button.linklike` are 16-20px. Decide whether the 44px contract extends to them and either pad the skip link in lsat-static/app/globals.css or state the exception, then widen the selector in lsat-static/e2e/responsive.spec.ts to match. _Surfaced in:_ specs/051-backlog-zero (while closing BL-20260901-03).
- **BL-20260905-20** — *tech-debt, low* — On a short lsat-static page the phone header can never reach the `hidden` state: condensing collapses `.brand`, the document shrinks, the browser clamps scrollY upward, and the direction handler in lsat-static/app/page.tsx reads that as a scroll back and restores the bar. Consider ignoring a scroll delta that coincides with a scrollHeight change so the header hides at the bottom of a short view too. _Surfaced in:_ specs/051-backlog-zero (while closing BL-20260901-03).
- **BL-20260905-21** — *tech-debt, med* — `openAgentStream` in frontend/lib/agentStream.ts abandons the socket after a 3000ms wait for `ready` and silently runs the analysis unstreamed. On a cold Channels layer or a loaded dev server that handshake loses the race, so live agent progress disappears with no signal to the user; the e2e spec has to pre-warm a socket to be deterministic. Raise the timeout, retry once, or surface the fallback in the UI. _Surfaced in:_ specs/051-backlog-zero (while closing BL-20260811-16).
- **BL-20260905-22** — *feature, low* — `{submitting && <LiveTrace …/>}` in frontend/components/AnalysisStudio.tsx unmounts the live agents panel the instant the REST response lands, so on the degraded path it is visible for a few hundred milliseconds. Keep the last run's step list on screen (or fold it into the AgentTrace card) so the streamed detail survives the run that produced it. _Surfaced in:_ specs/051-backlog-zero (while closing BL-20260811-16).
- **BL-20260905-23** — *infra, low* — The a11y tab-order specs take up to a minute on /agents because AgentDashboard polls every 5s (`POLL_MS`) and each Tab is a round-trip; frontend/e2e/*.spec.ts now cap `networkidle` at 5s to avoid hanging on it. A test-mode pause for the dashboard poll (an env flag or a `?poll=off` query the component honours) would cut several minutes off the nightly run. _Surfaced in:_ specs/051-backlog-zero (while closing BL-20260831-09).
- **BL-20260905-24** — *test-gap, low* — frontend/app/api/backend/[...path]/route.ts (the same-origin proxy) has no unit coverage: nothing asserts that it strips an inbound X-API-Key, attaches the server-side one, passes the upstream status and body through unchanged, or returns 502 when the backend is unreachable. The e2e spec covers the first two only when the stack is gated. _Surfaced in:_ specs/051-backlog-zero (while closing BL-20260430-11).
- **BL-20260905-25** — *doc-gap, med* — specs/008-agent-api-auth/spec.md FR-5/FR-6 and its tasks.md still describe `NEXT_PUBLIC_AGENT_API_KEY` being read in the browser and documented in .env.example; that variable no longer exists (apiFetch sends no credential, the proxy route attaches the key). Add a dated amendment note to spec 008 pointing at `frontend/app/api/backend/[...path]/route.ts`, `frontend/app/api/ws-ticket/route.ts` and `backend/law_ai/core/ws_ticket.py`. _Surfaced in:_ specs/051-backlog-zero (while closing BL-20260430-07).
- **BL-20260905-26** — *test-gap, med* — Nothing exercises the proxy end to end: `frontend/__tests__/lib/backendProxy.test.ts` calls the route handler with a stubbed fetch, and the vitest env pins `NEXT_PUBLIC_API_BASE_URL` back to the backend origin. Add a Playwright case (frontend/e2e/) that loads a screen with `NEXT_PUBLIC_API_BASE_URL=/api/backend` and asserts the browser only ever requests same-origin `/api/backend/...`, plus one that opens the agent stream with `AGENT_API_KEY` set and checks the socket carries a `ticket=` and no `api_key=`. _Surfaced in:_ specs/051-backlog-zero (while closing BL-20260430-07).
- **BL-20260905-27** — *feature, low* — `lsat-static/components/ShortcutHelp.tsx` documents hint keys (H reveal next hint, J/K move through hints, R reveal the final step) that the platform's `frontend/components/lsat/SolveAssist.tsx` does not bind, so `frontend/components/lsat/drillShortcuts.ts` deliberately omits them. Bind them in SolveAssist and add the rows, or record the divergence in docs/ui-ux.md § feature parity. _Surfaced in:_ specs/051-backlog-zero (while closing BL-20260901-10).
- **BL-20260905-28** — *tech-debt, low* — `docker-compose.yml` still passes `NEXT_PUBLIC_API_URL=http://localhost:8000` to the frontend service (and `docker-compose.debug.yml` repeats it); no code reads that name — `frontend/lib/api.ts` reads `NEXT_PUBLIC_API_BASE_URL`. Drop the dead variable so the compose env stops implying a second, ignored base URL. _Surfaced in:_ specs/051-backlog-zero (while closing BL-20260430-07).
- **BL-20260905-29** — *feature, low* — The settings cookie is mirrored whole. If the settings array ever grows past ~3.5KB encoded, `mirrorToCookie` in `frontend/lib/scope/store.ts` drops it and the layout silently reverts to reflow-on-load. Mirror only `LAYOUT_SETTINGS` keys (the ones the server render actually consults) so growth in feature settings cannot cost the first paint. _Surfaced in:_ specs/051-backlog-zero (while closing BL-20260905-09).
- **BL-20260905-30** — *refactor, low* — The Layout menu's 'Labelled rail (wide screens)' row stays enabled when `ui.rail.visible` is off, where it controls nothing visible. Either disable it with an explanation while the rail is hidden or nest it under the rail row in `frontend/components/shell/LayoutMenu.tsx`. _Surfaced in:_ specs/051-backlog-zero (while closing BL-20260831-06).
- **BL-20260905-31** — *refactor, med* — Phase 2 of the LSAT Lab decomposition: once specs/039-design-system ships frontend/ui/components/, swap the Tailwind class strings in frontend/components/lsat/{LrPanel,PassagePanel,QuestionCard,TutorPane,AuthoringPanel,StatsPanel,OverviewPanel,LabPrimitives}.tsx onto the 039 primitives (Button/Choice/Panel). Phase 1 (the behaviour-preserving split) is done; spec 039 is still Status: planned and frontend/ui/ has no components/ directory, so the 'onto frontend/ui primitives' half of BL-20260830-02 cannot land yet. _Surfaced in:_ specs/051-backlog-zero (while closing BL-20260830-02).
- **BL-20260905-32** — *feature, low* — Decide the LR pacing denominator as a product question. frontend/components/lsat/LrPanel.tsx currently publishes `bank size - questions graded this session` to the timer store, mirroring the static drill's `questions.length - answeredCount`; a real LSAT LR section is a fixed ~25 items, so a 200-item bank quotes an 8-second-per-question pace that means nothing. Consider a fixed section size or a 'drill of N' setting. _Surfaced in:_ specs/051-backlog-zero (while closing BL-20260829-01).
- **BL-20260905-33** — *feature, low* — `lsat.timer.duration` (frontend/lib/settings/catalog.ts) is in SETTING_CATALOG but deliberately not in LAYOUT_SETTINGS (frontend/lib/shell/layout.ts), so 'Reset layout' leaves a 5-minute homework clock set. Decide whether the drill length belongs in the layout reset group or needs its own reset affordance on the timer menu. _Surfaced in:_ specs/051-backlog-zero (while closing BL-20260829-02).
- **BL-20260905-34** — *tech-debt, low* — The static drill keeps per-question seconds twice: lsat-static/components/Drill.tsx's `answers` Map (for savedSeconds when paging back) and the shared store's `answeredSeconds` (for the avg readout). They can drift if a revisited question is regraded. Consider making the store the only accumulator, with the Map holding only the chosen letter. _Surfaced in:_ specs/051-backlog-zero (while closing BL-20260830-04).
- **BL-20260905-35** — *test-gap, low* — frontend/mocks/server.ts still has no default POST /api/lsat/tutor handler; every suite that reaches the tutor has to install its own via server.use. Adding one (used_llm true, a named model) would give the other suites a stable mock. Skipped this pass because mocks/server.ts is under concurrent edit. _Surfaced in:_ specs/051-backlog-zero (while closing BL-20260503-07).
- **BL-20260905-36** — *infra, med* — tests/test_lsat_site.py::TestContentDrift fails on main-in-progress (test_question_ids_match_bank, test_counts_match, test_passages_fully_synced): backend/law_ai/lsat/services/data/{lr,rc,lg}_bank.json and passages.json changed without a matching `make lsat-export` re-generation of lsat-static/content.json. Not caused by this package; the export needs re-running before the branch merges. _Surfaced in:_ specs/051-backlog-zero (while closing BL-20260830-04).
- **BL-20260905-37** — *tech-debt, high* — `backend/law_ai/lsat/urls.py` calls `audit_store.record("lsat_intake_ocr", {...})` with two arguments, but `law_ai.core.audit_jsonl.record` takes a single event dict — the TypeError is swallowed by the surrounding `except Exception`, so the OCR-intake audit event is never written and the only trace is a warning log. It is also the source of the two new `arg-type`/`call-arg` errors in the mypy baseline for that file. Fold the type into the dict (`{"type": "lsat_intake_ocr", ...}`) like every other call site, and add a test asserting the event lands in the store. _Surfaced in:_ specs/051-backlog-zero (while closing BL-20260905-01).
- **BL-20260905-38** — *refactor, med* — `StatsView` now walks `audit_store.tail(10_000)` three separate times per request (`_fold_reading`, `_fold_hints`, `_fold_writing`) on top of the grade pass — four full reads of the JSONL for one response. Take the tail once in `_fold_extras` (or in the view) and pass the event list down; the folds are already pure functions of it. _Surfaced in:_ specs/051-backlog-zero (while closing BL-20260831-27).
- **BL-20260905-39** — *tech-debt, med* — Library read state is reconstructed from `audit_store.tail(10_000)` in `_read_article_ids`, so once a deployment's audit log rotates past the read events an article silently un-marks itself server-side — the client's localStorage union hides it locally but a fresh browser would see less progress than the learner has. Either project read state into a small table (mirroring what `LsatAttempt` did for grades) or snapshot the derived set periodically. _Surfaced in:_ specs/051-backlog-zero (while closing BL-20260903-05).
- **BL-20260905-40** — *feature, med* — The `?concept=` deep link only reaches LR: `LsatLab` sends the concept to `LrPanel` and hard-defaults the tab to `LR`, so a link for an RC- or LG-only concept opens a section that has no questions for it and shows the empty state. `PassagePanel` could filter its question stack by concept (the questions already carry `concepts`), and the tab default could follow the concept's own `sections` from `/api/lsat/concepts/<id>`. _Surfaced in:_ specs/051-backlog-zero (while closing BL-20260905-01).
- **BL-20260905-41** — *feature, low* — The static site's two-stage Escape in the writing editor is only half-ported: on the platform Escape blurs the textarea (handled on the element, since `lib/lsat/keyboard.ts` refuses shell-reserved keys) but a second press does not return to the prompt list the way `lsat-static/components/Writing.tsx` does — the '← All prompts' button is the only route out. Decide whether the shell's Escape should chain to a page-registered handler, or record the divergence in the `?` sheet copy. _Surfaced in:_ specs/051-backlog-zero (while closing BL-20260901-06).
- **BL-20260905-42** — *feature, low* — `LsatLab.refreshStats` runs only from `onAttempt` (a graded MCQ), so submitting a writing evaluation from the WS tab leaves the Stats tab's new WritingProgress card stale until the next graded question. Give `WritingPanel` an `onEvaluated` callback that the lab wires to `refreshStats`, the way the drill panels wire `onAttempt`. _Surfaced in:_ specs/051-backlog-zero (while closing BL-20260831-27).
- **BL-20260905-43** — *test-gap, low* — `GET /api/lsat/factory/status` is covered only against an empty/near-empty factory output dir: `latest_manifest_summary` is exercised through its None branch and the frontend fixture, never against a real manifest on disk. Add a case to `backend/tests/lsat/test_factory_status_api.py` that plans a manifest into a tmp output dir (the pattern in `test_factory_pipeline.py`) and asserts `manifest_id`, `jobs` and `by_tier` come back from it. _Surfaced in:_ specs/051-backlog-zero (while closing BL-20260702-06).
- **BL-20260905-44** — *feature, med* — Human editorial pass over the 100 `LSATContentFactory build100` bank items (58 LR, 28 RC, 14 LG): each currently carries `review.method: "machine-judge"` in backend/law_ai/lsat/services/data/{lr,rc,lg}_bank.json. A reviewer who reads an item should flip its record to `editorial` with their own name; backend/tests/lsat/test_bank_review.py already enforces that machine review is never labelled editorial. _Surfaced in:_ specs/051-backlog-zero (while closing BL-20260429-19).
- **BL-20260905-45** — *feature, low* — Surface the factory judge verdict and the linked guide draft in the HITL queue UI: `meta.factory.judge` (verdict, issues, key_agrees) and `meta.guide_for_proposal` are written by backend/law_ai/lsat/factory/{judge,guides}.py but nothing in frontend/components/lsat/ or the /api/lsat/proposals payload renders them, so reviewers cannot see the objection or the paired guide. _Surfaced in:_ specs/051-backlog-zero (while closing BL-20260702-02).
- **BL-20260905-46** — *feature, low* — Promote a factory-drafted writing prompt from the UI/API: backend/law_ai/lsat/services/proposals.py now has `promote_writing_prompt`, but backend/law_ai/lsat/urls.py has no approve route for `proposal_kind="writing_prompt"`, so a queued writing draft can only be promoted from a shell. _Surfaced in:_ specs/051-backlog-zero (while closing BL-20260831-28).
- **BL-20260905-47** — *test-gap, low* — backend/tests/lsat/test_factory_ollama_integration.py has never executed its assertions: the Docker ollama here cannot load mistral:7b (4.9 GiB needed). Run `make test-integration-ollama` on a box with enough RAM, or point OLLAMA_INTEGRATION_URL at one, and confirm the llm_call/agent_call assertions hold against a real generation. _Surfaced in:_ specs/051-backlog-zero (while closing BL-20260702-05).
- **BL-20260905-48** — *tech-debt, low* — backend/law_ai/lsat/services/proposals.py:promote_to_bank writes the bank files with `json.dumps(..., indent=4)` while the checked-in banks use 2-space indent, so the first production promotion reformats the whole file. Align it with the on-disk convention. _Surfaced in:_ specs/051-backlog-zero (while closing BL-20260429-19).
- **BL-20260905-49** — *feature, low* — Extend the nightly `_run_lsat_factory` autonomy runner in backend/law_ai/core/management/commands/run_autonomy.py with the judge and cross-check steps (spec 047 T-062): the judge tier now exists (backend/law_ai/lsat/factory/judge.py) but the beat runs with `judge_enabled` off, so nightly drafts reach the queue unjudged. _Surfaced in:_ specs/051-backlog-zero (while closing BL-20260702-04).
- **BL-20260905-50** — *feature, med* — The synthesis engine still declares only easy/med/hard: `backend/law_ai/lsat/synth/schemas.py` has no `intro` schema variant, so the low band can only be grown by hand. Add one-step conditional and single-rule LG variants that emit `intro`, so `make lsat-synth-generate` can keep the intro band above the floor that `backend/tests/lsat/test_bank_bands.py` now enforces. Elite stays hand-authored until measured difficulty lands (BL-20260903-14). _Surfaced in:_ specs/051-backlog-zero (while closing BL-20260901-01).
- **BL-20260905-51** — *tech-debt, med* — The 43 items this package added carry no `review` record now that `QuestionReview` exists in `backend/law_ai/lsat/services/bank.py`: their editorial gate was PR review, which the model has no method for (`editorial` means a person read it in the HITL queue). Decide how a hand-authored, PR-reviewed bank item records its provenance — a `method` value, or a documented convention that `review: null` means "reviewed in the PR that added it" — before a test starts requiring the field. _Surfaced in:_ specs/051-backlog-zero (while closing BL-20260503-02).
- **BL-20260905-52** — *test-gap, med* — Library search is still two hand-mirrored implementations (`backend/law_ai/lsat/services/library.py` and `lsat-static/lib/search.ts`), now with a stemmer, a synonym table, a typo predicate and five scoring helpers each. `backend/tests/lsat/fixtures/search_parity.json` pins behaviour but not code: consider generating the TypeScript mirror from a shared rule spec, or extending the fixture with per-field score vectors so a scoring divergence (not just a ranking one) fails a suite. _Surfaced in:_ specs/051-backlog-zero (while closing BL-20260903-06).
- **BL-20260905-53** — *feature, low* — `pick_librarian_targets` in `backend/law_ai/lsat/services/library.py` drops a coverage gap when no article serves that section, because `expand` drafts a body and cannot write the frontmatter that gives an article its id, level and review status. Add a "new article" path — a frontmatter scaffold the librarian fills, or a `lsat_library scaffold <id>` subcommand — so an entirely uncovered section is reachable by the autonomous cycle rather than only by a human. _Surfaced in:_ specs/051-backlog-zero (while closing BL-20260903-08).
- **BL-20260905-54** — *feature, low* — Bank items still carry no `archetype` field, so `select_exemplars` in `backend/law_ai/lsat/factory/blueprints.py` infers the archetype from concept overlap and now ranks by the archetype's primary concept. Stamping items with the archetype they instantiate (at authoring time, and backfilled for the 208 existing items) would make exemplar selection exact and let the coverage census report archetype counts directly instead of via a proxy concept. _Surfaced in:_ specs/051-backlog-zero (while closing BL-20260901-02).
- **BL-20260905-55** — *doc-gap, low* — Solve-guide operations are documented in `docs/lsat-library.md` under "The neighbouring loop", which is the wrong home — the library doc is about prose articles and explicitly distinguishes them from guides. Once the backfill run is complete, split the guide runbook (backfill, review, judge tier, `guides.json` promotion) into its own `docs/lsat-solve-guides.md` and leave a cross-reference behind. _Surfaced in:_ specs/051-backlog-zero (while closing BL-20260831-23).
- **BL-20260905-56** — *feature, med* — Surface passage promotion in the Authoring queue: a proposal whose meta.factory.pending_passage_path is set needs a 'Promote passage' button calling POST /api/lsat/proposals/passages/approve (frontend/components/lsat/AuthoringPanel.tsx + a promoteLsatPassage client in frontend/lib/api.ts). Today the endpoint exists but a reviewer can only reach it with curl, and approving the drafts first now returns 409. _Surfaced in:_ specs/051-backlog-zero (while closing BL-20260702-07).
- **BL-20260905-57** — *tech-debt, med* — proposals._tail() still keeps only the last 5000 events (backend/law_ai/lsat/services/proposals.py), so once the log passes that a proposal's create event drops out of the replay and the row vanishes from the JSONL path. Now that LsatProposal mirrors current state, make the reader rotation-proof: either read from the mirror unconditionally for rows the tail no longer covers, or rotate proposals.jsonl into dated files and replay across them. _Surfaced in:_ specs/051-backlog-zero (while closing BL-20260527-05).
- **BL-20260905-58** — *feature, low* — lsat_cross_check_sweep is manual only. Consider an autonomy kind (backend/law_ai/core/management/commands/run_autonomy.py) or a nightly job that runs it with a small --limit per section, so cross-check coverage grows on a schedule instead of when someone remembers; it bills provider calls, so it needs its own budget knob. _Surfaced in:_ specs/051-backlog-zero (while closing BL-20260831-21).
- **BL-20260905-59** — *test-gap, low* — regression_report() reads the JSONL tail plus the newest AuditEvent rows but nothing prunes or windows by date, so a long-lived bank will compare a verdict from months ago against today's. Add a --since/window parameter (backend/law_ai/lsat/services/regression.py) and a test that an old first verdict ages out of the flip comparison. _Surfaced in:_ specs/051-backlog-zero (while closing BL-20260527-06).
- **BL-20260905-60** — *refactor, low* — answer_key_skew now lives in backend/law_ai/agents_runtime/crews/lsat_content_author.py because both the factory intake and the agent need it, which makes law_ai.lsat.factory.intake import from an agents_runtime crew. If more LSAT-wide quality checks appear, move the family into a law_ai/lsat/services/quality.py that both sides import instead. _Surfaced in:_ specs/051-backlog-zero (while closing BL-20260606-02).
- **BL-20260905-61** — *feature, med* — Under a shuffled serve the AI tutor (backend/law_ai/lsat/services/tutor.py) and cross-check still reason and answer in the bank's stored labels, so the tutor can name a choice letter the learner is not looking at. Remapping its output is unsafe because it reasons about the choices; the prompt should receive the displayed board (and the guide's canonical labels alongside it). _Surfaced in:_ specs/051-backlog-zero (while closing BL-20260606-01).
- **BL-20260905-62** — *feature, med* — Two more LG archetypes are provable but unbuilt: lg-max-min needs bounded-count statements (at-most/at-least over a group) in backend/law_ai/lsat/synth/logic.py, and lg-rule-substitution needs a new verification family in synth/verify.py whose rule is 'the substitute leaves the valid-arrangement set unchanged in both directions'. Both would take archetype coverage from 17 to 19 of 45. _Surfaced in:_ specs/051-backlog-zero (while closing BL-20260903-13).
- **BL-20260905-63** — *feature, low* — lr-parallel-reasoning and lr-parallel-flaw are decidable by shape-matching over schemas._shape() but need whole mini-arguments as answer choices, i.e. a structural guarantee like CausalSchema rather than a model-theoretic proof. Adding them needs authored argument pools in the domain packs (lexicon.py) the way causal_scenarios already are. _Surfaced in:_ specs/051-backlog-zero (while closing BL-20260903-13).
- **BL-20260905-64** — *tech-debt, low* — difficulty.SCORE_CUTS (14.7 / 16.0) were derived from the 200-item sweep of the pre-expansion registry; the six schemas added since (four-term chain, the four LG families, supported-inference) moved the score distribution. Re-run `make lsat-synth-calibrate ARGS='--structural'` and update the constant deliberately — existing items re-band when it changes. _Surfaced in:_ specs/051-backlog-zero (while closing BL-20260903-14).
- **BL-20260905-65** — *test-gap, low* — The polish prompt's real yield is now measurable but has never been measured: backend/tests/lsat/test_synth_polish_live.py stays skipped without LSAT_SYNTH_LIVE_POLISH=1, and no polish_yield.json exists. Someone should run `make lsat-synth-polish-yield` once against a pinned tier (LLM_PROVIDER_CHAIN=ollama for a free run) and record the number and its tier. _Surfaced in:_ specs/051-backlog-zero (while closing BL-20260903-17).
- **BL-20260905-66** — *tech-debt, low* — Structural-proof schemas get no difficulty proxy at all (measure() returns None), so lr-causal-weaken and lr-percent-vs-number are indistinguishable to the census and keep whatever band their author declared. A structural-only proxy — attack-pool depth, inert-fact similarity, stimulus length — would put them on some scale rather than none. _Surfaced in:_ specs/051-backlog-zero (while closing BL-20260903-14).
- **BL-20260905-67** — *tech-debt, low* — Bank explanations and spec 045 guide steps in backend/law_ai/lsat/services/data/*.json are still authored with bare answer labels ('A is correct: …'), so shuffling depends on a regex rewrite. Migrating them to {{A}}-style placeholders plus a validation.py rule rejecting bare labels in new content would make the remap a substitution instead. _Surfaced in:_ specs/051-backlog-zero (while closing BL-20260606-01).
- **BL-20260905-68** — *tech-debt, low* — Retire BL-20260615-01 as obsolete: it asks to rename LSAT_LLM_PROVIDER to DEV_LLM_PROVIDER as a dev-time gate, but the premise was repealed by spec 034 and the setting itself was deleted by BL-20260811-22 (backend/law_ai/settings/base.py, backend/law_ai/core/claude_code.py). Nothing in the tree reads it any more. _Surfaced in:_ specs/051-backlog-zero (while closing BL-20260811-22).
- **BL-20260905-69** — *feature, med* — Token counts and cost_usd now land on every llm_call AuditEvent, but nothing reads them back: there is no per-agent or per-tier spend rollup anywhere (no endpoint, no management command, no panel). Add a `make llm-spend`-style command or an /api/health-adjacent rollup over AuditEvent payloads in backend/law_ai/audit/, otherwise the accounting from BL-20260811-21 is write-only. _Surfaced in:_ specs/051-backlog-zero (while closing BL-20260811-21).
- **BL-20260905-70** — *infra, low* — LLM_PRICE_TABLE ships empty (backend/law_ai/settings/base.py), so cost_usd is null out of the box and every deployment must hand-enter vendor prices. Ship a documented starter table for the current Claude and Grok ids in .env.example (commented, dated) or a `scripts/` helper that prints one, so the default experience is priced rather than silent. _Surfaced in:_ specs/051-backlog-zero (while closing BL-20260811-21).
- **BL-20260905-71** — *infra, med* — The permanent-failure memory added in BL-20260811-23 (_permanent_failures in backend/law_ai/core/llm/router.py) is per-process, so a misconfigured key is still re-hit once per daphne/Celery worker per TTL window. Share it through the Django cache the way BL-20260810-15 shares the Ollama probe verdict in backend/law_ai/agents_runtime/llm.py — same L1/L2 shape, same fail-open wrapping. _Surfaced in:_ specs/051-backlog-zero (while closing BL-20260811-23).
- **BL-20260905-72** — *feature, low* — XAI_INTERACTIVE_MODEL ships blank because choosing a faster Grok id needs a live SuperGrok subscription the suite may never touch (spec 050 AC-5). Someone with `make xai-login` should run `make validate-xai` (which now lists the served ids) plus a timed IRAC through the xai tier, pick a candidate, and record the measured latency and any IRAC-quality regression in docs/adr/0007-xai-runtime-provider.md before setting a default. _Surfaced in:_ specs/051-backlog-zero (while closing BL-20260905-11).
- **BL-20260905-73** — *test-gap, low* — backend/tests/core/test_privileged_data_guarantee.py drives POST /api/lsat/tutor and POST /api/analysis through the real ASGI app, so it fails whenever any module reachable from backend/law_ai/urls.py is mid-edit (it did, transiently, while law_ai/core/urls_auth.py was landing). Consider a thinner service-level variant of those two cases so the guarantee has a check that cannot be broken by an unrelated urlconf import. _Surfaced in:_ specs/051-backlog-zero (while closing BL-20260811-24).
- **BL-20260905-74** — *feature, med* — LangGraph nodes still cannot stream: `ChatProviderChain._astream` exists but `LegalWorkflow` calls `ainvoke`, so `/api/analysis` emits one `agent_step` per finished agent and no tokens. Thread `astream` through the `analyze`/`cite_check` nodes in backend/law_ai/agents_runtime/graphs/legal_workflow.py and forward the deltas as `token` events from backend/law_ai/analysis/urls.py, keeping `agent_step`/`complete` unchanged; the JSON-parsing nodes will need the same prose-vs-JSON contract split the LSAT tutor now uses. _Surfaced in:_ specs/051-backlog-zero (while closing BL-20260811-20).
- **BL-20260905-75** — *tech-debt, low* — backend/law_ai/agentsapi/replay.py builds and closes a redis.asyncio client per recorded event (`_client()` in `record`/`events_since`), so a streamed run pays one connect/disconnect per delta. Hold a module-level client or connection pool, keeping the per-call failure fallback to the in-process buffer. _Surfaced in:_ specs/051-backlog-zero (while closing BL-20260811-14).
- **BL-20260905-76** — *feature, low* — `METRICS_CHANGED` is defined in backend/law_ai/agentsapi/streaming.py but never emitted — only `runs_changed` fires, from `provenance.log_agent_call`. Emit it from the metrics/health writers (or drop the constant) so the dashboard can invalidate its metrics card independently of its run list. _Surfaced in:_ specs/051-backlog-zero (while closing BL-20260429-16).
- **BL-20260905-77** — *feature, low* — `TutorTrace.eliminated` is accepted and used by the prompt, the offline fallback and the cache key, but no LSAT surface lets a learner mark a choice as eliminated, so it is always empty in practice. Add elimination toggles to frontend/components/lsat/QuestionCard.tsx (and the `lsat-static` twin) and feed them into the trace `QuestionCard.attemptTrace` builds. _Surfaced in:_ specs/051-backlog-zero (while closing BL-20260429-18).
- **BL-20260905-78** — *test-gap, med* — backend/tests/api/test_analysis.py::test_default_engine_path_never_500s_when_engine_explodes asserts `confidence == 0.0`, which only holds while Neo4j is empty: the shared dev graph now has rows, PrecedentHunter returns a real precedent, and the mean becomes 0.16. Isolate the graph for that test (stub PrecedentHunter or clear/seed the fixture) so it stops depending on whatever else has touched the container. _Surfaced in:_ specs/051-backlog-zero (while closing BL-20260811-15).
- **BL-20260905-79** — *feature, low* — TutorPane renders streamed coaching but never surfaces a dropped stream to the learner: `openAgentStream`'s reconnect is silent and the `interrupted` step only clears the text. Expose the reconnect/interrupted state through frontend/lib/agentStream.ts and show "reconnecting…" in frontend/components/lsat/TutorPane.tsx and frontend/components/AnalysisStudio.tsx. _Surfaced in:_ specs/051-backlog-zero (while closing BL-20260503-03).
- **BL-20260905-80** — *feature, low* — Add a `response_schema: dict | None` field to `ChatProviderChain` (backend/law_ai/core/llm/langchain.py) and pass it through `_agenerate`/`_generate` to `router.agenerate`, so the LangChain adapter and `core.llm.agenerate` stay feature-equivalent; add one case to backend/tests/core/test_llm_langchain.py. Deferred here because that file is owned by another work package and was being edited concurrently. _Surfaced in:_ specs/051-backlog-zero (while closing BL-20260811-28).
- **BL-20260905-81** — *feature, med* — Define and enforce resume semantics for `/api/analysis` `thread_id`: resuming a thread with a different question/jurisdiction currently overwrites the persisted channels silently. Either reject with 409 when `AnalysisRequest.text`/`jurisdiction` differ from the checkpointed `question`/`jurisdiction` (readable via `LegalWorkflow.get_state`), or branch into a new thread and say so in the response. Files: backend/law_ai/analysis/urls.py, backend/law_ai/agents_runtime/crews/legal_analyst.py. _Surfaced in:_ specs/051-backlog-zero (while closing BL-20260810-13).
- **BL-20260905-82** — *test-gap, low* — Extend backend/tests/agents/graphs/test_legal_workflow_postgres.py (LANGGRAPH_INTEGRATION opt-in) to assert the checkpoint tables actually land in the `langgraph` schema — `SELECT table_name FROM information_schema.tables WHERE table_schema='langgraph'` after `ensure_schema()`. The unit tests prove the conn string carries `options=-csearch_path%3Dlanggraph` but nothing proves Postgres honours it end to end. _Surfaced in:_ specs/051-backlog-zero (while closing BL-20260811-25).
- **BL-20260905-83** — *feature, low* — Sort pre-flagged LSAT question proposals to the top of the pending queue in frontend/components/lsat/AuthoringPanel.tsx (or add a 'flagged only' filter). `meta.review.flagged` is rendered as a badge and an amber card border today, but a reviewer with fifty rows still scrolls to find them. Left to the LsatLab owner since it is a list-layout decision. _Surfaced in:_ specs/051-backlog-zero (while closing BL-20260527-04).
- **BL-20260905-84** — *feature, low* — Surface `WorkflowCitation.attribution` (court / jurisdiction / decided_at / binding-persuasive) in frontend/components/AnalysisStudio.tsx next to each citation's verified badge, and in the Precedent list. The backend and the `Attribution` TS type now carry it end to end but no UI renders it, so a reviewer cannot see binding-vs-persuasive without reading the JSON. _Surfaced in:_ specs/051-backlog-zero (while closing BL-20260803-04).
- **BL-20260905-85** — *test-gap, med* — Add a legalbench-marked LLM-judged test for the prose half of the §13 attribution rule: the deterministic gate in backend/law_ai/agents_runtime/attribution.py is per-citation, so an answer paragraph that states law without naming an authority still passes. Judge `IRACOutput.application` for unattributed statements of law against the citation set. _Surfaced in:_ specs/051-backlog-zero (while closing BL-20260803-04).
- **BL-20260905-86** — *tech-debt, low* — `law_ai.core.provenance.logged_node` binds `model` at decoration time, so LegalWorkflow's node events can only say `(provider chain)`; the tier that actually served the call is recorded separately in `state['model_label']` and on the OTel span. Let `logged_node` read a `model_label` key off the node's returned dict (falling back to the static label) so the per-node audit rows name the real provider too. _Surfaced in:_ specs/051-backlog-zero (while closing BL-20260615-02).
- **BL-20260905-87** — *tech-debt, med* — `backend/law_ai/core/neo4j/migrations/006_derived_document.cypher` declares two property-existence constraints (`derived_document_agent_version_exists`, `derived_document_kind_exists`) that are Enterprise-only and are rejected by the pinned `neo4j:5-community` image in docker-compose.yml. `migrate_neo4j` now defers the file instead of failing, but the constraints are simply absent in every dev/CI environment, so nothing actually enforces the `DerivedDocument` provenance invariant the spec-015 tests assert on paper. _Surfaced in:_ specs/051-backlog-zero (while closing BL-20260509-02).
- **BL-20260905-88** — *test-gap, low* — `backend/law_ai/core/management/commands/densify_backfill.py` and `backfill_embeddings.py` are unit-tested against fake sessions only. Add `@pytest.mark.integration` tests under `backend/tests/db/` that seed a real `(:Case)-[:HAS_CITATION]->(:Citation)` pair with a resolvable alias (and a vector-less `:Case`) and assert the `CITES` edge / `embedding` property actually lands, plus that a second `--commit` run is a no-op. _Surfaced in:_ specs/051-backlog-zero (while closing BL-20260429-11).
- **BL-20260905-89** — *feature, low* — `backend/law_ai/core/neo4j/graph_queries.py::list_cases` filters `court` by case-insensitive substring because court values are free-form strings. Add a `/api/graph/courts` endpoint returning the distinct `Case.court` values (with counts) so `frontend/components/KnowledgeGraph.tsx` can populate its court `<select>` from the whole corpus rather than only from the 25 cases currently loaded. _Surfaced in:_ specs/051-backlog-zero (while closing BL-20260429-23).
- **BL-20260905-90** — *feature, low* — `GraphRAGRetriever._vector_cases` in `backend/law_ai/agents_runtime/tools/graph_rag.py` covers `:Case` only; `statute_section_embedding_vec` is created by 008 and filled by `backfill_embeddings` but never queried, so statute retrieval is still lexical-only. Add a `_vector_statutes` leg and fuse it with `_lexical_statutes` the same way. _Surfaced in:_ specs/051-backlog-zero (while closing BL-20260810-17).
- **BL-20260905-91** — *infra, low* — `commit_extraction` (backend/law_ai/core/neo4j/queries.py) now makes one synchronous-in-the-await-sense embedding call per case at ingest. On a large `make ingest` run that serialises N HTTP round-trips to Ollama. Batch the embeddings per `ExtractionResult` batch via `embed_texts`, or move the embedding write to a Celery follow-up task that reuses `backfill_embeddings`. _Surfaced in:_ specs/051-backlog-zero (while closing BL-20260810-17).
- **BL-20260905-92** — *doc-gap, low* — `docs/local-ai.md` does not mention that `nomic-embed-text` is now load-bearing for retrieval quality (not just LSAT intake dedup) and that `make backfill-embeddings COMMIT=1` must be run after `make migrate` on an existing corpus. Add a short section pointing at `core/llm/embeddings.py` and the new make target. _Surfaced in:_ specs/051-backlog-zero (while closing BL-20260810-17).
- **BL-20260905-93** — *infra, med* — The backend image needs a rebuild before the two new optional dependencies work at runtime: `pypdf` (declared in backend/pyproject.toml for the CRS PDF fallback in law_ai/ingestionapp/services/colorado_statutes.py) and the `nlp` extra's `en_core_web_sm` wheel (for law_ai/ingestionapp/services/ner.py). Until then `test_real_pypdf_extraction_finds_sections` in backend/tests/ingestion/test_colorado_statutes_pdf.py stays skipped and ENABLE_NER=true degrades to no entities. _Surfaced in:_ specs/051-backlog-zero (while closing BL-20260509-06).
- **BL-20260905-94** — *test-gap, med* — backend/tests/agents/graphs/test_topic_frontier_integration.py seeds Neo4j through the module-level `get_neo4j_driver()` singleton and fails with 'Future attached to a different loop' whenever it runs in the same process after a test that bound the singleton to another loop (reproducible with `pytest tests/ingestion/ ... tests/agents/graphs/test_topic_frontier_integration.py -m ""`; it passes alone and under `make test-integration`). Adopt the per-test driver pattern now used in backend/tests/ingestion/test_force_quarantine_integration.py. _Surfaced in:_ specs/051-backlog-zero (while closing BL-20260602-01).
- **BL-20260905-95** — *feature, low* — Ordinance quarantine rows (kind=ordinance_section) still have no commit path: `_commit_by_kind` in backend/law_ai/ingestionapp/services/approval.py records an audited 'unsupported quarantine kind' commit_error. Once an ordinance scout exists, extend the dispatch and mirror StatuteScout.commit_section's rehydrate-from-envelope shape. _Surfaced in:_ specs/051-backlog-zero (while closing BL-20260811-03).
- **BL-20260905-96** — *feature, low* — `approval.reextract_review` (backend/law_ai/ingestionapp/services/approval.py) supports kind=case only; a statute row raises ApprovalError. Statute re-extraction would need a StatuteScout entry point that re-scores a stored section payload rather than re-parsing title HTML. _Surfaced in:_ specs/051-backlog-zero (while closing BL-20260503-10).
- **BL-20260905-97** — *tech-debt, low* — Each Django admin action adds a `[untyped-decorator]` mypy error because django-stubs is not installed (backend/law_ai/ingestionapp/admin.py now has three, one per action; two were already in the baseline). Installing django-stubs would clear a recurring class of baseline errors across the admin and management-command modules. _Surfaced in:_ specs/051-backlog-zero (while closing BL-20260503-10).
- **BL-20260905-98** — *feature, low* — PDF-derived CRS sections are penalised into the HITL queue by design (PDF_CONFIDENCE_PENALTY in backend/law_ai/ingestionapp/services/colorado_statutes.py), so a large PDF import floods the review queue. A column-aware extractor (or a per-title bulk-approve verb in manage.py review_queue) would make the fallback usable at volume. _Surfaced in:_ specs/051-backlog-zero (while closing BL-20260509-06).
- **BL-20260905-99** — *tech-debt, med* — Backfill `:Case.holding_summary` on nodes ingested before BL-20260810-19. The extractor now writes a deterministic excerpt and `MERGE_CASE_CYPHER` persists it, but existing nodes still render "(no holding summary stored)" in every GraphRAG passage. `:Case` does not store opinion text, so the backfill must either re-fetch from the source or accept a title-only summary; a `manage.py backfill_holding_summaries` alongside `densify_backfill` and `resolve_statute_citations` is the natural home. _Surfaced in:_ specs/051-backlog-zero (while closing BL-20260810-19).
- **BL-20260906-01** — *feature, low* — Add the optional audited LLM holding-summary pass reserved by `ExtractionResult.holding_summary_kind == 'summary'`. It needs `IngestionScout.extract` to gain an async variant (it is sync today, which is why the excerpt shipped alone), gated behind an `INGEST_LLM_SUMMARY` setting and routed through `law_ai.core.llm` so the `llm_call` provenance event is written. _Surfaced in:_ specs/051-backlog-zero (while closing BL-20260810-19).
- **BL-20260906-02** — *feature, med* — Widen `citation_resolver.statute_section_id_from_normalized` beyond the Colorado Revised Statutes. It recognises only CRS reporters today because CRS is the only statutory corpus in the graph; the moment a second corpus lands (U.S.C., Denver's DRMC via BL-20260509-05) the mapper needs a per-corpus reporter table rather than a hard-coded CRS tuple, and `queries.LIST_CASES_WITH_STATUTE_CITATIONS_CYPHER` needs its reporter list to follow. _Surfaced in:_ specs/051-backlog-zero (while closing BL-20260509-07).
- **BL-20260906-03** — *feature, low* — The `(:Case)-[:INTERPRETS]->(:StatuteSection)` edge remains declared-only in docs/data-model.md. Deciding that an opinion *construes* a section rather than merely citing it is a judgement the rule-based extractor cannot make, so it needs either an audited LLM pass or a signal-based heuristic (pin-cite depth, quotation of the section text). _Surfaced in:_ specs/051-backlog-zero (while closing BL-20260509-07).
- **BL-20260906-04** — *feature, med* — The review queue has no re-extract button. `approval.reextract_review` (BL-20260503-10) is the third review verb and is exposed in Django admin and `manage.py review_queue`, but `backend/law_ai/ingestionapp/urls.py` only ships approve/reject, so a web reviewer cannot ask "would today's extractor still quarantine this?". Add a POST reviews/re-extract route and a button in `frontend/components/ReviewQueue.tsx`. _Surfaced in:_ specs/051-backlog-zero (while closing BL-20260811-01).
- **BL-20260906-05** — *test-gap, low* — No E2E coverage for `/agents/reviews`. The approve->commit path is covered by RTL against MSW and by Django test-client tests, but nothing exercises the real page against the real API. A Playwright spec under `frontend/e2e/` (owned by P02) would catch a proxy-route or nav-registration break that both existing layers miss. _Surfaced in:_ specs/051-backlog-zero (while closing BL-20260811-01).
- **BL-20260906-06** — *feature, med* — Denver ingestion has no chapter discovery: `--chapters` must be typed by hand and `parse_chapter_html` ignores the code's article/division layer, so `Ordinance` is one flat node per chapter. Add a table-of-contents parse that enumerates chapters, and decide whether articles deserve their own node or a property on `OrdinanceSection`. _Surfaced in:_ specs/051-backlog-zero (while closing BL-20260509-05).
- **BL-20260906-07** — *feature, low* — Ordinances are invisible to retrieval. `agents_runtime/tools/graph_rag.py` reads `:Case` and `:StatuteSection` only, so the `:OrdinanceSection` nodes `ordinance_queries.py` now writes cannot surface in an answer even though migration 007 fulltext-indexes their text. Add an ordinance leg to the hybrid retriever alongside `_lexical_statutes`. _Surfaced in:_ specs/051-backlog-zero (while closing BL-20260509-05).
- **BL-20260906-08** — *feature, med* — No sign-in surface in the frontend: `/api/auth/login` exists but nothing in `frontend/` renders a login form, so the Share control in `frontend/components/AnalysisStudio.tsx` can only succeed for someone who already has a Django session from `/admin/`. Add a small account menu (sign in / whoami / sign out) wired to `/api/auth/{csrf,login,logout,me}` in `frontend/components/shell/`, and have `frontend/app/api/backend/[...path]/route.ts` forward the session cookie so the same-origin proxy path works too. _Surfaced in:_ specs/051-backlog-zero (while closing BL-20260429-26).
- **BL-20260906-09** — *tech-debt, med* — WebSocket auth still ignores sessions: `backend/law_ai/agentsapi/consumers.py` compares a query-string key against `AGENT_API_KEY` only and never consults `ApiToken` or a Django session, so a signed-in browser user with no key cannot open `/ws/agents/<id>` even though every REST route now accepts their session. Teach the consumer the same three credentials `core/auth.py` accepts. _Surfaced in:_ specs/051-backlog-zero (while closing BL-20260503-13).
- **BL-20260906-10** — *refactor, low* — `phoenix_trace_url` is now a misnomer: `backend/law_ai/core/telemetry.py` keeps it as an alias for the backend-agnostic `trace_url()`, and the field name is echoed through `law_ai/agents_runtime/crews/legal_analyst.py`, `analysis/urls.py` and `frontend/lib/api.ts`. Rename the API field to `trace_url` with a deprecation window that emits both, once no client reads the old name. _Surfaced in:_ specs/051-backlog-zero (while closing BL-20260502-07).
- **BL-20260906-11** — *test-gap, med* — `frontend/__tests__/fixtures/api-schema.json` is a generated fixture with no regeneration gate in CI, so any backend pydantic change silently reds `__tests__/lib/apiContract.test.ts` for whoever runs the suite next (it did so twice during this package for `thread_id`/`resumed`/`degraded_reason` added elsewhere). Add `manage.py export_api_schema --check` to the CI lint job so the mismatch fails on the PR that caused it. _Surfaced in:_ specs/051-backlog-zero (while closing BL-20260429-25).
- **BL-20260906-12** — *feature, low* — `law_ai.core.SettingValue`, `law_ai.analysis.AnalysisRun` and `ShareLink` have no Django admin, so an operator cannot inspect or clear an instance-wide locked setting, archive a run, or revoke a share link without a shell. Register read-mostly ModelAdmins in `backend/law_ai/core/admin.py` and a new `backend/law_ai/analysis/admin.py` (using the TYPE_CHECKING `_ModelAdmin` alias pattern now in those files). _Surfaced in:_ specs/051-backlog-zero (while closing BL-20260830-07).
- **BL-20260906-13** — *tech-debt, low* — `AUDIT_DB_THREAD_OFFLOAD` defaults to false in `backend/law_ai/settings/base.py`, so production still takes the Celery hand-off and dev takes the thread — the parity the item wanted only holds where Celery is eager. Decide whether prod should also offload (removing the Celery round-trip for audit rows entirely) or whether dev should run a real worker, and collapse the two paths. _Surfaced in:_ specs/051-backlog-zero (while closing BL-20260811-07).
- **BL-20260906-14** — *feature, med* — Finish the drafting export: add `python-docx` and one PDF engine (weasyprint or reportlab) to backend/pyproject.toml + backend/Dockerfile, then render the structure `law_ai/matters/drafting/memo.compose_memo` already returns into DOCX and PDF behind `GET /api/matters/<slug>/memo?output=docx|pdf` (currently 501). Needs its own spec sub-package per the item, and a UPL wording review of the draft disclaimer. _Surfaced in:_ specs/051-backlog-zero (while closing BL-20260817-03).
- **BL-20260906-15** — *feature, med* — Nothing currently passes `matter_id` into `LegalWorkflow`, so the retrieval boost set is reachable only by a caller that sets the state key by hand. Thread an optional matter through `/api/analysis` (and `LegalAnalyst.run`) into `agents_runtime/graphs/legal_workflow.py`, and surface `retrieval_coverage.boost_source`/`boosted_count` in the Analysis Studio coverage envelope so the bias is visible to the reader, not just recorded. _Surfaced in:_ specs/051-backlog-zero (while closing BL-20260817-05).
- **BL-20260906-16** — *feature, med* — `MatterAuthority.node_id` is an unvalidated string and `MatterArtifact.analysis_id` is a string join to `AnalysisRun`. Validate a recorded authority against Neo4j (`core/neo4j/queries.py`) when the graph is reachable, and make the analysis link a real nullable FK, so an export bundle cannot point at authorities or runs that do not exist. _Surfaced in:_ specs/051-backlog-zero (while closing BL-20260817-01).
- **BL-20260906-17** — *feature, med* — `frontend/components/shell/SettingsForm.tsx` now edits the deepest settable scope, which means a signed-in admin can no longer seed the *instance* default for a layout setting from the UI — they always write their own user row. Add a scope selector (user / instance, instance gated on `is_staff`) to /settings so an admin can set and lock an instance-wide layout default. _Surfaced in:_ specs/051-backlog-zero (while closing BL-20260905-10).
- **BL-20260906-18** — *feature, low* — `LsatAttempt` records graded multiple-choice answers only; writing-section evaluations still land in the JSONL audit log alone (open item BL-20260831-27). Persist a writing evaluation per user — either on `LsatAttempt` with a section='WS' shape or a sibling model — so `/api/lsat/stats` per-learner totals cover the writing section too. _Surfaced in:_ specs/051-backlog-zero (while closing BL-20260503-05).
- **BL-20260906-19** — *test-gap, low* — The Celery beat entry `matter-task-reminders` in `backend/law_ai/celery.py` is only exercised through a direct call to `law_ai.matters.tasks.sweep_task_reminders` in `backend/tests/matters/test_tasks.py`. There is no test asserting the beat schedule actually registers it (name, hourly interval), so a typo in the task name would ship silently — the same gap the other beat entries have. _Surfaced in:_ specs/051-backlog-zero (while closing BL-20260817-02).
- **BL-20260906-20** — *doc-gap, low* — `backend/law_ai/ingestionapp/management/commands/review_queue.py` still records a bare `--reviewer` string with no way to name a Django account. Add a `--reviewer-user <username>` option that resolves the account and passes it to `record_decision(reviewer_user=...)`, so an operator running the CLI gets the same joinable attribution the admin path now produces. _Surfaced in:_ specs/051-backlog-zero (while closing BL-20260811-04).
- **BL-20260906-21** — *feature, low* — The nav rail does not highlight Agent Ops on `/autonomy`: `NavRail.tsx` computes `active` from `pathname.startsWith(mod.nav.href)`, while `moduleForPath` in `frontend/lib/modules/catalog.ts` now also resolves routes a module claims through a sidebar link. Make NavRail (and MobileTabBar/DockZone, which use the same prefix test) ask `moduleForPath` instead so a module-claimed route lights up its rail entry. _Surfaced in:_ specs/051-backlog-zero (while closing BL-20260511-03).
- **BL-20260906-22** — *feature, med* — `compose_digest`'s new '## Autonomy Cycles' section lists rows but ignores `AutonomyRun.summary`, so per-cycle counts (prs_opened, backlog_ids, quarantined, legalbench_delta) still have to be reconstructed from `AuditEvent` scans in `backend/law_ai/core/autonomy.py`. Fold the summary fields into the four existing digest sections and retire the event scan for windows the table covers. _Surfaced in:_ specs/051-backlog-zero (while closing BL-20260511-04).
- **BL-20260906-23** — *feature, med* — `audit.AutonomyRun` has no consumer beyond `compose_digest`. Add a `/api/agents/autonomy/runs` view in `backend/law_ai/agentsapi/autonomy_views.py` and a fourth panel in `frontend/components/AutonomyDashboard.tsx` showing the last N cycles by kind/status/duration — the table's composite `(kind, -started_at)` index exists precisely for that query. _Surfaced in:_ specs/051-backlog-zero (while closing BL-20260511-04).
- **BL-20260906-24** — *test-gap, med* — The live-model leg of `backend/tests/core/test_run_autonomy_integration.py` and `backend/tests/lsat/test_factory_ollama_integration.py` has never executed: the compose `ollama` service only has ~4.0 GiB available and `mistral:7b-instruct-q4_K_M` needs 4.9, so both skip on every developer box tried so far. Either raise the ollama service's memory in `docker-compose.yml` or pin `make test-integration-ollama` to a small model (e.g. a 1-3B instruct) so these assertions actually run somewhere. _Surfaced in:_ specs/051-backlog-zero (while closing BL-20260527-08).
- **BL-20260906-25** — *test-gap, low* — `backend/tests/core/test_run_autonomy_integration.py` and `test_factory_ollama_integration.py` probe Ollama at *import* time (`_reachable(_URL)` at module scope, with a 180s generate timeout), so every collection of `backend/tests/` — including `make test-backend`, which deselects them — pays that network round trip twice. Move the probe into a session-scoped fixture or cache it so collection stays offline. _Surfaced in:_ specs/051-backlog-zero (while closing BL-20260526-02).
- **BL-20260906-26** — *refactor, low* — `_runner` in both `backend/law_ai/core/tasks.py` and `backend/law_ai/core/management/commands/run_autonomy.py` now needs `# noqa: PLR0911` because the autonomy kinds outgrew ruff's 6-return limit (the seventh, `commit_approved`, landed during this work). Replace the duplicated if-chains with one shared `{kind: runner}` dispatch table so adding a pillar stops editing two files and suppressing a lint rule. _Surfaced in:_ specs/051-backlog-zero (while closing BL-20260511-23).
- **BL-20260906-27** — *doc-gap, low* — `docs/constitution.md` §12 invariant I4 describes the audited entry point but not the two behaviours added here: `--cycle-id` now makes `run_cycle` idempotent (replay instead of re-run) and every cycle is additionally projected into `audit.AutonomyRun`. Both are documented in `docs/local-ai.md` and `docs/data-model.md`; fold a sentence into I4 so the invariant text matches the implementation. _Surfaced in:_ specs/051-backlog-zero (while closing BL-20260511-29).
- **BL-20260906-28** — *test-gap, high* — Record and commit the first real LegalBench baseline: on a host that can load mistral:7b-instruct-q4_K_M run `make legalbench-cache && make legalbench-baseline`, commit backend/var/legalbench/baseline.json, and fill the score/commit columns in the docs/legalbench.md "Baseline scores" table. The dataset cache and the --fail-on-synthetic gate already landed; only the numbers are missing. _Surfaced in:_ specs/051-backlog-zero (while closing BL-20260811-10).
- **BL-20260906-29** — *feature, med* — check_regression() in backend/law_ai/eval/legalbench.py compares accuracies without checking that baseline.json's `model` and `scorers` match the current run, so a baseline recorded with a different model or scorer silently produces false regressions. Refuse (or loudly warn and skip) the comparison when either differs. _Surfaced in:_ specs/051-backlog-zero (while closing BL-20260811-10).
- **BL-20260906-30** — *infra, low* — backend/law_ai/eval/fetch.py pins DATA_REVISION/PROMPT_REVISION by hand. Add a nightly (or monthly) job that fetches the upstream HEAD SHAs and opens a BACKLOG/PR note when the pinned revisions drift, so the benchmark ages deliberately rather than by neglect; `MANIFEST=update make legalbench-cache` is the intended follow-through. _Surfaced in:_ specs/051-backlog-zero (while closing BL-20260811-09).
- **BL-20260906-31** — *feature, low* — The dashboard half of the score-history ask is still open: no endpoint serves backend/var/legalbench/history.jsonl and frontend/components/AgentDashboard.tsx has no eval card. If reviewers want it in the UI, add a read-only GET /api/agents/health/legalbench-history plus a sparkline next to the local-AI health panel (P11 owns that component). _Surfaced in:_ specs/051-backlog-zero (while closing BL-20260811-12).
- **BL-20260906-32** — *test-gap, low* — backend/tests/eval/test_legalbench_cli.py's loader tests (test_load_synthetic_stub_when_no_cache, test_limit_is_respected) now read the real cached dataset on any machine that has run `make legalbench-cache`, so they no longer test what their names claim. Point them at an isolated cache dir the way test_run_eval_returns_report_dict now does. _Surfaced in:_ specs/051-backlog-zero (while closing BL-20260811-11).
- **BL-20260906-33** — *infra, med* — Apply the checked-in branch-protection ruleset: `gh api -X POST repos/bamr87/law-ai/rulesets --input .github/rulesets/main-required-checks.json`. The JSON, its sync tests and the docs shipped with BL-20260815-01, but the API call is a repo-settings write that the agent permission layer denied, so `gh api repos/bamr87/law-ai/rulesets` still returns `[]` and nothing blocks a merge on a red check today. _Surfaced in:_ specs/051-backlog-zero (while closing BL-20260815-01).
- **BL-20260906-34** — *infra, med* — Prove the LegalBench scored gate green once. After this branch merges, run `gh workflow run nightly-tests.yml` and confirm 'Pull the LegalBench gate model' and 'Run LegalBench eval (regression gate)' both succeed on a hosted runner, then record the run id in docs/legalbench.md § 'CI status of the scored gate'. The workflow is re-enabled and the missing model-pull step is added, but neither the 2026-07-16 disk-space fix (613ab69) nor the new pull step has ever been exercised by an actual run. _Surfaced in:_ specs/051-backlog-zero (while closing BL-20260511-26).
- **BL-20260906-35** — *tech-debt, low* — Decide the fate of the unmerged AM-1 auto-merge work before it is forgotten. `scripts/check_am1_eligible.py`, `tests/test_am1_eligible.py`, `.github/workflows/am1-automerge.yml` and an ADR numbered 0004 exist only on origin/claude/cranky-burnell-fd2782 (commit 7c8a0f9) and were never merged to main — main has since reused ADR number 0004 for 0004-jurisprudential-stance.md, and the org still shows a disabled 'AM-1 auto-merge' workflow. Either promote it under a fresh ADR number or record it as abandoned; the local worktree that held it has now been deleted. _Surfaced in:_ specs/051-backlog-zero (while closing BL-20260818-03).
- **BL-20260906-36** — *test-gap, low* — scripts/ and root tests/ are outside the formatters' reach: `make lint`/`make format` run ruff and black inside the backend container at /app (= ./backend/), so scripts/backlog_lint.py, scripts/visual_evidence_gate.py and everything under tests/ are never checked. Running the container's black over them wants to reformat pre-existing code, which means they have drifted. Either add a lint step scoped to the repo-root Python or declare them out of scope explicitly. _Surfaced in:_ specs/051-backlog-zero (while closing BL-20260503-14).
- **BL-20260906-37** — *infra, low* — `scripts/backlog_lint.py` carries a `#!/usr/bin/env python3` shebang but is mode 644, which ruff flags as EXE001 (as do several siblings: evolve_audit.py, fetch_legalbench.py, legalbench_summary.py, spec_validator.py). Others (next_backlog_id.py, pick_backlog_item.py, ux_audit.py) are 755. Pick one convention and apply it — the mixed state means `./scripts/backlog_lint.py` works for some scripts and not others. _Surfaced in:_ specs/051-backlog-zero (while closing BL-20260503-14).
- **BL-20260906-38** — *doc-gap, low* — docs/ao-sdlc-guide.md is a pure redirect stub to AO-SDLC_Outline_Guide.md, but several BACKLOG items and dossiers still name it as the home for CI/autonomy documentation. The three sections added this pass (branch protection, the evolve kill switch, local workflow smoke-testing) went into docs/ao-sdlc.md instead. Either fold the stub's table into the root guide and delete it, or make it clearer that it is not a documentation target. _Surfaced in:_ specs/051-backlog-zero (while closing BL-20260818-02).
- **BL-20260906-39** — *test-gap, low* — The `driver.sh` GUI smoke has no automated caller. `FRONTEND=1 bash .claude/skills/run-law-ai/driver.sh` now exercises the pages and the Next->Django proxy hop end to end, but only when a human or agent runs it. Once the e2e harness lands (BL-20260811-16), consider promoting the launch logic to scripts/ and running the smoke in CI — the item explicitly deferred this because there was nothing to reuse it. _Surfaced in:_ specs/051-backlog-zero (while closing BL-20260615-04).
- **BL-20260906-40** — *infra, med* — Boot the LangGraph Studio host end to end once a free LANGSMITH_API_KEY exists: `make studio-up`, confirm backend/Dockerfile.studio builds against langchain/langgraph-api:3.12 with `-c /api/constraints.txt`, that LANGSERVE_GRAPHS resolves law_ai/agents_runtime/graphs/studio.py:make_graph, and that a run steps through retrieve → analyze → cite_check in smith.langchain.com/studio. Everything but the boot is verified today. _Surfaced in:_ specs/051-backlog-zero (while closing BL-20260502-01).
- **BL-20260906-41** — *feature, med* — Wire the vLLM server (docker-compose.gpu.yml, profile `vllm`) into `law_ai/core/llm/providers.py` as an OpenAI-compatible chain tier. It serves an OpenAI API on :8001 today but nothing in the product can call it, and adding a tier is a constitution §1 amendment, not a compose change. _Surfaced in:_ specs/051-backlog-zero (while closing BL-20260502-02).
- **BL-20260906-42** — *infra, med* — Validate the GPU overlay on a real Linux + NVIDIA host: `make local-ai-up-gpu` (device reservations, 70B gate model, 7200s start_period) and `make local-ai-up-server` (nvidia/dcgm-exporter, vllm/vllm-openai:v0.11.0). Both image tags and every `deploy.resources` block are currently validated only by `docker compose config`. _Surfaced in:_ specs/051-backlog-zero (while closing BL-20260502-02).
- **BL-20260906-43** — *tech-debt, low* — Retire the dead DEFAULT_MODEL / FALLBACK_MODEL settings (backend/law_ai/settings/base.py:25-26, :204-205 and .env.example) — nothing reads them, and DEFAULT_MODEL advertising llama3.1:70b-q4_K_M reads like the live knob when OLLAMA_DEFAULT_MODEL is. They are only annotated as dead right now, because base.py is shared with other in-flight packages. _Surfaced in:_ specs/051-backlog-zero (while closing BL-20260502-02).
- **BL-20260906-44** — *feature, low* — Expose a Django /metrics endpoint (django-prometheus) and add it to infra/prometheus/prometheus.yml, so API latency, error rate and Celery task outcomes join the Grafana dashboard. Today Prometheus only sees vLLM, Redis and DCGM — the app itself is invisible to the server-tier dashboard. _Surfaced in:_ specs/051-backlog-zero (while closing BL-20260502-03).
- **BL-20260906-45** — *infra, low* — Let scripts/ollama-bundle.sh bundle a SUBSET of models: it tars the whole `ollama` volume today, so refreshing one model means re-shipping tens of GB. Prune by manifest against OLLAMA_BOOTSTRAP_MODELS, or add a --models 'a b' filter. _Surfaced in:_ specs/051-backlog-zero (while closing BL-20260502-06).
- **BL-20260906-46** — *doc-gap, med* — A human must read xAI's legal pages in a browser (x.ai/legal/terms-of-service, x.ai/legal/privacy-policy, x.ai/legal/europe-privacy-policy-addendum) and record the decision in docs/adr/0007-xai-runtime-provider.md's 'Terms-of-service and data-retention review' section, replacing the draft, plus the outcome in docs/constitution.md §1's xAI amendment block. The pages 403 automated fetches, so no agent can close this. Until then the default LLM_PROVIDER_CHAIN keeps a second unreviewed third-party egress path (settings/base.py:35). _Surfaced in:_ specs/051-backlog-zero (while closing BL-20260904-03).
- **BL-20260906-47** — *tech-debt, low* — scripts/spec_validator.py has no 'superseded' status: SHIPPED_STATUSES = {'shipped'} and the symmetric check errors when every task is [x] but the status is anything else, so specs/025-lsat-static-site/spec.md had to keep '- **Status**: shipped — **superseded**'. Add 'superseded' to SHIPPED_STATUSES (and to the status enum in specs/_template/spec.md) so a retired spec can say so in the field the validator reads. _Surfaced in:_ specs/051-backlog-zero (while closing BL-20260716-11).
- **BL-20260906-48** — *test-gap, low* — The constitution §13 review-question check in scripts/spec_validator.py (stronger_question_warnings) only prints WARN lines and never affects the exit code, so nothing in CI surfaces them. Consider a --strict flag used by the spec-gate job, or grepping for 'WARN ' in the make lint-specs step, once the 34 legacy '## 2. Goals' specs have been migrated to the new §2. _Surfaced in:_ specs/051-backlog-zero (while closing BL-20260803-05).
- **BL-20260906-49** — *doc-gap, low* — docs/llm-provider-chain.md's Claude-transport sections (Setup, Validate the connection, Run a live agent) are still H2s inside a page whose subject is now the whole chain, held together only by a 'everything from here to Configuration reference documents tiers 1-2' sentence. Demote them to H3 under '## The Claude transport' the next time that file is edited substantively. _Surfaced in:_ specs/051-backlog-zero (while closing BL-20260904-07).
- **BL-20260906-50** — *refactor, low* — tests/test_docs.py now carries two overlapping link scanners: test_no_case_mismatched_doc_links walks the repo with os.walk and _LINK_SCAN_SKIP_DIRS, while the new test_no_broken_relative_doc_links enumerates via git ls-files and strips code fences/spans. The strict existence check subsumes the case-only one on every file git knows about; fold the case-mismatch message into the strict test and drop the duplicate walk. _Surfaced in:_ specs/051-backlog-zero (while closing BL-20260602-04).
- **BL-20260906-51** — *tech-debt, med* — `npm ci` has never been run against the pruned frontend/package-lock.json: BL-20260830-01 rebuilt it by script because `npm uninstall` and `npm install --package-lock-only` were both refused by the permission classifier. Run `docker compose build frontend` (or `docker compose run --rm frontend npm ci`) once to confirm the lockfile installs, and drop the four removed packages from the shared node_modules volume. _Surfaced in:_ specs/051-backlog-zero (while closing BL-20260830-01).
- **BL-20260906-52** — *feature, low* — Skeleton loaders under frontend/components/lsat/ (LabPrimitives.tsx:73,89 and TutorPane.tsx:99) still use bare `animate-pulse` with no `motion-reduce:animate-none`; BL-20260831-03 gated the platform shell and homepage but left that tree alone because it was being rewritten concurrently by the LSAT Lab split. _Surfaced in:_ specs/051-backlog-zero (while closing BL-20260831-03).
- **BL-20260906-53** — *tech-debt, med* — `useFocusTrap` in frontend/components/shell/Overlay.tsx restored focus only while the trapped node still contained document.activeElement, so any overlay that unmounts (rather than flipping `active` to false) lost focus to <body> — fixed narrowly for BL-20260831-07. Audit the other overlays (Drawer, CommandPalette, ShortcutsHelp) for the same unmount path and add a shared RTL case asserting focus restoration on unmount. _Surfaced in:_ specs/051-backlog-zero (while closing BL-20260831-07).
- **BL-20260906-54** — *test-gap, low* — GraphViewer's keyboard node cycling (arrow keys / Enter, BL-20260831-12) is untested: Cytoscape needs a real <canvas>, so only tabIndex and the aria-label are asserted. Cover it in frontend/e2e (Playwright) where a real browser can drive the canvas. _Surfaced in:_ specs/051-backlog-zero (while closing BL-20260831-12).
- **BL-20260906-55** — *feature, low* — Node size on the graph is now CITES in-degree *within the rendered neighbourhood* (BL-20260803-03), which changes as you traverse. If a corpus-wide citation count is ever wanted, it needs a backend field on the :Case node plus the same litigation-frequency labelling in GraphViewer's aria-label and KnowledgeGraph's Legend. _Surfaced in:_ specs/051-backlog-zero (while closing BL-20260803-03).
- **BL-20260906-56** — *doc-gap, low* — `GET /api/agents/proposed-tests` (BL-20260511-17) is not listed in docs/architecture.md's agentsapi route table alongside backlog/specs/health; add it when the docs owner next touches that section. _Surfaced in:_ specs/051-backlog-zero (while closing BL-20260511-17).
- **BL-20260906-57** — *tech-debt, med* — Burn `backend/law_ai/lsat/urls.py` down to strict-clean and re-bank with `make mypy-baseline`. It is 25 of the 59 remaining entries in `backend/mypy-baseline.txt` — all `no-untyped-def` on DRF view `get`/`post` methods needing `(self, request: Request, *args: Any, **kwargs: Any) -> Response`. Left alone here only because the file was being edited concurrently by another work package. _Surfaced in:_ specs/051-backlog-zero (while closing BL-20260429-04).
- **BL-20260906-58** — *tech-debt, low* — Clear the remaining 34 non-`lsat/urls.py` entries in `backend/mypy-baseline.txt` app by app: `agentsapi/urls.py` (8), `lsat/services/bank.py` (5), `ingestionapp/services/courtlistener.py` (3), `core/auth.py` (3), `agents_runtime/graphs/runtime.py` (3, `BaseCheckpointSaver` missing type args), `celery.py`/`core/tasks.py`/`ingestionapp/tasks.py` (2 each), plus six single-error files. When the baseline reaches zero, delete it and drop the ratchet call from `Makefile` and `.github/workflows/ci.yml` so plain `mypy law_ai --strict` is the gate — `scripts/mypy_ratchet.py` prints that instruction itself. _Surfaced in:_ specs/051-backlog-zero (while closing BL-20260429-04).
- **BL-20260906-59** — *tech-debt, low* — Celery publishes no type stubs, so `celery.*` sits in the `ignore_missing_imports` override in `backend/pyproject.toml` and every `@shared_task` produces an `untyped-decorator` error (6 of the 59 baseline entries, in `law_ai/celery.py`, `core/tasks.py`, `ingestionapp/tasks.py`). Evaluate `celery-types` as a dev dep; if accurate enough it clears those and lets the override drop `celery.*`. _Surfaced in:_ specs/051-backlog-zero (while closing BL-20260429-04).
- **BL-20260906-60** — *infra, low* — `backend/mypy-baseline.txt` carries a global `# total:` header, so two PRs that each burn a different file down conflict on that one line. If that becomes annoying, drop the header total and relax `tests/test_mypy_ratchet.py::TestCommittedBaseline::test_header_total_matches_the_entries`, or teach `scripts/mypy_ratchet.py --update` to merge per-file entries rather than rewrite the file. _Surfaced in:_ specs/051-backlog-zero (while closing BL-20260429-04).
- **BL-20260906-61** — *test-gap, low* — BL-20260901-03's second implementer finding still needs a BACKLOG entry: at the bottom of a short page (e.g. Overview at 390px) the site header can never reach the 'hidden' state, because the document is not tall enough to scroll HIDE_AFTER_PX past the condensed layout — so the hide-on-scroll behaviour is unreachable there. No test asserts anything about it either way. (The other finding from the same batch, the skip link measuring 40.8px, was fixed in this pass rather than deferred.) _Surfaced in:_ specs/051-backlog-zero (while closing BL-20260901-03).
- **BL-20260906-62** — *tech-debt, low* — lsat-static/components/ShortcutHelp.tsx renders each row with `key={keys}` and the Argumentative Writing group lists 'O' twice ('Open the first prompt...' and 'Return to the editor after Esc'), so React logs 'Encountered two children with the same key, `O`' every time the sheet mounts. One-line fix: key on `g.title + keys` (or the row index). Surfaced by the new pageShortcuts suite, which is the first test to open the real dialog. _Surfaced in:_ specs/051-backlog-zero (while closing BL-20260901-07).
- **BL-20260906-63** — *infra, low* — lsat-static/e2e now takes ~18s in the browser image but `make lsat-static-e2e` re-runs `npm ci` and a full `next build` on every invocation (~2 min). A cached-build variant (or reusing lsat-static/out when it is newer than the sources) would make the viewport suite cheap enough to run per-PR behind the existing lsat-static paths filter, rather than only nightly. _Surfaced in:_ specs/051-backlog-zero (while closing BL-20260901-03).
- **BL-20260906-64** — *doc-gap, low* — CLAUDE.md's command table still describes `make lint-specs` as "host stdlib, no container"; since BL-20260511-14 it also runs `python3 -m pytest tests/test_evolve_audit.py`, so it needs pytest on the host interpreter. AGENTS.md and tests/README.md were corrected; CLAUDE.md was deliberately left alone (agents must not edit it). _Surfaced in:_ specs/051-backlog-zero (while closing BL-20260511-14).
- **BL-20260906-65** — *tech-debt, med* — The a11y baseline still amnesties re-use of an already-accepted colour pair: new text painted `#62748e` on a dark slate ground passes because that signature is recorded. The only real close is paying off the contrast debt (`text-slate-500` on `bg-slate-950`/`bg-slate-900`) and emptying frontend/e2e/a11y-baseline.json, at which point any color-contrast violation fails outright. _Surfaced in:_ specs/051-backlog-zero (while closing BL-20260831-09).
- **BL-20260906-66** — *tech-debt, med* — Adding /matters to the a11y sweep surfaced a `scrollable-region-focusable` violation on `#main` for that route — the shell's scroller has no keyboard entry point there. It is now baselined as known debt rather than fixed. _Surfaced in:_ specs/051-backlog-zero (while closing BL-20260831-09).
- **BL-20260906-67** — *infra, med* — The new ci.yml `a11y` job boots the whole compose stack (both app images) on every PR touching frontend/. The nightly had to drop from daily to weekly over runner disk exhaustion, which is why the job reclaims ~25 GB of preinstalled toolchains first — but nobody has watched it run yet. Check its first few PR runs for runtime and disk, and consider a prebuilt image or a cached build if it is marginal. _Surfaced in:_ specs/051-backlog-zero (while closing BL-20260831-09).
- **BL-20260906-68** — *tech-debt, low* — The app shell calls account-scoped `/api/matters` on every page and takes a 401 on every anonymous visit — correct behaviour, but it means every browser session logs four-plus 401s and any 'no denied API call' assertion has to special-case it (api-auth.spec.ts now does, explicitly). Not fetching it while signed out would be cleaner. _Surfaced in:_ specs/051-backlog-zero (while closing BL-20260430-11).
- **BL-20260906-69** — *infra, low* — refresh-lsat-content.yml's PR leg pushes with GITHUB_TOKEN, which by design raises no `push` event — so the bot commit does not re-trigger CI on the PR. That is why the drift gate defers in the same run rather than relying on a re-run. If the deferral condition in ci.yml and the workflow's trigger ever diverge, stale content.json could reach main; tests/test_lsat_site.py::test_the_drift_gate_defers_only_where_the_job_will_fix_it is the guard, but a periodic check on main would be belt-and-braces. _Surfaced in:_ specs/051-backlog-zero (while closing BL-20260702-11).
- **BL-20260906-70** — *test-gap, low* — The governance triage now has two homes (the Celery beat entry and the nightly workflow step) writing the same titled issue under the same label. Idempotency across the two is argued in docs/ao-sdlc.md and unit-tested for the library path, but nothing exercises the shell step's `gh` branch — a live smoke (or nektos/act run) of the nightly triage step would close that. _Surfaced in:_ specs/051-backlog-zero (while closing BL-20260503-14).
- **BL-20260906-71** — *doc-gap, low* — BL-20260831-03's missing follow-up entry is now moot in code — the residual unconditional pulses it named (lsat/TutorPane.tsx, lsat/LabPrimitives.tsx SkeletonQuestion/SkeletonGrid) are gated with motion-reduce:animate-none and covered by __tests__/components/HomeMotion.test.tsx. The main loop may still want a BACKLOG/tasks.md note that the reduced-motion sweep is complete rather than partial, since specs/051-backlog-zero/tasks.md still reads '_pending: populated as each package lands._'. _Surfaced in:_ specs/051-backlog-zero (while closing BL-20260831-03).
- **BL-20260906-72** — *tech-debt, low* — There is no mechanical gate that a reduced-motion regression cannot re-enter through a new file: HomeMotion.test.tsx only renders the components it imports. A one-line ux_audit.py rule ('no bare animate-* utility in frontend/app or frontend/components') would make the whole tree the contract instead of five sampled components. _Surfaced in:_ specs/051-backlog-zero (while closing BL-20260831-03).
- **BL-20260906-73** — *feature, med* — An instance write from /settings' new 'Instance defaults' scope chooser is refused server-side for a non-staff caller (core/urls_settings.py may_write) and the row silently stays local to that browser. The GET /api/settings/values payload does not say who may write which scope, so the UI cannot grey the option out honestly. Adding a `writable_scope_ids` field to that response (and reading it in SettingsForm) would turn the help text's caveat into a real affordance. _Surfaced in:_ specs/051-backlog-zero (while closing BL-20260905-10).
- **BL-20260906-74** — *tech-debt, low* — PassagePanel's concept filter asks /api/lsat/questions with limit=25, which is the endpoint's hard cap (_bounded_int hi=25). No concept in the current bank tags more than 21 questions, but a future concept above 25 would have some of its passages missed from the filtered set. A dedicated `passage_ids` projection (or a higher cap for id-only queries) would remove the ceiling. _Surfaced in:_ specs/051-backlog-zero (while closing BL-20260905-01).
- **BL-20260906-75** — *doc-gap, low* — docs/ui-ux.md still describes layout preferences as 'instance-scoped' (spec 050 section) even though BL-20260905-10 moved the 15 ui.*/lsat.timer.*/lsat.library.* keys to the user scope with the instance value as the inherited default, and /settings now carries a scope chooser. Worth a sentence in that paragraph. _Surfaced in:_ specs/051-backlog-zero (while closing BL-20260905-10).
- **BL-20260906-76** — *feature, low* — LSAT item authoring (lsat_content_author._generate, measured at 68s on the xAI tier) still buffers its call: it now passes the interactive model override but does not stream. Give it the same delta relay the IRAC path got (llm.astream + an emit_stream_event sink keyed on a stream_id) so the authoring wait is visible too; the same applies to lsat/services/crosscheck.py and lsat_writing_evaluator.py. _Surfaced in:_ specs/051-backlog-zero (while closing BL-20260905-11).
- **BL-20260906-77** — *tech-debt, low* — Streamed analysis deltas write one ws_event_sent provenance row per chunk and each consumes a slot in the 200-event replay buffer, so a long IRAC answer can evict the run's earlier agent_step frames for a reconnecting client. The LSAT tutor has the same shape; consider coalescing token events (time- or size-bucketed) in law_ai/agentsapi/streaming.py, or exempting them from the replay buffer. _Surfaced in:_ specs/051-backlog-zero (while closing BL-20260905-11).
- **BL-20260906-78** — *feature, low* — No Grok-variant latency/quality evaluation exists, so XAI_INTERACTIVE_MODEL still ships blank: an operator with a live subscription should measure at least one non-reasoning candidate against grok-4.6 on an IRAC question and an LSAT authoring run and record the numbers (or a reasoned 'none suitable') in docs/adr/0007. It needs live billed calls, so it cannot be done from CI or an agent run. _Surfaced in:_ specs/051-backlog-zero (while closing BL-20260905-11).
- **BL-20260906-79** — *tech-debt, low* — LegalAnalyst's direct-LLM path now runs one lexical GraphRAG query per model-named authority (previously only for the ones the alias resolver missed) because §13 attribution needs the passage behind a resolved :Case id. Batch the lookups into one query, or have the citation resolver return court/decided_at alongside the id, if the extra round trips show up in analysis latency. _Surfaced in:_ specs/051-backlog-zero (while closing BL-20260803-04).
- **BL-20260906-80** — *test-gap, med* — docs/legalbench.md still records _TBD_ for the core_reasoning and precedent_retrieval baselines, so the LegalWorkflow backfill has unit-level but no eval-level parity evidence. This is BL-20260811-10's work (a run on a host that can load the gate model); docs/legalbench.md now names the dependency explicitly next to the table. _Surfaced in:_ specs/051-backlog-zero (while closing BL-20260511-06).
- **BL-20260906-81** — *test-gap, med* — Nothing in CI or the nightly workflows runs `make test-integration-ollama`. The factory Ollama slice and the autonomy->HITL slice now both pass for real, but only when someone runs the target by hand, so a regression in the executor->intake->proposals path would still reach main unnoticed. Wire the target into the nightly workflow (it needs a runner that can hold the model, or OLLAMA_INTEGRATION_MODEL pointed at a small one) and keep it continue-on-error at first. _Surfaced in:_ specs/051-backlog-zero (while closing BL-20260702-05).
- **BL-20260906-82** — *infra, low* — The default OLLAMA_BOOTSTRAP_MODELS set (mistral:7b + llama3.1:8b) cannot load on a Docker VM with less than ~6 GiB free, which makes every local-model integration test a permanent skip on ordinary laptops. I pulled qwen2.5:3b-instruct-q4_K_M into the shared ollama volume by hand to run them. Consider adding a small instruct model to the bootstrap set (or a documented `make local-ai-pull-small`) so the opt-in local tests are runnable out of the box rather than by hand. _Surfaced in:_ specs/051-backlog-zero (while closing BL-20260702-05).
- **BL-20260906-83** — *test-gap, med* — The polish prompt's yield is now measured against the free local tier only (30/30 = 1.00 on ollama/qwen2.5:3b-instruct-q4_K_M, committed at backend/var/lsat_synth/polish_yield.json). Yield is not comparable across tiers, so the hosted tiers (Claude, xAI) are still uncalibrated and the 0.50 floor is unvalidated for the chain's default first tier. Run `make lsat-synth-polish-yield` once against the default chain and commit the second report alongside the local one. _Surfaced in:_ specs/051-backlog-zero (while closing BL-20260903-17).
- **BL-20260906-84** — *tech-debt, low* — The polish path's real loss is at the transport, not the lint: 3 of 8 measured rounds never produced a countable proposal (2 provider-unavailable timeouts, 1 reply that was prose rather than a JSON object). PolishYield.error keeps those out of the yield rate, so a headline of 1.00 can sit on top of a 37% round-failure rate. Consider a bounded retry on 'unparseable' (a re-ask costs one call and the lint already discards junk) and surfacing a round-success rate next to the yield. _Surfaced in:_ specs/051-backlog-zero (while closing BL-20260903-17).
- **BL-20260906-85** — *feature, med* — The AI tutor (backend/law_ai/lsat/services/tutor.py) and the cross-check still reason in stored answer labels, so during a shuffled attempt a tutor answer can name a letter the learner is not looking at. Remapping the tutor's output is not enough — it reasons about the choices — so the prompt needs to receive the displayed board. Documented in docs/lsat-answer-shuffling.md 'What is not covered yet'; constitution §11 wants it mirrored into BACKLOG.md as a BL- item, which this agent is not permitted to edit. _Surfaced in:_ specs/051-backlog-zero (while closing BL-20260606-01).
- **BL-20260906-86** — *tech-debt, low* — Bank content is still authored with bare answer labels ('A is correct: …', '(D) is the exception'), so the shuffle has to rewrite explanation prose with a pattern matcher rather than substitute placeholders. A migration to {{A}}-style placeholders would make the remap a substitution; the conservative rewrite exists precisely so that migration is not a prerequisite, but it remains the safer end state. _Surfaced in:_ specs/051-backlog-zero (while closing BL-20260606-01).
- **BL-20260906-87** — *doc-gap, high* — Amend the register for BL-20260429-03: BACKLOG.md:191 still reads "Reintroduce Blackstone NER for `_extract_entities`" with no note that Blackstone was deliberately dropped (it pins spacy==2.1.8 against this project's spacy>=3.8 and publishes no Python 3.12 wheels; upstream unmaintained since 2024-07), and BACKLOG.md:300 (BL-20260429-08) still asserts "`blackstone` now lives in `[project.optional-dependencies].nlp` in `backend/pyproject.toml`", which is false — the extra now carries only the en_core_web_sm wheel. _Surfaced in:_ specs/051-backlog-zero (while closing BL-20260429-03).
- **BL-20260906-88** — *feature, med* — Statute-citation recall on pre-change corpora: resolve_statute_citations can only read citation strings earlier ingests stored, and opinions ingested before scout._CRS_CITATION_RES landed have none for the two forms Colorado courts actually write (eyecite returns UnknownCitation('§') for "C.R.S. § 18-3-102" and nothing for "section 13-80-102, C.R.S."). Needs a re-extraction pass — persist or re-fetch opinion text, re-run _extract_citations, then MERGE — or an explicit decision that those cases are recovered only by re-ingestion. _Surfaced in:_ specs/051-backlog-zero (while closing BL-20260509-07).
- **BL-20260906-89** — *tech-debt, med* — Decimal-article CRS numbers are still invisible to three other regexes after the parser fix: citation_resolver._CRS_SECTION_RE (`\b(\d{1,2})-(\d{1,3})-(\d{1,4}(?:\.\d+)?)\b`) never matches "18-1.3-401", scout._CRS_SECTION_NUMBER has the same shape, and services/colorado_statutes._PDF_SECTION_RE truncates "18-1.3-401." to "18-1". So a case citing C.R.S. § 18-1.3-401 gets no CITES_STATUTE edge even on a fresh ingest, and the PDF fallback writes wrong section ids. The HTML parser's _SECTION_NUMBER_RE was fixed under BL-20260511-07; the other three were left alone to avoid widening scope. _Surfaced in:_ specs/051-backlog-zero (while closing BL-20260511-07).
- **BL-20260906-90** — *test-gap, med* — The Justia live drift smoke can still only ever skip: law.justia.com answers every plain HTTP client with a Cloudflare 403, so the parser has never once run against real Justia markup and the frozen fixture (tests/ingestion/fixtures/co/title_18_article_3.html) is hand-written and models an *article* page while the adapter fetches the *title index* URL. Either drive the fetch through a browser context in the nightly, or point the smoke at the already-supported COLORADO_STATUTES_PDF_BASE_URL fallback, so a drift baseline exists at all. _Surfaced in:_ specs/051-backlog-zero (while closing BL-20260511-07).
- **BL-20260906-91** — *infra, high* — tests/test_configs.py::test_ci_extras_match_dockerfile is currently RED in the shared tree and not from this group's work: backend/Dockerfile installs `.[dev,local-ai,future-auth]` while ci.yml (3 jobs), integration-tests.yml and the Makefile still install without `future-auth`. Whoever added the future-auth extra needs to propagate it. (My ci.yml edit adds `nlp` to the backend-test job only, which the same test explicitly permits — extras beyond the Dockerfile's are allowed.) _Surfaced in:_ specs/051-backlog-zero (while closing BL-20260429-03).
- **BL-20260906-92** — *tech-debt, low* — IngestionScout.run_and_commit emits the `hitl_gate_disabled` provenance event on every run while ENABLE_HUMAN_APPROVAL_GATES is False, including for high-confidence extractions that would have committed anyway, and its detail string says "low-confidence extraction committed without human review" regardless. The audit trail therefore over-reports overrides and mislabels them. Behaviour left as shipped and pinned by the new tests; worth narrowing the emission to the sub-threshold case and fixing the wording. _Surfaced in:_ specs/051-backlog-zero (while closing BL-20260810-03).
- **BL-20260906-93** — *doc-gap, med* — BL-20260503-12's BACKLOG text still names `django-ratelimit`, but the shipped mechanism is DRF's ScopedActorRateThrottle. The divergence is recorded in backend/law_ai/core/throttling.py:20 and docs/security.md, but the item line itself needs amending to say so rather than being ticked as written. I cannot edit BACKLOG.md. _Surfaced in:_ specs/051-backlog-zero (while closing BL-20260503-12).
- **BL-20260906-94** — *infra, med* — No CI workflow runs the ollama integration tests (`make test-integration-ollama`, Makefile:238) — `grep -rn 'test-integration-ollama|OLLAMA_INTEGRATION_URL' .github/` is empty. Now that tests/core/test_run_autonomy_integration.py actually executes and asserts liveness, an opt-in workflow_dispatch job that pulls a small model (qwen2.5:3b or smaller) would keep it from rotting. _Surfaced in:_ specs/051-backlog-zero (while closing BL-20260527-08).
- **BL-20260906-95** — *feature, low* — POST /api/analysis now accepts an owner-checked `matter_id` and frontend/lib/api.ts declares it, but no UI sends one — a "research within this matter" entry point on the matter page would close the last link of BL-20260817-05's loop and let a user actually see boosted_count/boost_source. _Surfaced in:_ specs/051-backlog-zero (while closing BL-20260817-05).
- **BL-20260906-96** — *tech-debt, low* — `[future-auth]` (python-jose, passlib) is now installed by backend/Dockerfile and every CI job, and law_ai.core.jwt_auth degrades to key+session only when it is absent. Consider folding the two into core `dependencies` and dropping the extra, or keeping the extra and adding a test that the degraded path (DEPENDENCIES_AVAILABLE False) behaves — today only the installed path is covered. _Surfaced in:_ specs/051-backlog-zero (while closing BL-20260503-13).
- **BL-20260906-97** — *test-gap, med* — tests/api/test_analysis.py::test_default_engine_path_never_500s_when_engine_explodes is order- and data-dependent: it asserts confidence == 0.0, which only holds while PrecedentHunter degrades. With Case nodes present in the shared dev neo4j and the driver warmed by an earlier test, the hunter succeeds and returns 0.16. Reproduced with git-HEAD copies of my changed files, so it is pre-existing. It should stub the hunter or assert on the analyst's degraded flag instead of the aggregate confidence. _Surfaced in:_ specs/051-backlog-zero (while closing BL-20260817-05).
- **BL-20260906-98** — *test-gap, high* — Four tests in backend/tests/core/test_run_autonomy.py fail on the current tree because a concurrent change added a `governance-triage` beat entry bound to law_ai.core.tasks.governance_triage: test_beat_tasks_point_at_autonomy_cycle allow-lists only autonomy_cycle/compose_digest_task, and the three TestBeatScheduleSmoke cases assume every beat entry carries kwargs['kind']. Not mine (I reproduced it before touching tasks.py) — whoever owns the governance work needs to update those tests. _Surfaced in:_ specs/051-backlog-zero (while closing BL-20260511-05).
- **BL-20260906-99** — *tech-debt, low* — An untracked stray file literally named `$L` sits at the repo root (contents are another agent's BL-20260810-05 / BL-20260810-17 log lines). Left in place because it is not mine to delete; it should not be committed. _Surfaced in:_ specs/051-backlog-zero (while closing BL-20260503-13).
