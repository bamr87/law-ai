# Spec: Backlog Zero

- **ID**: 051-backlog-zero
- **Status**: in-progress
- **Owner**: @bamr87
- **Created**: 2026-09-05
- **Roadmap Epic**: [BACKLOG.md](../../BACKLOG.md) triage rule 2 (items unclaimed for more than 60 days are reviewed and either closed or escalated)
- **Constitution Compliance**: confirmed against [docs/constitution.md](../../docs/constitution.md)

## 1. Problem & Motivation

The backlog had grown to 237 open and 20 claimed items, the oldest from April 2026. A register that large stops being a task graph and becomes an archive: the `/evolve` picker samples it, but nobody reads it end to end, so duplicates accumulate (three separate asks for an `lsat-static` test runner), shipped work stays listed as open (spec 048 and 049 deliverables), and the small items that would unblock whole families (the static test runner, the Playwright harness, user accounts) never get picked because each is individually unglamorous. This spec is a single sweep to take the register to zero: verify every item against the code, close what is already done or moot with evidence, and implement the rest in dependency order.

## 2. Goals

- G1: Every item that was open or claimed on 2026-09-05 ends in `## Done` with evidence, or is explicitly recorded as blocked on a human decision. Items claimed by this spec: BL-20260831-18, BL-20260831-08, BL-20260901-07, BL-20260901-11, BL-20260831-26, BL-20260903-07, BL-20260905-03, BL-20260905-04, BL-20260831-22, BL-20260831-19, BL-20260831-20, BL-20260831-25, BL-20260901-05, BL-20260702-10, BL-20260831-24, BL-20260503-04, BL-20260811-16, BL-20260429-27, BL-20260430-11, BL-20260831-05, BL-20260831-09, BL-20260503-17, BL-20260901-03, BL-20260831-01, BL-20260831-11, BL-20260905-07, BL-20260831-06, BL-20260831-14, BL-20260905-08, BL-20260905-09, BL-20260831-02, BL-20260430-07, BL-20260901-10, BL-20260830-02, BL-20260831-15, BL-20260830-04, BL-20260829-01, BL-20260829-02, BL-20260831-13, BL-20260905-02, BL-20260503-07, BL-20260702-13, BL-20260901-08, BL-20260901-06, BL-20260901-09, BL-20260905-01, BL-20260905-06, BL-20260903-05, BL-20260830-13, BL-20260831-27, BL-20260503-06, BL-20260702-06, BL-20260830-14, BL-20260702-08, BL-20260702-01, BL-20260702-02, BL-20260702-03, BL-20260702-04, BL-20260702-05, BL-20260901-04, BL-20260905-13, BL-20260831-28, BL-20260429-19, BL-20260903-09, BL-20260903-06, BL-20260903-08, BL-20260901-02, BL-20260503-02, BL-20260901-01, BL-20260831-23, BL-20260810-08, BL-20260527-06, BL-20260606-02, BL-20260702-07, BL-20260831-21, BL-20260527-05, BL-20260903-15, BL-20260903-17, BL-20260903-14, BL-20260903-16, BL-20260903-13, BL-20260606-01, BL-20260811-22, BL-20260905-12, BL-20260810-05, BL-20260810-15, BL-20260811-21, BL-20260811-23, BL-20260811-24, BL-20260904-04, BL-20260904-05, BL-20260904-06, BL-20260905-11, BL-20260811-20, BL-20260811-26, BL-20260811-15, BL-20260429-16, BL-20260811-14, BL-20260503-03, BL-20260503-01, BL-20260429-18, BL-20260511-21, BL-20260511-31, BL-20260615-02, BL-20260811-28, BL-20260511-06, BL-20260615-03, BL-20260803-02, BL-20260810-18, BL-20260811-25, BL-20260811-27, BL-20260527-04, BL-20260803-04, BL-20260810-13, BL-20260830-15, BL-20260429-12, BL-20260526-01, BL-20260429-11, BL-20260429-22, BL-20260429-23, BL-20260509-02, BL-20260509-03, BL-20260810-17, BL-20260429-06, BL-20260503-10, BL-20260511-09, BL-20260602-01, BL-20260810-03, BL-20260429-03, BL-20260509-06, BL-20260511-07, BL-20260511-08, BL-20260602-07, BL-20260811-02, BL-20260811-03, BL-20260803-01, BL-20260810-19, BL-20260509-07, BL-20260811-01, BL-20260509-05, BL-20260503-13, BL-20260429-25, BL-20260429-26, BL-20260811-06, BL-20260503-12, BL-20260430-12, BL-20260830-07, BL-20260503-23, BL-20260502-07, BL-20260811-07, BL-20260810-10, BL-20260811-04, BL-20260503-05, BL-20260817-04, BL-20260817-05, BL-20260817-01, BL-20260817-02, BL-20260817-03, BL-20260830-08, BL-20260905-10, BL-20260511-11, BL-20260511-23, BL-20260511-05, BL-20260511-29, BL-20260511-03, BL-20260511-04, BL-20260511-19, BL-20260527-08, BL-20260511-14, BL-20260511-15, BL-20260526-02, BL-20260811-09, BL-20260811-10, BL-20260811-11, BL-20260811-12, BL-20260810-04, BL-20260502-08, BL-20260503-14, BL-20260503-25, BL-20260511-18, BL-20260511-26, BL-20260615-04, BL-20260811-17, BL-20260811-29, BL-20260815-01, BL-20260815-02, BL-20260815-04, BL-20260818-02, BL-20260818-03, BL-20260905-05, BL-20260702-11, BL-20260817-08, BL-20260502-01, BL-20260502-02, BL-20260502-06, BL-20260502-03, BL-20260602-02, BL-20260602-03, BL-20260702-12, BL-20260716-11, BL-20260811-19, BL-20260831-29, BL-20260904-07, BL-20260503-08, BL-20260803-05, BL-20260602-04, BL-20260904-03, BL-20260527-07, BL-20260811-18, BL-20260830-01, BL-20260831-03, BL-20260831-07, BL-20260831-10, BL-20260511-17, BL-20260810-16, BL-20260831-12, BL-20260803-03, BL-20260429-04.
- G2: Foundations that unblock families land first: the `lsat-static` Vitest runner (BL-20260831-18), the Playwright harness (BL-20260811-16), user accounts (BL-20260503-13), persisted analyses (BL-20260429-25), and chain streaming (BL-20260811-20).
- G3: Every closure is verified adversarially before it moves to `## Done`, so the register stays trustworthy.
- G4: The quality gates stay green throughout: lint, typecheck (no new mypy errors against the recorded baseline), the backend, frontend, and root suites, and `make lint-specs`.

## 3. Non-Goals

- NG1: Items whose remaining work is a human decision (counsel review of the UPL disclaimer wording, BL-20260811-05; the owner's acceptance of xAI as a processor of legal text, BL-20260904-03) are prepared for that decision but not closed by engineering.
- NG2: No new LLM vendor, framework, or runtime dependency outside constitution section 2.
- NG3: No spec-039 palette or component-library work; the LSAT Lab decomposition is a behaviour-preserving split only.

## 4. User Stories

- As the repo owner, I want the backlog to describe only work that is genuinely outstanding, so that `/evolve` and human triage pick real tasks.
- As a learner on the static site, I want the keyboard, writing, and library behaviour to be covered by real component tests, so that regressions are caught before deploy.
- As an operator, I want accounts, persisted analyses, and streaming to exist, so that the platform features specified in 036 and 022 stop being blocked on foundations.

## 5. Functional Requirements

Use stable IDs; `tasks.md` references these.

- **FR-P01**: Package group P01 (P01_lsat_static): lsat-static test runner, component tests, and static-site polish. Resolves BL-20260831-18, BL-20260831-08, BL-20260901-07, BL-20260901-11, BL-20260831-26, BL-20260903-07, BL-20260905-03, BL-20260905-04, BL-20260831-22, BL-20260831-19, BL-20260831-20, BL-20260831-25, BL-20260901-05, BL-20260702-10, BL-20260831-24, BL-20260503-04.
- **FR-P02**: Package group P02 (P02_e2e): Playwright end-to-end harness and the browser-level checks that were blocked on it. Resolves BL-20260811-16, BL-20260429-27, BL-20260430-11, BL-20260831-05, BL-20260831-09, BL-20260503-17, BL-20260901-03.
- **FR-P03**: Package group P03 (P03_shell): app-shell navigation, layout menu, dock, modules menu, and first-paint layout preferences. Resolves BL-20260831-01, BL-20260831-11, BL-20260905-07, BL-20260831-06, BL-20260831-14, BL-20260905-08, BL-20260905-09, BL-20260831-02, BL-20260430-07, BL-20260901-10.
- **FR-P04**: Package group P04 (P04a_lsat_lab_refactor, P04b_lsat_lab_features): LSAT Lab decomposition, timer consolidation, keyboard drill parity, writing surface, and concept deep links. Resolves BL-20260830-02, BL-20260831-15, BL-20260830-04, BL-20260829-01, BL-20260829-02, BL-20260831-13, BL-20260905-02, BL-20260503-07, BL-20260702-13, BL-20260901-08, BL-20260901-06, BL-20260901-09, BL-20260905-01, BL-20260905-06, BL-20260903-05, BL-20260830-13, BL-20260831-27, BL-20260503-06, BL-20260702-06, BL-20260830-14.
- **FR-P05**: Package group P05 (P05a_lsat_factory, P05b_lsat_library_data, P05c_lsat_proposals, P05d_lsat_synth): LSAT content factory, proposals persistence, library search and audit, synthesis engine growth, and bank content. Resolves BL-20260702-08, BL-20260702-01, BL-20260702-02, BL-20260702-03, BL-20260702-04, BL-20260702-05, BL-20260901-04, BL-20260905-13, BL-20260831-28, BL-20260429-19, BL-20260903-09, BL-20260903-06, BL-20260903-08, BL-20260901-02, BL-20260503-02, BL-20260901-01, BL-20260831-23, BL-20260810-08, BL-20260527-06, BL-20260606-02, BL-20260702-07, BL-20260831-21, BL-20260527-05, BL-20260903-15, BL-20260903-17, BL-20260903-14, BL-20260903-16, BL-20260903-13, BL-20260606-01.
- **FR-P06**: Package group P06 (P06a_llm_core, P06b_streaming): provider-chain hardening, xAI tier checks, and streaming through the chain to the WebSocket consumer. Resolves BL-20260811-22, BL-20260905-12, BL-20260810-05, BL-20260810-15, BL-20260811-21, BL-20260811-23, BL-20260811-24, BL-20260904-04, BL-20260904-05, BL-20260904-06, BL-20260905-11, BL-20260811-20, BL-20260811-26, BL-20260811-15, BL-20260429-16, BL-20260811-14, BL-20260503-03, BL-20260503-01, BL-20260429-18.
- **FR-P07**: Package group P07 (P07a_agents, P07b_graph, P07c_ingestion, P07d_extraction): agent crews, GraphRAG and citation resolver, Neo4j migrations, ingestion sources and quarantine loop. Resolves BL-20260511-21, BL-20260511-31, BL-20260615-02, BL-20260811-28, BL-20260511-06, BL-20260615-03, BL-20260803-02, BL-20260810-18, BL-20260811-25, BL-20260811-27, BL-20260527-04, BL-20260803-04, BL-20260810-13, BL-20260830-15, BL-20260429-12, BL-20260526-01, BL-20260429-11, BL-20260429-22, BL-20260429-23, BL-20260509-02, BL-20260509-03, BL-20260810-17, BL-20260429-06, BL-20260503-10, BL-20260511-09, BL-20260602-01, BL-20260810-03, BL-20260429-03, BL-20260509-06, BL-20260511-07, BL-20260511-08, BL-20260602-07, BL-20260811-02, BL-20260811-03, BL-20260803-01, BL-20260810-19, BL-20260509-07, BL-20260811-01, BL-20260509-05.
- **FR-P08**: Package group P08 (P08_accounts_core, P08w2_matters): user accounts, persisted analyses, share links, settings persistence, matters and drafting exports. Resolves BL-20260503-13, BL-20260429-25, BL-20260429-26, BL-20260811-06, BL-20260503-12, BL-20260430-12, BL-20260830-07, BL-20260503-23, BL-20260502-07, BL-20260811-07, BL-20260810-10, BL-20260811-04, BL-20260503-05, BL-20260817-04, BL-20260817-05, BL-20260817-01, BL-20260817-02, BL-20260817-03, BL-20260830-08, BL-20260905-10.
- **FR-P09**: Package group P09 (P09a_autonomy, P09b_eval): autonomy loop persistence and views, LegalBench fetch/baseline/scoring, root-test alignment. Resolves BL-20260511-11, BL-20260511-23, BL-20260511-05, BL-20260511-29, BL-20260511-03, BL-20260511-04, BL-20260511-19, BL-20260527-08, BL-20260511-14, BL-20260511-15, BL-20260526-02, BL-20260811-09, BL-20260811-10, BL-20260811-11, BL-20260811-12, BL-20260810-04.
- **FR-P10**: Package group P10 (P10a_infra, P10b_local_ai, P10c_docs): CI gates, devcontainers, compose overlays, local-AI packaging, documentation and spec-process fixes. Resolves BL-20260502-08, BL-20260503-14, BL-20260503-25, BL-20260511-18, BL-20260511-26, BL-20260615-04, BL-20260811-17, BL-20260811-29, BL-20260815-01, BL-20260815-02, BL-20260815-04, BL-20260818-02, BL-20260818-03, BL-20260905-05, BL-20260702-11, BL-20260817-08, BL-20260502-01, BL-20260502-02, BL-20260502-06, BL-20260502-03, BL-20260602-02, BL-20260602-03, BL-20260702-12, BL-20260716-11, BL-20260811-19, BL-20260831-29, BL-20260904-07, BL-20260503-08, BL-20260803-05, BL-20260602-04, BL-20260904-03.
- **FR-P11**: Package group P11 (P11_frontend_other): dashboard, analysis studio, and knowledge-graph component fixes. Resolves BL-20260527-07, BL-20260811-18, BL-20260830-01, BL-20260831-03, BL-20260831-07, BL-20260831-10, BL-20260511-17, BL-20260810-16, BL-20260831-12, BL-20260803-03.
- **FR-P12**: Package group P12 (P12_mypy): mypy strict ratchet with django-stubs and a CI baseline. Resolves BL-20260429-04.

## 6. Non-Functional Requirements

- **NFR-AUDIT-1**: Every new LLM call, tool use, and retrieval path added by this sweep logs through `law_ai.core.provenance`; model calls go through `law_ai.core.llm`.
- **NFR-HITL-1**: Any new agent output path without an existing verification gate declares `human_approval_required`; ingestion and proposal paths keep their HITL queues. No direct-write path is added beyond the spec-049 proved-item exemption.
- **NFR-GATES-1**: `make lint`, `make typecheck` (no new errors against the 2026-09-05 mypy baseline of 210), `make test`, the root structural suite, and `make lint-specs` pass at the end of every wave.
- **NFR-DOCKER-1**: Every test, lint, and type-check command runs inside Docker via the Makefile or `docker compose run`; no host toolchains.

## 7. Data Model Impact

Postgres: user accounts on API tokens (spec 036 T-013 shape), persisted `Analysis` rows with trace ids, share links, setting values, LSAT attempt history, LSAT proposal persistence, autonomy runs, matter tasks. Neo4j: migration runner and vector index migration (BL-20260509-02, BL-20260810-17), citation resolver improvements. Every new node keeps `source`, `confidence`, `ingest_timestamp`; nothing is hard-deleted.

## 8. API Surface

Additive only. New routes under `/api/analysis` (persisted analyses, share links), `/api/lsat` (concept counts, writing evaluations, hint events, reading progress, drill deep links), `/api/agents` (autonomy views, proposed-test review, replay), `/api/ingestion` (review UI), `/api/settings`, `/api/matters`. Existing response shapes gain fields; none are removed.

## 9. Agent / Crew Impact

New crews: `LSATContentReviewer`, `LSATGuideReviewer`, `LSATDraftJudge`. Modified: `LegalWorkflow` and `LegalAnalyst` (real PrecedentHunter, checkpointer use), `TopicFrontier`. Streaming becomes a first-class provider capability.

## 10. Acceptance Criteria

- **AC-1**: Given the 2026-09-05 register, when the sweep finishes, then every id listed in G1 is under `## Done` with a resolution note, except the two NG1 items which carry an explicit human-action note.
- **AC-2**: Given the final tree, when the gates in NFR-GATES-1 run, then all pass and the mypy error count does not exceed the baseline.
- **AC-3**: Given every package, when it completes, then its follow-ups are recorded under `## Follow-ups Discovered` and mirrored into `BACKLOG.md`.
- **AC-4**: Given any user-visible frontend or static-site change, when the PR is opened, then screenshots under `docs/images/` accompany it.

## 11. LegalBench Impact

- Tasks affected: none directly; the eval harness gains a dataset fetcher, a stored baseline, and richer scoring (FR-P09), which changes how scores are produced, not the reasoning under test.
- Expected delta: 0 pp; any measured change is reported, not gated, until the nightly baseline exists.

## 12. Risks & Open Questions

- **R-1**: Parallel implementation across packages can race on shared files (`Makefile`, `frontend/lib/api.ts`, `backend/law_ai/lsat/urls.py`). Mitigation: single ownership per hot file, additive edits, a final per-item verification pass.
- **R-2**: Accounts and persisted analyses change auth semantics. Mitigation: backwards-compatible token auth, per-router key fallback preserved, migrations forward-only.
- **R-3**: The mypy ratchet may raise the count before lowering it once django-stubs land. Mitigation: baseline file and a fail-on-growth gate rather than fail-on-any.

## 13. Out of Scope / Follow-ups

- Spec 039 component library adoption for the extracted LSAT and dashboard panels.
- The counsel and owner decisions in NG1.
