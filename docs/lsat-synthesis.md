# LSAT Item Synthesis Engine

A second way to grow the question bank: **derive the item from a formal model, prove the key, and vary only the surface.**

The spec 024 factory prompts a model for an item and a human checks it. This engine builds an item from a skeleton whose credited answer a finite-model checker *proves* is entailed and whose distractors it proves are not. Nothing about the logic is left to a language model, so nothing about the logic can be wrong — and because the words come from swappable dataset "domain packs", one proved skeleton yields as many distinct items as there are domains and seeds.

Introduced by [specs/049-lsat-synthesis-engine](../specs/049-lsat-synthesis-engine/spec.md).

## The one idea

**Logic and words never mix.**

| Layer | Contains | Never contains |
| ----- | -------- | -------------- |
| `schemas.py` | premises, credited answer, distractor pools — as *structures* over slot names | any English |
| `data/domains/*.json` | subjects, properties, entity names, settings, scenarios | any premise, inference, or key |
| `realize.py` | the template fill where the two meet | any inference |

Swapping the domain changes every noun in an item and cannot change a single entailment, because the checker never sees a word. It also makes verification cheap: the proof is a property of the *skeleton*, so it is computed once and reused across every realization of it.

## Quick start

```bash
make lsat-synth-list                     # what exists, and which schemas prove vs construct
make lsat-synth-sweep                    # generate across everything and verify each item
make lsat-synth-preview ARGS='--schema lr-quantifier-most-overlap --domain field-biology'
make lsat-synth-generate ARGS='--schema lr-necessary-assumption --count 20 --emit proposals'
```

Everything above is offline. The only path that calls a model is `--polish`.

## The checker

Four bounded model spaces, each enumerated exhaustively:

| Space | A model is | Bound | Decides |
| ----- | ---------- | ----- | ------- |
| `prop` | truth assignment over K atoms | 2^K, K ≤ 8 | conditionals about one subject |
| `region` | count vector over the 2^K Venn regions | (C+1)^(2^K) | all / some / no / most / exactly-n |
| `order` | permutation of E entities | E!, E ≤ 7 | sequencing games |
| `assign` | function entities → groups | G^E | grouping games |

`region` is the load-bearing one. Every LSAT quantifier statement is a function of *how many* things fall in each Venn region, not of which, so counting regions rather than enumerating individuals makes `most` exact and keeps the space small. `MAX_MODELS` is enforced, not advisory: a schema that outgrows the engine fails at authoring time rather than hanging CI.

`evaluate()` returns each candidate's **truth mask** over the premise-satisfying models. One structure answers three questions — entailed (all bits set), contradicted (no bits), equivalent-to-another-choice (identical masks) — so an item is classified with one enumeration.

The guard that matters most: **an inconsistent premise set entails everything**, which would certify all five choices. `evaluate` raises rather than reporting that as a pass.

## Two proof kinds, never conflated

**`logical`** — the credited answer's status is *decided* by the checker and each distractor is decided not to have it. Covers conditional chains, cannot-be-true, quantifier combination, both assumption families, and both game families.

The assumption families have exact model-theoretic criteria, which is why they sit on this side of the line. Over the premise-satisfying models, with `mask_c` for the conclusion:

- **sufficient** — `mask_choice ⊆ mask_c`: every case where the assumption holds
  is a case where the conclusion holds, so adding it forces the conclusion.
- **necessary** — `mask_c ⊆ mask_choice`: every case where the argument succeeds
is a case where the assumption holds. That is the negation test written as a set inclusion.

**`structural`** — the item is *built* to commit exactly one enumerated defect, the credited answer names it, and distractors come from a disjoint inert pool. Covers causal weaken/strengthen and percentage-versus-number, where the credited answer is prose and no checker can certify a description. A real guarantee about where the text came from — and not a proof, so the promotion gate refuses it.

## What verification actually checks

Beyond the family rule, every item must clear:

- `premises_satisfiable` — a contradiction would certify everything
- `no_equivalent_choices` — two choices with the same truth mask are one choice
written twice (skipped on acceptability items, where every distractor is impossible *by design*)
- `choices_distinct`, `choices_non_trivial`, `choice_length_band`
- `credited_length_is_unremarkable` — the credited answer must not be the unique
length outlier in *either* direction, or "pick the longest" (or shortest) solves the item without reading it

Distractor selection builds two properties in rather than checking them afterwards: candidates are drawn only from statements the checker proved are not credited, and only with pairwise-distinct truth masks and — where possible — the same *form* as the credited answer, so the five options are parallel sentences.

## Adding a domain pack

Drop a JSON file in `backend/law_ai/lsat/synth/data/domains/`. No engine code changes. It needs:

| Field | Notes |
| ----- | ----- |
| `subjects` | ≥2. **Every subject must accept every property** — the binder pairs them freely, so "the survey site was genetically sequenced" is a pack bug. |
| `properties` | ≥6, each with singular/plural × affirmative/negative verb phrases, a modifier, and `modifier_plural` when the modifier is a relative clause. |
| `entities`, `entity_noun` | ≥6 surnames, plus what they are ("applicants"). |
| `groups`, `orderings` | Game scaffolding. Frames take `{n}` for the entity count. |
| `causal_scenarios` | Observation plus the three attacks, a control comparison, and ≥4 **genuinely inert** facts. The structural guarantee is this disjointness. |
| `ratio_scenarios` | A rate, a base change, and ≥4 inert facts. |

Then `make lsat-synth-sweep`. Author the inert facts in the same length band as the attacks, or the length gate will (correctly) reject the items.

Verb forms are authored rather than derived on purpose: explicit forms make output grammatical with no morphology dependency, and the loader rejects an incomplete pack.

## Adding a schema

Implement `build`, `stem`, `explain`, `method` and register the instance. `build` returns a `Blueprint` — space, premises, credited choice, distractors — containing no English. Supply a *generous* distractor pool and let `select_distractors` draw from the ones the checker proved are not credited; a schema author cannot then accidentally ship a "wrong" answer that is in fact entailed.

Two traps worth knowing:

- **Do not pin every atom.** Premises that determine every atom leave one model,
and in one model every true statement is entailed — an item with five correct answers. Hang extra conditionals off the chain in the direction that stays unresolved once the trigger fires.
- **Slot letters avoid A–E.** Those are the answer labels, and a stimulus
symbolized `A → B` beside choices labelled (A)–(E) confuses readers and trips the spec 045 guide linter.

## Where items go

**Default — the review queue.** `--emit proposals` records pending proposals; `lsat_factory execute --executor synth` fulfils manifest jobs with no network and sends drafts through the same dedup, lint and balance gates as LLM drafts.

**The bounded exemption — `--emit bank --promote`.** Constitution §5 enforces HITL through "confidence and verification thresholds, not by a subject-matter classifier", and says a new output path "inherits the requirement until the spec earns an explicit exemption". A finite-model proof is a verification threshold — a stronger one than the 0.7 confidence score that already licenses an unattended ingestion commit. So the exemption exists and is bounded by five conditions that must *all* hold:

1. `proof_kind == "logical"` — structural guarantees are never eligible
2. a clean report, **re-run at the gate** rather than trusted from the caller
3. the item reproduces from its provenance
4. `LSAT_SYNTH_AUTOPROMOTE` enabled — default off
5. `--promote` passed explicitly — the setting alone is not consent

Every promotion writes an `lsat_synth.promoted` audit event carrying the proof summary: space, models enumerated, models satisfying the premises, and each choice's status. That record is the justification for skipping a human, so it is kept verbatim.

## The optional AI wiring

`--polish` is the one path that calls a model, and it never touches the logic.

The model proposes **lexicon entries, not sentences**. Asking it to reword a rendered stimulus would let it change the logical form — "if" to "only if" is one word and a different item — and no cheap check would catch that. Instead it proposes *properties*, the item is regenerated from the same schema and seed through the unchanged templates, and the logic is preserved by construction. Proposals are linted for logical vocabulary, length and duplication, and a failing proposal is discarded rather than repaired. No provider means the unpolished item, which was already correct.

## Guardrails

- Every skeleton and every pack is original (CC0). No real LSAT items.
- Generation is deterministic: `(schema, domain, seed)` reproduces an item
  byte-for-byte, so anything in the bank can be regenerated from its provenance.
- RC passages, main point, tone and method are deliberately **out of scope**:
their correctness depends on prose judgement no checker can certify, and asserting a key there would be the failure this engine exists to remove.
