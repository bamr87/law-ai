# Spec: Legal journey platform — the matter spine

- **ID**: 036-legal-journey-platform
- **Status**: planned
- **Owner**: @bamr87
- **Created**: 2026-08-17
- **Roadmap Epic**: whole-legal-journey platform (user directive 2026-08-17; [PRD](../../docs/prd.md) §5 Phase 2 "user workspaces, project folders", §8.1 Dashboard/Library)
- **Constitution Compliance**: confirmed against [docs/constitution.md](../../docs/constitution.md) — no amendment required; §1 (local-first reachable, no third vendor), §4 (provenance, soft-delete), §5 (HITL on new agent output paths), §13 (power-aware outputs) each addressed below

## 1. Problem & Motivation

The platform's stage-local capabilities are real: ingestion feeds a knowledge graph, GraphRAG-backed agents produce IRAC analyses, the graph explorer renders precedent networks, and the LSAT Lab teaches. What does not exist is the connective tissue that would make these a *journey*:

- **Nothing persists.** `POST /api/analysis` builds a full `AnalysisResponse` — IRAC, precedents, agent trace — returns it, and forgets it (`backend/law_ai/analysis/urls.py`; the gap is BL-20260429-25). LSAT progress lives in browser `localStorage`. A user who did an hour of research yesterday starts from zero today.
- **Nobody exists.** The API authenticates scope-keys, not people (`law_ai.core.models.ApiToken` has no user link). There is no way to say "my matters", no reviewer identity on HITL decisions (BL-20260811-04), no per-user anything (BL-20260503-05, BL-20260811-06 are all blocked on this).
- **Nothing represents the *matter*.** A legal journey — a dispute, a filing, a research question, a course of study — has a beginning, accumulating artifacts, and stages. The platform has no noun for it, so it cannot answer the only question a journeying user actually has: *where am I, and what should I do next?*

The goal set for this epic — *a platform that facilitates the whole legal journey* — therefore reduces to building the spine: **user accounts + a durable Matter workspace that threads every existing stage capability + a navigator over that state**, and then attaching each stage (intake → issues → research → analysis → drafting → action → resolution, plus the parallel learning journey) to it.

## 2. Origin & Background

**Origin.** User directive (2026-08-17): "build a platform that can facilitate the whole legal journey." Roadmap anchors: [PRD](../../docs/prd.md) §5 Phase 2 (workspaces, project folders, export), §8.1 (Dashboard, Library, persistent tabs per matter); [Law_AI_Proposal](../../docs/history/2026-04-proposal.md) collaboration layer.

**Backlog items claimed by this spec** (moved to `## Claimed` in [BACKLOG.md](../../BACKLOG.md)):

- **BL-20260429-25** — persist analyses (request + response + trace ids) in Postgres so users can revisit a run — becomes matter-scoped artifact persistence (FR-6).
- **BL-20260429-26** — "save & share": bookmark an analysis with a slug and produce a shareable URL (FR-9).
- **BL-20260503-05** — persist per-user LSAT attempt history once auth lands (FR-14).
- **BL-20260503-13** — auth on top of `core.ApiToken` — delivered as first-class Django user accounts with session auth for the frontend plus per-user API tokens; the JWT/OAuth *mechanism* named in the item is deliberately deferred (see §12 RQ-1).
- **BL-20260811-04** — reviewer identity as a real user FK on HITL decisions instead of free text (FR-2).

**Related, deliberately left open**: BL-20260811-06 (per-user quotas — unblocked by FR-2, but quota policy is guardrails work), BL-20260803-01 (disposition metadata — feeds the resolution stage later), BL-20260503-12 (per-token rate limiting), BL-20260811-05 (counsel review of UPL wording — this spec adds surfaces that inherit that open review).

**Constitution §13 review question** — *who is the stronger here, and what does this feature do for them?* The journey platform's beneficiary is the party without institutional process memory: the pro se litigant, the legal-aid or solo lawyer without a docketing system, associates, or a matter file that survives the week. Repeat players already have all of this; a matter spine hands the one-shot player the repeat player's memory. Two §13 hazards follow and are bound here: (a) the navigator (FR-11) recommends **process steps grounded in the matter's own state**, never outcome predictions — "similar parties usually lose" framing is prohibited by schema (AC-6), because that would launder the corpus's victor bias into advice; (b) every authority surfaced inside a matter keeps the platform's existing attribution and coverage-envelope labelling (philosophy P1–P5) — the journey layer adds navigation, never a new authority score.

## 3. Goals

- G1: One durable, user-owned **Matter** threads intake → issues → research → analysis → drafting → action → resolution; every existing stage capability can attach its output to it.
- G2: Nothing a user produces vanishes: analyses, research runs, notes, drafts, and intake facts persist as matter artifacts with full provenance.
- G3: A **journey navigator** tells the user where they are and what grounded next steps exist — process guidance, never legal advice, never outcome prediction.
- G4: Confidentiality is a **per-matter property**: a matter marked confidential pins every LLM call in its context to the local tier (constitution §1's `ollama` pin), enforced in code, visible in provenance.
- G5: The learning journey persists per user (LSAT attempt history server-side), so the student track rides the same spine as the practice track.
- G6: Everything anonymous keeps working — accounts add capability, they never become a wall in front of existing flows.

## 4. Non-Goals

- NG1: E-filing, court/PACER integration, or deadline-rule computation. The action stage records what the user logs; it does not talk to courts (follow-up BL-20260817-02).
- NG2: Practice-management accounting (time capture, billing, invoicing, trust ledgers).
- NG3: Organizations, teams, roles, SSO. Ownership is single-user + revocable read-only share links; workspace RBAC stays future work.
- NG4: Outcome prediction or party-success scoring, in any stage. Prohibited framing per constitution §13 — see AC-6.
- NG5: New runtime LLM vendors, new top-level frameworks, or Neo4j schema changes. The journey spine is workspace state and lives in Postgres; the knowledge graph is referenced by id, never mutated by this spec.
- NG6: Client-to-lawyer matching or referral. The platform facilitates the journey; it does not broker representation.
- NG7: Document upload/ingestion of user files into the corpus. Matter artifacts hold *user-authored and agent-produced* content; corpus ingestion keeps its own quarantined pipeline.

## 5. User Stories

- As a **pro se litigant**, I want to describe my situation in plain language and get a structured matter with spotted issues and a map of what comes next, so that I can navigate a process built for professionals.
- As a **solo practitioner**, I want yesterday's research and analyses attached to the matter I ran them for, so that the file builds itself as I work instead of living in my browser history.
- As a **lawyer under a confidentiality obligation**, I want to mark a matter confidential and know that no prompt text from it reaches a third party, so that I can use the platform on privileged facts (constitution §1).
- As a **law student**, I want my practice history and accuracy to survive devices and browsers, so that my learning journey is cumulative.
- As an **auditor or reviewer**, I want every matter mutation and HITL decision attributed to a real user with a timestamp, so that the file is reconstructible after the fact.

## 6. Functional Requirements

### Journey spine (phase A — the concrete build of this spec)

- **FR-1**: A canonical journey-stage model — `intake`, `issues`, `research`, `analysis`, `drafting`, `action`, `resolution` — codified once (enum in the new `matters` app) and documented in [docs/data-model.md](../../docs/data-model.md). Stages label matters and artifacts; transitions are non-linear (see §12 RQ-2).
- **FR-2**: User accounts as first-class API principals: Django's existing `django.contrib.auth` user model exposed through session login/logout/whoami endpoints for the frontend; `core.ApiToken` gains a nullable `user` FK so a token can act *as* a user; `ingestionapp.PendingReview` reviewer attribution and LSAT proposal approve/reject gain the same user FK (closes BL-20260811-04).
- **FR-3**: A `Matter` model: title, description, jurisdiction, current stage, `confidential` flag, owner FK, `created_at`, `archived_at` (soft-archive only; no hard delete anywhere — constitution §4).
- **FR-4**: A `MatterArtifact` model: kind (`analysis` | `research` | `note` | `draft` | `intake`), stage tag, JSON payload, originating trace ids, creating user, `created_at`, `archived_at`. Append-only: artifacts are archived, never edited in place or deleted.
- **FR-5**: A `JourneyEvent` timeline per matter: stage transitions, artifact attachments, share-link grants/revocations, and HITL decisions, each carrying actor + timestamp. The timeline is the matter-level audit surface.
- **FR-6**: `POST /api/analysis` accepts an optional `matter_id`; when present and the caller may write that matter, the full `AnalysisResponse` is persisted as an `analysis` artifact plus a journey event (closes BL-20260429-25 in matter scope). Without `matter_id`, behaviour is byte-for-byte today's.
- **FR-7**: A matter API under `/api/matters/*`: list (owner-scoped, archived excluded by default), create, detail, update (stage, metadata), archive, artifact list/attach, timeline. Pydantic-validated at every boundary.
- **FR-8**: Confidential matters pin the provider chain: every `law_ai.core.llm` call made in the context of a matter with `confidential=True` is issued with the chain restricted to the local tier, using the existing per-call provider-restriction parameter shipped by spec 034 — no ambient global state. Provenance records the pin on each call.
- **FR-9**: Read-only share links: an owner can mint an unguessable slug for a matter artifact, anyone with the slug can view that artifact (with disclaimers), and the owner can revoke it (closes BL-20260429-26).

### Journey navigation (phase B)

- **FR-10**: A matter workspace frontend at `frontend/app/matters/`: matter list, matter detail with stage indicator, artifact list, journey timeline, and "attach this analysis to a matter" flow in Analysis Studio.
- **FR-11**: A `JourneyGuide` agent (LangGraph workflow over `ChatProviderChain`): given a matter's state (stage, artifacts, issue list, coverage gaps), it emits a structured set of **process recommendations** — each typed against a closed recommendation-kind enum (e.g. `run_research`, `run_analysis`, `review_pending`, `record_outcome`, `consult_professional`), each grounded in named matter artifacts or named coverage gaps. Output declares `human_approval_required` (constitution §5: new output path with no existing gate inherits the requirement) and carries the UPL disclaimer. No free-text "you will win/lose" channel exists in the schema.
- **FR-12**: Guided intake: plain-language narrative in → structured matter profile out (parties, jurisdiction, timeline, goals, candidate issue tags) via an `IntakeExtractor` agent. Extractions below the existing confidence threshold (0.7, mirroring `IngestionScout`) land as a `pending` intake artifact requiring explicit user confirmation before the matter profile updates — the HITL gate for this path.

### Deliverables & learning journey (phases C–D, seams built here, bodies graduate to sub-specs)

- **FR-13**: The `draft` artifact kind and a memo-composition seam: an endpoint that assembles a matter's analysis artifacts into a draft memo artifact, every legal proposition carrying its authority attribution (court, jurisdiction, date, binding/persuasive — constitution §13). DOCX/PDF export with Bluebook citations and a provenance footer is explicitly a follow-up sub-spec (BL-20260817-03), not this spec.
- **FR-14**: Per-user LSAT attempt history: an `LsatAttempt` Postgres model; authenticated attempts persist server-side and `/api/lsat/stats` returns per-user accuracy over time; anonymous behaviour (localStorage) unchanged (closes BL-20260503-05).

## 7. Non-Functional Requirements

- **NFR-AUDIT-1**: Every matter mutation (create, stage transition, artifact attach, share grant/revoke, archive) and every navigator/intake agent call logs through `law_ai.core.provenance` with the acting user — JSONL-first dual-write preserved (constitution §4). Model calls go only through `law_ai.core.llm`.
- **NFR-PRIV-1**: For a confidential matter, the local-tier pin is sufficient on its own to guarantee no prompt text leaves the host: no code path in matter context may construct a chain call without the restriction. Asserted by test (complements the still-open BL-20260811-24 end-to-end check).
- **NFR-SEC-1**: Matter access is owner-only by default; share slugs are ≥ 32 bytes of `secrets` entropy, single-artifact scoped, revocable; session auth uses Django's hardened defaults (CSRF on unsafe methods); credentials and slugs never logged.
- **NFR-DATA-1**: No hard delete of matters, artifacts, events, or attempts — `archived_at` soft-delete only, mirroring the graph rule (constitution §4).
- **NFR-HITL-1**: Both new agent output paths (FR-11, FR-12) declare `human_approval_required` semantics from day one; the navigator ships behind `ENABLE_JOURNEY_NAVIGATOR` (default `False`) until the production-deployment gate for a new agent role (constitution §5) is explicitly passed.
- **NFR-SAFE-1**: Every navigator and intake output surface renders the existing UPL disclaimer (spec 030 `LegalDisclaimer`) plus process-guidance framing; wording inherits the open counsel-review item BL-20260811-05 rather than inventing new legal language.
- **NFR-PERF-1**: Matter list and detail p95 < 500 ms with 1k artifacts per matter (paginated artifact/timeline queries; indexed FKs).
- **NFR-COMPAT-1**: Every existing anonymous flow (scope-key `POST /api/analysis`, graph, LSAT endpoints, static site) works unchanged with no account — verified by regression tests, not by intention.

## 8. Data Model Impact

**Postgres (new `law_ai.matters` Django app)**: `Matter`, `MatterArtifact`, `JourneyEvent`, `ShareLink`, plus `LsatAttempt` (lsat app) — all with `created_at`/`archived_at`, FK indexes, and no cascade hard-deletes (`on_delete=PROTECT`/`SET_NULL` per relation). **Changed**: `core.ApiToken` + `ingestionapp.PendingReview` gain nullable `user` FKs (additive migrations; existing rows untouched). **Neo4j**: no schema change — matters reference graph nodes by id in artifact payloads only. **Django migrations are schema migrations** and therefore carry the constitution §5 HITL flag: `human_approval_required: true` at the PR gate.

## 9. API Surface

| Method & path | Request / response (Pydantic) | Notes |
|---|---|---|
| `POST /api/auth/login`, `POST /api/auth/logout`, `GET /api/auth/me` | `LoginRequest` → `SessionInfo` | Django session; CSRF-protected |
| `GET/POST /api/matters` | `MatterCreate` → `MatterSummary[]` / `MatterDetail` | owner-scoped; `?include_archived=` |
| `GET/PATCH /api/matters/{id}` | `MatterUpdate` → `MatterDetail` | stage transition = PATCH, evented |
| `POST /api/matters/{id}/archive` | — → `MatterDetail` | soft-archive |
| `GET/POST /api/matters/{id}/artifacts` | `ArtifactAttach` → `ArtifactSummary[]` | paginated |
| `GET /api/matters/{id}/timeline` | → `JourneyEventList` | paginated |
| `POST/DELETE /api/matters/{id}/share` | `ShareRequest` → `ShareLinkInfo` | mint/revoke slug |
| `GET /api/shared/{slug}` | → `SharedArtifactView` | unauthenticated, read-only, disclaimed |
| `POST /api/matters/{id}/navigate` | → `JourneyGuideOutput` | flag-gated (NFR-HITL-1) |
| `POST /api/matters/{id}/intake` | `IntakeRequest` → `IntakeResult` | HITL below threshold |
| `POST /api/analysis` | `AnalysisRequest` gains optional `matter_id` | back-compat (NFR-COMPAT-1) |
| `GET /api/lsat/stats` | per-user series when authenticated | anonymous unchanged |

## 10. Agent / Crew Impact

Two new agents, both under the AGENTS.md contract (`run(input: dict) -> dict`, Pydantic output, versioned prompts in `agents_runtime/prompts/`, tests in `backend/tests/agents/`, all model calls via `law_ai.core.llm`):

- **JourneyGuide** (`agents_runtime/graphs/journey_guide.py`) — FR-11. Reads matter state; emits typed process recommendations. Never retrieves fresh authority itself; it points at gaps for the existing tools to fill.
- **IntakeExtractor** (`agents_runtime/crews/intake_extractor.py`) — FR-12. Narrative → structured matter profile with per-field confidence.

Existing `LegalAnalyst` / `PrecedentHunter` / `LegalWorkflow` are unchanged; their outputs become persistable via FR-6. [docs/agent-roles.md](../../docs/agent-roles.md) gains both roles at implement time (constitution §9).

## 11. Acceptance Criteria

- **AC-1**: Given an authenticated owner and a matter, when `POST /api/analysis` runs with `matter_id`, then an `analysis` artifact and a journey event exist for that matter and the artifact's payload round-trips the full `AnalysisResponse` (integration, real Postgres).
- **AC-2**: Given a matter with `confidential=True`, when any agent runs in its context, then the chain call carries the local-tier restriction and the `llm_call` provenance event records it; a test asserts no non-local provider attempt is recorded (unit + integration).
- **AC-3**: Given no session and today's scope keys, when every pre-existing endpoint is exercised without `matter_id`, then responses are unchanged (regression suite passes untouched).
- **AC-4**: Given an archived matter, then it is absent from default lists, present with `?include_archived=true`, and no code path performs a hard delete (model-level test proves `delete()` is not reachable via the API).
- **AC-5**: Given a minted share slug, an unauthenticated GET renders the read-only artifact with disclaimer; after revocation the same slug returns 404 (integration).
- **AC-6**: Given any matter state, `JourneyGuide` output contains only recommendations whose `kind` is in the closed enum, each referencing at least one matter artifact or named gap; the Pydantic schema rejects free-text outcome-prediction fields by construction, and `human_approval_required` is present (agent test).
- **AC-7**: Given an intake narrative extracted below 0.7 confidence, the matter profile is NOT updated and a `pending` intake artifact awaits explicit confirmation; upon confirmation the profile updates and both steps appear as journey events (agent + integration test).
- **AC-8**: Given an authenticated user completing an LSAT question, the attempt persists and `/api/lsat/stats` reflects it across sessions; given no session, stats behave exactly as today (unit).
- **AC-9**: Given any matter mutation, an `AuditEvent`/JSONL provenance event exists naming the acting user, the matter, and the mutation kind (unit).
- **AC-10**: `docs/data-model.md`, `docs/architecture.md`, and `docs/agent-roles.md` document the journey-stage model, the matters app, and both new agent roles in the same PR that implements them (constitution §9).

## 12. Risks & Resolved Questions

Resolved via `/clarify` (2026-08-17); each answer is derived from the constitution, existing code, or a shipped spec — none required inventing policy:

- **RQ-1** *(was OQ-1: JWT/OAuth vs session auth?)* — **Django session auth + CSRF for the frontend; per-user `ApiToken` for programmatic access.** `django.contrib.auth` and session middleware are already installed and constitution §2 locks the stack while §8 makes every new dependency justify itself — python-jose/passlib add a key-rotation surface with no current cross-origin need. BL-20260503-13's JWT mechanism is deferred, recorded in its claim annotation; revisit when a third-party client exists.
- **RQ-2** *(was OQ-2: gated vs free stage transitions?)* — **Free (any stage → any stage), every transition evented.** Real matters loop research ↔ analysis ↔ drafting; a turnstile would misrepresent the domain and philosophy P6 keeps decision power with the human. Rigor lives where stakes are: HITL on agent outputs (NFR-HITL-1), not on navigation.
- **RQ-3** *(was OQ-3: contextvar vs explicit provider restriction?)* — **Explicit per-call provider restriction, derived in one matters-service helper.** Spec 034 already ships the per-call `providers=` parameter; constitution §4 auditability favors a visible argument over ambient state that hides the decision from call sites and tests.
- **RQ-4** *(was OQ-4: reuse `PendingReview` for intake HITL?)* — **No — matter-scoped `pending` intake artifact confirmed by the matter owner.** `PendingReview` is corpus quarantine with *operator* reviewers and graph-commit blast radius; intake is the *owner* confirming their own facts before their own matter profile updates. Different reviewer, different blast radius, same 0.7 threshold constant. The §5 gate is preserved either way; this places it with the right human.

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Scope creep — "whole journey" swallows quarters | high | high | Phases: A concrete here; C–D bodies graduate to sub-specs via `/specify` (BL-20260817-03 et al.); tasks in this spec stay single-PR sized |
| UPL exposure as guidance surfaces multiply | med | high | NFR-SAFE-1 reuses spec 030 disclaimers; navigator flag-gated off (NFR-HITL-1); counsel review already tracked (BL-20260811-05) |
| Client facts now stored server-side | med | high | Confidential pin (FR-8, NFR-PRIV-1); owner-only access (NFR-SEC-1); soft-delete audit trail (NFR-DATA-1); data-portability/deletion follow-up (BL-20260817-01) |
| Auth work regresses anonymous flows | med | med | NFR-COMPAT-1 regression suite; accounts additive, never required for existing endpoints |
| Navigator becomes de-facto legal advice | med | high | Closed recommendation-kind enum (AC-6); grounded-in-artifacts requirement; `consult_professional` is a first-class recommendation kind |

## 13. Out of Scope / Follow-ups

Mirrored to [BACKLOG.md](../../BACKLOG.md) as BL-20260817-01 … BL-20260817-05 (see `tasks.md` § Follow-ups Discovered): matter data portability & account deletion; action-stage deadline/task tracking; drafting & export sub-spec (DOCX/PDF, Bluebook); doctrine-gap → study-plan linkage; matter-scoped retrieval memory. Also explicitly out: everything in §4 Non-Goals.
