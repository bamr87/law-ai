# Tasks: LSAT Content Factory

> Each task references `FR-*` / `NFR-*` / `AC-*` IDs from `spec.md`; [spec_validator.py](../../scripts/spec_validator.py) enforces full coverage.

## Conventions

- Status: `[ ]` todo / `[~]` in-progress / `[x]` done.
- Verify commands run inside Docker per CLAUDE.md.

---

## T-001 — Taxonomy + config foundations

- **Refs**: FR-1, FR-2, FR-10
- **Owner**: @bamr87 (+Claude Code)
- **Status**: `[x]`
- **Files**: `backend/lawgraph/lsat/factory/{__init__,taxonomy,config}.py`, `backend/lawgraph/lsat/services/data/concepts.json`
- **Steps**: define `Archetype` + registry (≥14 LR / ≥6 RC / ≥5 LG) with concept mappings + tier hints; `validate_taxonomy()` against `load_concepts()`; `ModelTier` + `FactoryConfig.from_settings()` with `LSAT_FACTORY_*` overrides and Claude tier defaults (haiku/sonnet/opus/fable); add the 6 new concept entries and widen `must-be-true` to LR+LG.
- **Verify**: `docker compose run --rm backend pytest tests/lsat/test_factory_taxonomy.py -q --no-cov`

## T-002 — Coverage planner

- **Refs**: FR-3
- **Owner**: @bamr87 (+Claude Code)
- **Status**: `[x]`
- **Files**: `backend/lawgraph/lsat/factory/coverage.py`
- **Steps**: census over `load_bank()` per (section, archetype, difficulty); `plan_targets()` ranks under-target cells, boosts cells matching `gap_analysis()` weak concepts, deterministic ordering.
- **Verify**: `docker compose run --rm backend pytest tests/lsat/test_factory_coverage.py -q --no-cov`

## T-003 — Blueprint compiler + versioned prompts

- **Refs**: FR-4
- **Owner**: @bamr87 (+Claude Code)
- **Status**: `[x]`
- **Files**: `backend/lawgraph/lsat/factory/blueprints.py`, `backend/lawgraph/agents_runtime/prompts/lsat_factory_item.v1.md`, `backend/lawgraph/agents_runtime/prompts/lsat_factory_passage.v1.md`
- **Steps**: exemplar picker (same archetype/section, cap K, serialized with answer keys); prompt renderer merging template + archetype guidance + concept slice + JSON contract; passage-mode template for new RC passages / LG games.
- **Verify**: `docker compose run --rm backend pytest tests/lsat/test_factory_blueprints.py -q --no-cov`

## T-004 — Manifest lifecycle

- **Refs**: FR-5
- **Owner**: @bamr87 (+Claude Code)
- **Status**: `[x]`
- **Files**: `backend/lawgraph/lsat/factory/manifest.py`
- **Steps**: `GenerationJob` / `GenerationManifest` Pydantic models (schema_version=1), write/read under `LSAT_FACTORY_DIR`, unique job ids, config snapshot embedded.
- **Verify**: `docker compose run --rm backend pytest tests/lsat/test_factory_manifest.py -q --no-cov`

## T-005 — Executors (tiered Claude dev-gate / Ollama / draft-file)

- **Refs**: FR-6, NFR-SEC-1, AC-5
- **Owner**: @bamr87 (+Claude Code)
- **Status**: `[x]`
- **Files**: `backend/lawgraph/lsat/factory/executors.py`
- **Steps**: `Executor` protocol; `ClaudeCodeExecutor` mapping job tier → model id, structured-output schema reuse, hard `is_active()` gate raising `ExecutorUnavailable`; `OllamaExecutor`; `DraftFileExecutor` keyed by job_id.
- **Verify**: `docker compose run --rm backend pytest tests/lsat/test_factory_executors.py -q --no-cov`

## T-006 — Intake gates + HITL recording

- **Refs**: FR-7, FR-9, NFR-AUDIT-1, NFR-HITL-1, AC-3, AC-4
- **Owner**: @bamr87 (+Claude Code)
- **Status**: `[x]`
- **Files**: `backend/lawgraph/lsat/factory/intake.py`, `backend/lawgraph/lsat/services/proposals.py` (additive `meta` kwarg)
- **Steps**: gates schema → concept lint → Jaccard dedup (bank + pending + intra-batch) → answer-balance flagging; survivors to `record_proposal(meta=…)`; one `log_agent_call` per batch; typed reject reasons.
- **Verify**: `docker compose run --rm backend pytest tests/lsat/test_factory_intake.py tests/lsat/test_proposals.py -q --no-cov`

## T-007 — Pipeline facade + management command

- **Refs**: FR-8, AC-1, AC-2
- **Owner**: @bamr87 (+Claude Code)
- **Status**: `[x]`
- **Files**: `backend/lawgraph/lsat/factory/pipeline.py`, `backend/lawgraph/lsat/management/commands/lsat_factory.py`
- **Steps**: `plan/compile/execute/ingest/status` functions; command wiring all five subcommands with JSON output options; offline-safe defaults.
- **Verify**: `docker compose run --rm backend pytest tests/lsat/test_factory_pipeline.py tests/lsat/test_factory_command.py -q --no-cov`

## T-008 — Quality gates: full test pass + lint + types

- **Refs**: NFR-TEST-1
- **Owner**: @bamr87 (+Claude Code)
- **Status**: `[x]`
- **Files**: `backend/tests/lsat/test_factory_*.py`
- **Steps**: run the whole factory suite plus existing LSAT tests; ruff + mypy --strict on the new package.
- **Verify**: `docker compose run --rm backend pytest tests/lsat tests/api/test_lsat.py -q --no-cov` · `docker compose run --rm backend ruff check lawgraph/lsat/factory` · `docker compose run --rm backend mypy lawgraph/lsat/factory --strict`

## T-009 — Live multi-model demonstration (dev-time)

- **Refs**: AC-2, G5
- **Owner**: @bamr87 (+Claude Code)
- **Status**: `[x]` — ran 2026-07-02: manifest `mfst-20260702-223055-39bd7a` (12 jobs) fulfilled externally with tier-mapped Claude models (3×haiku, 7×sonnet, 2×opus) + fable judges; 30 drafts generated, 24 judge-kept (fable caught 3 wrong-keyed haiku LG items), 18 passed intake gates into the HITL queue (6 gate rejects: 3 intra-batch dups, 3 six-choice schema violations), 1 new grouping game parked; 2 jobs failed at generation (structured-output retry cap) and simply went unfulfilled — the pipeline degraded gracefully.
- **Files**: operational artifacts under `backend/var/lsat_factory/` (not committed)
- **Steps**: `compile` a manifest from real coverage gaps; fulfill jobs externally with tier-mapped Claude models (haiku=bulk, sonnet=standard, opus=premium, fable=judge) writing a drafts JSONL; `ingest`; confirm pending proposals with factory meta via the API/store.
- **Verify**: pending proposals visible with `meta.manifest_id`, gate stats reported, audit events present.

---

## Done-When (Definition of Done)

- All FR/NFR/AC covered by tasks above; factory suite green in Docker; ruff + mypy --strict clean on the new package; no bank-write path outside `promote_to_bank`; spec + BACKLOG cross-referenced.

## Follow-ups Discovered

_Populated at implementation close — mirrored to [BACKLOG.md](../../BACKLOG.md)._

- **BL-20260702-01** — *feature, med* — Embedding-based near-duplicate detection for intake (token Jaccard misses paraphrases); local sentence-transformers or Ollama embeddings, cached per bank revision.
- **BL-20260702-02** — *feature, med* — `judge` tier wiring inside `run`: after generation, route each surviving draft through a judge-tier adversarial review (single-best-answer check) and attach verdicts to proposal meta (extends BL-20260527-04's reviewer-agent idea to the factory path).
- **BL-20260702-03** — *feature, low* — `lsat_factory export-manifest` subcommand emitting a self-contained prompts-only bundle (no repo checkout needed) for fully external generation farms.
- **BL-20260702-04** — *infra, low* — Celery beat entry `autonomy-lsat-factory` running `plan→compile→run(ollama)→ingest` nightly under `AUTONOMY_ENABLED`, budget-capped, mirroring spec 019's beat pattern.
- **BL-20260702-05** — *test-gap, low* — Integration test running `lsat_factory run --executor ollama` against the live Docker Ollama service (marker `integration`) asserting proposals land with provenance.
- **BL-20260702-06** — *feature, low* — Surface factory status (coverage matrix, last manifest, gate stats) on the Authoring tab so reviewers see what the next batch will target (extends BL-20260527-07).
- **BL-20260702-07** — *feature, med* — Passage-set promotion path: extend `promote_to_bank` (or a sibling) to write parked `pending_passages/*.passage.json` into `passages.json` and wire `passage_id` onto the approved drafts; today intake parks the new context and linkage is a manual reviewer step.
- **BL-20260702-08** — *refactor, med* — Dedup gate: strip embedded passage/game-setup text from stems before Jaccard similarity (LG stems that restate the shared setup scored ~0.93 against batch-mates in the live run and were rejected as duplicates even though the questions differed); compare only the question-specific sentence(s).
