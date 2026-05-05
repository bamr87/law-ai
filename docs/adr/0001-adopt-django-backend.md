# ADR 0001 — Adopt Django as the backend HTTP / orchestration framework

- **Status**: accepted
- **Date**: 2026-05-03
- **Spec**: [specs/011-django-backend](../../specs/011-django-backend/spec.md)
- **Constitution clauses amended**: [§2 Tech Stack (Locked)](../constitution.md#2-tech-stack-locked), [§11 Continuous Evolution — mission-drift guard](../constitution.md#11-continuous-evolution-self-improving-repo)

## Context

Through specs 001 → 010, the LawGraph backend was a FastAPI application under [backend/app/](../../backend/app/) — five routers ([api/health.py](../../backend/app/api/health.py), [api/agents.py](../../backend/app/api/agents.py), [api/analysis.py](../../backend/app/api/analysis.py), [api/graph.py](../../backend/app/api/graph.py), [api/lsat.py](../../backend/app/api/lsat.py)), an env-driven API-key middleware in [core/security.py](../../backend/app/core/security.py), JSONL audit logging in [core/audit_store.py](../../backend/app/core/audit_store.py), and ad-hoc SQL/Cypher migrations in [db/postgres_migrations/](../../backend/app/db/postgres_migrations/) and [db/neo4j_migrations/](../../backend/app/db/neo4j_migrations/). FastAPI delivered the surface area we needed quickly, but four pressures have accumulated:

1. **No first-class admin UI for HITL queues.** Spec 004's `pending_review` table and the audit log have no review surface; [BL-20260429-15](../../BACKLOG.md) (HITL approve/reject) and [BL-20260429-14](../../BACKLOG.md) (run drill-down) keep being deferred because we would have to hand-roll CRUD + auth + permissions for each.
2. **Auth has plateaued at API keys.** Specs 008/009 shipped per-router env-keyed auth ([core/security.py](../../backend/app/core/security.py)) but cannot grow into per-user roles, rotation, audit trails, or rate limits ([BL-20260430-09](../../BACKLOG.md)) without effectively re-implementing `django.contrib.auth`.
3. **Background work has no home.** [IngestionScout.run_and_commit](../../backend/app/ingestion/scout.py) does its low-confidence quarantine inline in the request path; spec 005's tutor and spec 010's LangGraph workflow have no broker for retries, scheduling, or fan-out.
4. **Streaming is blocked.** Three open backlog items ([BL-20260503-03](../../BACKLOG.md), [BL-20260429-24](../../BACKLOG.md), [BL-20260429-16](../../BACKLOG.md)) want SSE/WebSocket push. FastAPI can do these but we have nothing standardized; Django Channels gives us one ASGI consumer pattern repo-wide.

The previous version of [docs/constitution.md](../constitution.md) §2 explicitly locked the backend to FastAPI and §11 mission-drift guard explicitly forbade "Django-style frameworks" in BACKLOG promotions. This ADR amends both clauses.

## Decision

Replace FastAPI with **Django 5 (ASGI via daphne) + Django REST Framework + Channels + Celery** as the backend HTTP / orchestration layer. The product runtime LLM remains Ollama (local-first, open weights) per [docs/constitution.md](../constitution.md) §1 — this ADR concerns the backend platform, not the product runtime. Specifically:

1. **HTTP layer**: Django + DRF replaces FastAPI routers. `drf-pydantic` lets us reuse the existing Pydantic request/response models so [frontend/lib/api.ts](../../frontend/lib/api.ts) sees zero JSON-shape change.
2. **ORM**: Django ORM (async) manages new Postgres tables (`audit.AuditEvent`, `ingestionapp.PendingReview`, `core.ApiToken`). Existing raw SQL migrations are encoded as `RunSQL` operations inside the initial Django migration so a fresh `make migrate` reproduces today's schema.
3. **Neo4j layer**: unchanged. The async neo4j driver and the Cypher helpers in [backend/app/db/](../../backend/app/db/) are relocated to `backend/lawgraph/core/neo4j/` with no logic change.
4. **Auth**: `core.ApiToken` model + custom DRF `ApiKeyAuthentication` + `HasScope` permission preserve the spec-008/009 env-driven UX via an idempotent `manage.py seed_api_keys` command.
5. **Async**: fully ASGI via daphne. All current `async def` view bodies (notably `await asyncio.gather(LegalAnalyst.run, PrecedentHunter.run)`) port directly. Celery handles background work (ingestion quarantine, JSONL audit fallback). Channels exposes `/ws/agents/{run_id}` for future agent-trace streaming.
6. **Agent runtime**: framework-agnostic. CrewAI crews, LangGraph workflows, and Pydantic domain models move under `backend/lawgraph/agents_runtime/` with no logic change. The `@logged_node` decorator and `register_all_agents()` keep their signatures so the agent code is unchanged beyond import paths.
7. **Constitution**: §2 backend stack list updated; §11 mission-drift guard reworded to forbid "frameworks not listed in §2" (the previous explicit "Django-style frameworks" phrasing is dropped).

The migration is a **big-bang** cutover on a long-lived feature branch (`feat/011-django-backend`) with green CI per commit; [backend/app/](../../backend/app/) is deleted in the final commit ([spec 011 T-016](../../specs/011-django-backend/tasks.md)).

## Consequences

**Positive**

- Django admin lights up `PendingReview` triage and audit browsing for free, unblocking [BL-20260429-15](../../BACKLOG.md) and [BL-20260429-14](../../BACKLOG.md).
- `django.contrib.auth` is the foundation for future JWT/OAuth ([BL-20260503-13](../../BACKLOG.md)) and per-token rate limiting ([BL-20260503-12](../../BACKLOG.md)).
- Celery (Redis broker) standardizes background work; ingestion quarantine moves out of the request path.
- Channels gives us one consumer pattern for all future agent-trace streaming work ([BL-20260429-24](../../BACKLOG.md), [BL-20260503-03](../../BACKLOG.md), [BL-20260429-16](../../BACKLOG.md)).
- Django migrations replace ad-hoc SQL files; `manage.py check --deploy` adds an explicit production hardening gate.
- Constitutional ambiguity is removed: the ADR + amended §2 + amended §11 prevent future `/specify` agents from "correcting" the stack back to FastAPI.

**Negative / Risks**

- Larger framework surface (admin, auth, ORM, signals, migrations, middleware) — more to learn and lint.
- Django async ORM has rough edges around transactions; mitigated by keeping ORM writes single-row and using `sync_to_async` for complex flows ([spec 011 R-1](../../specs/011-django-backend/spec.md#12-risks--open-questions)).
- `drf-pydantic` is a small dependency; pinned and a hand-written-serializer fallback is documented ([spec 011 R-2](../../specs/011-django-backend/spec.md#12-risks--open-questions)).
- LangGraph checkpointer schema collision with Django migrations — mitigated by isolating the checkpointer in its own `langgraph` Postgres schema ([spec 011 FR-13, AC-6](../../specs/011-django-backend/spec.md)).
- Big-bang merge non-buildability risk — mitigated by branch protection (green CI per commit) and by deleting [backend/app/](../../backend/app/) only after the test rewrite passes ([spec 011 R-4](../../specs/011-django-backend/spec.md#12-risks--open-questions)).

**Neutral**

- The HTTP contract (`/health`, `/api/agents/*`, `/api/analysis`, `/api/graph/*`, `/api/lsat/*`, `X-API-Key` semantics, response JSON shapes) is preserved 1:1; [frontend/lib/api.ts](../../frontend/lib/api.ts) and the Vitest suite under [frontend/__tests__/](../../frontend/__tests__/) require no changes.
- LegalBench score is expected at parity (≥ 0 pp delta on `core_reasoning` and `precedent_retrieval`); the agent runtime moves but does not change. Spec 011 NFR-LEGALBENCH-1 makes any regression > 1 pp blocking.

## Alternatives Considered

| Alternative | Why rejected |
| ----------- | ------------ |
| **Stay on FastAPI** | The four pressures listed under Context are not addressable without re-implementing meaningful pieces of Django (admin, auth, migrations, ORM-backed permissions). Each individual backlog item gets cheaper after the move. |
| **Django + django-ninja** instead of DRF | django-ninja matches FastAPI's ergonomics best (decorator-based, native Pydantic) but DRF is the ecosystem-standard auth/permission/serialization layer and integrates more cleanly with admin actions. We pay a small ergonomics tax for a much larger ecosystem. |
| **Django plain views (no DRF)** | Lightest dependency footprint but we would hand-roll auth, permissions, and response negotiation. Net loss vs. DRF. |
| **Hybrid (Django for admin, FastAPI for APIs)** | Long-term dual-stack maintenance cost; reverse-proxy plumbing; two test infrastructures. Rejected by the planning interview. |
| **Strangler-fig migration** (parallel FastAPI + Django) | Lower per-PR risk but multiplies the time the codebase is split across two frameworks. The user explicitly chose big-bang at the planning interview. |
| **Adopt `neomodel` Neo4j OGM** as part of the same refactor | OGM adds a maintenance-risk dependency and obscures the Cypher we lean on for graph traversal. Out of scope for this ADR. |

## Supersedes / Superseded by

- **Supersedes**: the previous "FastAPI-locked" wording in [docs/constitution.md](../constitution.md) §2 and the "Django-style frameworks must be rejected" wording in §11.
- **Superseded by**: none.

## References

- [specs/011-django-backend/spec.md](../../specs/011-django-backend/spec.md) — full functional + non-functional requirements, acceptance criteria, and risk register.
- [specs/011-django-backend/plan.md](../../specs/011-django-backend/plan.md) — architecture diagram, component change list, alternatives matrix, rollout plan.
- [specs/011-django-backend/tasks.md](../../specs/011-django-backend/tasks.md) — T-001 through T-016 implementation sequence.
- [docs/constitution.md](../constitution.md) — amended in the same PR as this ADR.
- [BACKLOG.md](../../BACKLOG.md) — items unblocked by this decision (BL-20260503-09 through BL-20260503-18).
