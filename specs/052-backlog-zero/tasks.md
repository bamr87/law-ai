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

- **BL-20260811-05** — *doc-gap, med* — Have counsel review the spec-030 UPL disclaimer wording and decide whether jurisdiction-specific text or a first-run click-through acknowledgement is warranted; the shipped text is engineering-authored, not legally reviewed. _Surfaced in:_ specs/030-safety-guardrails.
- **BL-20260904-03** — *doc-gap, med* — No terms-of-service / data-retention review exists for xAI as a processor of legal text; ADR 0005 accepted Anthropic's terms, nobody has done the equivalent for xAI. Complete it before BL-20260904-01 ships, since the amendment adds a second default egress path. _Surfaced in:_ docs/adr/0007-xai-runtime-provider.
- **BL-20260905-25** — *doc-gap, med* — specs/008-agent-api-auth/spec.md FR-5/FR-6 and its tasks.md still describe `NEXT_PUBLIC_AGENT_API_KEY` being read in the browser and documented in .env.example; that variable no longer exists (apiFetch sends no credential, the proxy route attaches the key). Add a dated amendment note to spec 008 pointing at `frontend/app/api/backend/[...path]/route.ts`, `frontend/app/api/ws-ticket/route.ts` and `backend/law_ai/core/ws_ticket.py`. _Surfaced in:_ specs/052-backlog-zero (while closing BL-20260430-07). _Remaining (blocked):_ The main loop owns specs/. The amendment note should point at frontend/app/api/backend/[...path]/route.ts, frontend/app/api/ws-ticket/route.ts and backend/law_ai/core/ws_ticket.py, dated 2026-09-06.
- **BL-20260905-31** — *refactor, med* — Phase 2 of the LSAT Lab decomposition: once specs/039-design-system ships frontend/ui/components/, swap the Tailwind class strings in frontend/components/lsat/{LrPanel,PassagePanel,QuestionCard,TutorPane,AuthoringPanel,StatsPanel,OverviewPanel,LabPrimitives}.tsx onto the 039 primitives (Button/Choice/Panel). Phase 1 (the behaviour-preserving split) is done; spec 039 is still Status: planned and frontend/ui/ has no components/ directory, so the 'onto frontend/ui primitives' half of BL-20260830-02 cannot land yet. _Surfaced in:_ specs/052-backlog-zero (while closing BL-20260830-02). _Remaining (blocked):_ Unblocks only when spec 039 ships frontend/ui/components/ with Button/Choice/Panel. Left in the register for the main loop; I did not touch BACKLOG.md.
- **BL-20260905-44** — *feature, med* — Human editorial pass over the 100 `LSATContentFactory build100` bank items (58 LR, 28 RC, 14 LG): each currently carries `review.method: "machine-judge"` in backend/law_ai/lsat/services/data/{lr,rc,lg}_bank.json. A reviewer who reads an item should flip its record to `editorial` with their own name; backend/tests/lsat/test_bank_review.py already enforces that machine review is never labelled editorial. _Surfaced in:_ specs/052-backlog-zero (while closing BL-20260429-19). _Remaining (blocked):_ Needs a human reviewer to read items and stamp their own name; leave in the register as a human task.
- **BL-20260905-47** — *test-gap, low* — backend/tests/lsat/test_factory_ollama_integration.py has never executed its assertions: the Docker ollama here cannot load mistral:7b (4.9 GiB needed). Run `make test-integration-ollama` on a box with enough RAM, or point OLLAMA_INTEGRATION_URL at one, and confirm the llm_call/agent_call assertions hold against a real generation. _Surfaced in:_ specs/052-backlog-zero (while closing BL-20260702-05). _Remaining (blocked):_ Skip reason is the honest one: `ollama cannot run 'qwen2.5:3b-instruct-q4_K_M': {"error":"model requires more system memory (2.5 GiB) than is available (2.4 GiB)"}` (mistral:7b needs 4.9 GiB).
- **BL-20260905-54** — *feature, low* — Bank items still carry no `archetype` field, so `select_exemplars` in `backend/law_ai/lsat/factory/blueprints.py` infers the archetype from concept overlap and now ranks by the archetype's primary concept. Stamping items with the archetype they instantiate (at authoring time, and backfilled for the 208 existing items) would make exemplar selection exact and let the coverage census report archetype counts directly instead of via a proxy concept. _Surfaced in:_ specs/052-backlog-zero (while closing BL-20260901-02). _Remaining (partial):_ The backfill of the 208 existing items is NOT done: stamping them with the value the concept proxy already infers would freeze a guess, and deciding each item's archetype is a content judgement.
- **BL-20260905-63** — *feature, low* — lr-parallel-reasoning and lr-parallel-flaw are decidable by shape-matching over schemas._shape() but need whole mini-arguments as answer choices, i.e. a structural guarantee like CausalSchema rather than a model-theoretic proof. Adding them needs authored argument pools in the domain packs (lexicon.py) the way causal_scenarios already are. _Surfaced in:_ specs/052-backlog-zero (while closing BL-20260903-13). _Remaining (blocked):_ Remains open. Needs its own spec package: a CausalSchema-style structural guarantee plus argument pools in lexicon.py + the four domain JSON packs, then flipping the coverage assertion in test_synth_generate.py:636.
- **BL-20260905-65** — *test-gap, low* — The polish prompt's real yield is now measurable but has never been measured: backend/tests/lsat/test_synth_polish_live.py stays skipped without LSAT_SYNTH_LIVE_POLISH=1, and no polish_yield.json exists. Someone should run `make lsat-synth-polish-yield` once against a pinned tier (LLM_PROVIDER_CHAIN=ollama for a free run) and record the number and its tier. _Surfaced in:_ specs/052-backlog-zero (while closing BL-20260903-17). _Remaining (blocked):_ Same RAM wall as BL-20260905-47: the ollama container reports 1.2 GiB available and the smallest pulled instruct model needs 2.5 GiB. No polish_yield.json was produced.
- **BL-20260905-66** — *tech-debt, low* — Structural-proof schemas get no difficulty proxy at all (measure() returns None), so lr-causal-weaken and lr-percent-vs-number are indistinguishable to the census and keep whatever band their author declared. A structural-only proxy — attack-pool depth, inert-fact similarity, stimulus length — would put them on some scale rather than none. _Surfaced in:_ specs/052-backlog-zero (while closing BL-20260903-14). _Remaining (blocked):_ Remains open. A safe first step would be an advisory-only ItemComplexity that the census reads but blend() ignores, so the scale exists before it is allowed to move any band.
- **BL-20260905-67** — *tech-debt, low* — Bank explanations and spec 045 guide steps in backend/law_ai/lsat/services/data/*.json are still authored with bare answer labels ('A is correct: …'), so shuffling depends on a regex rewrite. Migrating them to {{A}}-style placeholders plus a validation.py rule rejecting bare labels in new content would make the remap a substitution instead. _Surfaced in:_ specs/052-backlog-zero (while closing BL-20260606-01). _Remaining (blocked):_ Closing it means migrating 208 explanations plus 40 guides to placeholders and adding a validation rule that would reject the phrasing models naturally produce — a content migration and an authoring-contract change, not a tight sweep edit.
- **BL-20260905-72** — *feature, low* — XAI_INTERACTIVE_MODEL ships blank because choosing a faster Grok id needs a live SuperGrok subscription the suite may never touch (spec 050 AC-5). Someone with `make xai-login` should run `make validate-xai` (which now lists the served ids) plus a timed IRAC through the xai tier, pick a candidate, and record the measured latency and any IRAC-quality regression in docs/adr/0007-xai-runtime-provider.md before setting a default. _Surfaced in:_ specs/052-backlog-zero (while closing BL-20260905-11). _Remaining (blocked):_ Cannot be done from an agent run: choosing a faster Grok id needs `make validate-xai` against a real subscription plus a timed IRAC comparison, and the result belongs in docs/adr/0007. Duplicates BL-20260906-78 in substance.
- **BL-20260905-87** — *tech-debt, med* — `backend/law_ai/core/neo4j/migrations/006_derived_document.cypher` declares two property-existence constraints (`derived_document_agent_version_exists`, `derived_document_kind_exists`) that are Enterprise-only and are rejected by the pinned `neo4j:5-community` image in docker-compose.yml. `migrate_neo4j` now defers the file instead of failing, but the constraints are simply absent in every dev/CI environment, so nothing actually enforces the `DerivedDocument` provenance invariant the spec-015 tests assert on paper. _Surfaced in:_ specs/052-backlog-zero (while closing BL-20260509-02). _Remaining (partial):_ Still open: nothing enforces the invariant *in the graph*. The only real closes are running CI/dev Neo4j on Enterprise (a licensing decision, not a code change) or a write-path guard — and there is no DerivedDocument write path yet, which is why the model is the right place today.
- **BL-20260905-88** — *test-gap, low* — `backend/law_ai/core/management/commands/densify_backfill.py` and `backfill_embeddings.py` are unit-tested against fake sessions only. Add `@pytest.mark.integration` tests under `backend/tests/db/` that seed a real `(:Case)-[:HAS_CITATION]->(:Citation)` pair with a resolvable alias (and a vector-less `:Case`) and assert the `CITES` edge / `embedding` property actually lands, plus that a second `--commit` run is a no-op. _Surfaced in:_ specs/052-backlog-zero (while closing BL-20260429-11).
- **BL-20260905-91** — *infra, low* — `commit_extraction` (backend/law_ai/core/neo4j/queries.py) now makes one synchronous-in-the-await-sense embedding call per case at ingest. On a large `make ingest` run that serialises N HTTP round-trips to Ollama. Batch the embeddings per `ExtractionResult` batch via `embed_texts`, or move the embedding write to a Celery follow-up task that reuses `backfill_embeddings`. _Surfaced in:_ specs/052-backlog-zero (while closing BL-20260810-17). _Remaining (blocked):_ The Celery alternative is worse than the latency: deferring the embedding write would silently stop embedding on every path without a worker, including scripts/ingest_sample.py behind `make ingest`, and vectors would go missing rather than be slow.
- **BL-20260906-03** — *feature, low* — The `(:Case)-[:INTERPRETS]->(:StatuteSection)` edge remains declared-only in docs/data-model.md. Deciding that an opinion *construes* a section rather than merely citing it is a judgement the rule-based extractor cannot make, so it needs either an audited LLM pass or a signal-based heuristic (pin-cite depth, quotation of the section text). _Surfaced in:_ specs/052-backlog-zero (while closing BL-20260509-07). _Remaining (blocked):_ Now cheaper than it was: the --refetch pass added under BL-20260906-88 already holds the opinion body and the resolved section ids in one place, so a quotation-overlap heuristic (or an audited LLM pass behind a flag like the new INGEST_LLM_SUMMARY) has a natural home in _refetch_case.
- **BL-20260906-06** — *feature, med* — Denver ingestion has no chapter discovery: `--chapters` must be typed by hand and `parse_chapter_html` ignores the code's article/division layer, so `Ordinance` is one flat node per chapter. Add a table-of-contents parse that enumerates chapters, and decide whether articles deserve their own node or a property on `OrdinanceSection`. _Surfaced in:_ specs/052-backlog-zero (while closing BL-20260509-05). _Remaining (partial):_ The second half is untouched: the article/division layer is still absent, so Ordinance remains one flat node per chapter and an article is neither a node nor a property.
- **BL-20260906-14** — *feature, med* — Finish the drafting export: add `python-docx` and one PDF engine (weasyprint or reportlab) to backend/pyproject.toml + backend/Dockerfile, then render the structure `law_ai/matters/drafting/memo.compose_memo` already returns into DOCX and PDF behind `GET /api/matters/<slug>/memo?output=docx|pdf` (currently 501). Needs its own spec sub-package per the item, and a UPL wording review of the draft disclaimer. _Surfaced in:_ specs/052-backlog-zero (while closing BL-20260817-03). _Remaining (blocked):_ Remains open. compose_memo in law_ai/matters/drafting/memo.py already returns the structure to render; what is missing is the dependency decision, the renderers, and the UPL review.
- **BL-20260906-16** — *feature, med* — `MatterAuthority.node_id` is an unvalidated string and `MatterArtifact.analysis_id` is a string join to `AnalysisRun`. Validate a recorded authority against Neo4j (`core/neo4j/queries.py`) when the graph is reachable, and make the analysis link a real nullable FK, so an export bundle cannot point at authorities or runs that do not exist. _Surfaced in:_ specs/052-backlog-zero (while closing BL-20260817-01). _Remaining (partial):_ MatterArtifact.analysis_id is still a CharField join to AnalysisRun, not a nullable FK. Converting it needs a schema migration plus a data migration for existing rows in an app another wave-1 package owns, which is more concurrency risk than this sweep should take mid-wave; docs/data-model.md now sa…
- **BL-20260906-28** — *test-gap, high* — Record and commit the first real LegalBench baseline: on a host that can load mistral:7b-instruct-q4_K_M run `make legalbench-cache && make legalbench-baseline`, commit backend/var/legalbench/baseline.json, and fill the score/commit columns in the docs/legalbench.md "Baseline scores" table. The dataset cache and the --fail-on-synthetic gate already landed; only the numbers are missing. _Surfaced in:_ specs/052-backlog-zero (while closing BL-20260811-10). _Remaining (blocked):_ Needs a host with more free RAM for the ollama container (freeing it here would mean stopping services other agents are using, which is out of bounds for this sweep).
- **BL-20260906-33** — *infra, med* — Apply the checked-in branch-protection ruleset: `gh api -X POST repos/bamr87/law-ai/rulesets --input .github/rulesets/main-required-checks.json`. The JSON, its sync tests and the docs shipped with BL-20260815-01, but the API call is a repo-settings write that the agent permission layer denied, so `gh api repos/bamr87/law-ai/rulesets` still returns `[]` and nothing blocks a merge on a red check today. _Surfaced in:_ specs/052-backlog-zero (while closing BL-20260815-01). _Remaining (blocked):_ The owner runs exactly one command: gh api -X POST repos/bamr87/law-ai/rulesets --input .github/rulesets/main-required-checks.json. Everything else the item asks for already shipped.
- **BL-20260906-34** — *infra, med* — Prove the LegalBench scored gate green once. After this branch merges, run `gh workflow run nightly-tests.yml` and confirm 'Pull the LegalBench gate model' and 'Run LegalBench eval (regression gate)' both succeed on a hosted runner, then record the run id in docs/legalbench.md § 'CI status of the scored gate'. The workflow is re-enabled and the missing model-pull step is added, but neither the 2026-07-16 disk-space fix (613ab69) nor the new pull step has ever been exercised by an actual run. _Surfaced in:_ specs/052-backlog-zero (while closing BL-20260511-26). _Remaining (blocked):_ Remaining work, unchanged: after merge, `gh workflow run nightly-tests.yml`, confirm 'Pull the LegalBench gate model' and 'Run LegalBench eval (regression gate)' both succeed, then record the run id in docs/legalbench.md § 'CI status of the scored gate' (the placeholder paragraph is already there).
- **BL-20260906-35** — *tech-debt, low* — Decide the fate of the unmerged AM-1 auto-merge work before it is forgotten. `scripts/check_am1_eligible.py`, `tests/test_am1_eligible.py`, `.github/workflows/am1-automerge.yml` and an ADR numbered 0004 exist only on origin/claude/cranky-burnell-fd2782 (commit 7c8a0f9) and were never merged to main — main has since reused ADR number 0004 for 0004-jurisprudential-stance.md, and the org still shows a disabled 'AM-1 auto-merge' workflow. Either promote it under a fresh ADR number or record it as abandoned; the local worktree that held it has now been deleted. _Surfaced in:_ specs/052-backlog-zero (while closing BL-20260818-03). _Remaining (blocked):_ Needs an owner's call: promote the AM-1 work under a fresh ADR number, or record it abandoned. Either way it is a one-commit change once decided — the blocker is the decision, not the work.
- **BL-20260906-40** — *infra, med* — Boot the LangGraph Studio host end to end once a free LANGSMITH_API_KEY exists: `make studio-up`, confirm backend/Dockerfile.studio builds against langchain/langgraph-api:3.12 with `-c /api/constraints.txt`, that LANGSERVE_GRAPHS resolves law_ai/agents_runtime/graphs/studio.py:make_graph, and that a run steps through retrieve → analyze → cite_check in smith.langchain.com/studio. Everything but the boot is verified today. _Surfaced in:_ specs/052-backlog-zero (while closing BL-20260502-01). _Remaining (blocked):_ Blocked on exactly the precondition the item names ("once a free LANGSMITH_API_KEY exists"), plus a smith.langchain.com session to step a run through retrieve -> analyze -> cite_check. I deliberately did not half-do it by building the image without being able to boot or drive it.
- **BL-20260906-41** — *feature, med* — Wire the vLLM server (docker-compose.gpu.yml, profile `vllm`) into `law_ai/core/llm/providers.py` as an OpenAI-compatible chain tier. It serves an OpenAI API on :8001 today but nothing in the product can call it, and adding a tier is a constitution §1 amendment, not a compose change. _Surfaced in:_ specs/052-backlog-zero (while closing BL-20260502-02). _Remaining (blocked):_ Needs the AO-SDLC path: an ADR and a constitution amendment first, then the provider class, then a chain-position decision. The compose service (docker-compose.gpu.yml, profile vllm) is unaffected and still serves an OpenAI API on :8001.
- **BL-20260906-42** — *infra, med* — Validate the GPU overlay on a real Linux + NVIDIA host: `make local-ai-up-gpu` (device reservations, 70B gate model, 7200s start_period) and `make local-ai-up-server` (nvidia/dcgm-exporter, vllm/vllm-openai:v0.11.0). Both image tags and every `deploy.resources` block are currently validated only by `docker compose config`. _Surfaced in:_ specs/052-backlog-zero (while closing BL-20260502-02). _Remaining (blocked):_ Needs a machine with NVIDIA hardware; no code change can close it.
- **BL-20260906-43** — *tech-debt, low* — Retire the dead DEFAULT_MODEL / FALLBACK_MODEL settings (backend/law_ai/settings/base.py:25-26, :204-205 and .env.example) — nothing reads them, and DEFAULT_MODEL advertising llama3.1:70b-q4_K_M reads like the live knob when OLLAMA_DEFAULT_MODEL is. They are only annotated as dead right now, because base.py is shared with other in-flight packages. _Surfaced in:_ specs/052-backlog-zero (while closing BL-20260502-02). _Remaining (partial):_ Partial only because the item asked for FALLBACK_MODEL too; that request is obsolete rather than unfinished. New test `TestRetiredSettings::test_default_model_is_gone` asserts `not hasattr(django_settings, 'DEFAULT_MODEL')`.
- **BL-20260906-44** — *feature, low* — Expose a Django /metrics endpoint (django-prometheus) and add it to infra/prometheus/prometheus.yml, so API latency, error rate and Celery task outcomes join the Grafana dashboard. Today Prometheus only sees vLLM, Redis and DCGM — the app itself is invisible to the server-tier dashboard. _Surfaced in:_ specs/052-backlog-zero (while closing BL-20260502-03). _Remaining (blocked):_ Wants its own change window: add django-prometheus to backend/pyproject.toml, rebuild the image, mount /metrics, add a `law-ai` job to infra/prometheus/prometheus.yml, and add Grafana panels. Not safe to do inside a concurrent wave.
- **BL-20260906-46** — *doc-gap, med* — A human must read xAI's legal pages in a browser (x.ai/legal/terms-of-service, x.ai/legal/privacy-policy, x.ai/legal/europe-privacy-policy-addendum) and record the decision in docs/adr/0007-xai-runtime-provider.md's 'Terms-of-service and data-retention review' section, replacing the draft, plus the outcome in docs/constitution.md §1's xAI amendment block. The pages 403 automated fetches, so no agent can close this. Until then the default LLM_PROVIDER_CHAIN keeps a second unreviewed third-party egress path (settings/base.py:35). _Surfaced in:_ specs/052-backlog-zero (while closing BL-20260904-03). _Remaining (blocked):_ By construction not closable by an agent: x.ai/legal/terms-of-service, /privacy-policy and /europe-privacy-policy-addendum 403 automated fetches, and the ADR itself says the acceptance is the owner's to give.
- **BL-20260906-47** — *tech-debt, low* — scripts/spec_validator.py has no 'superseded' status: SHIPPED_STATUSES = {'shipped'} and the symmetric check errors when every task is [x] but the status is anything else, so specs/025-lsat-static-site/spec.md had to keep '- **Status**: shipped — **superseded**'. Add 'superseded' to SHIPPED_STATUSES (and to the status enum in specs/_template/spec.md) so a retired spec can say so in the field the validator reads. _Surfaced in:_ specs/052-backlog-zero (while closing BL-20260716-11). _Remaining (partial):_ Remaining: the status enum line specs/_template/spec.md:4 (`draft | clarified | planned | in-progress | shipped`) should gain `| superseded`, and specs/025-lsat-static-site/spec.md can drop its '- **Status**: shipped — **superseded**' workaround.
- **BL-20260906-55** — *feature, low* — Node size on the graph is now CITES in-degree *within the rendered neighbourhood* (BL-20260803-03), which changes as you traverse. If a corpus-wide citation count is ever wanted, it needs a backend field on the :Case node plus the same litigation-frequency labelling in GraphViewer's aria-label and KnowledgeGraph's Legend. _Surfaced in:_ specs/052-backlog-zero (while closing BL-20260803-03). _Remaining (blocked):_ Not obsolete (the description of today's behaviour is accurate) and not actionable: it is a design note gated on a product decision. Should stay in the register as an option, not a defect.
- **BL-20260906-58** — *tech-debt, low* — Clear the remaining 34 non-`lsat/urls.py` entries in `backend/mypy-baseline.txt` app by app: `agentsapi/urls.py` (8), `lsat/services/bank.py` (5), `ingestionapp/services/courtlistener.py` (3), `core/auth.py` (3), `agents_runtime/graphs/runtime.py` (3, `BaseCheckpointSaver` missing type args), `celery.py`/`core/tasks.py`/`ingestionapp/tasks.py` (2 each), plus six single-error files. When the baseline reaches zero, delete it and drop the ratchet call from `Makefile` and `.github/workflows/ci.yml` so plain `mypy law_ai --strict` is the gate — `scripts/mypy_ratchet.py` prints that instruction itself. _Surfaced in:_ specs/052-backlog-zero (while closing BL-20260429-04). _Remaining (blocked):_ Wants a single-owner pass on a quiet tree: burn the files down app by app, `make mypy-baseline` once at the end, then delete the file and drop the ratchet call from the Makefile and ci.yml (scripts/mypy_ratchet.py prints that instruction itself).
- **BL-20260906-59** — *tech-debt, low* — Celery publishes no type stubs, so `celery.*` sits in the `ignore_missing_imports` override in `backend/pyproject.toml` and every `@shared_task` produces an `untyped-decorator` error (6 of the 59 baseline entries, in `law_ai/celery.py`, `core/tasks.py`, `ingestionapp/tasks.py`). Evaluate `celery-types` as a dev dep; if accurate enough it clears those and lets the override drop `celery.*`. _Surfaced in:_ specs/052-backlog-zero (while closing BL-20260429-04). _Remaining (blocked):_ Needs an operator-approved image change: add celery-types to the backend dev deps, rebuild, drop "celery.*" from the ignore_missing_imports override in backend/pyproject.toml, then re-bank the baseline. Best done between waves, not while other agents share the image.
- **BL-20260906-60** — *infra, low* — `backend/mypy-baseline.txt` carries a global `# total:` header, so two PRs that each burn a different file down conflict on that one line. If that becomes annoying, drop the header total and relax `tests/test_mypy_ratchet.py::TestCommittedBaseline::test_header_total_matches_the_entries`, or teach `scripts/mypy_ratchet.py --update` to merge per-file entries rather than rewrite the file. _Surfaced in:_ specs/052-backlog-zero (while closing BL-20260429-04). _Remaining (blocked):_ The item's own trigger ('if that becomes annoying') has not fired. If it ever does, dropping the header total is the cheap option, but it costs the half-edit cross-check.
- **BL-20260906-64** — *doc-gap, low* — CLAUDE.md's command table still describes `make lint-specs` as "host stdlib, no container"; since BL-20260511-14 it also runs `python3 -m pytest tests/test_evolve_audit.py`, so it needs pytest on the host interpreter. AGENTS.md and tests/README.md were corrected; CLAUDE.md was deliberately left alone (agents must not edit it). _Surfaced in:_ specs/052-backlog-zero (while closing BL-20260511-14). _Remaining (blocked):_ Needs the repo owner to edit CLAUDE.md line 34, e.g. `make lint-specs` (host; needs pytest on the host interpreter). AGENTS.md:265 and tests/README.md:36,45 already carry the corrected description, so the only stale copy is CLAUDE.md.
- **BL-20260906-65** — *tech-debt, med* — The a11y baseline still amnesties re-use of an already-accepted colour pair: new text painted `#62748e` on a dark slate ground passes because that signature is recorded. The only real close is paying off the contrast debt (`text-slate-500` on `bg-slate-950`/`bg-slate-900`) and emptying frontend/e2e/a11y-baseline.json, at which point any color-contrast violation fails outright. _Surfaced in:_ specs/052-backlog-zero (while closing BL-20260831-09). _Remaining (partial):_ To finish: catch the /agents red badge with a seeded failed run (it is almost certainly the `text-red-300` on `bg-red-500/20` badge in agents/RunRow.tsx or RunDetailModal.tsx) and close BL-20260906-66. The file is then empty and the rule can drop its amnesty entirely.
- **BL-20260906-66** — *tech-debt, med* — Adding /matters to the a11y sweep surfaced a `scrollable-region-focusable` violation on `#main` for that route — the shell's scroller has no keyboard entry point there. It is now baselined as known debt rather than fixed. _Surfaced in:_ specs/052-backlog-zero (while closing BL-20260831-09). _Remaining (blocked):_ Two candidate fixes, both in files other wave-3 groups are editing right now: (a) `tabindex="0"` on #main in the shell — one attribute, the canonical a11y answer for a scrollable region, but it adds a tab stop on all seven routes and would change the tab order the specs I just touched assert on; (b)…
- **BL-20260906-67** — *infra, med* — The new ci.yml `a11y` job boots the whole compose stack (both app images) on every PR touching frontend/. The nightly had to drop from daily to weekly over runner disk exhaustion, which is why the job reclaims ~25 GB of preinstalled toolchains first — but nobody has watched it run yet. Check its first few PR runs for runtime and disk, and consider a prebuilt image or a cached build if it is marginal. _Surfaced in:_ specs/052-backlog-zero (while closing BL-20260831-09). _Remaining (blocked):_ Do it after the branch opens a PR: check the a11y job's wall time and post-cleanup free disk on its first two or three runs, and consider a prebuilt image or a cached build if it is marginal.
- **BL-20260906-70** — *test-gap, low* — The governance triage now has two homes (the Celery beat entry and the nightly workflow step) writing the same titled issue under the same label. Idempotency across the two is argued in docs/ao-sdlc.md and unit-tested for the library path, but nothing exercises the shell step's `gh` branch — a live smoke (or nektos/act run) of the nightly triage step would close that. _Surfaced in:_ specs/052-backlog-zero (while closing BL-20260503-14). _Remaining (blocked):_ Wants either an `act` run of the triage step against a throwaway repo, or a deliberate live run on a scratch label with the issue cleaned up afterwards. Both need an owner's go-ahead to write to GitHub.
- **BL-20260906-76** — *feature, low* — LSAT item authoring (lsat_content_author._generate, measured at 68s on the xAI tier) still buffers its call: it now passes the interactive model override but does not stream. Give it the same delta relay the IRAC path got (llm.astream + an emit_stream_event sink keyed on a stream_id) so the authoring wait is visible too; the same applies to lsat/services/crosscheck.py and lsat_writing_evaluator.py. _Surfaced in:_ specs/052-backlog-zero (while closing BL-20260905-11). _Remaining (partial):_ Not done: the same relay for lsat/services/crosscheck.py and lsat_writing_evaluator.py, and the client half — AuthoringPanel does not open a WebSocket before calling generateLsatProposals, so the backend deltas have no subscriber yet. Filed as a follow-up.
- **BL-20260906-77** — *tech-debt, low* — Streamed analysis deltas write one ws_event_sent provenance row per chunk and each consumes a slot in the 200-event replay buffer, so a long IRAC answer can evict the run's earlier agent_step frames for a reconnecting client. The LSAT tutor has the same shape; consider coalescing token events (time- or size-bucketed) in law_ai/agentsapi/streaming.py, or exempting them from the replay buffer. _Surfaced in:_ specs/052-backlog-zero (while closing BL-20260905-11). _Remaining (partial):_ Still outstanding: each delta continues to write one `ws_event_sent` provenance row. I left that alone deliberately — every coalescing scheme I could write tightly either needed a payload field the two producers do not share (`analysis_token` carries cumulative `chars`, `tutor_token` does not) or pe…
- **BL-20260906-78** — *feature, low* — No Grok-variant latency/quality evaluation exists, so XAI_INTERACTIVE_MODEL still ships blank: an operator with a live subscription should measure at least one non-reasoning candidate against grok-4.6 on an IRAC question and an LSAT authoring run and record the numbers (or a reasoned 'none suitable') in docs/adr/0007. It needs live billed calls, so it cannot be done from CI or an agent run. _Surfaced in:_ specs/052-backlog-zero (while closing BL-20260905-11). _Remaining (blocked):_ Cannot be run from CI or an agent session. An operator with `make xai-login` done needs to time an IRAC question and an LSAT authoring run per candidate and record the numbers (or a reasoned 'none suitable') in docs/adr/0007.
- **BL-20260906-79** — *tech-debt, low* — LegalAnalyst's direct-LLM path now runs one lexical GraphRAG query per model-named authority (previously only for the ones the alias resolver missed) because §13 attribution needs the passage behind a resolved :Case id. Batch the lookups into one query, or have the citation resolver return court/decided_at alongside the id, if the extra round trips show up in analysis latency. _Surfaced in:_ specs/052-backlog-zero (while closing BL-20260803-04). _Remaining (blocked):_ Remains open. The clean shape is a separate resolve_citation_details() returning {name: {id, court, decided_at, jurisdiction_code}} alongside the existing id-only resolver, with _name_lookup called only for names that came back without court+decided_at.
- **BL-20260906-83** — *test-gap, med* — The polish prompt's yield is now measured against the free local tier only (30/30 = 1.00 on ollama/qwen2.5:3b-instruct-q4_K_M, committed at backend/var/lsat_synth/polish_yield.json). Yield is not comparable across tiers, so the hosted tiers (Claude, xAI) are still uncalibrated and the 0.50 floor is unvalidated for the chain's default first tier. Run `make lsat-synth-polish-yield` once against the default chain and commit the second report alongside the local one. _Surfaced in:_ specs/052-backlog-zero (while closing BL-20260903-17). _Remaining (blocked):_ Needs an operator to run `make lsat-synth-polish-yield` once with hosted credentials and commit the second report next to the local one. Keep it open in the register.
- **BL-20260906-86** — *tech-debt, low* — Bank content is still authored with bare answer labels ('A is correct: …', '(D) is the exception'), so the shuffle has to rewrite explanation prose with a pattern matcher rather than substitute placeholders. A migration to {{A}}-style placeholders would make the remap a substitution; the conservative rewrite exists precisely so that migration is not a prerequisite, but it remains the safer end state. _Surfaced in:_ specs/052-backlog-zero (while closing BL-20260606-01). _Remaining (blocked):_ Remains open as the safer end state. Needs a migration script over backend/law_ai/lsat/services/data/*.json, a re-export of lsat-static/content.json, and the simplification of remap_labels once no bare labels remain.
- **BL-20260906-87** — *doc-gap, high* — Amend the register for BL-20260429-03: BACKLOG.md:191 still reads "Reintroduce Blackstone NER for `_extract_entities`" with no note that Blackstone was deliberately dropped (it pins spacy==2.1.8 against this project's spacy>=3.8 and publishes no Python 3.12 wheels; upstream unmaintained since 2024-07), and BACKLOG.md:300 (BL-20260429-08) still asserts "`blackstone` now lives in `[project.optional-dependencies].nlp` in `backend/pyproject.toml`", which is false — the extra now carries only the en_core_web_sm wheel. _Surfaced in:_ specs/052-backlog-zero (while closing BL-20260429-03). _Remaining (blocked):_ For the main loop: amend BACKLOG.md:484 so BL-20260429-08 reads that blackstone was REMOVED from the nlp extra rather than moved into it, and that the extra now carries only the en_core_web_sm wheel (docs/related-github-repos.md:131 already states this correctly).
- **BL-20260906-90** — *test-gap, med* — The Justia live drift smoke can still only ever skip: law.justia.com answers every plain HTTP client with a Cloudflare 403, so the parser has never once run against real Justia markup and the frozen fixture (tests/ingestion/fixtures/co/title_18_article_3.html) is hand-written and models an *article* page while the adapter fetches the *title index* URL. Either drive the fetch through a browser context in the nightly, or point the smoke at the already-supported COLORADO_STATUTES_PDF_BASE_URL fallback, so a drift baseline exists at all. _Surfaced in:_ specs/052-backlog-zero (while closing BL-20260511-07). _Remaining (blocked):_ The frozen fixture's second problem is real and independent: tests/ingestion/fixtures/co/title_18_article_3.html is hand-written and models an *article* page while the adapter fetches the *title index* URL, so even a working fetch would be compared against the wrong shape.
- **BL-20260906-97** — *test-gap, med* — tests/api/test_analysis.py::test_default_engine_path_never_500s_when_engine_explodes is order- and data-dependent: it asserts confidence == 0.0, which only holds while PrecedentHunter degrades. With Case nodes present in the shared dev neo4j and the driver warmed by an earlier test, the hunter succeeds and returns 0.16. Reproduced with git-HEAD copies of my changed files, so it is pre-existing. It should stub the hunter or assert on the analyst's degraded flag instead of the aggregate confidence. _Surfaced in:_ specs/052-backlog-zero (while closing BL-20260817-05).
- **BL-20260907-01** — *infra, med* — Ingest embeds one case at a time over one HTTP round trip each, and no batching is possible with the current transport: law_ai.core.llm.embeddings.embed_texts loops POSTs against Ollama's single-prompt /api/embeddings, and commit_extraction/run_and_commit have no batch entry point above them. Either switch embed_texts to Ollama's array-input /api/embed (one call for N texts, needs a response-shape change and a dimension check per entry) or introduce a real batch commit path so a large `make ingest` stops serialising N generations. _Surfaced in:_ specs/052-backlog-zero (while closing BL-20260905-91).
- **BL-20260907-02** — *tech-debt, med* — Backfill the archetype stamp onto the 208 pre-existing bank items. Question.archetype now exists and is stamped at promotion (BL-20260905-54), but every item authored before it still has archetype=None, so the coverage census and exemplar selection keep the primary-concept proxy as a fallback and archetype counts stay approximate. Needs a decision per item (the proxy's inference is a guess, not evidence) plus a one-shot migration command and a test that the census reports stamped counts directly. _Surfaced in:_ specs/052-backlog-zero (while closing BL-20260905-54).
- **BL-20260907-03** — *feature, med* — Finish the interactive-streaming pass for LSAT: relay deltas from lsat/services/crosscheck.py and agents_runtime/crews/lsat_writing_evaluator.py the way lsat_content_author now does, and open the client half — AuthoringPanel must subscribe to /ws/agents/<stream_id> before calling generateLsatProposals and render authoring_token deltas, or the backend relay added for BL-20260906-76 has no subscriber and the 68-second authoring wait still looks like a spinner. _Surfaced in:_ specs/052-backlog-zero (while closing BL-20260906-76).
- **BL-20260907-04** — *tech-debt, med* — The mypy strict ratchet now reports zero errors across law_ai while backend/mypy-baseline.txt still allows 34, and scripts/mypy_ratchet.py itself prints "Zero strict errors. Delete backend/mypy-baseline.txt and drop the ratchet so `mypy law_ai --strict` is the gate on its own." Fourteen files are listed as reclaimable slack. Until the baseline is dropped, a file can regress by up to its banked allowance without failing CI — the ratchet is currently weaker than the code deserves. _Surfaced in:_ specs/052-backlog-zero (while closing BL-20260906-23 / BL-20260906-26 (running the ratchet to check my files added no strict errors)).
- **BL-20260907-05** — *tech-debt, med* — GET /api/lsat/questions reports `count` as the size of the returned sample, not the size of the matching pool, and above its hard cap of 25 it returns `random.sample(pool, 25)` — so a caller cannot distinguish '25 of 25' from '25 of 60', and gets a different 25 on each request. Any client that treats the response as the complete answer to a filter is silently wrong (that is how BL-20260906-74 arose). Either report the pool size in a separate field, or make the endpoint say it truncated. _Surfaced in:_ specs/052-backlog-zero (while closing BL-20260906-74).
- **BL-20260907-06** — *feature, med* — Ordinances are now retrievable but semantically invisible: the new ordinance leg in GraphRAGRetriever is lexical-only because migration 008 creates vector indexes for :Case and :StatuteSection only, and neither the ingest path nor `manage.py backfill_embeddings` writes an `embedding` onto :OrdinanceSection. Municipal code is the label most likely to be asked about in words the drafters never used ("can the city tow my car from my own driveway?"), so lexical-only under-recalls it exactly where it matters. _Surfaced in:_ specs/052-backlog-zero (while closing BL-20260906-07).
- **BL-20260907-07** — *tech-debt, med* — Finish the phoenix_trace_url -> trace_url deprecation across the LSAT surface so the old name can eventually be dropped. /api/analysis now emits both names identically and the Analysis Studio prefers the new one, but the LSAT tutor still emits only the old spelling (backend/law_ai/lsat/services/tutor.py:210 and :768) and frontend/components/lsat/TutorPane.tsx:131 reads only that, so `phoenix_trace_url` cannot be removed while a client still depends on it. _Surfaced in:_ specs/052-backlog-zero (while closing BL-20260906-10).
- **BL-20260907-08** — *test-gap, med* — No end-to-end coverage of the browser session round-trip now that the proxy forwards cookies (BL-20260906-08). The RTL tests run against MSW and the proxy tests stub fetch, so nothing exercises Next -> Django with a real csrftoken/sessionid: a Django CSRF or cookie-attribute change (SESSION_COOKIE_SAMESITE, a future CSRF_TRUSTED_ORIGINS requirement, SECURE flags in prod) would break sign-in with every unit test still green. A Playwright case in frontend/e2e that signs in as a seeded user through /api/backend and asserts /api/auth/me comes back authenticated would close it. _Surfaced in:_ specs/052-backlog-zero (while closing BL-20260906-08).
- **BL-20260907-09** — *feature, med* — The /settings scope chooser offers 'Instance defaults' to every signed-in user, not only staff (frontend/components/shell/SettingsForm.tsx:96, gated on userScope alone). The server refuses a non-admin instance write, but the client writes the row locally first and mirrors optimistically, so a non-staff user who picks that scope ends up with a local instance row the instance does not actually have — the UI shows a value nobody else will ever inherit, with no error. _Surfaced in:_ specs/052-backlog-zero (while closing BL-20260906-17).
- **BL-20260907-10** — *feature, med* — The intro band can now be generated but the bank has not been fed from it: `lg-sequencing-one-rule` and `lr-conditional-one-step` exist, yet the intro depth in backend/law_ai/lsat/services/data/*_bank.json is still whatever was hand-authored, and test_bank_bands.py's floor is held by hand. Run a promotion batch of intro items through `lsat_synth generate --emit bank --promote` (or the review queue) so the intro band has generator-backed depth in both MCQ sections, and record the promotion in the audit trail. _Surfaced in:_ specs/052-backlog-zero (while closing BL-20260905-50).
- **BL-20260907-11** — *infra, med* — The `BL-YYYYMMDD-NN` id scheme caps at 99 items per discovery date, and the 2026-09-05/06 backlog-zero sweep exhausted both days, so its last ten follow-ups carry 2026-09-07 ids despite being discovered on the 6th (noted in Triage rules below). Widen the ordinal to three digits in `scripts/backlog_lint.py`'s `BULLET_RE` and the Conventions table, or accept the date drift and say so. _Surfaced in:_ specs/052-backlog-zero (while closing the follow-up sweep).
