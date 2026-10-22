# Plan: LSAT Item Synthesis Engine

> Implementation plan for [spec.md](spec.md). Slices ship in order; one slice = one PR.

## 1. Architecture Overview

Four stages, and the whole design rests on where the boundary between them falls.

```
schema (logic, no words)  ─┐
                           ├─► formal item ─► CHECKER ─► proof ─┐
domain pack (words, no logic) ┘        │                        │
                                       └─► REALIZER ────────────┴─► Question + SolveGuide + Report
                                                    │
                     ┌──────────────────────────────┴───────────────────────────┐
                     ▼                          ▼                               ▼
              lsat_synth generate        SynthExecutor                   --promote
              (jsonl / preview)      → factory intake gates      (logical proofs only,
                                       → HITL proposal queue      off by default, audited)
```

**Logic and words never mix.** A schema declares premises, a credited answer and distractors as *statements* — structures over abstract slot names, with no English in them. A domain pack supplies English — subjects, properties, settings, names — with no logic in it. The realizer is the only place the two meet, and it is a template fill.

That boundary is what makes the spec's central claim true. Swapping the domain changes every noun in the item and cannot change a single entailment, because the checker never sees a word. It also makes verification cheap (NFR-PERF-1): the proof is a property of the skeleton, so it is computed once and reused across every realization of it.

### The checker

Four bounded model spaces, each enumerated exhaustively:

| Space | A model is | Bound | Decides |
| ----- | ---------- | ----- | ------- |
| `prop` | truth assignment to K atoms | 2^K, K ≤ 8 | conditionals about one subject |
| `region` | count vector over the 2^K Venn regions of K predicates, summing to ≤ N | compositions of N into 2^K parts | all / some / no / most / exactly-n |
| `order` | permutation of E entities | E!, E ≤ 7 | sequencing games |
| `assign` | function entities → groups | G^E, G^E ≤ 4096 | grouping games |

The `region` representation is the load-bearing one. Enumerating *individuals* is exponential in universe size and redundant — every LSAT quantifier statement is a function of how many things fall in each Venn region, not of which. Counting regions instead makes `most` exact and keeps the space small enough to enumerate in milliseconds.

`entails(premises, candidate)` returns `entailed` / `contingent` / `contradicted` and, crucially, the number of models satisfying the premises. Zero is an error, not a pass: an inconsistent premise set entails everything, which would certify every distractor as correct.

### Two proof kinds

`logical` — the credited answer's status is *decided* by the checker, and each distractor is decided not to have that status. This covers conditional chains, quantifier combination, cannot-be-true, sufficient and necessary assumption (both have exact model-theoretic criteria: sufficient is `premises ∧ C ⊨ conclusion`, necessary is `premises ∧ conclusion ⊨ C`), and both game families.

`structural` — the item is *built* to commit exactly one enumerated defect, the credited answer names that defect, and distractors are drawn from a disjoint pool of defects the construction provably does not commit. This covers causal weaken/strengthen and the flaw families, where the credited answer is a description in prose and no checker can certify a description. The report says `structural`, and the promotion gate refuses it.

Keeping these apart is the difference between a useful tool and a confident one.

## 2. Component Changes

| Component | Change |
| --------- | ------ |
| `backend/law_ai/lsat/synth/logic.py` | **New.** Statement AST, four model spaces, entailment API. |
| `backend/law_ai/lsat/synth/lexicon.py` | **New.** Domain-pack models + validating loader. |
| `backend/law_ai/lsat/synth/schemas.py` | **New.** Schema registry (logic only). |
| `backend/law_ai/lsat/synth/realize.py` | **New.** Formal item + domain → `Question` + `SolveGuide`. |
| `backend/law_ai/lsat/synth/verify.py` | **New.** `VerificationReport` + quality gates. |
| `backend/law_ai/lsat/synth/generate.py` | **New.** Orchestrator, `SynthItem`, batch + promotion. |
| `backend/law_ai/lsat/synth/polish.py` | **New.** Opt-in lexicon proposals + lint. |
| `backend/law_ai/lsat/synth/data/domains/*.json` | **New.** The domain packs. |
| `backend/law_ai/lsat/management/commands/lsat_synth.py` | **New.** `list`/`preview`/`verify`/`generate`/`sweep`. |
| `backend/law_ai/lsat/factory/executors.py` | `SynthExecutor` implementing the `Executor` protocol. |
| `backend/law_ai/lsat/services/proposals.py` | Promotion accepts a synth-provenance draft. |
| `backend/law_ai/settings/base.py` | `LSAT_SYNTH_AUTOPROMOTE` (default `False`). |
| `Makefile` | `lsat-synth-preview`, `lsat-synth-generate`, `lsat-synth-sweep`. |
| `docs/lsat-synthesis.md` | **New.** Engine, schema authoring, domain authoring, the promotion gate. |

## 3. Data & Schema Migrations

None. Generated items are ordinary `Question` values; they reach users through the JSON bank or the existing proposal store. The one new setting is additive and defaults to the safe value.

## 4. Tech Choices & Alternatives

- **Finite-model enumeration over a SAT/SMT solver.** Alternative: `z3-solver`. Rejected — a new binary
dependency for formulas with fewer than a dozen atoms, and enumeration gives us something a solver does not: a *model count*, which is how the satisfiability and non-vacuity checks are expressed.
- **Venn-region counting over individual enumeration.** The only representation that makes `most` exact while keeping the space enumerable.
- **Template realization over natural-language generation.** Alternative: have a model write the prose.
Rejected — that reintroduces exactly the failure mode the engine exists to eliminate, and templates plus authored lexicon entries are grammatical by construction.
- **Polish operates on lexicon entries, not sentences.** A model rewriting a rendered sentence could change
its logical form, and no cheap check would catch it. Proposing *vocabulary* that is then re-rendered through the unchanged template preserves the logic by construction — the difference between trusting the model and not needing to.
- **Reuse the spec 024 `Executor` protocol.** The dedup, lint, balance and HITL machinery already exists and is tested; a deterministic executor is a drop-in.

## 5. Provenance & Audit Hook-up

- Every `SynthItem` carries `schema_id`, `schema_version`, `domain_id`, `seed` and `engine_version`, so any item in the bank can be regenerated byte-for-byte (NFR-AUDIT-1).
- Generation makes no model call and therefore writes no `llm_call` event; `--polish` does, through `law_ai.core.llm`, which logs it.
- Direct promotion writes an `lsat_synth.promoted` audit event carrying the proof summary — space, models enumerated, models satisfying premises, per-choice status.
- `SynthExecutor` output flows through `ingest_batch`, which already records proposal creation.

## 6. HITL Gates

Default posture is unchanged: generated drafts land as `pending` proposals and a human approves them.

The direct-write path is the exemption spec §12/R2 argues for, and it is bounded by five conditions that must *all* hold — `proof_kind == "logical"`, a clean verification report, passing intake gates, the `LSAT_SYNTH_AUTOPROMOTE` setting on, and an explicit `--promote` flag. Structural proofs are never eligible. The rationale is the constitution's own: §5 enforces HITL through "confidence and verification thresholds", and a finite-model proof that the key is entailed and no distractor is *is* a verification threshold — a stronger one than the 0.7 confidence score that already licenses an unattended ingestion commit.

## 7. Test Strategy

| Layer | Coverage |
| ----- | -------- |
| Checker | Truth tables for each space; known entailments and non-entailments; the inconsistent-premises guard. |
| Region space | `most`+`most` overlap, `all` chaining, and the non-entailments that look like entailments. |
| Schemas | Every schema verifies; a deliberately broken skeleton fails, and fails at the expected check. |
| Lexicon | An incomplete pack fails to load; every shipped pack round-trips. |
| Realization | Determinism, cross-domain word disjointness, `Question` validity, guide quality. |
| Sweep | Every schema × domain × N seeds, as a test and as a CI-able command. |
| Promotion | Refuses structural, refuses setting-off, audits on success. |
| Polish | Lint rejects logical operators; no provider yields the unpolished item. |

## 8. Rollout

1. **Checker** — `logic.py` and its tests, standalone and provable on their own.
2. **Schemas + lexicon** — the registry and the domain packs.
3. **Realize + verify + generate** — items come out and carry proofs.
4. **Delivery** — command, executor, promotion gate.
5. **Polish** — the opt-in AI wiring, last, because nothing depends on it.

## 9. Risks & Mitigations

| Risk | Mitigation |
| ---- | ---------- |
| Enumeration blows up on a wide schema | Each space declares a hard bound and refuses to enumerate past it; schemas are written to stay inside it, and a test asserts the sweep's runtime. |
| "Proved" overclaimed (spec R1) | Bounds documented per space; the report states what was enumerated. |
| Structural mistaken for logical (spec R5) | Distinct enum, printed in every report, and the promotion gate keys on it. |
| Template monotony (spec R3) | Multiple stem phrasings per schema; a cross-domain disjointness test. |
| A future edit weakens the proof and the exemption silently survives | The promotion path re-runs verification itself rather than trusting a passed-in report. |

## 10. Estimated Effort

| Slice | Scope | Estimate |
| ----- | ----- | -------- |
| 1 | Statement language + four model spaces + tests | ~1.5 days |
| 2 | 12+ schemas, 4+ domain packs | ~2 days |
| 3 | Realizer, verifier, guide emission | ~1.5 days |
| 4 | Command, executor, promotion gate | ~1 day |
| 5 | Polish + lint | ~0.5 day |
