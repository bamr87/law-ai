# Plan: LSAT Content Factory

## Architecture

A new self-contained package `backend/lawgraph/lsat/factory/` — the batch content-growth plugin. Data flows one way:

```
                    ┌─ concepts.json / *_bank.json / passages.json (read-only)
                    │
 taxonomy.py ──► coverage.py ──► blueprints.py ──► manifest.py          [plan/compile: pure, offline]
 (archetypes)    (census +       (few-shot          (jobs as file
                  gap ranking)    prompts)            artifacts)
                                                        │
                                          ┌─────────────┼──────────────┐
                                   ClaudeCodeExecutor  OllamaExecutor  DraftFileExecutor
                                   (dev-gated, tiered   (runtime        (external drafts,
                                    haiku/sonnet/        default)        no network)
                                    opus/fable)
                                          └─────────────┼──────────────┘
                                                        ▼
                                                    intake.py            [gates: schema → concept lint
                                                        │                 → dedup → answer balance]
                                                        ▼
                                        proposals.record_proposal(meta=…)  ──► HITL Authoring tab
                                                        │                       (approve → bank)
                                                        ▼
                                              provenance.log_agent_call
```

Key design decisions:

1. **Manifest decoupling is the scale lever.** Plan/compile/ingest are pure-Python file stages; execution is pluggable. A manifest can be fulfilled by in-process executors, or exported and fulfilled by anything that can write a drafts JSONL (a Claude Code session fanning out per-tier subagents, a script farm, CI). The repo never gains a runtime dependency on a closed model.
2. **Constitution enforcement at the executor boundary.** `ClaudeCodeExecutor.__init__`/`execute` check `core.claude_code.is_active()` and raise `ExecutorUnavailable` otherwise — the same triple gate (dev env + `LSAT_LLM_PROVIDER=claude_code` + OAuth token) spec 019 uses. Ollama remains the default for `run`.
3. **Tier→model as configuration, not code.** `FactoryConfig.claude_tier_models` maps `bulk→haiku-4.5`, `standard→sonnet-5`, `premium→opus-4-8`, `judge→fable-5`, overridable via `LSAT_FACTORY_CLAUDE_TIERS` (JSON) — model churn is a settings change. Archetype `tier_hint` + difficulty pick the tier per job (`easy→bulk`, `med→standard`, `hard/passage→premium`).
4. **Reuse spec-019 contracts.** `DraftQuestion` stays the single draft schema; the proposal store stays the single HITL intake; `_DRAFTS_RESPONSE_SCHEMA` is exported for the Claude structured-output path. The factory adds the layers that were missing (what to build, how to prompt it, how to check it) without forking what exists.
5. **Dedup = normalized token Jaccard** over stems (lowercase, strip punctuation, token set) vs live bank + pending proposals + intra-batch, threshold 0.60 default. Cheap, deterministic, no embeddings dependency; embedding-based near-dup detection is a recorded follow-up.

## Module inventory

| File | Purpose | ~LOC |
|------|---------|------|
| `factory/__init__.py` | public facade re-exports | 30 |
| `factory/taxonomy.py` | `Archetype` model + LR/RC/LG registry + `validate_taxonomy` | 260 |
| `factory/config.py` | `ModelTier`, `FactoryConfig.from_settings()` | 120 |
| `factory/coverage.py` | census, `plan_targets()` gap-weighted ranking | 150 |
| `factory/blueprints.py` | exemplar selection + prompt compilation | 160 |
| `factory/manifest.py` | `GenerationJob`/`GenerationManifest` write/read | 120 |
| `factory/executors.py` | protocol + 3 executors | 170 |
| `factory/intake.py` | 4 quality gates + proposal recording + provenance | 220 |
| `factory/pipeline.py` | `plan/compile/execute/ingest/status` orchestration | 150 |
| `management/commands/lsat_factory.py` | CLI | 180 |
| `agents_runtime/prompts/lsat_factory_item.v1.md` | item-generation template | — |
| `agents_runtime/prompts/lsat_factory_passage.v1.md` | passage/game-set template | — |

## Testing strategy

`backend/tests/lsat/test_factory_*.py`, all offline (no LLM): taxonomy validity against the real catalog; planner determinism + gap boost; blueprint prompt content (exemplars, guidance, contract); manifest roundtrip; each intake gate with crafted drafts (valid / bad-concept / duplicate / skewed batch); pipeline e2e via `DraftFileExecutor` into a tmp proposal store (reusing the spec-019 `_isolate_state` fixture pattern); management-command smoke via `call_command`. Executor gating (AC-5) tested by asserting `ExecutorUnavailable` outside dev opt-in.

## Rollout

Pure additive: new package + command + two prompts + additive `meta` kwarg + concept entries. No migration, no API change, no frontend change. Ops artifacts land under `backend/var/` (already the operational-data convention).
