# Tasks: LSATContentAuthor — Autonomous LSAT Content Generation & Refinement

> Each task references one or more `FR-*` / `NFR-*` / `AC-*` IDs from [spec.md](spec.md). All commands run inside Docker per [AGENTS.md](../../AGENTS.md) §"Docker-First Workflow".

## Conventions

- Status: `[ ]` todo / `[~]` in-progress / `[x]` done.
- Owner: `@copilot`.

---

## T-001 — `LSATContentAuthor` crew + versioned prompt

- **Refs**: FR-1, FR-2, FR-3, NFR-AUDIT-1, NFR-AUDIT-2, NFR-SEC-1, NFR-PERF-1, AC-7
- **Owner**: @copilot
- **Status**: `[x]`
- **Files**:
  - `backend/law_ai/agents_runtime/crews/lsat_content_author.py` (new)
  - `backend/law_ai/agents_runtime/prompts/lsat_content_author.v1.md` (new)
- **Steps**:
  1. Define `GenerateQuestionsInput` (section, difficulty, count<=10, concepts?, passage_id?), `DraftQuestion` (mirrors `Question` schema), `GenerateQuestionsOutput` (drafts list + trace_id + confidence + model + degraded flag).
  2. Implement `async run(input_data)` that loads the prompt file, calls Ollama (`format="json"`), validates response into `DraftQuestion` list, and falls back to a deterministic placeholder draft when Ollama fails.
  3. Single `provenance.log_agent_call(agent_name="LSATContentAuthor", ..., input_data={"child_trace_ids":[draft.id, ...]})` per invocation.
- **Verify**: Unit test `test_lsat_content_author.py` mocks Ollama, asserts schema and provenance call.

## T-002 — Proposals service (JSONL store + gap analysis)

- **Refs**: FR-4, FR-5, FR-6, FR-8, NFR-HITL-1
- **Owner**: @copilot
- **Status**: `[x]`
- **Files**:
  - `backend/law_ai/lsat/services/proposals.py` (new)
  - `backend/var/lsat_proposals/.gitkeep` (new)
- **Steps**:
  1. `record_proposal(draft, *, agent_trace_id, model, confidence) -> str` returns proposal id; appends JSONL row with status="pending".
  2. `list_proposals(status, limit)` tails the JSONL, returns newest-first with latest-status semantics (replay log).
  3. `set_status(id, status, *, reviewer, note)` appends a status-transition row.
  4. `promote_to_bank(id)` loads the latest draft, writes it into the matching `*_bank.json`, clears `load_bank.cache_clear()`, sets status="approved" with `question_id` field.
  5. `gap_analysis(window=5000)` tails audit for `lsat_grade` events, aggregates per `(section, concept)` with `attempts >= 3`, returns sorted ascending-accuracy list.
- **Verify**: `test_proposals.py` round-trips record→list→approve and asserts bank cache invalidation.

## T-003 — REST endpoints under `/api/lsat/`

- **Refs**: FR-7, FR-12, AC-1, AC-2, AC-3, AC-4
- **Owner**: @copilot
- **Status**: `[x]`
- **Files**:
  - `backend/law_ai/lsat/urls.py` (edit — add 5 `APIView` classes + url patterns)
  - `backend/tests/lsat/test_proposals_api.py` (new)
- **Steps**:
  1. `ProposalsView (GET)` — list with status filter.
  2. `ProposalGenerateView (POST)` — accepts `GenerateQuestionsInput`, calls `LSATContentAuthor.run`, persists each draft, returns `{proposals, trace_id}`.
  3. `ProposalApproveView (POST)` — calls `promote_to_bank`, returns `{question_id}`.
  4. `ProposalRejectView (POST)` — calls `set_status(id, "rejected", note=...)`.
  5. `GapsView (GET)` — returns gap_analysis output.
  6. All views reuse `RequireLsat` permission.
- **Verify**: API tests run with Django test client; assert all four AC-1..AC-4 paths.

## T-004 — Register agent + autonomy dispatcher hook

- **Refs**: FR-9, FR-10, FR-11, AC-5, AC-6
- **Owner**: @copilot
- **Status**: `[x]`
- **Files**:
  - `backend/law_ai/agents_runtime/registry.py` (edit)
  - `backend/law_ai/core/tasks.py` (edit — add `"lsat_content"` branch)
  - `backend/law_ai/core/management/commands/run_autonomy.py` (edit — add choice + `_run_lsat_content`)
  - `backend/law_ai/celery.py` (edit — `autonomy-lsat-content` beat entry)
- **Steps**:
  1. `register_all_agents()` adds `LSATContentAuthor` with `human_approval_required=True` class attribute already set.
  2. `autonomy_cycle` dispatches `kind="lsat_content"` to `_run_lsat_content`.
  3. `_run_lsat_content` picks weakest `(section, concept)` from `gap_analysis()` (falls back to LR / med when no learner data), calls the crew with `count=budget`, persists every draft as `pending`.
  4. Beat entry `autonomy-lsat-content` at `crontab(hour=4, minute=0)` with `kwargs={"kind": "lsat_content", "budget": 5}`.
- **Verify**: `curl /api/agents | jq '.agents[] | select(.name=="LSATContentAuthor")'` returns the row with `human_approval_required:true`. `python manage.py run_autonomy --kind lsat_content --budget 1 --dry-run` exits 0.

## T-005 — Frontend Authoring tab

- **Refs**: FR-12, AC-8
- **Owner**: @copilot
- **Status**: `[x]`
- **Files**:
  - `frontend/lib/api.ts` (edit — add 5 typed wrappers + `LsatProposal` / `LsatGap` interfaces)
  - `frontend/components/LsatLab.tsx` (edit — add `'authoring'` tab + `AuthoringPanel` component)
- **Steps**:
  1. Extend `TABS` array with `'authoring'`.
  2. `AuthoringPanel` fetches `/api/lsat/proposals?status=pending` + `/api/lsat/gaps` every 10s (manual refresh button).
  3. Generate form (section, difficulty, count, concepts) → posts to `/api/lsat/proposals/generate`.
  4. Each proposal renders draft preview + Approve / Reject buttons.
- **Verify**: Smoke test in browser at `/lsat` — Authoring tab loads, generate→approve flow works end-to-end against local stack.

## T-006 — Backlog + spec gates green

- **Refs**: AC-9
- **Owner**: @copilot
- **Status**: `[x]`
- **Files**:
  - `BACKLOG.md` (edit — append `BL-20260527-*` follow-ups under `## Claimed` for this spec)
- **Steps**:
  1. Append BL entries for the follow-ups recorded in plan §6.
  2. Run `python3 scripts/spec_validator.py && python3 scripts/backlog_lint.py`.
- **Verify**: both validators exit 0.

---

## Follow-ups Discovered

- **BL-20260527-04** — *feature, low* — Promote `LsatProposal` to an ORM model (Postgres) once approval throughput exceeds ~50/week so we can index by reviewer and date. _Surfaced in:_ specs/019-lsat-content-autogen.
- **BL-20260527-05** — *infra, low* — Implement JSONL rotation for `backend/var/lsat_proposals/proposals.jsonl` (rotate at 50k lines, keep last 25k) mirroring `audit_jsonl`. _Surfaced in:_ specs/019-lsat-content-autogen.
- **BL-20260527-06** — *feature, med* — Add IRT-style difficulty calibration that adjusts each promoted question's `difficulty` label based on observed `lsat_grade` accuracy after N>=20 attempts. _Surfaced in:_ specs/019-lsat-content-autogen.
- **BL-20260527-07** — *feature, low* — Add a "feedback loop" mode where `LSATContentAuthor` also re-drafts existing bank items flagged by `gap_analysis` as low-accuracy + low-confidence (questions learners consistently miss for stated reasons). _Surfaced in:_ specs/019-lsat-content-autogen.
- **BL-20260527-08** — *doc-gap, low* — Add a `LSATContentAuthor` row to [docs/agent-roles.md](../../docs/agent-roles.md) and a brief authoring section to [docs/legalbench.md](../../docs/legalbench.md) noting that LSAT bank growth is decoupled from LegalBench scoring. _Surfaced in:_ specs/019-lsat-content-autogen.
