# Spec: LSAT Continuous Curriculum

- **ID**: 047-lsat-continuous-curriculum
- **Status**: in-progress
- **Owner**: @bamr87
- **Created**: 2026-08-31
- **Roadmap Epic**: BACKLOG BL-20260831-23, BL-20260702-04, BL-20260831-24, BL-20260702-02
- **Constitution Compliance**: confirmed against [docs/constitution.md](../../docs/constitution.md)

## 1. Problem & Motivation

The LSAT module has a real content factory (28-archetype taxonomy → coverage census → manifest → executor → dedup/balance intake → HITL queue) and a real solving-aid layer (typed solve guides with 5 diagram representations). What it does not have is *growth*. Concretely, as of 2026-08-31:

- **126 questions** across three sections, but **86 of them (68%) have no solve guide** — the published site tells most visitors "No step-by-step guide for this question yet."
- **Nothing schedules the factory.** `lsat_factory plan/compile/run/ingest` exists and is only ever run by hand. BL-20260702-04 has flagged the missing beat entry since spec 024 shipped.
- **The factory can only add, never improve.** There is no code path that revises an existing bank item in light of cross-check disagreement, learner accuracy, or a validation finding.
- **The LSAT's writing section does not exist at all.** `Section = Literal["LR","RC","LG"]` and `Question` hard-requires five choices plus a key, so an argumentative-writing task has nowhere to live.
- **Concepts are thin and one-directional.** 18 of 30 concepts carry no worked example, 24 carry no reference, and nothing links a concept back to the guides, archetypes, or passages that teach it.
- **AI-derived explanation never reaches the static site.** Cross-check verdicts and tutor output are server-only; `content.json` carries only what a human approved into the bank.
- **The offline artifact is one monolithic 339 KB `content.json`** with no abbreviated, sharded, or printable form (BL-20260831-24).

The goal is a training tool that grows and improves on a schedule rather than only when a human sits down to author content.

## 2. Goals

- **G1**: Cover every task type a modern LSAT taker faces — including the argumentative writing section — not just the three multiple-choice sections.
- **G2**: Make the bank grow and *improve* on a schedule, with quality gated by machine verification and bounded human review rather than by human throughput.
- **G3**: Make every question teachable: a solve guide, a diagram appropriate to its reasoning pattern, and links into a concept reference deep enough to study from.
- **G4**: Make the whole curriculum consumable offline — in the browser, as a bundled artifact, and on paper.
- **G5**: Measure the curriculum's health over time so "improving" is a claim backed by a number.

## 3. Non-Goals

- **NG1**: Reproducing real, copyrighted LSAT items. All content stays original (CC0) and pattern-derived.
- **NG2**: Predicting or claiming score equivalence with an official LSAT scaled score.
- **NG3**: Adaptive per-learner sequencing / spaced repetition. Learner modelling is a separate epic; this spec only exposes gap analysis to the *authoring* loop.
- **NG4**: Building a `high_stakes` subject-matter classifier (constitution §5 forbids describing one as enforced until a spec builds it).
- **NG5**: Replacing Logic Games. LSAC retired LG from the scored exam in August 2024; LG stays as a reasoning trainer but does not receive equal expansion priority.

## 4. User Stories

- As a **test taker**, I want a writing prompt with a scoring rubric and a model response, so that I can practise the argumentative writing section and grade my own draft with no network connection.
- As a **test taker**, I want the diagram that fits the question I am on — a conditional chain for a formal-logic item, a causal map for a weaken item, an in/out board for a selection game — so the hint helps rather than forcing my reasoning into the wrong shape.
- As a **test taker**, I want each concept page to show worked examples, common traps, its prerequisites, and every bank question that drills it, so the reference is study material and not a glossary.
- As a **test taker**, I want to print a problem set with an answer key and walkthroughs, so that I can drill away from a screen.
- As a **content reviewer**, I want the factory to run on a schedule and hand me only the drafts that machine verification could not settle, so my time goes to the ambiguous cases.
- As a **maintainer**, I want a curriculum health report showing coverage, guide coverage, concept enrichment, key balance, and cross-check agreement over time, so I can see whether the loop is helping.

## 5. Functional Requirements

### Writing section (slice 1)

- **FR-1**: A writing-sample content type independent of the multiple-choice `Question` model: `WritingPrompt` (scenario, two decision positions, perspectives/criteria, task instruction) and `WritingRubric` (weighted criteria × performance bands), loaded through the same file-backed, Pydantic-validated, `lru_cache`d pattern as `bank.py`. `Question` must explicitly reject `section == "WS"` so writing content can never masquerade as an MCQ item.
- **FR-2**: A seeded prompt library covering the recurring argumentative-writing shapes, each carrying a model response annotated per rubric criterion and a self-check list a learner can score against offline.
- **FR-3**: The static site gains a Writing view: prompt selection, a 35-minute timed drafting surface whose draft persists in `localStorage`, then rubric self-scoring and the annotated model response — all with zero network calls.
- **FR-4**: An `LSATWritingEvaluator` agent implementing `run(input: dict) -> Pydantic`, scoring a learner draft per rubric criterion with band, evidence quote, and improvement note; routed through `law_ai.core.llm` with a deterministic degraded fallback, never a direct provider transport.
- **FR-5**: API surface: `GET /api/lsat/writing/prompts`, `GET /api/lsat/writing/prompts/<id>`, `GET /api/lsat/writing/rubric`, `POST /api/lsat/writing/evaluate` (LLM-throttled scope).
- **FR-6**: `lsat_export` ships writing prompts and rubrics into `content.json` under stable ordering, and the drift gate covers them the way it covers questions.

### Question-type and difficulty expansion (slice 2)

- **FR-7**: The archetype taxonomy expands to cover the LR patterns currently absent (point at issue, role of a claim, most strongly supported, cannot be true, evaluate the argument, fill in the blank, percentage-vs-number, sampling flaw, circular reasoning), the RC patterns absent (comparative Passage A/B, analogous situation, phrase-in-context), and the LG patterns absent (rule substitution, in/out selection, numeric distribution, hybrid, maximum/minimum).
- **FR-8**: Difficulty gains finer bands than `easy|med|hard`, with a documented mapping from the existing three so no stored item is invalidated.
- **FR-9**: `PassageContext` supports comparative RC sets (Passage A / Passage B) in the model, the exporter, and both UIs.

### Diagramming (slice 3)

- **FR-10**: New typed representations beside the existing five: conditional chain (with contrapositive), causal map (cause/effect with alternate-cause and confound arrows), quantifier overlap, in/out selection board, numeric distribution board, hypothetical branch tree ("frames"), answer-choice elimination trace, and comparative two-column passage map.
- **FR-11**: Each new representation renders in both the platform lab and the static site from one shared contract, so the two products cannot drift apart in what a guide can express.

### Concept depth and linking (slice 4)

- **FR-12**: Every concept carries a detail body, at least two worked examples, at least one reference, and a named common-trap list; enforced by a test, not by convention.
- **FR-13**: A concept graph: bidirectional links concept↔question, concept↔archetype, concept↔guide, concept↔section, plus a prerequisite ordering so the reference can be walked as a syllabus.
- **FR-14**: A per-concept page in both apps showing the graph links, the worked examples, the traps, and a "drill this concept" action that filters the bank.

### Offline and abbreviated copies (slice 5)

- **FR-15**: `lsat_export` gains selectable profiles (at minimum a full profile, an abbreviated profile, and per-section profiles) plus optional sharding, so a consumer can take a small slice instead of the whole bundle.
- **FR-16**: An offline study-packet export producing printable problem sets with answer keys and guide walkthroughs, generated inside Docker via `make` and reproducible byte-for-byte for unchanged content.

### Publishing AI-derived explanation (slice 6)

- **FR-17**: Machine-derived explanation reaches the static site: per-choice rationales (why each distractor fails), cross-check verdicts with the model named, and guide walkthroughs — each labelled with its provenance so a reader can tell human-approved content from machine-derived content.
- **FR-18**: Every bank question has a solve guide (closes BL-20260831-23).

### The loop (slice 7)

- **FR-19**: The factory gains an *improvement* path: given cross-check disagreement, a validation finding, or weak learner accuracy, it drafts a revision of an existing bank item rather than only appending new ones.
- **FR-20**: A verification-gated auto-promotion path: a draft that passes deterministic validation **and** an adversarial judge-tier review **and** a blind cross-check agreeing with its own key promotes automatically; anything that fails any of the three lands in the HITL queue for a human. The gate is a confidence-and-verification mechanism in the constitution §5 sense, is named explicitly, and is killable by configuration.
- **FR-21**: A scheduled loop running plan → compile → generate → judge → cross-check → promote-or-queue, budget-capped, gated by `AUTONOMY_ENABLED` and entered through `law_ai.core.autonomy.run_cycle` so every cycle is audited.
- **FR-22**: A curriculum health report — coverage deficit, guide coverage, concept enrichment, answer-key balance, cross-check agreement rate, bank size by section and difficulty — emitted per cycle so improvement is measurable across cycles.

## 6. Non-Functional Requirements

- **NFR-AUDIT-1**: Every LLM call in this spec routes through `law_ai.core.llm` (which writes the `llm_call` event) and every agent run writes one `provenance.log_agent_call` parent event. No feature module calls a provider transport directly.
- **NFR-HITL-1**: FR-20's auto-promotion is the explicit constitution §5 exemption for this spec's authoring path: it is granted only because three independent verification gates are built and named here, it applies only to practice content (never to legal analysis), and it is disabled by a single configuration flag whose default is the conservative setting.
- **NFR-OFFLINE-1**: The static site and every exported packet make zero network calls for content, including for writing prompts, rubrics, model responses, and diagrams.
- **NFR-PERF-1**: Bundle growth is bounded — the abbreviated profile of FR-15 stays materially smaller than the full profile, and the full bundle's growth is reported rather than discovered.
- **NFR-COST-1**: Every scheduled cycle is budget-capped before it starts; exceeding the cap ends the cycle rather than continuing.
- **NFR-PROV-1**: Machine-derived content published to learners (FR-17) is labelled with the producing model and prompt version wherever it is displayed.

## 7. Data Model Impact

No Neo4j or Postgres schema change. All content stays file-backed JSON under `backend/law_ai/lsat/services/data/`, loaded through Pydantic models — the established pattern for LSAT content, which is versioned in git and reviewable in a diff rather than living in a database.

New data files: `writing_prompts.json`, `writing_rubrics.json` (slice 1). Extended files in later slices: `concepts.json` (FR-12/FR-13 fields), `passages.json` (comparative sets), `guides.json` (new representations).

`Section` gains `"WS"` so writing can carry section metadata and concept tags; `Question` gains a validator rejecting it, keeping the MCQ contract intact.

Proposal rows (`law_ai.lsat.services.proposals`) gain a `writing` proposal kind in slice 1's wake and verification-verdict fields in slice 7.

## 8. API Surface

| Method | Path | Request | Response |
|--------|------|---------|----------|
| GET | `/api/lsat/writing/prompts` | `?difficulty=` | `{prompts: [PublicWritingPrompt], count}` |
| GET | `/api/lsat/writing/prompts/<id>` | `?model_response=1` | `{prompt, rubric_id, model_response?}` |
| GET | `/api/lsat/writing/rubric` | `?id=` | `{rubric: WritingRubric}` |
| POST | `/api/lsat/writing/evaluate` | `{prompt_id, response}` | `WritingEvaluation` |
| GET | `/api/lsat/concepts/<id>` | — | *(slice 4)* extended with graph links |
| GET | `/api/lsat/curriculum/health` | — | *(slice 7)* `CurriculumHealth` |

Existing `/api/lsat/sections` gains a `writing_prompt_count` field so the WS section reports its inventory without overloading `question_count`.

## 9. Agent / Crew Impact

- **`LSATWritingEvaluator`** (new, slice 1) — scores a learner's writing draft against a rubric. `human_approval_required = True` at the class level: its output is formative feedback shown to one learner, never content promoted into the bank.
- **`LSATContentAuthor`** (existing) — extended in slice 2 for the new archetypes, in slice 7 for the revision path.
- **`LSATSolveGuideAuthor`** (existing) — extended in slice 3 for the new representations; driven in bulk by slice 6's backfill.
- **`LSATDraftJudge`** (new, slice 7) — adversarial judge-tier review of a draft, one of FR-20's three gates. Wires up the `judge` tier `FactoryConfig` already defines (BL-20260702-02).

## 10. Acceptance Criteria

- **AC-1**: Writing prompts and rubrics load through validated Pydantic models; a prompt referencing an unknown rubric, or a self-check referencing an unknown criterion, fails the load loudly rather than serving.
- **AC-2**: `Question.model_validate` rejects `section == "WS"`, and `load_bank()` therefore cannot contain a writing item.
- **AC-3**: Given a seeded prompt library, `GET /api/lsat/writing/prompts` lists prompts without their model responses, and `GET /api/lsat/writing/prompts/<id>` withholds the model response unless it is explicitly requested.
- **AC-4**: `LSATWritingEvaluator.run()` returns a Pydantic evaluation with one scored criterion per rubric criterion; with every provider unreachable it returns a degraded result with confidence 0.0 rather than raising.
- **AC-5**: `make lsat-export` writes writing prompts and rubrics into `content.json`, and the root-suite drift gate fails when a writing data file changes without a re-export.
- **AC-6**: The static site renders the Writing view — prompt, timed drafting surface, rubric self-score, annotated model response — with no network request for content.
- **AC-7**: *(slice 2)* Every archetype in FR-7 exists in the taxonomy, validates against the concept catalog, and its difficulty weights sum to 1.
- **AC-8**: *(slice 3)* Each new representation in FR-10 has a renderer in both apps and a guide in the bank exercising it.
- **AC-9**: *(slice 4)* A test fails when any concept lacks a detail body, two worked examples, a reference, or a trap list; concept graph links resolve in both directions.
- **AC-10**: *(slice 5)* The abbreviated export profile is materially smaller than the full profile and both are byte-identical across runs for unchanged content apart from the timestamp.
- **AC-11**: *(slice 6)* Every bank question has a solve guide, and machine-derived published explanation carries its model and prompt version in the payload the site renders.
- **AC-12**: *(slice 7)* A draft failing any one of the three FR-20 gates does not auto-promote; disabling the gate flag routes every draft to the HITL queue; a cycle exceeding its budget ends and records the reason.

## 11. LegalBench Impact

- Tasks affected: none. The LegalBench harness stays pinned to Ollama and reads no LSAT content (CLAUDE.md non-negotiable).
- Expected delta: 0 pp.

## 12. Risks & Open Questions

- **R-1** — *Auto-promotion ships a wrong answer key.* Mitigated by requiring all three FR-20 gates to agree, by the flag default, and by the FR-22 agreement-rate metric surfacing a degrading gate.
- **R-2** — *Bundle size.* `content.json` already doubled to 339 KB when guides landed; slice 6 adds per-choice rationales on top. Mitigated by FR-15's profiles and sharding, sequenced *before* slice 6.
- **R-3** — *Generated content converges on a house style* and stops resembling real exam variety. Mitigated by exemplar rotation and by the FR-22 report tracking archetype and difficulty spread.
- **R-4** — *Writing evaluation is subjective* and a model band may not match a human reader's. Mitigated by NFR-PROV-1 labelling, by shipping the rubric and model response so the learner can self-check independently, and by never presenting a band as an official score.
- **R-5** — *Scheduled generation cost.* Mitigated by NFR-COST-1's per-cycle cap and by `AUTONOMY_ENABLED` defaulting off.

## 13. Out of Scope / Follow-ups

- Adaptive learner modelling and spaced repetition (see NG3).
- Embedding-based near-duplicate detection (BL-20260702-01) — the loop of slice 7 makes it more valuable but does not require it.
- Passage-set promotion automation (BL-20260702-07).
- A test runner for `lsat-static` (BL-20260831-18) — slice 1 adds the Writing view under the same untested conditions as the rest of that app; the shared behavioural contract belongs to that backlog item.
