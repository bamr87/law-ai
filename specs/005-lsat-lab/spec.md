# Spec: LSAT Lab

- **ID**: 005-lsat-lab
- **Status**: shipped
- **Owner**: @copilot
- **Created**: 2026-04-29
- **Roadmap Epic**: User request 2026-04-29 — "build the lsat lab"
- **Constitution Compliance**: confirmed against [docs/constitution.md](../../docs/constitution.md) §§1–11.

> **Scope has grown well past this MVP.** Sections 1–13 below are the LR-only spec that shipped in 2026-04 and are kept verbatim as the historical record; `## 14. Scope evolution (post-MVP)` at the end records what the LSAT module actually is today and which specs got it there (BL-20260503-08).

## 1. Problem & Motivation

The home page advertises an "LSAT Lab" tile but `/lsat` 404s today. Law students need an interactive way to drill Logical Reasoning (LR) questions against a transparent, open question bank with per-attempt grading and rationale — not a closed black-box scorer. This spec ships an MVP grounded in the same provenance/audit machinery that powers the agent dashboard so every grading event is auditable (constitution §1, §3).

## 2. Goals

- G1: Ship a small, MIT-licensed, in-repo LR question bank (≥ 5 items) with stem, choices, correct answer, and explanation.
- G2: Expose `GET /api/lsat/questions` and `POST /api/lsat/grade` (stateless, no auth).
- G3: Render `/lsat` — a single-screen practice flow (one question at a time, immediate feedback, session score).
- G4: Log every grade event via `audit_store` so it surfaces in Agent Ops.

## 3. Non-Goals

- NG1: Full LSAT (Reading Comprehension, Logic Games) — LR only this cycle.
- NG2: Persistent user accounts / cross-session history. Session-only state (in-memory React).
- NG3: Adaptive difficulty / IRT scoring.
- NG4: AI-generated rationales. Rationales are author-written and shipped with the bank.

## 4. User Stories

- As a **law student**, I want to draw a random LR question, pick an answer, and immediately see the correct choice + rationale so I can self-quiz.
- As a **maintainer**, I want every grade attempt logged in the audit store so the dashboard reflects real usage.

## 5. Functional Requirements

- **FR-1**: New module `app.lsat.bank` exposes `load_bank() -> list[Question]` reading `app/lsat/data/lr_bank.json`. `Question` is a Pydantic model: `{id: str, type: "LR", stem: str, choices: list[Choice], correct: str, explanation: str, difficulty: "easy"|"med"|"hard"}`. `Choice = {label: "A".."E", text: str}`.
- **FR-2**: `GET /api/lsat/questions?limit=N&difficulty=…` returns up to N questions (1 ≤ N ≤ 25, default 5) **without** the `correct` or `explanation` fields. `difficulty` is optional filter.
- **FR-3**: `POST /api/lsat/grade` body `{question_id: str, choice: "A".."E"}` returns `{question_id, correct: bool, correct_choice: str, explanation: str}`. Invalid `question_id` → 404; invalid `choice` → 422.
- **FR-4**: `GET /api/lsat/stats` returns aggregate counts derived from audit events (`{attempts: int, correct: int, accuracy: float}` over the lifetime of the audit ring).
- **FR-5**: Each `POST /grade` writes one audit event `{type: "lsat_grade", question_id, choice, correct, ts}` via `audit_store.record`.
- **FR-6**: Frontend `/lsat` page: fetches a question, presents 5 radio choices, "Submit" reveals correctness + rationale + "Next" button, persistent session score (correct/attempted) in a header pill.

## 6. Non-Functional Requirements

- **NFR-PERF-1**: `GET /api/lsat/questions?limit=5` returns in < 50 ms (in-memory bank).
- **NFR-AUDIT-1**: Grade events are recorded after the response is computed; audit failures must not 500 the request.
- **NFR-COVERAGE-1**: Backend coverage stays ≥ 75%. New module ≥ 90% line coverage.
- **NFR-SEC-1**: Bank is loaded once at import; no path traversal — `question_id` lookup is dict-keyed.
- **NFR-LICENSE-1**: All bank items must be original or MIT/CC0 licensed; each item carries `source` metadata.

## 7. Data Model Impact

- No Neo4j/Postgres changes.
- One new on-disk artifact: `backend/app/lsat/data/lr_bank.json`.
- Reuses existing `audit_store` JSONL.

## 8. API Surface

```
GET  /api/lsat/questions?limit=N&difficulty=easy|med|hard
     -> {"questions": [{id,type,stem,choices,difficulty}], "count": N}
POST /api/lsat/grade
     body: {question_id, choice}
     -> {question_id, correct, correct_choice, explanation}
GET  /api/lsat/stats
     -> {attempts, correct, accuracy}
```

## 9. Agent / Crew Impact

- None this cycle. Future work: a "LR Tutor" agent that explains *why* a wrong answer is wrong using the user's reasoning trace. Filed as follow-up.

## 10. Acceptance Criteria

- **AC-1**: `GET /api/lsat/questions?limit=3` returns exactly 3 questions, each with no `correct`/`explanation` field.
- **AC-2**: `POST /api/lsat/grade` with the seeded correct choice for a known `question_id` returns `correct: true` and an `explanation` string.
- **AC-3**: `POST /api/lsat/grade` with an unknown `question_id` returns 404; invalid `choice` returns 422.
- **AC-4**: After two grade calls (one correct, one wrong), `GET /api/lsat/stats` returns `{attempts: 2, correct: 1, accuracy: 0.5}`.
- **AC-5**: `lr_bank.json` parses cleanly; every item has 5 choices labeled A–E and a `correct` ∈ {A..E}.
- **AC-6**: `/lsat` frontend route renders without 404 and shows a question stem + 5 choices.

## 11. LegalBench Impact

- Tasks affected: none. LSAT LR is not currently a LegalBench task.
- Expected delta: 0 pp.

## 12. Risks & Open Questions

- **R-1**: Question bank quality. Mitigation: ship 5 authored items + open BACKLOG follow-up to expand and add review process.
- **R-2**: Stats endpoint scans the full audit ring on every call. Mitigation: ring is bounded at 10k entries (NFR enforced by spec 003); revisit if grade volume dominates audit traffic.

## 13. Out of Scope / Follow-ups

- LR Tutor agent.
- Reading Comprehension + Logic Games.
- Per-user history (requires auth + DB).
- Question import pipeline from public LSAT prep banks.

## 14. Scope evolution (post-MVP)

Recorded 2026-09-05 (BL-20260503-08). Nothing above is retracted — it simply stopped being the whole story. FR-1…FR-6, NG1 ("LR only") and §8 describe the first cycle; the module now spans four section types, a concept catalog, passages, solve guides, a knowledge library, a tutor and an HITL authoring queue. `app.lsat.*` paths in §5/§7 are also pre-Django: the module lives at `backend/law_ai/lsat/` since [spec 011](../011-django-backend/spec.md).

**What changed, and where it came from**

| Expansion | What it added | Spec |
|---|---|---|
| Multi-section bank | `Section` enum (LR / RC / LG / WS) with `sections.json`, per-section metadata and counts, replacing the single `lr_bank.json` of FR-1 (NG1 retired) | [011](../011-django-backend/spec.md), [024](../024-lsat-content-factory/spec.md) |
| Concept catalog | `concepts.json` + `/api/lsat/concepts`, question→concept tags, `taught_in` back-links | [024](../024-lsat-content-factory/spec.md), [048](../048-lsat-knowledge-library/spec.md) |
| Passages | Shared RC passages / LG game setups addressed by id, so several questions can hang off one stimulus | [011](../011-django-backend/spec.md), [024](../024-lsat-content-factory/spec.md) |
| Tutor | `POST /api/lsat/tutor` — chain-backed explanation of a specific attempt (the "LR Tutor" follow-up BL-20260429-18 above), rate-limited under the `llm` throttle scope | [019](../019-lsat-content-autogen/spec.md), [030](../030-safety-guardrails/spec.md) |
| Authoring + HITL queue | `LSATContentAuthor`, `/api/lsat/proposals*`, scanned-page intake — nothing model-drafted reaches the bank without human approval, which keeps NG4's spirit (no unreviewed AI rationales) | [019](../019-lsat-content-autogen/spec.md), [024](../024-lsat-content-factory/spec.md) |
| Solve guides | Per-question progressive hint steps with typed diagrams, served spoiler-stripped | [045](../045-lsat-solving-aids/spec.md) |
| Argumentative Writing (WS) | `writing_prompts.json` + `writing_rubrics.json`, offline self-scoring, `POST /api/lsat/writing/evaluate` for formative feedback | [047](../047-lsat-continuous-curriculum/spec.md) |
| Knowledge library | Compiled typed-block articles, tracks, search and health checks | [048](../048-lsat-knowledge-library/spec.md) |
| Item synthesis | Generated-with-provenance items and calibration behind the same HITL queue | [049](../049-lsat-synthesis-engine/spec.md) |
| Static delivery | The approved bank exported to a serverless practice site | [025](../025-lsat-static-site/spec.md) → [docs/lsat-static.md](../../docs/lsat-static.md) |

**Current route table** (`backend/law_ai/lsat/urls.py`, mounted at `/api/lsat/`). Worked `curl` examples for the read routes, the tutor and the authoring queue are in [docs/api-examples.md](../../docs/api-examples.md#lsat-lab--apilsat).

| Method | Route | Purpose |
|---|---|---|
| GET | `sections` · `sections/<code>` | Section catalog + per-section counts (incl. `writing_prompt_count`) |
| GET | `concepts` · `concepts/<id>` | Concept catalog and detail (`taught_in` links into the library) |
| GET | `passages` · `passages/<id>` | RC passages / LG game setups |
| GET | `questions` · `questions/<id>` | Keyed items, answer + explanation withheld (FR-2 still holds) |
| GET | `questions/<id>/guide` | Solve guide, spoiler steps stripped until graded |
| GET | `questions/<id>/cross-check` | Cross-check report for an item |
| GET | `validation` | Bank-wide loader/validation report |
| GET | `library` · `library/tracks` · `library/search` · `library/health` · `library/<id>` | Knowledge library index, tracks, search, health, article |
| GET | `writing/prompts` · `writing/prompts/<id>` · `writing/rubric` | Writing prompts (model response withheld until submit) and the rubric |
| POST | `writing/evaluate` | Rubric-scored formative feedback (`LSATWritingEvaluator`) |
| POST | `grade` | Grade one attempt (FR-3, unchanged) |
| GET | `stats` | Aggregate accuracy from audit events (FR-4, unchanged) |
| POST | `tutor` | Explanation for one attempt, through `LLM_PROVIDER_CHAIN` |
| GET/POST | `proposals` · `proposals/generate` · `guides/generate` · `proposals/<id>/approve` · `proposals/<id>/reject` · `proposals/passages/approve` | HITL authoring queue |
| POST | `intake/ocr` | Scanned-page intake into the queue |
| GET | `gaps` | Coverage gaps across sections/concepts |

## Follow-ups Discovered

- **BL-20260429-18** — *feature, med* — Author "LR Tutor" agent that produces personalized rationales per attempt (constitution §3 audit-grade) — see spec 005 Out of Scope.
- **BL-20260429-19** — *feature, low* — Expand `lr_bank.json` to ≥ 50 items with editorial review; add a CI check that validates schema + label set.
- **BL-20260429-20** — *feature, low* — Add Reading Comprehension + Logic Games question types (extend `Question.type` enum).
