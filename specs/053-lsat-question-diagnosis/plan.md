# Plan: LSAT Question-Type Diagnosis

> Companion to `spec.md`. Describes **how** we will satisfy the requirements.

## 1. Architecture Overview

The exercise is a thin, deterministic layer over two things the lab already had: the archetype taxonomy (spec 024) and the bank. A new `playbooks` service owns the catalog, the stem-cue classifier, option dealing and grading. The bank is stamped once by a management command so the key is explicit data; the classifier stays as the consistency check and the fallback for unstamped items. Two endpoints expose the exercise, two expose the reference catalog, and the existing stats fold gains one more block. On the client, one setting in the lab header gates a new step inside `QuestionCard`; a new page renders the catalog.

```mermaid
flowchart LR
  Bank[(bank JSON + archetype stamp)] --> PB[services/playbooks.py]
  Cat[(playbooks.json)] --> PB
  Tax[factory/taxonomy.py] --> PB
  PB --> D[GET/POST /questions/id/diagnose]
  PB --> P[GET /playbooks, /playbooks/id]
  D --> Audit[(audit_jsonl: lsat_diagnose)]
  D --> Row[(LsatDiagnosisAttempt)]
  Row --> S[GET /stats diagnosis block]
  Audit --> S
  D --> Card[QuestionCard → DiagnoseStep]
  P --> Page[/lsat/playbooks PlaybookBrowser]
  S --> Stats[StatsPanel DiagnosisProgress]
```

## 2. Component Changes

| Layer | File / Module | Change |
|-------|---------------|--------|
| Data | `backend/law_ai/lsat/services/data/playbooks.json` | new — strategies, traps, 45 playbooks with cue patterns |
| Service | `backend/law_ai/lsat/services/playbooks.py` | new — models, loaders, `classify`, `diagnosis_options`, `grade_diagnosis`, public views |
| Command | `backend/law_ai/lsat/management/commands/lsat_archetype_backfill.py` | new — stamp the bank; `--check`, `--force` |
| Data | `backend/law_ai/lsat/services/data/{lr,rc,lg}_bank.json` | `archetype` stamped on all 208 items |
| Model | `backend/law_ai/lsat/models.py`, `migrations/0005_lsat_diagnosis_attempt.py` | new `LsatDiagnosisAttempt` |
| Service | `backend/law_ai/lsat/services/attempts.py` | `record_diagnosis_attempt`, `diagnosis_summary`, `diagnosis_stats` |
| API | `backend/law_ai/lsat/urls.py` | `DiagnoseView`, `PlaybooksView`, `PlaybookDetailView`, `_fold_diagnosis`, `archetype` filter |
| Frontend | `frontend/lib/api.ts` | types + `fetchLsatDiagnosis`, `submitLsatDiagnosis`, `fetchLsatPlaybooks`, `fetchLsatPlaybook`, `archetype` filter |
| Frontend | `frontend/lib/lsat/diagnoseMode.ts` | new — persisted setting store + hook |
| Frontend | `frontend/components/lsat/DiagnoseStep.tsx` | new — the exercise + feedback |
| Frontend | `frontend/components/lsat/QuestionCard.tsx` | gate choices, guide, keys behind the step; header chip |
| Frontend | `frontend/components/LsatLab.tsx`, `LrPanel.tsx`, `lib/shell/viewState.ts` | header toggle; `?archetype=` deep link |
| Frontend | `frontend/components/lsat/PlaybookBrowser.tsx`, `app/(app)/lsat/playbooks/page.tsx` | new catalog page |
| Frontend | `frontend/components/lsat/StatsPanel.tsx`, `OverviewPanel.tsx` | recognition card; link |
| Static | `lsat-static/content.json` | regenerated (stamps) |
| Docs | `docs/lsat-playbooks.md` | new runbook |

## 3. Data & Schema Migrations

One Django migration adding `LsatDiagnosisAttempt`. Forward-only, additive. The bank stamp is a data change committed in the PR; `lsat_archetype_backfill --check` is the idempotence guard.

## 4. Tech Choices & Alternatives

| Decision | Chosen | Alternatives Considered | Why |
|----------|--------|-------------------------|-----|
| Answer key | Stem-cue classifier + committed stamps | Concept-only proxy; LLM labelling | Concept matching was ambiguous for most items (every causal weaken matched Weaken and Causal Flaw); the stem is how the exam signals type, so the key and the lesson are the same rule. No model, no HITL round-trip. |
| Storage of diagnoses | Sibling table | Flag on `LsatAttempt` | A diagnosis has no `choice`; putting it on the attempt row would pollute accuracy and the review queue (same reasoning as `LsatWritingAttempt`). |
| Partial credit | Playbook `family` | Only exact match | The distinctions that matter (necessary vs sufficient, causal vs general flaw) deserve "close", and the confusion matrix needs the sub-type resolution. |
| LG ambiguity | Task cues win; global must-be-true falls to game-type archetype by concept | Split the LG taxonomy | Keeps the spec 024 registry intact; the rule is explicit and tested. |
| Where teaching happens | Before the choices | Post-grade panel | Spec 045 FR-12 keeps the post-grade area free of author rationale; pre-choice is also the pedagogically right moment. |

No deviation from constitution §2.

## 5. Provenance & Audit Hook-up

`DiagnoseView.post` writes `lsat_diagnose` through `law_ai.core.audit_jsonl` for every call; a signed-in learner also gets an `LsatDiagnosisAttempt` row (best-effort, never fails the response). No LLM call exists on any new path, so no `llm_call` event is expected.

## 6. HITL Gates

- Bank stamps and the playbook catalog are reviewed as data diffs in the pull request.
- No agent output; no runtime approval gate is needed.

## 7. Test Strategy

- Unit: `backend/tests/lsat/test_playbooks.py` — catalog integrity, stamp agreement for all 208 items, precedence tables per section, prompt never leaks the key, grading and partial credit, summary maths.
- API: `backend/tests/api/test_lsat_diagnose.py` — both diagnose verbs, 422s, audit event, anonymous and signed-in stats fold, playbook endpoints, archetype filter, no stamp in question payloads.
- Frontend: `DiagnoseStep.test.tsx`, `PlaybookBrowser.test.tsx`, `lsatDiagnoseMode.test.ts`, plus new cases in `QuestionCard.test.tsx` and `StatsPanel.test.tsx`.
- Integration: none required beyond the Postgres the API tests already use.
- LegalBench: not affected.

## 8. Rollout

- Works after `make dev` and `make migrate`.
- Setting defaults off; opt-in per browser.
- Backfill already applied to the committed bank; `make manage CMD='lsat_archetype_backfill --check'` verifies.
- `make lsat-export` regenerates `lsat-static/content.json` with the stamps.

## 9. Risks & Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Cue over-match on a future stimulus | low | med | Only the question sentence is matched; stamp-agreement test |
| Factory census shifts for LG game-type archetypes | high | low | Recorded follow-up; census still counts by stamp as BL-20260905-54 intended |
| Learner finds the extra step slow | med | low | Opt-in, skippable per question |

## 10. Estimated Effort

One agent session (about 8 hours); no human pairing needed beyond reviewing the stamp diff.
