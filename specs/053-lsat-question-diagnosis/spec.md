# Spec: LSAT Question-Type Diagnosis

- **ID**: 053-lsat-question-diagnosis
- **Status**: shipped
- **Owner**: @bamr87
- **Created**: 2026-09-07
- **Roadmap Epic**: LSAT continuous curriculum ([specs/047](../047-lsat-continuous-curriculum/spec.md)) — the exam-literacy layer
- **Constitution Compliance**: confirmed against [docs/constitution.md](../../docs/constitution.md)

## 1. Problem & Motivation

The LSAT Lab drills answers. A learner reads a stem, picks A–E, and is told right or wrong. What it never asks is the question a strong test-taker answers silently before reading a single choice: *what kind of question is this, and what do I do first?* The exam signals its type through stem phrasing ("most weakens", "depends on assuming", "most similar in its flawed reasoning"), and the type fixes the task, the task fixes the method, and the method names the traps planted in the wrong answers. That recognition skill is the single most teachable pattern in the exam, and the lab had no way to practise or measure it.

The material to teach it already existed in three unstructured places: the archetype registry's authoring guidance in the factory taxonomy, the free-prose "orient" step at the top of every solve guide (titled "Read the question type" seventeen times), and the `[!trap]` callouts in the knowledge library. None of it was machine-readable, none of it was an exercise, and no bank item carried a stored question type at all — `Question.archetype` was `None` on every one of the 208 items (BL-20260905-54).

This spec adds a second training layer beside answering: **diagnose first**. Before the choices appear, the learner names the question type and the strategy; the lab marks the call and hands over the type's playbook — the cue that gave it away, the task, the method, and the traps — then shows the choices. Over time the stats surface says not just "62% on type" but "you keep calling necessary assumptions sufficient".

## 2. Origin & Background

- Backlog items claimed: **BL-20260905-54** (bank items carry no `archetype` stamp; the backfill of the 208 existing items was left undone because a stamp copied from the concept proxy would freeze a guess). This spec resolves it with a stem-cue classifier whose stamps are the same call the exercise marks a learner on, reviewed as a data diff in the PR.
- Prior art: [specs/024](../024-lsat-content-factory/spec.md) (the archetype taxonomy this keys on), [specs/045](../045-lsat-solving-aids/spec.md) (solve guides; FR-12 forbids author rationale and external links in the post-grade answer area, which this design respects by placing all teaching before the choices), [specs/047](../047-lsat-continuous-curriculum/spec.md) (NG3 excludes adaptive sequencing, which stays excluded here), [specs/048](../048-lsat-knowledge-library/spec.md) (library articles carry `archetypes:` frontmatter, which the playbook detail endpoint uses for "taught in").
- **Review question (constitution §13)**: no — this feature ranks, scores and summarises LSAT question types and a learner's recognition of them; it never touches legal authority.

## 3. Goals

- G1: Every bank item carries a machine-readable question type, derived from the stem the way a learner is taught to read it, and reviewable as data.
- G2: A structured playbook per question type — cues, task, strategies, method, traps, look-alikes — with strategies and traps as shared catalogs so the same trap is named the same way everywhere.
- G3: An exercise that asks the learner to commit to a type and a strategy before seeing the choices, marks the call with family-level partial credit, and teaches from the playbook.
- G4: A stats readout of recognition accuracy that is actionable: weakest types and most frequent confusions, each linking to its playbook.
- G5: Zero model calls. Everything is deterministic data over the bank and the taxonomy.

## 4. Non-Goals

- NG1: Adaptive sequencing (dealing the next question from the weakest type) — spec 047 NG3 fences it off; it is a follow-up.
- NG2: `lsat-static` parity for the exercise and the playbook page — the static export gets the stamped bank via `content.json` now; the UI mirror is a follow-up.
- NG3: LLM-drafted playbooks through the HITL queue. The 45 playbooks are hand-authored data in this spec.
- NG4: Per-choice trap tagging (naming the trap a learner *fell for* on a wrong answer). Spec 047 FR-17's per-choice rationales are the natural home; follow-up.
- NG5: Any change to answer grading, the Leitner review queue, or the accuracy denominator. A diagnosis is a different response and never enters them.

## 5. User Stories

- As a learner, I want to be asked what type a question is before I see the choices, so that I practise the read the exam rewards instead of skipping straight to elimination.
- As a learner who called a causal flaw a general flaw, I want to be told I had the right family and the wrong sub-type, so that the feedback is proportionate and I learn the distinction that matters.
- As a learner, I want to see which types I misread most and which pairs I swap, so that I know what to study next.
- As a learner, I want one page listing every question type with how to spot it, what it asks, the method, and the traps, so that I can study the exam's structure as a whole.
- As a content maintainer, I want the archetype stamp on every bank item to be derived by a rule I can read and re-run, so that a new item that arrives without a stamp fails a test rather than silently degrading the exercise.

## 6. Functional Requirements

- **FR-1**: A playbook catalog (`data/playbooks.json`) with three shared collections — strategies, traps, playbooks — where every question archetype in the taxonomy has exactly one playbook, and every strategy, trap and `confused_with` reference resolves. Loading fails loudly otherwise.
- **FR-2**: Every bank item carries `archetype`, stamped by a management command (`lsat_archetype_backfill`) that derives it from the stem via FR-3, writes it into the bank JSON, and supports `--check` (report, fail if anything is unstamped) and `--force` (re-derive every stamp).
- **FR-3**: A deterministic classifier that matches the stem's *question sentence* (its last paragraph) against each same-section playbook's cue patterns, resolving ties by an explicit priority (specific before general: parallel-flaw before parallel-reasoning; a flaw sub-type only when the item carries its concept), then concept overlap. A stored stamp always wins. With no cue hit it falls back to the unique archetype whose primary concept the item carries, and to "unclassifiable" rather than a guess.
- **FR-4**: `GET /api/lsat/questions/<id>/diagnose` deals the prompt: the key plus same-section distractor types (preferring the key's `confused_with`), and candidate strategies (always including the key's primary), shuffled deterministically per question. Nothing in the payload marks the key.
- **FR-5**: `POST /api/lsat/questions/<id>/diagnose` with `{archetype_id, strategy_id?}` returns the marked diagnosis: the key and its name, `archetype_correct`, `family_correct`, `strategy_correct` (null when no strategy was named; any of the key's strategies counts), the cue quoted from this stem, and the full playbook. Unknown ids are 422.
- **FR-6**: Family-level partial credit: each playbook declares a `family`; a wrong type in the right family is reported as such and rendered as "close", not "wrong".
- **FR-7**: `GET /api/lsat/stats` gains a `diagnosis` block — attempts, type/family/strategy accuracy, `by_archetype` weakest-first, `weakest`, and `confusions` (chosen, actual, count) most-frequent-first — in both readings: a signed-in learner's rows from a new `LsatDiagnosisAttempt` table, everyone else from `lsat_diagnose` audit events. Section filter applies.
- **FR-8**: `GET /api/lsat/playbooks?section=` returns the playbooks (optionally one section's) with the strategy and trap catalogs; `GET /api/lsat/playbooks/<archetype_id>` adds `taught_in` (library articles naming the archetype), `question_count` (stamped items), and the taxonomy's difficulty weights.
- **FR-9**: `GET /api/lsat/questions` accepts `archetype=<id>` and the lab honours `/lsat?tab=LR&archetype=<id>` so a playbook's "drill this type" lands on the type. Passage sections link by the type's primary concept, which their panels already filter on. The stamp itself is never shipped in a question payload.
- **FR-10**: A "Diagnose first" setting in the lab header (persisted per browser). While on, `QuestionCard` renders the diagnosis step in place of the choice list, the keyboard hints, the solve guide and the submit button until the learner has checked a type or skipped; letter shortcuts and Enter are inert meanwhile. A card restored with a saved graded answer is never re-asked.
- **FR-11**: The diagnosis feedback shows the verdicts, the quoted cue and the type's cue phrases, the task, the method as ordered steps, the strategies, the traps, the look-alike types, a link to the type's playbook, and a "Now answer it" control. After continuing, the card's header carries the learner's read as a chip.
- **FR-12**: A `/lsat/playbooks` page renders the whole catalog by section with the trap glossary, deep-linkable by `#<archetype_id>`, each entry carrying its drill link. The lab's Overview links to it.

## 7. Non-Functional Requirements

- **NFR-AUDIT-1**: Every diagnosis writes an `lsat_diagnose` event through `law_ai.core.audit_jsonl`, signed-in or not, with the key, the call, and the verdicts.
- **NFR-DETERMINISM-1**: Classification and option dealing are pure functions of the bank, the catalog and a seed; a test asserts every stamp in the bank is reproduced by the classifier.
- **NFR-SPOILER-1**: No question payload or diagnosis prompt exposes `archetype`; the type is revealed only by a graded diagnosis.
- **NFR-PROV-1**: No LLM is called anywhere on these paths; the playbooks carry `source: original (CC0)`.
- **NFR-SEP-1**: Diagnoses live in their own table and never enter the answer-accuracy denominator or the Leitner review queue.

## 8. Data Model Impact

- New Postgres table `lsat_lsatdiagnosisattempt` (migration `0005_lsat_diagnosis_attempt`): user FK (CASCADE), `question_id`, `section`, `archetype_id`, `chosen_archetype`, `archetype_correct`, `family_correct`, `chosen_strategy`, nullable `strategy_correct`, `created_at`; indexes on `(user, -created_at)` and `(user, archetype_id)`.
- Bank JSON: `archetype` populated on all 208 items (was null). `coverage._matches` already prefers the stamp, so the factory census now counts by stamp.
- New data file `backend/law_ai/lsat/services/data/playbooks.json` (29 strategies, 22 traps, 45 playbooks).
- No Neo4j change.

## 9. API Surface

| Method | Path | Request | Response |
| ------ | ---- | ------- | -------- |
| GET | `/api/lsat/questions/<id>/diagnose` | — | `DiagnosisPrompt` |
| POST | `/api/lsat/questions/<id>/diagnose` | `{archetype_id, strategy_id?}` | `DiagnosisResult` |
| GET | `/api/lsat/playbooks?section=` | — | `{playbooks, count, strategies, traps}` |
| GET | `/api/lsat/playbooks/<archetype_id>` | — | playbook view + `taught_in`, `question_count`, `difficulty_weights` |
| GET | `/api/lsat/questions?archetype=` | filter | unchanged shape |
| GET | `/api/lsat/stats` | — | adds `diagnosis` |

Models live in `law_ai.lsat.services.playbooks` (`Playbook`, `Strategy`, `Trap`, `Classification`, `DiagnosisPrompt`, `DiagnosisResult`).

## 10. Agent / Crew Impact

None invoked at runtime. The factory's `select_exemplars` and coverage census read the new stamps, which makes exemplar selection exact (the goal of BL-20260905-54) and shifts the LG census toward task archetypes (see follow-ups).

## 11. Acceptance Criteria

- **AC-1**: Given the taxonomy, when the catalog loads, then every question archetype has one playbook and every referenced strategy, trap and look-alike id exists.
- **AC-2**: Given the bank, when each item's stamp is cleared and the classifier re-run, then it reproduces the stored stamp for all 208 items and every item has one.
- **AC-3**: Given `GET .../diagnose`, when the prompt is returned, then the key is among the type options, all options are same-section and distinct, the key's primary strategy is among the strategy options, and no field marks the key.
- **AC-4**: Given `POST .../diagnose` with the right type and one of its strategies, then both verdicts are true, the playbook is attached, and an `lsat_diagnose` audit event exists.
- **AC-5**: Given a causal-flaw item and the call "general flaw", then `archetype_correct` is false and `family_correct` is true.
- **AC-6**: Given a signed-in learner who diagnoses, then a `LsatDiagnosisAttempt` row exists, `/api/lsat/stats` reports it under `diagnosis` with the confusion pair, and `attempts` (answer accuracy) is unchanged.
- **AC-7**: Given `GET /api/lsat/playbooks/lr-necessary-assumption`, then `taught_in` names `lr-assumption-family` and `question_count` is at least one; an unknown id is 404; `?section=WS` is 422; `?archetype=lr-weaken` on the questions list returns only weaken items and no `archetype` field.
- **AC-8**: Given "Diagnose first" is on, when a card mounts, then the answer radiogroup, submit button and solve guide are absent and the letter keys select nothing until the learner skips or checks; a card with a saved graded answer shows the choices immediately.
- **AC-9**: Given a checked diagnosis, then the feedback renders the verdicts, the quoted cue, method steps, traps and the playbook link, and "Now answer it" reveals the choices with the learner's read as a header chip.
- **AC-10**: Given the playbooks page, then one section shows at a time, each entry has a drill link (`?archetype=` for LR, `?concept=` for RC/LG), and the trap glossary renders once.
- **AC-11**: Given a stats payload with a `diagnosis` block, then the stats panel renders the accuracies, the confusions as "Called X 'Y' ×n" with playbook links, and nothing when there are no diagnoses.

## 12. LegalBench Impact

- Tasks affected: none. No reasoning path or model prompt changes.
- Expected delta: 0 pp.

## 13. Risks & Open Questions

- **R-1**: Logic Games archetypes mix task (acceptability, local conditional) with game type (grouping, hybrid, in/out). The classifier resolves it by an explicit rule — task cues win; a global must-be-true falls to the game-type archetype its concepts name — and the playbooks describe those three as "a global question in a grouping / hybrid / selection game". Mitigation: the rule is a test fixture, and the coverage census delta it causes is a recorded follow-up.
- **R-2**: A cue pattern that over-matches a future item's stimulus text. Mitigation: only the question sentence is matched, and the stamp-agreement test fails the build on any drift.
- **R-3**: Reading the type before the choices changes timing on a drill. Mitigation: the setting is opt-in and per browser, and the elapsed clock is unaffected by the diagnosis step.

## 14. Out of Scope / Follow-ups

- Static-site parity, adaptive sequencing by weakest type, LLM-drafted playbooks under HITL, per-choice trap tagging, a server-side type filter for passage sections, and the LG census delta — all recorded in `tasks.md` and mirrored to `BACKLOG.md`.
