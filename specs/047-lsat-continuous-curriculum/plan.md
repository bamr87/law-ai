# Plan: LSAT Continuous Curriculum

> Companion to `spec.md`. Describes **how** we will satisfy the requirements.

## 1. Architecture Overview

The LSAT module already has the right skeleton: file-backed content validated by Pydantic loaders, a coverage-driven factory that plans what to author next, an HITL proposals queue, and a deterministic exporter feeding a serverless static site. This spec adds three things that skeleton lacks — a **non-MCQ content type**, **richer teaching surfaces**, and a **closed loop** that runs on a schedule and can revise as well as append.

```mermaid
flowchart TD
  subgraph Content["Content (git-versioned JSON + Pydantic loaders)"]
    BANK[bank.py<br/>questions / passages / concepts / sections]
    GUIDES[guides.py<br/>solve guides + representations]
    WRITING[writing.py<br/>prompts + rubrics · NEW]
  end

  subgraph Loop["Continuous loop (slice 7)"]
    PLANNER[coverage.plan_targets<br/>+ revision targets]
    GEN[LSATContentAuthor<br/>LSATSolveGuideAuthor]
    JUDGE[LSATDraftJudge · NEW]
    XCHECK[crosscheck.cross_check]
    GATE{3 gates agree?}
    QUEUE[(HITL proposals)]
  end

  subgraph Delivery
    EXPORT[lsat_export<br/>profiles + packets]
    STATIC[lsat-static<br/>GitHub Pages]
    API[/api/lsat/*]
  end

  BANK --> PLANNER --> GEN --> JUDGE --> XCHECK --> GATE
  GATE -- yes --> BANK
  GATE -- no --> QUEUE --> BANK
  Content --> EXPORT --> STATIC
  Content --> API
  WRITING --> EVAL[LSATWritingEvaluator · NEW]
  EVAL --> API
```

Every LLM edge in that diagram goes through `law_ai.core.llm`; every agent box writes one `provenance.log_agent_call`.

## 2. Component Changes

| Layer | File / Module | Change |
|-------|---------------|--------|
| Content | `backend/law_ai/lsat/services/writing.py` | **new** — `WritingPrompt`, `WritingRubric`, cached loaders, public views |
| Content | `backend/law_ai/lsat/services/data/writing_prompts.json`, `writing_rubrics.json` | **new** — seeded library + rubric |
| Content | `backend/law_ai/lsat/services/bank.py` | `Section` gains `"WS"`; `Question` validator rejects it; `load_writing_*` reset hooks |
| Agent | `backend/law_ai/agents_runtime/crews/lsat_writing_evaluator.py` | **new** crew — rubric-scored evaluation |
| Agent | `backend/law_ai/agents_runtime/prompts/lsat_writing_evaluator.v1.md` | **new** versioned prompt |
| API | `backend/law_ai/lsat/urls.py` | four `writing/*` routes; `writing_prompt_count` on sections |
| Export | `backend/law_ai/lsat/management/commands/lsat_export.py` | ship `writing_prompts` + `writing_rubrics`; later `--profile` |
| Static | `lsat-static/lib/types.ts`, `lib/data.ts`, `components/Writing.tsx`, `app/page.tsx` | Writing view + types |
| Taxonomy | `backend/law_ai/lsat/factory/taxonomy.py` | slice 2 archetypes |
| Guides | `backend/law_ai/lsat/services/guides.py` | slice 3 representations |
| Loop | `backend/law_ai/lsat/factory/pipeline.py`, `law_ai/lsat/tasks.py` | slice 7 revision + auto-promotion + beat entry |

## 3. Data & Schema Migrations

None. No Neo4j and no Postgres migration: LSAT content is git-versioned JSON by established design, so a content change is reviewable as a diff and rolls back with `git revert`. The new `"WS"` member of `Section` is additive — existing items never carry it, and `Question` rejects it explicitly so no stored row changes meaning.

`lsat-static/content.json` is a build artifact, refreshed by `make lsat-export` and drift-gated by `tests/test_lsat_site.py`; it is regenerated, never migrated.

## 4. Tech Choices & Alternatives

| Decision | Chosen | Alternatives Considered | Why |
|----------|--------|-------------------------|-----|
| Writing content type | Separate `writing.py` module, parallel to `bank.py` | Extend `Question` with optional key/choices; a `WS` section on `Question` | A produce-a-response task shares no field with a five-choice item; forcing them together makes every MCQ invariant conditional and silently weakens `load_bank`'s guarantees |
| `Section` gains `"WS"` | Yes, plus a `Question` validator that rejects it | A second parallel literal (`SectionCode`) | One literal keeps concept tagging and section metadata uniform; the validator restores the MCQ invariant at exactly the place it matters |
| Writing evaluation | `core.llm` provider chain with a deterministic degraded fallback | Direct Anthropic transport; local-only | Constitution §1 mandates the chain; the fallback keeps the endpoint honest offline |
| Model response visibility | Withheld unless explicitly requested (API), locked until submit (static) | Always visible | Reading the model answer first destroys the exercise — the same reasoning as guide spoiler-locking |
| Static self-score | Ships rubric + annotated model response in the bundle | Require the API for all feedback | NFR-OFFLINE-1: the published site must stay useful with no backend |
| Auto-promotion gate | Three independent gates (deterministic validation, judge, blind cross-check) | Confidence threshold alone | A single confidence number is the model grading itself; three gates include one that never sees the proposed key |

No deviation from constitution §2, so no ADR is required.

## 5. Provenance & Audit Hook-up

- `LSATWritingEvaluator` calls `llm.agenerate(..., agent="lsat_writing_evaluator")`, so the router writes the `llm_call` event, and wraps the run in one `provenance.log_agent_call` carrying prompt id, model, latency, confidence, and the degraded flag.
- `POST /api/lsat/writing/evaluate` writes an `lsat_writing_evaluate` audit event through `audit_jsonl`, mirroring `lsat_grade` and `lsat_guide`, so writing practice shows up in the same stats surface as MCQ practice.
- The evaluator writes nothing to Neo4j and creates no nodes, so the `source` / `confidence` / `ingest_timestamp` node contract is not engaged.
- Slice 7's cycles enter through `law_ai.core.autonomy.run_cycle`, which emits the paired `autonomy_cycle.start` / `.end` events (invariant I4).

## 6. HITL Gates

| Gate | Where | Mechanism |
|------|-------|-----------|
| Spec approval | this document | PR review |
| Writing evaluation output | `LSATWritingEvaluator.human_approval_required = True` | Formative feedback for one learner; never promoted into the bank. The class flag makes the registry surface the gate. |
| Bank promotion (today) | `proposals.promote_to_bank` | Reviewer approves every draft |
| Bank promotion (slice 7) | FR-20 | Deterministic validation **and** judge review **and** blind cross-check agreement; any failure routes to the reviewer. Constitution §5 exemption is earned by building all three; a single config flag returns the path to full HITL. |

Nothing in slice 1 promotes content: the writing prompt library is hand-authored and reviewed in this PR's diff, exactly like the existing bank.

## 7. Test Strategy

- **Unit** — `backend/tests/lsat/test_writing.py`: loader validation, unknown-rubric and unknown-criterion rejection, `Question` rejecting `"WS"`, public-view withholding, export payload shape.
- **Agent** — `backend/tests/agents/test_lsat_writing_evaluator.py`: the `run(input: dict) -> Pydantic` contract, one scored criterion per rubric criterion, and the degraded path when the chain is unavailable (mocked `llm.agenerate`).
- **API** — `backend/tests/api/test_lsat_writing.py`: list/detail/rubric/evaluate, model-response withholding, 404s, validation errors.
- **Root suite** — `tests/test_lsat_site.py`: writing content is present in the artifact and drift-gated against the source data files.
- **Integration** — none required for slice 1: the writing path touches no database. Slice 7 adds an `integration`-marked test running a live cycle against the Docker Ollama service (BL-20260702-05's shape).
- **Frontend** — `lsat-static` has no test runner (BL-20260831-18); the Writing view is covered by the root-suite structural assertions until that lands.
- **LegalBench** — unaffected; no run required.

## 8. Rollout

- Works after `make dev`; no new service, no new environment variable required for slice 1. `POST /writing/evaluate` degrades to a labelled offline result when no provider is reachable.
- No feature flag for slice 1 — the Writing view is additive and the prompt library is committed content.
- Slice 7's loop is flagged twice: `AUTONOMY_ENABLED` (already exists, default off) and the FR-20 auto-promotion flag (default off).
- Backfill: `make lsat-export` regenerates `content.json`; the drift gate enforces it in CI.

## 9. Risks & Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| `Section` widening breaks a consumer that assumed three members | med | med | Add `"WS"` and grep every consumer in the same change; `Question` validator plus a test pins the MCQ invariant |
| Writing bundle inflates `content.json` further | high | med | Prompts are text-only and few; FR-15's profiles land before slice 6's larger additions |
| Model bands read as an official score | med | high | NFR-PROV-1 labelling, rubric shipped alongside, wording never claims an LSAT score |
| Slice sequencing slips and slice 6 lands before slice 5 | med | med | Spec sequences FR-15 ahead of FR-17 explicitly; tasks.md orders them |

## 10. Estimated Effort

Seven slices, one PR each. Slice 1 (writing vertical, T-001…T-008) is the largest single-PR unit at roughly 2 agent-days; slices 2–7 land at roughly 1–2 agent-days each. No task needs human pairing beyond normal PR review, except the slice 7 constitution §5 exemption, which needs an explicit human sign-off on the gate design before the flag default is ever flipped on.
