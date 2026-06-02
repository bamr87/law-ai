# Spec: LSATContentAuthor — Autonomous LSAT Content Generation & Refinement

- **ID**: 019-lsat-content-autogen
- **Status**: shipped
- **Owner**: @copilot
- **Created**: 2026-05-27
- **Roadmap Epic**: extends spec 005 (LSAT Lab) and spec 018 (autonomy framework)
- **Constitution Compliance**: confirmed against [docs/constitution.md](../../docs/constitution.md) — local-first product runtime (§1, Ollama only), provenance on every LLM call (§4), HITL gate on every generated question before it reaches the live bank (§5), AO-SDLC Level 2 retained (§10), autonomy invariants reused from spec 018 (§12).

## 1. Problem & Motivation

The LSAT Lab (spec 005) ships a hand-curated bank of ~dozens of questions across LR / RC / LG. Coverage of concepts is uneven, learner accuracy data is collected but never fed back into content authoring, and there is no mechanism for the platform to grow its own training set. This spec extends the spec 018 autonomy framework to LSAT content: a new `LSATContentAuthor` crew drafts questions, the existing audit log surfaces learner accuracy / weak concepts, and a HITL proposal queue guarantees no auto-generated item reaches learners without a human approve click.

## 2. Goals

- **G1**: Add an `LSATContentAuthor` crew that drafts new LR / RC / LG questions targeting a requested section, difficulty, and concept set, returning a validated `Question` payload + confidence + explanation.
- **G2**: Persist every draft as a `LsatProposal` row in an append-only JSONL store under `backend/var/lsat_proposals/` — never written to the live bank without explicit approval (constitution §5).
- **G3**: Expose REST endpoints `/api/lsat/proposals`, `/api/lsat/proposals/generate`, `/api/lsat/proposals/<id>/approve`, `/api/lsat/proposals/<id>/reject`, and `/api/lsat/gaps` so the LSAT Lab UI can drive the loop end-to-end.
- **G4**: Compute coverage gaps from the existing `lsat_grade` audit events — `(section, concept) → (attempts, accuracy)` — so the agent can be steered toward weak areas.
- **G5**: Wire a Celery beat entry `autonomy-lsat-content` (daily 04:00 UTC, budget 5 drafts) that calls `run_cycle(kind="lsat_content")` so the loop runs continuously when `AUTONOMY_ENABLED=true`.
- **G6**: Surface the proposal queue + gap analysis in the LSAT Lab frontend as a new "Authoring" tab so reviewers can approve/reject inline.

## 3. Non-Goals

- **NG1**: No auto-merge into the bank. Every approval is one human click.
- **NG2**: No closed-source LLM fallback — drafts come from the local Ollama default model (constitution §1). When Ollama is unreachable the agent records a `degraded` status and writes a deterministic placeholder rather than failing the cycle.
- **NG3**: No new persistence layer beyond JSONL in this MVP. A future spec may promote `LsatProposal` to an ORM model once approval throughput justifies it (recorded as a follow-up).
- **NG4**: No automated learner-difficulty calibration (e.g. IRT). Difficulty stays a free-form `easy|med|hard` tag chosen by the author agent; calibration is a follow-up.
- **NG5**: No new HITL surface outside the LSAT Lab page — proposals live and die in the existing UI plus the JSONL store.

## 4. User Stories

- As a **content lead**, I want to click "Generate 3 LR questions targeting the `parallel-reasoning` concept at hard difficulty" and review the drafts in-app before they reach learners.
- As an **operator**, I want a nightly beat job that quietly drafts a small batch (≤5) of questions for the section/concept with the worst measured accuracy, so the bank grows without ad-hoc operator effort.
- As a **learner**, I should never see an unreviewed auto-generated item — every question in the bank must have been approved by a human.
- As a **maintainer**, I want every draft and approval/rejection action recorded in the existing provenance audit log so I can reconstruct exactly how a question entered the bank.
- As a **reviewer**, I want a "Gaps" panel showing the three weakest `(section, concept)` pairs by accuracy so I know which drafts to prioritise.

## 5. Functional Requirements

- **FR-1**: `LSATContentAuthor` crew at `backend/lawgraph/agents_runtime/crews/lsat_content_author.py` exposes `async run(input_data: dict) -> GenerateQuestionsOutput` with strict Pydantic input/output models (`GenerateQuestionsInput`, `GenerateQuestionsOutput`, `DraftQuestion`).
- **FR-2**: A versioned prompt lives at `backend/lawgraph/agents_runtime/prompts/lsat_content_author.v1.md` and is loaded at runtime — never inlined in the Python module.
- **FR-3**: Every `run()` invocation logs one `provenance.log_agent_call` event with agent="LSATContentAuthor", model, latency_ms, confidence, sources, and `child_trace_ids=[…]` covering each draft persisted, matching the dashboard correlation contract.
- **FR-4**: Drafts are persisted to an append-only JSONL store at `backend/var/lsat_proposals/proposals.jsonl` via `lawgraph.lsat.services.proposals.record_proposal()`. Schema: `{id, created_at, status, section, difficulty, draft, agent_trace_id, model, confidence, source_concept_ids}`.
- **FR-5**: `lawgraph.lsat.services.proposals.list_proposals(status: str | None = "pending")` returns rows filtered by status, newest-first. `lawgraph.lsat.services.proposals.set_status(id, status, *, reviewer, note)` updates the row by appending a new revision (append-only — no in-place mutation).
- **FR-6**: `lawgraph.lsat.services.proposals.gap_analysis(window: int = 5000)` returns `{(section, concept): {attempts, correct, accuracy}}` from the existing `lsat_grade` events, sorted by lowest accuracy with `attempts ≥ 3`.
- **FR-7**: New endpoints under `/api/lsat/`:
  - `GET /lsat/proposals?status=pending|approved|rejected|all&limit=N` → `{proposals: [...], count}`
  - `POST /lsat/proposals/generate` body `{section, difficulty, concepts?, count?, passage_id?}` → triggers `LSATContentAuthor.run()` and returns `{proposals: [...], trace_id}`
  - `POST /lsat/proposals/<id>/approve` body `{note?}` → promotes to the live bank file (`lr_bank.json` / `rc_bank.json` / `lg_bank.json`) and clears the `load_bank` cache; returns `{id, status: "approved", question_id}`
  - `POST /lsat/proposals/<id>/reject` body `{note?}` → marks status `rejected`; returns `{id, status: "rejected"}`
  - `GET /lsat/gaps?limit=N` → `{gaps: [{section, concept, attempts, accuracy}, …], window}`
- **FR-8**: Promotion to the live bank writes the new question into the matching section file via a single atomic `Path.write_text` of the parsed-and-re-serialised JSON; the cached `load_bank()` is cleared on success.
- **FR-9**: Register `LSATContentAuthor` in `backend/lawgraph/agents_runtime/registry.py::register_all_agents` so it appears in `/api/agents` with `human_approval_required=True`.
- **FR-10**: Add `"lsat_content"` to the autonomy dispatcher in `backend/lawgraph/core/tasks.py::autonomy_cycle` and a matching sub-runner `_run_lsat_content(context, *, budget)` in `backend/lawgraph/core/management/commands/run_autonomy.py` that:
  1. Calls `gap_analysis()` to pick the weakest `(section, concept)` pair with `attempts ≥ 3` (falls back to a low-coverage section when no learner data yet).
  2. Invokes `LSATContentAuthor` with `count=budget`.
  3. Persists every draft via `record_proposal()` with status `pending`.
- **FR-11**: Celery beat entry `autonomy-lsat-content` runs daily at 04:00 UTC with `kwargs={"kind": "lsat_content", "budget": 5}` on the `autonomy` queue. Respects the existing `AUTONOMY_ENABLED` kill-switch via `autonomy.run_cycle`.
- **FR-12**: LSAT Lab frontend (`frontend/components/LsatLab.tsx`) gains an "Authoring" tab that:
  - Shows the three weakest `(section, concept)` pairs from `/api/lsat/gaps` with their accuracy.
  - Lists pending proposals from `/api/lsat/proposals?status=pending` with approve / reject buttons.
  - Exposes a "Draft N questions" form that posts to `/api/lsat/proposals/generate`.

## 6. Non-Functional Requirements

- **NFR-PERF-1**: Drafting 3 questions completes in <90s on the local Ollama stack with the default model. The agent caps `count` at 10 to bound latency.
- **NFR-AUDIT-1**: Every draft, approve, and reject action emits an audit event via `provenance.log_agent_call` or `audit_jsonl.record`; the entire lifecycle is reconstructable from the audit log alone.
- **NFR-HITL-1**: No proposal may be promoted to the live bank except via the `/api/lsat/proposals/<id>/approve` endpoint. The autonomy beat schedule never approves; it only drafts (constitution §5).
- **NFR-SEC-1**: All LLM calls go through the local Ollama client; no external HTTP. Generated `stem` / `choices` / `explanation` strings are length-capped (≤1500 chars stem, ≤400 chars per choice, ≤2000 chars explanation) before persistence.
- **NFR-AUDIT-2**: When Ollama is unreachable the agent records `model="fallback/offline"` + `confidence=0.0`, writes a single deterministic placeholder draft labelled `requires_human_review=True`, and the cycle still emits paired `autonomy_cycle.start/.end` events.

## 7. Data Model Impact

No new Neo4j labels or Postgres tables. New JSONL store `backend/var/lsat_proposals/proposals.jsonl` with one row per draft + one row per status transition (append-only). All existing constitution §4 invariants preserved — promoted questions land in the existing per-section `*_bank.json` files with the same `Question` Pydantic shape.

## 8. API Surface

Five new endpoints under `/api/lsat/` (see FR-7). No changes to existing endpoints. No new auth scopes — the new endpoints reuse the existing `RequireLsat` permission class.

## 9. Agent / Crew Impact

New crew **LSATContentAuthor** (added to [docs/agent-roles.md](../../docs/agent-roles.md) follow-up): drafts LSAT questions from a target `(section, difficulty, concepts)`. Tools: Ollama default model, `load_concepts()` for concept enrichment, `load_passages()` for RC/LG context lookup. `requires_human_approval=True` at the class level — every draft routes through the proposal queue.

## 10. Acceptance Criteria

- **AC-1**: `POST /api/lsat/proposals/generate {"section": "LR", "difficulty": "med", "count": 1}` returns HTTP 200 with `proposals: [{id, draft: {...}}]` and `trace_id`. The draft conforms to the `Question` schema and includes 5 choices A–E (FR-1, FR-4, FR-7).
- **AC-2**: After AC-1, `GET /api/lsat/proposals?status=pending` returns the new proposal at index 0 (FR-5, FR-7).
- **AC-3**: `POST /api/lsat/proposals/<id>/approve` (a) appends the draft to the matching section bank file, (b) clears `load_bank` cache, (c) makes the question retrievable via `GET /api/lsat/questions/<question_id>` (FR-7, FR-8).
- **AC-4**: `GET /api/lsat/gaps` returns a JSON shape `{gaps: [...], window: N}` sorted by ascending accuracy; with no `lsat_grade` events recorded it returns an empty list (FR-6, FR-7).
- **AC-5**: Running `python manage.py run_autonomy --kind lsat_content --budget 2` with `AUTONOMY_ENABLED=true` writes at least one `pending` row into `backend/var/lsat_proposals/proposals.jsonl` and emits paired `autonomy_cycle.start` / `autonomy_cycle.end` events (FR-10, FR-11, NFR-AUDIT-2).
- **AC-6**: `LSATContentAuthor` appears in the `/api/agents` registry response with `human_approval_required=true` (FR-9).
- **AC-7**: With Ollama unreachable, `POST /api/lsat/proposals/generate` still returns HTTP 200, the proposal carries `model="fallback/offline"`, `confidence=0.0`, and the audit event records `degraded=true` (NFR-AUDIT-2).
- **AC-8**: The LSAT Lab frontend renders a new "Authoring" tab; clicking "Draft 1 question" triggers `/proposals/generate`; approve / reject buttons drive the corresponding endpoints (FR-12).
- **AC-9**: `python3 scripts/spec_validator.py` and `python3 scripts/backlog_lint.py` both exit 0 after this spec lands.

## 11. LegalBench Impact

No impact — this spec only generates LSAT (test-prep) content, which is not part of the LegalBench reasoning regression suite. Expected delta: 0 pp ± 0 pp on every tracked subset.

## 12. Risks & Open Questions

- **R-1** *(med)*: LLM-drafted questions may have subtly wrong answer keys. Mitigation: every draft is `pending` and requires explicit human approval (NFR-HITL-1). Approval UI surfaces the agent's confidence so reviewers triage low-confidence drafts first. — accepted.
- **R-2** *(low)*: Append-only JSONL grows unbounded. Mitigation: same rotation strategy already used by `audit_jsonl` (rotate at `MAX_LINES`, keep tail). — accepted; rotation thresholds are a follow-up.
- **R-3** *(low)*: Promotion writes to a `*_bank.json` file in-place which is `git`-tracked. Mitigation: writes go through a single atomic re-serialisation; reviewers see the diff in PR. — accepted.
