# Plan: Legal journey platform — the matter spine

> Companion to `spec.md`. Describes **how** we will satisfy the requirements.

## 1. Architecture Overview

The spine is a new Django app, `law_ai.matters`, owning workspace state in Postgres. It sits *beside* the existing feature apps and threads them together: analysis persists into it (FR-6), agents read from it (FR-11, FR-12), the frontend navigates it (FR-10). The knowledge graph is untouched — matters reference graph nodes by id inside artifact payloads (spec §4 NG5). Identity reuses `django.contrib.auth` (already installed in `settings/base.py` `INSTALLED_APPS`) rather than inventing a user system; `core.ApiToken` gains a nullable `user` FK so the existing scope-key mechanism can act as a user when linked and stay anonymous when not (FR-2, NFR-COMPAT-1).

```mermaid
flowchart LR
  subgraph journey["law_ai.matters (new, Postgres)"]
    M[Matter] --> A[MatterArtifact]
    M --> E[JourneyEvent]
    M --> S[ShareLink]
  end
  UI[frontend/app/matters] --> API["/api/matters/*"]
  API --> journey
  AS["/api/analysis (matter_id)"] -->|persist artifact| A
  JG[JourneyGuide graph] -->|reads state / writes recommendation| M
  IE[IntakeExtractor crew] -->|pending intake artifact| A
  JG & IE --> LLM[law_ai.core.llm chain]
  M -. confidential=True .->|providers=local pin| LLM
  ALL[all mutations] --> PROV[core.provenance]
```

Confidentiality (FR-8) is enforced at the seam, not ambiently: matter-context call sites pass the spec-034 per-call provider-restriction parameter explicitly (spec §12 RQ-3), and a matters-service helper is the single place that derives `providers=` from `matter.confidential`, so no call site re-implements the rule.

## 2. Component Changes

| Layer | File / Module | Change |
|-------|---------------|--------|
| App | `backend/law_ai/matters/{__init__,apps,models,admin,urls,services/__init__,services/journey,services/llm_context}.py` | new Django app: models (FR-1, FR-3–FR-5, FR-9), owner-scoped DRF views (FR-7), journey service (events + provenance), confidential-pin helper (FR-8) |
| Settings | `backend/law_ai/settings/base.py` | add `law_ai.matters.apps.MattersConfig` to `INSTALLED_APPS`; add `ENABLE_JOURNEY_NAVIGATOR = env(false)` (NFR-HITL-1) |
| URLs | `backend/law_ai/urls.py` | mount `api/matters/`, `api/auth/`, `api/shared/` |
| Auth | `backend/law_ai/core/{models,auth}.py` + migration | `ApiToken.user` nullable FK; session-auth endpoints (`core/urls_auth.py`, FR-2); DRF authentication classes accept session OR scope key (NFR-COMPAT-1) |
| HITL identity | `backend/law_ai/ingestionapp/models.py` + migration; `lsat` proposal approve/reject path | nullable `reviewer_user` FK; populate when an authenticated reviewer acts (FR-2 / BL-20260811-04) |
| Analysis | `backend/law_ai/analysis/urls.py` | `AnalysisRequest.matter_id: str \| None`; on success, persist artifact + event via `matters.services.journey` (FR-6) |
| Agents | `backend/law_ai/agents_runtime/graphs/journey_guide.py`; `crews/intake_extractor.py`; `prompts/journey-guide.v1.md`, `prompts/intake-extractor.v1.md` | FR-11, FR-12 — both `run(input: dict) -> dict`, Pydantic outputs, all model calls through `law_ai.core.llm` |
| Drafting seam | `backend/law_ai/matters/services/drafting.py` | deterministic memo composition from analysis artifacts into a `draft` artifact, attribution preserved per proposition (FR-13); export graduates to a sub-spec |
| LSAT | `backend/law_ai/lsat/{models.py (new),urls.py}` + migration | `LsatAttempt` model; authed grade endpoint persists; `/api/lsat/stats` per-user series (FR-14) |
| Frontend | `frontend/app/matters/page.tsx`, `frontend/app/matters/[id]/page.tsx`, `frontend/components/{MatterTimeline,ArtifactList,AttachToMatter}.tsx`, `frontend/lib/api.ts` | FR-10; Analysis Studio gains attach-to-matter; typed client additions |
| Tests | `backend/tests/{matters/*,agents/test_journey_guide.py,agents/test_intake_extractor.py,api/test_auth_session.py,lsat/test_attempts.py}`; `frontend/__tests__/matters.test.tsx` | per §7 below |
| Docs | `docs/{data-model,architecture,agent-roles}.md` | journey-stage model, matters app, new agent roles (AC-10) |

## 3. Data & Schema Migrations

Postgres only, via Django app migrations (no raw SQL): `matters/0001_initial` (Matter, MatterArtifact, JourneyEvent, ShareLink — FK indexes, `on_delete=PROTECT` for owner, `SET_NULL` for artifact creator), `core/000X_apitoken_user` (additive nullable FK), `ingestionapp/000X_reviewer_user` (additive nullable FK), `lsat/0001_initial` (LsatAttempt). All additive and forward-only; existing rows untouched. **Neo4j: none.** Schema migrations carry the constitution §5 `human_approval_required: true` flag — approval happens at the PR gate before `make migrate` ships.

## 4. Tech Choices & Alternatives

| Decision | Chosen | Alternatives Considered | Why |
|----------|--------|-------------------------|-----|
| Frontend auth | Django session + CSRF (contrib.auth), per-user `ApiToken` for programmatic | JWT/OAuth (python-jose/passlib per BL-20260503-13); DRF TokenAuth | Zero new dependencies (constitution §2 locked stack; §8 dependency rule); sessions already middleware-wired; JWT adds a key-rotation surface with no current cross-origin-client need — deferred, claim annotated (spec §12 RQ-1) |
| Matter store | Postgres via Django ORM | Neo4j nodes for matters | Workspace state ≠ legal knowledge; graph invariants (`source`/`confidence` on every node) are ingestion semantics that don't fit user workspaces; keeps NG5 |
| Confidential pin | Explicit `providers=` threaded from matter context via one helper | contextvar consulted inside `core.llm` | Ambient state hides the decision from call sites and tests; explicit parameter is auditable and already supported since spec 034 (spec §12 RQ-3) |
| Intake HITL | Matter-scoped `pending` intake artifact + owner confirmation | Reuse `ingestionapp.PendingReview` | PendingReview is corpus-quarantine with operator reviewers; intake is the *matter owner* confirming their own facts — different reviewer, different blast radius (spec §12 RQ-4). Same 0.7 threshold constant reused |
| Stage transitions | Free (any→any), every transition evented | Linear gated pipeline | Real matters loop research↔analysis↔drafting; the journey is a map, not a turnstile (spec §12 RQ-2); gates stay where stakes are (HITL on agent outputs) |
| Navigator shape | LangGraph workflow over `ChatProviderChain` | CrewAI crew | State-machine fits read-state→reason→typed-recommendations; consistent with `LegalWorkflow` precedent (spec 035) |

No constitution §2 deviation ⇒ no ADR required.

## 5. Provenance & Audit Hook-up

- `matters.services.journey` is the sole mutation path for matters/artifacts/events/shares; every mutation calls `provenance.log_event("journey_event", {...actor, matter_id, kind})` (JSONL-first dual-write, constitution §4) *and* writes the `JourneyEvent` row — the timeline is a projection, the audit log stays canonical (NFR-AUDIT-1, AC-9).
- `JourneyGuide` / `IntakeExtractor` calls go through `law_ai.core.llm` exclusively — the `llm_call` event records provider, model, and the confidential pin when applied (FR-8, AC-2). Agent-level `log_agent_call` mirrors existing crews.
- No new Neo4j writes ⇒ node-creation provenance rules are untouched.

## 6. HITL Gates

| Gate | Mechanism |
|------|-----------|
| Spec gate | this package, human-reviewed PR |
| Schema migrations (§5 constitution) | `human_approval_required: true` — PR approval before merge |
| Intake extraction < 0.7 confidence | `pending` intake artifact; owner must explicitly confirm before the matter profile changes (FR-12, AC-7) |
| JourneyGuide output path | `human_approval_required` in every output; endpoint behind `ENABLE_JOURNEY_NAVIGATOR=False` until the new-agent-role production gate is passed (NFR-HITL-1) |
| Reviewer attribution | HITL decisions record the acting user FK (FR-2), closing the anonymous-reviewer gap |

## 7. Test Strategy

- **Unit** (`make test-backend`): model constraints + soft-archive (AC-4); owner scoping + share-slug revocation; analysis persistence branch with mocked agents (AC-1 shape); confidential-pin helper asserts `providers=` restriction and that no non-local attempt is recorded (AC-2); provenance-event emission per mutation (AC-9); LSAT attempt stats (AC-8); session auth + anonymous regression (AC-3, NFR-COMPAT-1).
- **Agents** (`backend/tests/agents/`): `JourneyGuide` closed-enum schema, grounding references, `human_approval_required` (AC-6); `IntakeExtractor` confidence gating (AC-7).
- **Integration** (`make test-integration`, real Postgres): matter CRUD → analysis persist → timeline round-trip (AC-1); share-link fetch + revoke 404 (AC-5); intake confirm flow (AC-7).
- **LegalBench**: not required — no reasoning-logic change to existing agents; harness stays pinned to Ollama (spec §11 of 036 is N/A; constitution §6).
- **Frontend** (`make test-frontend`): Vitest + RTL + MSW for matter list/detail render, attach flow, disclaimer presence on shared view.

## 8. Rollout

- `make dev` → `make migrate` applies the new app migrations; stack works with zero configuration change.
- Feature flag: `ENABLE_JOURNEY_NAVIGATOR` default `False` (NFR-HITL-1). Matter CRUD/persistence ships unflagged — it is inert until a user creates a matter; every anonymous flow is untouched (NFR-COMPAT-1).
- No backfill: pre-existing analyses were never persisted, so there is nothing to migrate. LSAT localStorage history stays client-side for anonymous users; no import in this spec.

## 9. Risks & Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Session+CSRF friction with the Next.js client | med | med | Same-origin API proxying already in place; `GET /api/auth/me` bootstraps CSRF token; regression suite (AC-3) |
| Confidential pin bypass via a forgotten call site | med | high | Single `llm_context` helper; grep-level test asserting matter-context agent entry points route through it (NFR-PRIV-1) |
| `PROTECT` FKs make user deletion impossible | low | med | Intentional for audit (NFR-DATA-1); account-deletion path is designed in follow-up BL-20260817-01, not ad hoc |
| Navigator prompt drifts into advice despite enum | med | high | Closed output schema (AC-6), versioned prompt, flag off by default, disclaimer (NFR-SAFE-1) |
| Epic stalls half-landed | med | med | Task order below is dependency-sorted; phases C–D are seams + sub-spec graduation, each PR-sized |

## 10. Estimated Effort

Phase A (T-001–T-008): ~5 agent-days, no human pairing beyond PR review. Phase B (T-009–T-011): ~3 agent-days; navigator prompt review benefits from human pairing. Phases C–D seams (T-012–T-013) + docs/validation (T-014–T-015): ~2 agent-days. Sub-spec graduations (drafting/export, portability, deadlines) are separately estimated in their own future specs.
