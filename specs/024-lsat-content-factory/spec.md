# Spec: LSAT Content Factory — Scalable Multi-Model Question Generation

- **ID**: 024-lsat-content-factory
- **Status**: shipped
- **Owner**: @bamr87
- **Created**: 2026-07-02
- **Roadmap Epic**: extends spec 005 (LSAT Lab) and spec 019 (LSATContentAuthor); resolves BL-20260606-02, advances BL-20260503-02 / BL-20260429-19 / BL-20260606-03
- **Constitution Compliance**: confirmed against [docs/constitution.md](../../docs/constitution.md) — Ollama stays the only product-runtime LLM (§1); the Claude executor rides the existing dev-time-only `core.claude_code` gate and is inert outside development; provenance on every LLM call and ingest batch (§4); HITL gate on every generated item — the factory writes proposals, never bank files (§5).

## 1. Problem & Motivation

Spec 019 gave us a single-shot author agent: one `(section, difficulty, concepts)` target, ≤10 drafts, one model. Growing the bank to the scale the Lab needs (BL-20260429-19 asks for ≥50 LR items; BL-20260503-02 for ≥10 RC/LG sets each) is manual and unstructured: nothing decides *what* to generate next, nothing compiles LSAT-pattern-aware prompts, nothing runs batches across models, and the only quality gates are per-draft schema checks — no dedup, no answer-key balance (BL-20260606-02), no concept lint against the catalog.

The factory turns content growth into a repeatable, auditable pipeline: **plan** (coverage matrix + learner gap analysis → prioritized targets) → **compile** (targets → few-shot, archetype-grounded prompts as a manifest artifact) → **execute** (pluggable executors: tiered dev-time Claude models, local Ollama, or externally-produced draft files) → **ingest** (schema → concept lint → dedup → balance → HITL proposals). Because plan/compile/ingest are pure Python file-artifact stages, generation fans out horizontally — N jobs × M models — without the repo ever depending on a closed-source runtime LLM.

## 2. Goals

- **G1**: A machine-readable **taxonomy** of LSAT question archetypes per section (LR/RC/LG) with concept-catalog mappings, difficulty bands, distractor guidance, and model-tier hints — validated against `concepts.json` at load.
- **G2**: A **coverage planner** that merges bank-census (items per section × archetype × difficulty cell) with `lsat_grade` gap analysis into a ranked list of `GenerationTarget`s.
- **G3**: A **blueprint compiler** that renders each target into a generation prompt seeded with real bank exemplars of the same archetype (few-shot) via versioned prompt templates.
- **G4**: A **manifest lifecycle** — plan/compile/execute/ingest as decoupled file artifacts under `backend/var/lsat_factory/` so any executor can fulfill jobs asynchronously and at scale.
- **G5**: **Model-tier routing** — `bulk` / `standard` / `premium` / `judge` tiers mapped per provider: dev-time Claude (haiku → sonnet → opus → fable) through the existing OAuth gate, local Ollama as the always-available default.
- **G6**: An **intake pipeline** with four quality gates (schema, concept lint, near-duplicate detection, batch answer-key balance) that lands survivors in the spec-019 HITL proposal store.
- **G7**: A `lsat_factory` management command exposing the whole lifecycle (`plan` / `compile` / `run` / `ingest` / `status`) for operators and CI.

## 3. Non-Goals

- **NG1**: No auto-approval — every generated item still requires one human click through the existing `/api/lsat/proposals/<id>/approve` flow.
- **NG2**: No product-runtime Claude. The `ClaudeCodeExecutor` is a dev-time convenience behind `core.claude_code.is_active()`; production and CI paths use Ollama or pre-produced draft files.
- **NG3**: No new database tables — manifests and drafts are file artifacts; proposals stay in the spec-019 JSONL store.
- **NG4**: No IRT/psychometric difficulty calibration (follow-up).
- **NG5**: No frontend changes — the existing Authoring tab already renders the proposal queue the factory feeds.

## 4. User Stories

- As a **content maintainer**, I want the factory to tell me which archetype × difficulty cells are thin, so batch generation targets real coverage gaps instead of duplicating what exists.
- As a **developer with a Claude subscription**, I want `lsat_factory run --executor claude_code` to route easy items to a cheap model and passage authoring to a top-tier model, so a large batch costs a fraction of an all-Opus run.
- As an **operator without any LLM**, I want `plan` / `compile` / `ingest` / `status` to work offline, so external generation (a Claude Code session, a script farm) can fulfill manifests and hand back drafts.
- As a **reviewer**, I want duplicate and answer-key-skewed drafts filtered or flagged before they reach my queue, so HITL time goes to borderline pedagogy, not mechanical rejects.

## 5. Functional Requirements

- **FR-1**: `law_ai.lsat.factory.taxonomy` defines an `Archetype` model (`id`, `section`, `name`, `concepts`, `difficulty_weights`, `guidance`, `tier_hint`, `requires_passage`) and a registry of ≥14 LR, ≥6 RC, ≥5 LG archetypes. `validate_taxonomy()` raises if ids collide or any referenced concept id is missing from `load_concepts()`.
- **FR-2**: `law_ai.lsat.factory.config` defines `ModelTier = Literal["bulk","standard","premium","judge"]` and a `FactoryConfig` Pydantic model (tier→model maps per provider, exemplar count, dedup threshold, balance tolerance, per-cell target counts, output dir). `FactoryConfig.from_settings()` reads `LSAT_FACTORY_*` settings with safe defaults; dev-time Claude tier defaults are haiku-4-5 / sonnet-5 / opus-4-8 / fable-5.
- **FR-3**: `law_ai.lsat.factory.coverage` builds a census of bank items per `(section, archetype, difficulty)` (an item matches an archetype when it carries ≥1 of the archetype's concepts) and `plan_targets()` returns deterministic, ranked `GenerationTarget`s for cells below target, boosted by `proposals.gap_analysis()` weakness rows.
- **FR-4**: `law_ai.lsat.factory.blueprints` compiles each target into a prompt: versioned template (`agents_runtime/prompts/lsat_factory_item.v1.md`, `lsat_factory_passage.v1.md`) + archetype guidance + up to K same-archetype bank exemplars (answer keys included — these are authoring references) + section-scoped concept catalog + strict JSON output contract. Templates are loaded from disk, never inlined.
- **FR-5**: `law_ai.lsat.factory.manifest` persists a compiled plan as a schema-versioned JSON manifest (`manifest_id`, `created_at`, config snapshot, jobs[] each with `job_id`, target, tier, `model_hint`, compiled prompt) under `LSAT_FACTORY_DIR` (default `backend/var/lsat_factory/`), and reads it back with validation.
- **FR-6**: `law_ai.lsat.factory.executors` defines an `Executor` protocol (`async execute(job) -> RawBatch`) with three implementations: `ClaudeCodeExecutor` (per-tier `model_id` via `claude_code.generate` + the drafts response schema; raises `ExecutorUnavailable` unless `claude_code.is_active()`), `OllamaExecutor` (local `/api/generate`, all tiers → `OLLAMA_DEFAULT_MODEL`), and `DraftFileExecutor` (reads externally-produced `{job_id → drafts[]}` JSONL — no network).
- **FR-7**: `law_ai.lsat.factory.intake` runs each raw batch through ordered gates — (1) `DraftQuestion` schema validation (reused from spec 019), (2) concept lint (ids ∈ catalog, section consistency, passage existence), (3) near-duplicate detection (normalized token Jaccard vs live bank + pending proposals + intra-batch, threshold from config), (4) batch answer-key balance (flag, not reject, when one label exceeds tolerance) — then records survivors via `proposals.record_proposal`, threading factory metadata, and logs one `provenance.log_agent_call` per ingested batch. Rejects are returned with machine-readable reasons.
- **FR-8**: `python manage.py lsat_factory {plan|compile|run|ingest|status}` drives the lifecycle: `plan` prints/serializes targets, `compile` writes a manifest, `run` executes a manifest with a chosen executor and ingests, `ingest` consumes an external drafts file against a manifest, `status` reports bank census + coverage holes + pending-proposal counts. All subcommands work without any LLM except `run` with a live executor.
- **FR-9**: `proposals.record_proposal` accepts an optional `meta: dict` recorded on the create event (additive, backward-compatible) so factory provenance (`manifest_id`, `job_id`, `archetype`, `tier`, `executor`) survives into the HITL queue.
- **FR-10**: `concepts.json` gains entries for archetypes not yet representable — `resolve-paradox`, `main-conclusion`, `method-of-reasoning`, `principle-application`, `rc-inference`, `grouping-game` — and `must-be-true` widens `sections` to `["LR","LG"]`; all with original CC0 text following the existing entry shape.

## 6. Non-Functional Requirements

- **NFR-AUDIT-1**: Every LLM executor call and every ingest batch emits provenance (`log_agent_call` with model label, latency, counts); the full factory lifecycle is reconstructable from manifests + proposals JSONL + audit log.
- **NFR-HITL-1**: The factory package contains no code path that writes `*_bank.json`; promotion remains exclusively spec-019 `promote_to_bank` behind the approve endpoint.
- **NFR-SEC-1**: `ClaudeCodeExecutor` is inert unless `core.claude_code.is_active()` (dev env + opt-in + token) — constitution §1 enforced at the executor boundary, not by caller discipline. No new external HTTP paths beyond the existing `claude_code` / Ollama clients.
- **NFR-TEST-1**: Factory modules ship with unit tests (taxonomy validity, planner determinism, blueprint content, manifest roundtrip, every intake gate, command smoke) runnable without network; `ruff` and `mypy --strict` clean.

## 7. Data Model Impact

None on Neo4j/Postgres. New file artifacts: `backend/var/lsat_factory/manifests/*.json` (compiled plans) and `backend/var/lsat_factory/drafts/*.jsonl` (external executor output) — both gitignored operational data, like `lsat_proposals/`. Proposal create events gain an optional `meta` object.

## 8. API Surface

No new HTTP endpoints. The factory feeds the existing `/api/lsat/proposals*` surface. CLI surface: `manage.py lsat_factory` (FR-8).

## 9. Agent / Crew Impact

No new registry agents. `LSATContentAuthor` (spec 019) remains the interactive single-target path; the factory is the batch path that shares its `DraftQuestion` contract and proposal store. Executors log under agent name `LSATContentFactory`.

## 10. Acceptance Criteria

- **AC-1**: In a Docker backend container with no LLM reachable, `lsat_factory plan`, `compile`, and `status` succeed; the manifest contains ≥1 job per under-covered cell with compiled prompts embedding ≥1 exemplar for populated archetypes.
- **AC-2**: End-to-end offline: `compile` → hand-written drafts JSONL keyed by `job_id` → `ingest` → drafts appear as `pending` proposals via `list_proposals()` carrying factory `meta`, and an audit event exists for the batch.
- **AC-3**: A draft whose stem is a near-copy of a bank item (or of another draft in the same batch) is rejected with reason `duplicate`, and rejects never reach the proposal store.
- **AC-4**: A batch whose answer keys skew past tolerance (e.g. 4/5 drafts keyed "C") records a `balance` flag in each affected proposal's meta rather than silently passing.
- **AC-5**: With `LSAT_LLM_PROVIDER` unset or outside a dev environment, instantiating/running `ClaudeCodeExecutor` raises `ExecutorUnavailable` and `run --executor claude_code` exits with a clear gate message.
