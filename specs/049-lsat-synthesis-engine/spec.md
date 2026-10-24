# Spec: LSAT Item Synthesis Engine

- **ID**: 049-lsat-synthesis-engine
- **Status**: shipped
- **Owner**: @bamr87
- **Created**: 2026-09-03
- **Roadmap Epic**: BACKLOG BL-20260903-10, BL-20260903-11, BL-20260903-12
- **Constitution Compliance**: confirmed against [docs/constitution.md](../../docs/constitution.md) (see §12 below for the §5 exemption this spec earns and bounds)

## 1. Problem & Motivation

The bank grows one way: a model drafts an item, a human reads it, a human approves it. Spec 024 built the machinery around that loop — taxonomy, coverage census, manifest, dedup and lint gates — and spec 047 scheduled it. The loop works, and it is bounded by two things that will not improve:

- **Human review throughput.** Every item costs a reviewer's attention, so the bank grows at the rate a person can read.
- **Model reliability on formal content.** An LLM asked for "a modus tollens question" produces something
that *looks* like one. Whether the credited answer actually follows, and whether all four distractors actually fail, is checked by a human reading it — which is exactly the check humans are worst at doing repeatedly. Spec 045's cross-check exists because this failure is real.

Meanwhile, most of what makes an LSAT item *hard* is not the vocabulary. A conditional-chain question about zoning applications and one about clinical trials are the same question: same skeleton, same inference, same four distractor shapes, different nouns. The exam's own item writers work this way.

That suggests a second production path the repo does not have: **derive the item from a formal model, prove the key, and vary only the surface.** Nothing about the logic is left to a language model, so nothing about the logic can be wrong. The lexicon — subjects, properties, settings, entity names — becomes swappable data, and one verified skeleton yields as many surface-distinct items as there are domains and seeds.

The prize is not volume for its own sake. It is that BL-20260901-01 (only three `intro` and one `elite` item in the whole bank), BL-20260901-02 (17 archetypes with no exemplars), and BL-20260901-04 (guide coverage falling as the bank grows) are all *authoring-throughput* problems, and a generator with a proof attached solves them without asking a reviewer to certify arithmetic.

## 2. Goals

- **G1**: Generate LSAT items from formal skeletons where the credited answer is **proved** by a model checker and each distractor is **proved not** to be credited — accuracy by construction, not by review.
- **G2**: Make the surface fully swappable: subjects, properties, settings and entity names come from dataset "domain packs" that contain no logic, so the same proved skeleton yields many distinct items.
- **G3**: Be honest about what is proved. Families whose correctness is a matter of prose judgement carry a *structural* guarantee, not a logical one, and the two are never conflated.
- **G4**: Emit a solve guide with every item, derived from the same proof, so generated content is teachable the day it lands rather than waiting for a backfill sweep.
- **G5**: Run with zero network by default. Optional, opt-in AI wiring touches surface vocabulary only and can never move the logic.
- **G6**: Feed the existing HITL queue through the existing gates, and — only for logically-proved items, only
when explicitly enabled — offer a direct bank-write path that the constitution's verification-threshold rule actually licenses.

## 3. Non-Goals

- **NG1**: Reproducing real LSAT items. Every skeleton and every domain pack is original (CC0).
- **NG2**: Replacing the spec 024 LLM factory. The two paths are complementary: this one covers the formal families with a proof; the factory covers everything else.
- **NG3**: Generating Reading Comprehension passages, main-point, tone, or method items. Their correctness
depends on judgements about prose that no checker can certify, and asserting a key there would be the exact failure this spec exists to remove.
- **NG4**: A general first-order theorem prover. The checker is a finite-model enumerator over four bounded model spaces, and it says so.
- **NG5**: Natural-language generation. Surface text comes from templates and authored lexicon entries, so output is grammatical by construction rather than by a model's good behaviour.
- **NG6**: Difficulty *measurement*. Schemas declare a difficulty band; whether learners actually find a band hard is an empirical question this spec does not answer.

## 4. User Stories

- As a **content maintainer**, I want to fill a coverage hole by running one command and getting fifty items whose keys are proved, so my review is about style rather than about whether the logic holds.
- As a **content maintainer**, I want the same skeleton rendered in a different domain, so the bank stops reading like it was written about one subject.
- As a **reviewer**, I want each generated item to carry a machine-readable proof — what was checked, over how many models, and what each distractor's status is — so I can trust it without redoing the reasoning.
- As a **learner**, I want generated items to arrive with a step-by-step guide, so a new item is as teachable as a hand-authored one.
- As a **maintainer**, I want a sweep command that generates across every schema and domain and reports any verification failure, so a regression in the engine fails CI rather than reaching the bank.
- As a **maintainer on a budget**, I want the whole thing to work with no model calls at all, and an opt-in flag when I want fresher vocabulary.

## 5. Functional Requirements

### The proof engine (slice 1)

- **FR-1**: A statement language and finite-model checker over four bounded model spaces:
`prop` (propositional atoms about one subject), `region` (monadic predicates over a finite universe, represented as Venn-region count vectors so `all`/`some`/`no`/`most`/`exactly-n` are decided exactly), `order` (permutations, for sequencing), and `assign` (entity→group functions, for grouping).
- **FR-2**: An entailment API returning, for a candidate statement against a premise set, exactly one of
`entailed` / `contingent` / `contradicted`, plus the count of models satisfying the premises. A premise set with **zero** satisfying models is an error, never a pass — an inconsistent premise set entails everything and would silently certify every distractor.
- **FR-3**: Documented soundness bounds. The checker decides entailment *over its enumerated space*; each space declares its bound and why that bound is sufficient for the statement forms the schemas use.

### Schemas and lexicon (slice 2)

- **FR-4**: An item *schema* declares its model space, how premises are built from typed slots, the credited
answer, the distractor set, the required verification status of every choice, its LSAT archetype id, and its difficulty band. Schemas contain no surface text.
- **FR-5**: A *domain pack* is data: subjects, properties (each with singular/plural affirmative and negative
verb phrases and a restrictive modifier), group names, ordering settings, and entity names. Domain packs contain no logic. Loading validates that every field a realizer needs is present.
- **FR-6**: At least 12 schemas spanning the provable families: conditional chains (modus ponens and modus
tollens), cannot-be-true, quantifier overlap, all/some combination, sufficient assumption, necessary assumption, sequencing acceptability and must-be-true, grouping acceptability, plus the structurally-guaranteed causal-weaken, necessary/sufficient flaw, and percentage-versus-number families.
- **FR-7**: At least 4 domain packs in visibly different subject areas, and a documented procedure for adding one without touching a line of engine code.

### Realization and verification (slice 3)

- **FR-8**: A realizer turning a formal item plus a domain pack into a canonical
`law_ai.lsat.services.bank.Question` — stem, five labelled choices, key, explanation, concept tags — deterministic in `(schema, domain, seed)`.
- **FR-9**: A `VerificationReport` recording proof kind, model space, models enumerated, models satisfying the
premises, per-choice entailment status, and every quality check with its result. An item that fails any check is never emitted as valid.
- **FR-10**: Two proof kinds, never conflated. `logical` — the key's status is decided by the model checker.
`structural` — the key is guaranteed by construction (the item was built to commit exactly one enumerated defect, and distractors are drawn from a disjoint inert pool) but not model-checked. Every report says which.
- **FR-11**: Quality gates beyond entailment: premises satisfiable; exactly one choice entailed where the
family requires it; no two choices logically equivalent; no duplicate or near-duplicate choice surface; key position varied across a batch; choice lengths within a band so the longest is not a tell.
- **FR-12**: A solve guide derived from the proof — symbolize, chain, apply, answer — with typed representations, valid against spec 045's `validate_guide_quality`, emitted alongside every item.

### Delivery (slice 4)

- **FR-13**: A `lsat_synth` management command: `list`, `preview`, `verify`, `generate`, `sweep`.
- **FR-14**: A `SynthExecutor` implementing the spec 024 `Executor` protocol, so `lsat_factory execute` can
fulfil manifest jobs deterministically and drafts pass the same dedup, lint and balance gates into the HITL queue.
- **FR-15**: A direct bank-write mode, subject to **all** of: `proof_kind == "logical"`, a clean
`VerificationReport`, passing the factory intake gates, the `LSAT_SYNTH_AUTOPROMOTE` setting enabled (default off), and an explicit `--promote` flag. Every auto-promotion writes an audit event carrying the proof summary. Structural-proof items are never eligible.
- **FR-16**: A `sweep` mode that generates across every schema × domain × N seeds and fails on any verification failure, runnable as a CI gate.

### Optional AI wiring (slice 5)

- **FR-17**: Opt-in surface polish that operates on **lexicon entries, never on rendered sentences**: the model
proposes subject and property vocabulary, the item is re-rendered through the unchanged template, and the logical form is therefore preserved by construction rather than by trust. Routed through `law_ai.core.llm` at its cheapest tier, with a deterministic no-op fallback.
- **FR-18**: Proposed vocabulary is linted before use: no logical operators (`if`, `only if`, `unless`, `all`,
`some`, `most`, `no`, `not`, `every`), length bounds, and no reuse of an existing entry. A proposal failing the lint is discarded, not repaired. Every polished item is re-verified end to end before it is emitted.

## 6. Non-Functional Requirements

- **NFR-OFFLINE-1**: `list`, `preview`, `verify`, `generate` and `sweep` make no network call. Only `--polish` does.
- **NFR-DETERMINISM-1**: `(schema, domain, seed)` fully determines the item. The same triple produces a byte-identical question, guide and report on any machine.
- **NFR-PERF-1**: Skeleton verification is cached per canonical skeleton, not repeated per realization —
surface variation cannot change logic — so a 500-item batch pays the enumeration cost once per skeleton. A full sweep completes inside the backend test budget.
- **NFR-AUDIT-1**: Every generated item carries its schema id, schema version, domain id, seed and engine version, so any item in the bank can be regenerated exactly.
- **NFR-SAFETY-1**: No generated content asserts anything about real law, and every item is original (CC0).

## 7. Data Model Impact

New package `backend/law_ai/lsat/synth/`:

- `logic.py` — statement AST, the four model spaces, entailment API.
- `schemas.py` — the schema registry.
- `lexicon.py` — domain-pack models and loader.
- `realize.py` — formal item → `Question` + `SolveGuide`.
- `verify.py` — `VerificationReport` and the quality gates.
- `generate.py` — the orchestrator and `SynthItem`.
- `polish.py` — the opt-in lexicon-proposal path.
- `data/domains/*.json` — the domain packs.

No database change: generated items are `Question` values that flow into the existing JSON bank or the existing proposal store. `settings/base.py` gains `LSAT_SYNTH_AUTOPROMOTE` (default `False`).

## 8. API Surface

No new HTTP endpoints. The engine is a library plus a management command; its output reaches users through the existing `/api/lsat/questions`, `/api/lsat/proposals` and static export surfaces. `SynthExecutor` is reachable through the existing `lsat_factory execute --executor synth`.

## 9. Agent / Crew Impact

No new agent. The one optional model call lives in `synth/polish.py`, is routed through `law_ai.core.llm` (never a provider transport), is opt-in, and proposes vocabulary rather than content. Because it is not an agent output path — it cannot affect an item's logic or its key — it does not add a crew member to the registry; it is logged as an `llm_call` by the provider chain like any other model use.

## 10. Acceptance Criteria

- **AC-1**: For every schema × domain × 25 seeds, `sweep` emits a verified item and reports zero failures.
- **AC-2**: A schema whose premises are unsatisfiable fails verification with an explicit `premises_satisfiable` check, and is never emitted.
- **AC-3**: On every `logical` schema, exactly one choice carries the status its family requires and no other choice does; a hand-broken skeleton (distractor made entailed) fails verification.
- **AC-4**: `(schema, domain, seed)` is reproducible — generating twice yields byte-identical output.
- **AC-5**: Two different domains on one schema yield items sharing no content word in the stem beyond function words, and both verify.
- **AC-6**: Every generated item validates against `Question`, and every generated guide passes `validate_guide_quality`.
- **AC-7**: `SynthExecutor` fulfils a manifest job with no network and its drafts pass the spec 024 intake gates into the HITL queue.
- **AC-8**: `--promote` refuses a structural-proof item, refuses any item when `LSAT_SYNTH_AUTOPROMOTE` is false, and writes an audit event carrying the proof summary when it does promote.
- **AC-9**: `--polish` with no provider reachable emits the unpolished item rather than failing, and a proposed vocabulary entry containing a logical operator is discarded by the lint.
- **AC-10**: `make lint`, `make typecheck`, `make test` and `make lint-specs` all pass.

## 11. LegalBench Impact

None. The LSAT module is disjoint from the LegalBench harness, which stays pinned to Ollama.

## 12. Risks & Open Questions

- **R1 — "Proved" overclaiming.** The checker decides entailment over a bounded enumeration, not over all
models. Mitigated by FR-3: each space declares its bound, and the schemas are restricted to statement forms those bounds decide. The report says what was enumerated so the claim is inspectable.
- **R2 — Constitution §5 and the direct-write path.** §5 gates on *verification thresholds, not subject
matter*, and states that a new output path "inherits the requirement until the spec earns an explicit exemption". This spec earns one for a narrow case and names the mechanism: a finite-model proof that the key is entailed and no distractor is. The exemption is bounded to `logical` proofs, is off by default, requires an explicit flag, and is audited. Structural proofs stay behind HITL. If the mechanism is ever weakened, the exemption lapses with it.
- **R3 — Template monotony.** One skeleton across many domains still reads as one item shape. Mitigated by multiple stem phrasings per schema and by treating the bank's variety as a coverage metric, not a claim.
- **R4 — Domain-pack authoring burden.** Every property needs four verb-phrase forms plus a modifier.
Deliberate: explicit forms make output grammatical without a morphology dependency, and the lint catches an incomplete pack at load. FR-17 exists partly to make expansion cheap.
- **R5 — Structural guarantees mistaken for proofs.** Mitigated by FR-10 and by the promotion gate refusing anything that is not `logical`.

## 13. Out of Scope / Follow-ups

- Difficulty calibration from real learner accuracy.
- Hybrid games, rule-substitution items, and numeric-distribution games.
- Generating comparative RC sets or writing prompts.
- A UI surface for browsing and approving synthesized batches.
