# Tasks: Legal journey platform — the matter spine

> Each task references `FR-*` / `NFR-*` / `AC-*` IDs from `spec.md`. CI's `spec_validator.py` enforces that every requirement in `spec.md` is referenced by at least one task. Docker-first: every gate below runs via `make` / `docker compose run --rm` ([AGENTS.md](../../AGENTS.md)).

## Conventions

- Status: `[ ]` todo / `[~]` in-progress / `[x]` done.
- Owner: GitHub handle or `@copilot` / `@agent:<role>`.
- Order is dependency-sorted; tasks marked `(parallel)` can run concurrently once their predecessors land.

---

## T-001 — Matters app skeleton: models, migrations, soft-archive

- **Refs**: FR-1, FR-3, FR-4, FR-5, NFR-DATA-1, AC-4
- **Owner**: @copilot
- **Status**: `[ ]`
- **Files**:
  - `backend/law_ai/matters/{__init__.py,apps.py,models.py,admin.py}` (new)
  - `backend/law_ai/matters/migrations/0001_initial.py` (new)
  - `backend/law_ai/settings/base.py` (INSTALLED_APPS)
  - `backend/tests/matters/test_models.py` (new)
- **Steps**:
  1. Define `JourneyStage` choices enum (`intake, issues, research, analysis, drafting, action, resolution`) — the single codification (FR-1).
  2. Models: `Matter` (owner FK `on_delete=PROTECT`, `confidential`, `stage`, `archived_at`), `MatterArtifact` (kind enum `analysis|research|note|draft|intake`, stage tag, JSON payload, trace ids, creator FK `SET_NULL`, `archived_at`), `JourneyEvent` (actor, kind, timestamp, payload), `ShareLink` (slug unique, artifact FK, `revoked_at`). Indexes on all FKs + `(owner, archived_at)`.
  3. No `delete()` exposure: model managers default-filter archived; admin uses archive action, not delete.
- **Verify**:
  - `docker compose run --rm backend pytest tests/matters/test_models.py -q` passes (constraints, soft-archive filtering, AC-4 no-hard-delete).
  - `make typecheck` clean on touched modules.

## T-002 — Accounts: session auth endpoints + `ApiToken.user` + anonymous regression

- **Refs**: FR-2, NFR-SEC-1, NFR-COMPAT-1, AC-3
- **Owner**: @copilot
- **Status**: `[ ]`
- **Files**:
  - `backend/law_ai/core/urls_auth.py` (new: login/logout/me, CSRF-aware)
  - `backend/law_ai/core/models.py` + `core/migrations/000X_apitoken_user.py` (nullable `user` FK)
  - `backend/law_ai/core/auth.py` (accept session OR scope key; never require session on existing routes)
  - `backend/law_ai/urls.py` (mount `api/auth/`)
  - `backend/tests/api/test_auth_session.py` (new), extend existing auth tests for regression
- **Steps**: session login/logout/whoami with Django defaults; wire DRF authentication so anonymous scope-key behaviour is byte-identical; never log credentials.
- **Verify**:
  - `docker compose run --rm backend pytest tests/api/test_auth_session.py -q` passes.
  - Full pre-existing suite green untouched: `make test-backend` (AC-3).

## T-003 — Reviewer identity: user FK on HITL decisions (parallel)

- **Refs**: FR-2, NFR-AUDIT-1
- **Owner**: @copilot
- **Status**: `[ ]`
- **Files**:
  - `backend/law_ai/ingestionapp/models.py` + migration (nullable `reviewer_user` FK)
  - LSAT proposal approve/reject path (`backend/law_ai/lsat/…` service that records reviewer/note)
  - `backend/tests/ingestion/test_reviewer_identity.py` (new)
- **Steps**: populate the FK whenever an authenticated reviewer approves/rejects (quarantine + LSAT proposals); keep free-text field as fallback for legacy rows. Closes BL-20260811-04.
- **Verify**: `docker compose run --rm backend pytest tests/ingestion/test_reviewer_identity.py -q`.

## T-004 — Matter API + journey service + provenance events

- **Refs**: FR-5, FR-7, NFR-AUDIT-1, NFR-PERF-1, AC-9
- **Owner**: @copilot
- **Status**: `[ ]`
- **Files**:
  - `backend/law_ai/matters/urls.py`, `matters/services/journey.py` (new)
  - `backend/law_ai/urls.py` (mount `api/matters/`)
  - `backend/tests/matters/test_api.py`, `tests/matters/test_provenance.py` (new)
- **Steps**: owner-scoped CRUD (list excludes archived by default, `?include_archived=`), PATCH stage transition, archive action, paginated artifacts + timeline. `services.journey` is the sole mutation path: each mutation writes the `JourneyEvent` row AND `provenance.log_event("journey_event", …)` with actor (JSONL-first).
- **Verify**:
  - `docker compose run --rm backend pytest tests/matters/ -q` passes (AC-9 event-per-mutation).
  - Pagination asserted at 1k artifacts (NFR-PERF-1 shape; latency measured in T-008).

## T-005 — Persist analyses into matters (`matter_id` on `/api/analysis`)

- **Refs**: FR-6, NFR-COMPAT-1, AC-1
- **Owner**: @copilot
- **Status**: `[ ]`
- **Files**:
  - `backend/law_ai/analysis/urls.py` (`AnalysisRequest.matter_id`, persistence branch)
  - `backend/tests/api/test_analysis_persistence.py` (new)
- **Steps**: after a successful run with `matter_id` + write access, store the full `AnalysisResponse` as an `analysis` artifact + journey event via `services.journey`; without `matter_id`, code path unchanged. Closes BL-20260429-25 (matter scope).
- **Verify**: `docker compose run --rm backend pytest tests/api/test_analysis_persistence.py -q` (round-trip payload; no-`matter_id` regression).

## T-006 — Confidential pin: matter-context LLM restriction

- **Refs**: FR-8, NFR-PRIV-1, AC-2
- **Owner**: @copilot
- **Status**: `[ ]`
- **Files**:
  - `backend/law_ai/matters/services/llm_context.py` (new — sole derivation of `providers=` from `matter.confidential`)
  - `backend/tests/matters/test_confidential_pin.py` (new)
- **Steps**: helper returns the local-tier-only restriction for confidential matters using the spec-034 per-call provider parameter; every matter-context agent entry point (navigator, intake, matter-scoped analysis) must obtain its restriction here — add a test that greps/imports entry points to prove routing.
- **Verify**: `docker compose run --rm backend pytest tests/matters/test_confidential_pin.py -q` — asserts restricted chain call, provenance records the pin, and no non-local provider attempt is recorded (AC-2).

## T-007 — Share links: mint, resolve, revoke (parallel)

- **Refs**: FR-9, NFR-SEC-1, AC-5
- **Owner**: @copilot
- **Status**: `[ ]`
- **Files**:
  - `backend/law_ai/matters/urls.py` (share endpoints), `backend/law_ai/urls.py` (mount `api/shared/`)
  - `backend/tests/matters/test_share_links.py` (new)
- **Steps**: slug = `secrets.token_urlsafe(32)`; single-artifact scope; unauthenticated read-only view carries the disclaimer; revocation → 404; mint/revoke evented. Closes BL-20260429-26.
- **Verify**: `docker compose run --rm backend pytest tests/matters/test_share_links.py -q`.

## T-008 — Phase-A integration suite (real Postgres)

- **Refs**: AC-1, AC-4, AC-5, NFR-PERF-1
- **Owner**: @copilot
- **Status**: `[ ]`
- **Files**:
  - `backend/tests/matters/test_journey_integration.py` (new, `@pytest.mark.integration`)
- **Steps**: end-to-end: create matter → run analysis with `matter_id` (agents mocked at the crew seam, DB real) → artifact + event round-trip → share → revoke → archive; matter detail p95 < 500 ms at 1k artifacts.
- **Verify**: `make test-integration` green including the new module.

## T-009 — Matter workspace frontend

- **Refs**: FR-10, NFR-SAFE-1
- **Owner**: @copilot
- **Status**: `[ ]`
- **Files**:
  - `frontend/app/matters/page.tsx`, `frontend/app/matters/[id]/page.tsx` (new)
  - `frontend/components/{MatterTimeline,ArtifactList,AttachToMatter}.tsx` (new)
  - `frontend/lib/api.ts` (typed matters client), `frontend/mocks/` handlers
  - `frontend/__tests__/matters.test.tsx` (new)
- **Steps**: list + detail (stage indicator, artifacts, timeline); Analysis Studio attach-to-matter flow; `LegalDisclaimer` present on all journey surfaces incl. shared view.
- **Verify**: `make test-frontend` green; `make typecheck` (tsc) clean.

## T-010 — JourneyGuide agent + flag-gated navigate endpoint

- **Refs**: FR-11, NFR-HITL-1, NFR-SAFE-1, AC-6
- **Owner**: @copilot
- **Status**: `[ ]`
- **Files**:
  - `backend/law_ai/agents_runtime/graphs/journey_guide.py`, `agents_runtime/prompts/journey-guide.v1.md` (new)
  - `backend/law_ai/matters/urls.py` (navigate endpoint, gated by `ENABLE_JOURNEY_NAVIGATOR`)
  - `backend/law_ai/settings/base.py` (flag, default `False`)
  - `backend/tests/agents/test_journey_guide.py` (new)
- **Steps**: LangGraph workflow over `ChatProviderChain`; Pydantic output = closed recommendation-kind enum (`run_research, run_analysis, review_pending, record_outcome, consult_professional, …`), each grounded in named artifacts/gaps; `human_approval_required` always set; UPL disclaimer in payload; confidential pin honored via T-006 helper.
- **Verify**: `docker compose run --rm backend pytest tests/agents/test_journey_guide.py -q` — schema rejects outcome-prediction free text by construction (AC-6); endpoint 404/disabled when flag off.

## T-011 — IntakeExtractor agent + guided intake with HITL confirm

- **Refs**: FR-12, NFR-HITL-1, AC-7
- **Owner**: @copilot
- **Status**: `[ ]`
- **Files**:
  - `backend/law_ai/agents_runtime/crews/intake_extractor.py`, `agents_runtime/prompts/intake-extractor.v1.md` (new)
  - `backend/law_ai/matters/urls.py` (intake + confirm endpoints)
  - `backend/tests/agents/test_intake_extractor.py`, `backend/tests/matters/test_intake_flow.py` (new)
- **Steps**: narrative → structured profile with per-field confidence; < 0.7 ⇒ `pending` intake artifact, profile untouched until owner confirms; confirm + extraction both evented; reuse the scout threshold constant.
- **Verify**: `docker compose run --rm backend pytest tests/agents/test_intake_extractor.py tests/matters/test_intake_flow.py -q` (AC-7 both halves).

## T-012 — Per-user LSAT attempt history (parallel)

- **Refs**: FR-14, AC-8
- **Owner**: @copilot
- **Status**: `[ ]`
- **Files**:
  - `backend/law_ai/lsat/models.py` + `lsat/migrations/0001_initial.py` (new `LsatAttempt`)
  - `backend/law_ai/lsat/urls.py` (persist authed attempts; per-user `/api/lsat/stats`)
  - `backend/tests/lsat/test_attempts.py` (new)
- **Steps**: authenticated grade calls persist attempts; stats aggregates per user across sessions; anonymous path byte-identical. Closes BL-20260503-05.
- **Verify**: `docker compose run --rm backend pytest tests/lsat/test_attempts.py -q` (AC-8 incl. anonymous regression).

## T-013 — Memo-draft seam (drafting stage) (parallel)

- **Refs**: FR-13
- **Owner**: @copilot
- **Status**: `[ ]`
- **Files**:
  - `backend/law_ai/matters/services/drafting.py` (new — compose analysis artifacts → `draft` artifact)
  - `backend/tests/matters/test_drafting_seam.py` (new)
- **Steps**: deterministic composition (no new LLM path in this spec): IRAC sections concatenated with every proposition's authority attribution preserved (court, jurisdiction, date, binding/persuasive); stored as `draft` artifact + event. DOCX/PDF + Bluebook export graduates via `/specify` to its own spec (BL-20260817-03).
- **Verify**: `docker compose run --rm backend pytest tests/matters/test_drafting_seam.py -q` — attribution fields asserted present per proposition.

## T-014 — Documentation: journey model, matters app, agent roles

- **Refs**: AC-10
- **Owner**: @copilot
- **Status**: `[ ]`
- **Files**:
  - `docs/data-model.md` (journey-stage model + Postgres tables)
  - `docs/architecture.md` (matters app in the system diagram)
  - `docs/agent-roles.md` (JourneyGuide, IntakeExtractor)
- **Steps**: same-PR-as-implementation rule (constitution §9); mark navigator flag default.
- **Verify**: repo-wide docs tests: `docker compose run --rm backend pytest ../tests -q -m specs` equivalent via `make lint-specs` + root suite.

## T-015 — Gates sweep & spec close-out

- **Refs**: AC-3, AC-10
- **Owner**: @copilot
- **Status**: `[ ]`
- **Files**: —
- **Steps**: run the full gate set; record LegalBench N/A rationale (no reasoning-logic change) in the PR; bump spec status when all tasks are `[x]`.
- **Verify**: `make lint && make typecheck && make test && make lint-specs` all green.

---

## Done-When (Definition of Done)

- All tasks `[x]`.
- All `AC-*` from `spec.md` covered by passing tests.
- `make lint && make typecheck && make test` green; `make test-integration` green for the journey suite.
- LegalBench: N/A recorded in PR description (no reasoning-logic change; harness stays pinned per constitution §1).
- Provenance logging verified manually for matter mutations + both new agent paths.
- **`## Follow-ups Discovered` section below populated** and mirrored into [BACKLOG.md](../../BACKLOG.md).

---

## Follow-ups Discovered

> Append-only. Mirror each item into [BACKLOG.md](../../BACKLOG.md) with a `BL-YYYYMMDD-NN` id. CI (`scripts/spec_validator.py`) checks this section exists. CI (`scripts/backlog_lint.py`) checks the BACKLOG mirror.

- BL-20260817-01 — feature, med — Matter data portability & account deletion: user-initiated full matter export (JSON bundle of artifacts + timeline) and an account-deletion path that honors PROTECT FKs and the soft-delete audit rules — a privacy obligation once user-owned matters hold client facts.
- BL-20260817-02 — feature, med — Action-stage deadline & task tracking: matter tasks with due dates, reminders, and a calendar surface; the action stage currently only records what users log as artifacts.
- BL-20260817-03 — feature, med — Drafting & export sub-spec: DOCX/PDF memo export with Bluebook-formatted citations and a provenance footer, graduating the deterministic memo seam into a real drafting stage.
- BL-20260817-04 — feature, low — Doctrine-gap → study-plan linkage: map a matter's issue tags to LSAT/doctrine concepts so the learning journey can recommend study material from live matters (bridges practice and learning tracks).
- BL-20260817-05 — feature, low — Matter-scoped retrieval memory: feed a matter's accumulated verified authorities into GraphRAG as a boost set so later research rounds within the matter rank its known-good citations first, with the boost labelled in the coverage envelope.
