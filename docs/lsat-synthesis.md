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

Four bounded model spaces, each enumerated exhaustively (plus one that is solved instead — see [Two ways to settle an entailment](#two-ways-to-settle-an-entailment)):

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

## Arrangements are drawn, not fixed

A schema used to hard-code one premise arrangement, so every item from it shared a stimulus shape across every domain and seed. Since `synth/2` (BL-20260903-15) the drawn schemas vary the *shape* under the same proof:

| Schema | What the seed draws |
| ------ | ------------------- |
| `lr-conditional-chain-*` | chain length 2–4, trigger position on any chain atom that leaves something to infer, one or two side conditionals hung in the unresolved direction |
| `lr-quantifier-*` | one of four premise pairs — order, the weaker quantifier (`some` vs `most`), or a third `not every` premise |
| `lg-sequencing-*` | two to four rules from a menu (before / immediately before / adjacent / at / not at), re-drawn until 2–30 arrangements survive (five or more for must-be-true, so four distinct truth patterns exist) |
| `lg-grouping-acceptability` | two to four rules from a menu (same / different / placed in / not placed in), re-drawn until more than one split survives |

Every draw goes through the same `select_distractors` proof, so a draw the checker cannot certify — one that pins every atom, contradicts itself, or entails nothing from the pool — is discarded and the next is tried. `MAX_ARRANGEMENT_DRAWS` caps the loop so a bad menu fails loudly instead of hanging a sweep. The assumption and structural schemas keep a fixed skeleton on purpose: their credited answer is defined by the gap, not the shape.

Two consequences worth knowing:

- **The skeleton is keyed on `(engine, schema, seed)` alone**; only the words are keyed on the domain as well. So the same seed yields the same proof in every domain, which makes the spec's "a domain swap changes words and nothing else" claim literal rather than approximate.
- **Provenance records the draw** (`arrangement`: chain length, trigger index, rule count, menu ids), and `ENGINE_VERSION` is bumped whenever the draw changes. The promotion gate refuses an item whose `engine_version` is not the current one: re-verifying an old seed against a new draw would prove a different item.

## Two ways to settle an entailment

Three predicates is where enumeration stops. A region space is a count vector over the 2^K Venn regions, so K=3 at three counts per region is 6,561 models — cheap — and K=4 is 43,046,721, two orders of magnitude past the engine's `MAX_MODELS` bound. Dropping the per-region cap to 1 would fit, but it also removes the 2-vs-1 margin `most` needs inside a single region, and an entailment decided over a truncated space is not the entailment the item claims.

So a four-term space is **decided rather than enumerated**. Every monadic statement is a linear constraint over the region counts — `All` and `No` are "this sum is zero", `Some` and `NotAll` are "this sum is at least one", `Most` is "this sum exceeds that one" — and entailment becomes two satisfiability questions: `premises ∧ ¬candidate` has no model (entailed), `premises ∧ candidate` has none (contradicted). `SymbolicRegionSpace` in `synth/logic.py` answers them with a depth-first search that first zeroes every region a universal premise empties, then collapses regions that appear in every constraint with the same coefficient into a single variable, then prunes on interval bounds. Typical items are decided in tens of milliseconds, and a search that will not close raises rather than hanging (`MAX_SEARCH_NODES`).

The soundness claim is not a promise, it is a test: `test_synth_logic.py::TestSymbolicRegionSpace` cross-checks the solver against full enumeration over the whole three-term pool, statement by statement, where both answers exist. Two things stay approximate on purpose. The *witness models* the solver builds along the way are a sample, not a census, so `supporting_models` on a symbolically-decided item reports witnesses (the report says `decided symbolically` so the number is never mistaken for a model count); and choice sameness is decided by mutual entailment — exactly — using those witnesses only to skip the pairs that obviously differ. The assumption families, whose criteria are set inclusions between truth masks, refuse a symbolic space outright rather than weaken the criterion.

What this buys is `lr-quantifier-chain-four-term`: three quantified premises across four terms, where the trap is that the chain's weakest link caps the conclusion — a majority through two universals is still a majority, two majorities meet only as "at least one".

## Difficulty is measured, not declared

A schema used to hand its band to every item it ever produced, which was wrong twice over. It was not comparable — `hard` on a quantifier schema and `hard` on an assumption schema were two authors' opinions wearing the same word — and it was not per item, because arrangements are drawn: a two-link chain with one side conditional and a four-link chain with two are not the same question.

So each proved item is scored on features that mean the same thing in every family (`backend/law_ai/lsat/synth/difficulty.py`): premises held at once, nesting depth of the deepest premise, slots in play, constraints the drawn arrangement imposed, the **closeness** of the best distractor (the share of premise-satisfying models in which it is true — the one number that compares a quantifier trap to an assumption trap directly), the log-size of the model space, and how many entailment relations the family's own verification rule demands. The score bands against `SCORE_CUTS`, the 40th and 75th percentiles of a full sweep, so the cuts are the engine's own distribution rather than a guess.

Two limits are deliberate. A **structural** item gets no proxy at all — no model space means every model-derived feature is zero, and `measure()` returns `None` rather than pretend, leaving the declared band in place. And the proxy never moves a band more than one step from the declared one: a prior worth keeping is still a prior, and `blend()` clamps. Provenance carries both, so a disagreement stays visible after the item ships.

Real evidence outranks both. `backend/law_ai/lsat/synth/calibrate.py` joins `lsat_grade` audit events to the schema that produced each item — the join key is the `lsat_synth.promoted` event, which carries the question id next to its provenance — and bands a schema by what learners actually did once it clears `MIN_ATTEMPTS` (30). Accuracy at or above 80% is `easy`, 55–80% is `med`, below that is `hard`; the thresholds are module constants, because a cut tuned per schema until the answer looks right is not a measurement. The factory census counts a synthesized item in its measured band when the evidence exists (`factory/coverage.py`), and keeps the emitted band until then.

```bash
make lsat-synth-calibrate                      # graded: accuracy per schema, and the disagreements
make lsat-synth-calibrate ARGS='--structural'  # offline: the proxy, and the cuts this registry implies
```

Both write `backend/var/lsat_synth/calibration.json`. Adding schemas moves the score distribution, so re-run `--structural` afterwards and update `SCORE_CUTS` deliberately if the suggestion has drifted — existing items re-band when you do.

## What the registry proves, and what it does not

The factory plans in *archetypes* — the taxonomy has 45 — and a schema declares which one it realizes. `SynthExecutor` refuses a target no schema covers rather than substituting something else, so the honest measure of this engine is how much of the taxonomy it can prove. **Seventeen archetypes today** (BL-20260903-13 took it from twelve), across nineteen schemas:

| Section | Archetypes proved |
| ------- | ----------------- |
| LR | conditional-inference, contrapositive-inference, must-be-true, most-strongly-supported, cannot-be-true, sufficient-assumption, necessary-assumption |
| LR (structural) | weaken, strengthen, percent-vs-number |
| LG | acceptability, must-be-true, could-be-true-except, local-conditional, in-out-selection, numeric-distribution, grouping |

The games families were the cheap half: could-be-true-except is the `cannot_be_true` rule over the ordering space, a local question is the global proof with the supposition added as a premise (rendered into the question sentence, where the exam puts it), in-out selection is conditional membership rules over the assignment space with their contrapositives already accounted for, and numeric distribution adds group-size rules and prefers a credited answer about the counts. `test_synth_generate.py::TestArchetypeCoverage` writes the covered set out in full, so gaining or losing one is a visible change to a test.

What stays out, and why:

- **The nine `rc-*` archetypes.** Their correctness depends on prose judgement no checker can certify. Asserting a key there would be the failure this engine exists to remove.
- **The rhetorical LR families** — equivocation, appeal-to-ignorance, principle-application, evaluate-the-argument, method-of-reasoning, point-at-issue, role-of-claim. "Which one describes the flaw" is a claim about *reasoning*, not entailment.
- **Parallel reasoning and parallel flaw**, which are decidable by shape-matching over `_shape()` but need whole arguments as answer choices; a structural guarantee like the causal families, not a proof, and not yet built.
- **`lg-max-min` and `lg-rule-substitution`**, both provable in principle — max/min needs bounded-count statements the checker does not have, and rule substitution needs its own verification family (the substitute must leave the valid-arrangement set exactly unchanged, in both directions).

The LLM executors exist for exactly these, which is the division of labour spec 049 argued for: prove what can be proved, and let a human review the rest.

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

### Measuring the prompt's yield

A prompt that is discarded more often than it is used is a broken prompt, so the polish path counts rather than assumes. Every proposal round produces a `PolishYield` — how many predicates the model proposed, how many survived the lint, and a count per reject reason (`bad-id`, `duplicate`, `missing-field`, `length`, `forbidden-word`, `not-an-object`, `unparseable`) — labelled with the provider tier that answered. It rides on the polished item's provenance under `polish`, so anything in the review queue records what the prompt produced, and it is aggregated by:

```bash
make lsat-synth-polish-yield ARGS='--rounds 2 --count 6'
```

That verb calls the provider chain by design — it is the measurement — and writes `backend/var/lsat_synth/polish_yield.json` alongside a stdout table: per domain, per provider tier, and overall. It also re-renders one item over each domain's accepted vocabulary, because a survivor that will not verify is not a survivor. `--strict` exits non-zero when the overall rate falls below `POLISH_YIELD_FLOOR` (0.5): below that the prompt is producing more rejects than vocabulary and needs re-authoring, not a bigger `--count`.

The same floor is asserted by `backend/tests/lsat/test_synth_polish_live.py`, which is marked `integration` and skipped unless `LSAT_SYNTH_LIVE_POLISH=1` — the chain's first two tiers are paid and the test settings blank LLM credentials, so a live measurement is always a deliberate act:

```bash
LSAT_SYNTH_LIVE_POLISH=1 docker compose run --rm backend \
    pytest tests/lsat/test_synth_polish_live.py -m integration -q --no-cov
```

Yield is only comparable within a tier: the same prompt yields differently on a frontier model and on a local one, which is why both the report and the failure message name the model that answered.

## Guardrails

- Every skeleton and every pack is original (CC0). No real LSAT items.
- Generation is deterministic: `(schema, domain, seed)` reproduces an item
  byte-for-byte, so anything in the bank can be regenerated from its provenance.
- RC passages, main point, tone and method are deliberately **out of scope**:
their correctness depends on prose judgement no checker can certify, and asserting a key there would be the failure this engine exists to remove.
