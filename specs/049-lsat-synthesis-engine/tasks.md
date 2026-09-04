# Tasks: LSAT Item Synthesis Engine

> Each task references one or more `FR-*` / `NFR-*` / `AC-*` IDs from `spec.md`. CI's [spec_validator.py](../../scripts/spec_validator.py) enforces that every requirement is referenced by at least one task.

## Conventions

- Status: `[ ]` todo / `[~]` in-progress / `[x]` done.
- Owner: GitHub handle or `@copilot` / `@agent:<role>`.
- Each task lists exact files to touch and how to verify.
- Tasks are grouped into **slices**; one slice = one PR.

---

# Slice 1 — The proof engine

## T-001 — Statement language and the four model spaces

- **Refs**: FR-1, FR-3, NFR-DETERMINISM-1
- **Owner**: @bamr87
- **Status**: `[x]`
- **Files**: `backend/law_ai/lsat/synth/logic.py` (new)
- **Steps**:
  1. Statement AST: propositional (`Atom`, `Not`, `And`, `Or`, `Implies`), monadic
     (`All`, `No`, `Some`, `NotAll`, `Most`, `AtLeast`, `Exactly`), ordering (`Before`,
     `Immediately`, `Adjacent`, `AtSlot`, `NotAtSlot`), grouping (`InGroup`, `SameGroup`,
     `DiffGroup`, `GroupSize`).
  2. `PropSpace`, `RegionSpace` (Venn-region count vectors), `OrderSpace`, `AssignSpace`,
     each enumerating exhaustively and refusing to exceed a declared bound.
  3. Document each space's bound and why it decides the forms the schemas use.
- **Verify**: `docker compose run --rm backend pytest tests/lsat/test_synth_logic.py -q --no-cov`.

## T-002 — Entailment API and the non-vacuity guard

- **Refs**: FR-2, AC-2
- **Owner**: @bamr87
- **Status**: `[x]`
- **Files**: `backend/law_ai/lsat/synth/logic.py` (edit)
- **Steps**: `classify(space, premises, candidate)` → `entailed` / `contingent` / `contradicted`
plus the premise model count; raise on an unsatisfiable premise set rather than reporting everything entailed.
- **Verify**: covered by `tests/lsat/test_synth_logic.py::TestEntailment`.

---

# Slice 2 — Schemas and lexicon

## T-010 — Domain packs

- **Refs**: FR-5, FR-7, NFR-SAFETY-1
- **Owner**: @bamr87
- **Status**: `[x]`
- **Files**: `backend/law_ai/lsat/synth/lexicon.py`, `backend/law_ai/lsat/synth/data/domains/*.json` (new)
- **Steps**: model subjects, properties (singular/plural × affirmative/negative verb phrases plus a
restrictive modifier), groups, ordering settings and entity names; validate on load; ship at least four packs in visibly different subject areas.
- **Verify**: `tests/lsat/test_synth_lexicon.py`.

## T-011 — Schema registry

- **Refs**: FR-4, FR-6, FR-10
- **Owner**: @bamr87
- **Status**: `[x]`
- **Files**: `backend/law_ai/lsat/synth/schemas.py` (new)
- **Steps**: at least 12 schemas across the provable families, each declaring its space, premise builder,
  credited answer, distractors, required per-choice status, archetype id, difficulty band and proof kind.
- **Verify**: `tests/lsat/test_synth_schemas.py`.

---

# Slice 3 — Realization and verification

## T-020 — Realizer and guide emission

- **Refs**: FR-8, FR-12, AC-5, AC-6
- **Owner**: @bamr87
- **Status**: `[x]`
- **Files**: `backend/law_ai/lsat/synth/realize.py` (new)
- **Steps**: formal item + domain pack → `Question` and a proof-derived `SolveGuide` with typed
  representations; deterministic in `(schema, domain, seed)`.
- **Verify**: `tests/lsat/test_synth_realize.py`, including a cross-domain word-disjointness case and
  `validate_guide_quality` on every emitted guide.

## T-021 — Verification report and quality gates

- **Refs**: FR-9, FR-11, AC-3
- **Owner**: @bamr87
- **Status**: `[x]`
- **Files**: `backend/law_ai/lsat/synth/verify.py` (new)
- **Steps**: per-choice status, premise satisfiability, single-entailed-choice, no equivalent choices, no
  duplicate surface, choice-length band, key-position spread across a batch.
- **Verify**: `tests/lsat/test_synth_verify.py`, including a deliberately broken skeleton.

## T-022 — Generator orchestration

- **Refs**: NFR-DETERMINISM-1, NFR-PERF-1, NFR-AUDIT-1, AC-1, AC-4
- **Owner**: @bamr87
- **Status**: `[x]`
- **Files**: `backend/law_ai/lsat/synth/generate.py` (new)
- **Steps**: `SynthItem` with full provenance; per-skeleton proof caching; batch generation with key-position
  balancing; a `sweep` that reports every failure.
- **Verify**: `tests/lsat/test_synth_generate.py`.

---

# Slice 4 — Delivery

## T-030 — `lsat_synth` management command

- **Refs**: FR-13, FR-16, NFR-OFFLINE-1
- **Owner**: @bamr87
- **Status**: `[x]`
- **Files**: `backend/law_ai/lsat/management/commands/lsat_synth.py` (new), `Makefile`
- **Verify**: `tests/lsat/test_synth_command.py`; `make lsat-synth-sweep` exits non-zero on any failure.

## T-031 — `SynthExecutor` into the factory

- **Refs**: FR-14, AC-7
- **Owner**: @bamr87
- **Status**: `[x]`
- **Files**: `backend/law_ai/lsat/factory/executors.py` (edit)
- **Verify**: `tests/lsat/test_synth_executor.py` — a job is fulfilled with no network and its drafts reach
  the HITL queue through the existing gates.

## T-032 — The bounded direct-write exemption

- **Refs**: FR-15, AC-8, AC-10
- **Owner**: @bamr87
- **Status**: `[x]`
- **Files**: `backend/law_ai/lsat/synth/generate.py` (edit), `backend/law_ai/settings/base.py`,
  `docs/lsat-synthesis.md` (new)
- **Steps**: promotion re-runs verification itself; refuses structural proofs; refuses when the setting is
  off; audits every success with the proof summary.
- **Verify**: `tests/lsat/test_synth_promote.py`; all four gates pass.

---

# Slice 5 — Optional AI wiring

## T-040 — Lexicon-proposal polish and its lint

- **Refs**: FR-17, FR-18, AC-9
- **Owner**: @bamr87
- **Status**: `[x]`
- **Files**: `backend/law_ai/lsat/synth/polish.py` (new)
- **Steps**: propose vocabulary through `law_ai.core.llm` at its cheapest tier; lint out logical operators,
length violations and duplicates; re-render and re-verify; degrade to the unpolished item when no provider is reachable.
- **Verify**: `tests/lsat/test_synth_polish.py`.

---

## Done-When (Definition of Done)

- Every task above is `[x]`.
- `make lint`, `make typecheck`, `make test`, `make lint-specs` pass.
- `make lsat-synth-sweep` reports zero verification failures.
- Follow-ups below are mirrored into [BACKLOG.md](../../BACKLOG.md) and copied into the PR body.

## Follow-ups Discovered

- **BL-20260903-13** — *feature, med* — Thirteen schemas cover the provable families,
but the archetype taxonomy has 45 entries. `SynthExecutor` correctly reports "no synthesis schema covers this archetype" for the other 32, which means the factory still falls back to an LLM for most targets. Extend the registry toward the remaining formal archetypes (parallel reasoning, role of a claim, evaluate the argument) where a proof is available.
- **BL-20260903-14** — *feature, med* — Difficulty is *declared* by each schema, not
measured. A `hard` quantifier item and a `hard` assumption item may not be comparably hard for real learners, and nothing folds `lsat_grade` accuracy back into the schema's band.
- **BL-20260903-15** — *tech-debt, low* — Each schema hard-codes one premise
arrangement, so every item from a schema shares a stimulus *shape* even across domains. Vary the arrangement (chain length, which atom is triggered, rule count) under the same proof so the bank does not read as thirteen templates.
- **BL-20260903-16** — *feature, low* — The `region` space is capped at three
predicates with `max_count=2`; four predicates need `max_count=1`, which cannot express `most`. A smarter representation (symbolic cardinality constraints rather than enumerated counts) would open up four-term quantifier items.
- **BL-20260903-17** — *test-gap, low* — `polish` is covered by unit tests with a
stubbed provider. Nothing exercises it against a real model, so the prompt's yield rate — how many proposals survive the lint — is unmeasured.
