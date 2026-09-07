# Plan: Refactor Backend from FastAPI to Django

> **Historical note (2026-09-05, BL-20260602-04).** `backend/app/` was the pre-Django FastAPI package. It was deleted by this spec's own T-016; the Django project package lives at `backend/law_ai/`. Every `backend/app/...` path below is therefore rendered as inline code, not as a link — the files it names no longer exist, and the ~110 dead hrefs 404'd on every platform. The text is otherwise unedited: it records the migration as it was specified.

> Companion to [spec.md](spec.md). Describes **how** we satisfy FR-1 through FR-16. Decisions captured in `/memories/session/plan.md` (interviewed 2026-05-03): Django 5 + DRF, big-bang rewrite, Django ORM async for Postgres, raw async neo4j driver kept, fully ASGI, admin + auth + Celery + Channels enabled, constitution amended in Phase 0.

## 1. Architecture Overview

```mermaid
flowchart LR
  Client[Next.js frontend\n(unchanged)]
  Daphne[daphne ASGI\nLaw AI.asgi:application]
  DRF[DRF Views\nanalysis · graph · lsat · agentsapi · core]
  Channels[Channels Consumer\n/ws/agents/{run_id}]
  Admin[Django Admin]
  Celery[Celery Worker\ningestionapp.tasks]
  Runtime[agents_runtime\nCrewAI · LangGraph\nNeo4j driver · Pydantic]
  PG[(Postgres\npublic schema:\naudit · pending_review · api_token · auth_*)]
  LG[(Postgres\nlanggraph schema:\ncheckpoints)]
  Neo[(Neo4j)]
  Redis[(Redis\nCelery broker · Channels layer)]
  Ollama[Ollama]
  Phoenix[Phoenix OTEL]

  Client -- HTTP X-API-Key --> Daphne --> DRF
  Client -- WS --> Daphne --> Channels
  Admin --- Daphne
  DRF --> Runtime
  Channels --> Runtime
  Celery --> Runtime
  DRF -. acreate AuditEvent .-> PG
  DRF -. enqueue .-> Redis --> Celery
  Celery -. PendingReview .-> PG
  Runtime --> Neo
  Runtime --> Ollama
  Runtime --> LG
  Runtime --> Phoenix
```

The dashed arrows are the only persistence paths owned by Django. Solid arrows from `Runtime` to Neo4j/Ollama/Phoenix/LangGraph keep the existing async drivers — Django is not in the data path for the agent stack.

## 2. Component Changes

| Layer | File / Module | Change |
|-------|---------------|--------|
| Constitution | [docs/constitution.md](../../docs/constitution.md) §2, §11 | Amend tech stack + drift guard |
| ADR | `docs/adr/0001-adopt-django-backend.md` (new) | Record amendment + rationale |
| Top-level docs | [AGENTS.md](../../AGENTS.md), [PRD.md](../../PRD.md), [.github/copilot-instructions.md](../../.github/copilot-instructions.md) | Replace FastAPI references |
| Deps | [backend/pyproject.toml](../../backend/pyproject.toml) | Swap fastapi/uvicorn → django/drf/channels/celery/daphne; move jose/passlib to `[future-auth]` |
| Project skeleton | `backend/manage.py`, `backend/law_ai/{settings/{base,dev,test,prod}.py, urls.py, asgi.py, wsgi.py, celery.py}` | New |
| Apps | `backend/law_ai/{core,audit,analysis,graph,lsat,ingestionapp,agentsapi,agents_runtime}/` | New (each `apps.py`, `urls.py`, `views.py`, `models.py`, `tasks.py`, `consumers.py` as needed) |
| Settings shim | `backend/law_ai/core/settings_proxy.py` | New — re-exports `django.conf.settings` so relocated framework-agnostic modules import once |
| Auth | `backend/law_ai/core/auth.py` | `ApiKeyAuthentication`, `HasScope` |
| Provenance | `backend/law_ai/core/provenance.py` | Reimpl on `audit.AuditEvent.objects.acreate`; signature unchanged |
| Audit model | `backend/law_ai/audit/models.py` + initial migration | New `AuditEvent` ORM model |
| Quarantine model | `backend/law_ai/ingestionapp/models.py` + initial migration (uses `RunSQL` to reproduce existing schema) | New `PendingReview` ORM model |
| Token model | `backend/law_ai/core/models.py` + initial migration | New `ApiToken` ORM model |
| Mgmt commands | `backend/law_ai/core/management/commands/{seed_api_keys,ensure_checkpointer}.py` | New |
| Routers → Views | `backend/law_ai/{core,agentsapi,analysis,graph,lsat}/views.py` + `urls.py` | Port from `backend/app/api/` (1:1 contract) |
| Channels | `backend/law_ai/agentsapi/consumers.py`, `backend/law_ai/asgi.py` routing | New consumer skeleton |
| Celery | `backend/law_ai/celery.py`, `backend/law_ai/ingestionapp/tasks.py` | New |
| Relocated runtime | `backend/law_ai/agents_runtime/{crews,graphs,tools,prompts,registry.py,checkpointer.py}` | Moved from `backend/app/agents/` and `backend/app/db/checkpointer.py`; imports rewritten |
| Relocated graph DB | `backend/law_ai/core/neo4j/{driver.py,graph_queries.py,queries.py,citation_resolver.py}` | Moved from `backend/app/db/`; imports rewritten |
| Relocated services | `backend/law_ai/lsat/services/`, `backend/law_ai/ingestionapp/services/`, `backend/law_ai/eval/`, `backend/law_ai/core/schemas/extraction.py`, `backend/law_ai/core/telemetry.py` | Moved from `backend/app/lsat/`, `backend/app/ingestion/`, `backend/app/eval/`, `backend/app/models/`, `backend/app/core/telemetry.py` |
| Tests | [backend/tests/conftest.py](../../backend/tests/conftest.py) and every file under [backend/tests/](../../backend/tests/) | Rewrite fixtures + import paths; assertions unchanged |
| Container | [backend/Dockerfile](../../backend/Dockerfile), [docker-compose.yml](../../docker-compose.yml) | New CMD chain (migrate → ensure_checkpointer → seed → daphne); add `worker` service |
| Tooling | [.vscode/tasks.json](../../.vscode/tasks.json), [Makefile](../../Makefile), `pytest.ini`, [.github/workflows/](../../.github/workflows/) | Update commands `app` → `law_ai`, `uvicorn` → `daphne`, add `make migrate`, set `DJANGO_SETTINGS_MODULE` |
| Cleanup | Delete entire `backend/app/` tree | Final commit |

## 3. Data & Schema Migrations

- **Initial Django migration `core.0001_initial`** — creates `core_apitoken` with the FR-6 schema; no data backfill (tokens seeded by `seed_api_keys`).
- **Initial Django migration `audit.0001_initial`** — creates `audit_auditevent` with the FR-6 schema and indexes.
- **Initial Django migration `ingestionapp.0001_initial`** — `RunSQL.noop`-style operation that includes the verbatim DDL from `backend/app/db/postgres_migrations/001_pending_review.sql` and `backend/app/db/postgres_migrations/002_pg_trgm.sql`, then a `RenameModel`/`RenameTable` to bring it under `ingestionapp_pendingreview`. Idempotent: if the legacy `pending_review` table already exists, a `state_operations`/`database_operations` split lets Django adopt it.
- **Neo4j migrations** — unchanged. The two existing files under `backend/app/db/neo4j_migrations/` (`001_case_constraints.cypher`, `002_case_aliases.cypher`) move to `backend/law_ai/core/neo4j/migrations/` and the runner remains a thin shell script invoked from `backend/scripts/init-db.sh`.
- **LangGraph checkpointer** — owned by the library; FR-13 isolates it in schema `langgraph` via the new `manage.py ensure_checkpointer` command.

All migrations are idempotent and forward-only (Constitution §3 of [ao-sdlc-guide.md](../../docs/ao-sdlc-guide.md)).

## 4. Tech Choices & Alternatives

| Decision | Chosen | Alternatives Considered | Why |
|----------|--------|-------------------------|-----|
| HTTP framework | Django + DRF | django-ninja; plain Django views | Most mature ecosystem; aligns with the admin/Channels/Celery story; DRF is industry-standard for token auth and permissions |
| Postgres access | Django ORM (async) for new tables | Raw asyncpg only; SQLAlchemy + Alembic | Buys admin + migrations + auth integration with no extra layer; spec 004 ORM containment is small enough to be safe |
| Neo4j access | Raw async neo4j driver (relocated) | `neomodel` OGM | Zero behavior change; OGM adds maintenance risk and obscures Cypher we already lean on |
| Async stance | Fully ASGI (daphne) | Sync DRF + `async_to_sync` islands | Required for `asyncio.gather(LegalAnalyst, PrecedentHunter)` and httpx async clients; Channels needs ASGI anyway |
| Pydantic ↔ DRF bridge | `drf-pydantic` | Hand-written DRF Serializers; pydantic-only views via raw `JsonResponse` | Reuses existing `AnalysisRequest/Response` etc. with no double-maintenance; small dep, easy to vendor if upstream stalls |
| Settings management | `django-environ` + 4-file split | `pydantic-settings` shim; single settings.py | Native to Django; `prod` settings hardening is a clear file boundary |
| Migration cutover | Big-bang | Strangler-fig (parallel FastAPI + Django) | User explicitly chose big-bang at planning; avoids long-lived dual-stack maintenance and reverse-proxy plumbing |
| Auth source of truth | New `core.ApiToken` model + env-driven seed command | Pure env-keyed middleware (status quo) | Required for admin-managed tokens; preserves env-driven UX via `seed_api_keys` |

The Django adoption itself deviates from [docs/constitution.md](../../docs/constitution.md) §2 — recorded in **`docs/adr/0001-adopt-django-backend.md`** (new) per FR-1.

## 5. Provenance & Audit Hook-up

- **Public surface preserved.** `ProvenanceLogger.log_request`, `.log_agent_call`, `.log_graph_query`, and the `@logged_node` decorator (used by `backend/app/agents/graphs/legal_workflow.py`) keep their function signatures; relocated agent code does not need to change beyond import paths.
- **Storage swap.** Internally, every method now calls `await audit.models.AuditEvent.objects.acreate(kind=..., payload=..., timestamp=now(), agent_version=..., trace_id=...)`. The JSONL writer from `backend/app/core/audit_store.py` becomes a Celery sink invoked when DB writes fail (configurable via `AUDIT_FALLBACK_PATH` env var, defaulting to today's path).
- **Request middleware.** A new `law_ai.core.middleware.ProvenanceMiddleware` (Django-style ASGI middleware) wraps every request and calls `await ProvenanceLogger.log_request(...)` after the response, mirroring the FastAPI middleware in `backend/app/main.py`.
- **OTEL/Phoenix.** `core.telemetry.init_tracing()` is called from `CoreConfig.ready()` (FR-10). Daphne and Celery worker both instrument `httpx`, Django views, and Channels consumers. Phoenix span IDs continue to surface in `AnalysisResponse.phoenix_trace_url` (no change).
- **Neo4j writes.** `commit_extraction` and `densify_extraction` continue to set `source`, `source_url`, `ingest_timestamp`, `agent_version`, `confidence` on every node/edge. Constitution §4 satisfied unchanged.

## 6. HITL Gates

- **Spec gate:** this spec must merge before any FR-2..FR-16 commit lands; FR-1 is the gate.
- **PR gate:** standard PR review on the cutover PR; reviewers must verify AC-1, AC-3, AC-4, AC-9 manually.
- **Ingestion gate (preserved):** `IngestionScout.run_and_commit` continues to route low-confidence extractions to the `PendingReview` queue (now via Celery task per FR-11). Admin reviewers approve via Django admin (`/admin/ingestionapp/pendingreview/`) — the model exposes a `mark_approved` admin action whose business logic mirrors today's quarantine resolver.
- **Agent outputs:** `LegalWorkflowOutput.human_approval_required` semantics from spec 010 unchanged. The `cite_check` node still flags unverified citations; admin queue surfaces them.
- **Deployment gate:** `python manage.py check --deploy` must pass in `prod` settings (NFR-SEC-1) before any production rollout — this is a new explicit gate enabled by Django.

## 7. Test Strategy

- **Unit tests** (mocked Neo4j/Postgres/Ollama):
  - `tests/test_settings.py` — every settings variant imports cleanly and exposes required keys (R-7 mitigation).
  - `tests/core/test_provenance.py` — `acreate` is invoked; JSONL fallback fires on DB error.
  - `tests/core/test_auth.py` — `ApiKeyAuthentication` constant-time compare; `HasScope` allow/deny matrix.
  - `tests/core/test_settings_proxy.py` — relocated modules can read `settings_proxy.NEO4J_URI`.
  - `tests/api/test_*` — every existing FastAPI router test ported one-to-one with payload-equality assertions (FR-15).
  - `tests/ingestionapp/test_tasks.py` — `quarantine_extraction.delay(...)` produces a `PendingReview` row (using `CELERY_TASK_ALWAYS_EAGER=True` in `test` settings).
- **Integration tests** (real services via `docker compose` profile):
  - `tests/integration/test_migrate_parity.py` — runs `manage.py migrate` and the legacy SQL files against twin Postgres containers, `pg_dump`-diffs them (NFR-MIGRATION-SAFETY-1, AC-4).
  - `tests/integration/test_checkpointer_isolation.py` — `ensure_checkpointer` creates `langgraph` schema; `migrate` does not touch it (AC-6).
  - `tests/integration/test_channels_ws.py` — async client connects to `/ws/agents/{run_id}` and receives the `ready` frame (AC-7).
  - `tests/integration/test_celery_worker.py` — enqueue + worker round-trip writes `PendingReview` + `AuditEvent` (AC-5).
- **LegalBench**: `Run LegalBench Eval` task on `core_reasoning` + `precedent_retrieval` before and after; record delta in PR description (NFR-LEGALBENCH-1, AC-10).
- **Frontend**: existing `cd frontend && npm test -- --run` (Vitest + RTL + MSW) must pass without source edits (AC-9, NFR-PARITY-2).

## 8. Rollout

- **Local docker compose:** `make dev` brings up `backend` (daphne) + `worker` (celery) + existing services. First-run cost: one extra `migrate` step folded into the `backend` container `CMD`.
- **Feature flag:** none. The cutover is a hard switch on the feature branch; `main` only sees Django after FR-16 lands.
- **Backfill / re-ingest:** none required. `audit.AuditEvent` is initially empty (audit log starts fresh; legacy JSONL preserved on disk for forensic continuity). `pending_review` rows are migrated in place via the FR-6 `RunSQL` adoption pattern. Neo4j and the LangGraph checkpointer schema are unchanged.
- **Container entrypoint chain** (FR-14): `migrate --noinput && ensure_checkpointer && seed_api_keys && daphne ...`. Each step is idempotent and exit-codes propagate to compose health checks.
- **Celery worker** is a separate service in compose; both share the same image build to keep the dependency graph small.

## 9. Risks & Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| R-1 Django async ORM rough edges (txn, select_for_update) | med | med | Keep ORM writes single-row `acreate`; wrap complex flows in `sync_to_async` |
| R-2 `drf-pydantic` v2 compatibility drift | low | med | Pin minor; fallback to hand-written serializers for the four POST endpoints |
| R-3 LangGraph checkpointer schema collision | med | high | FR-13 `langgraph` schema isolation + AC-6 enforcement |
| R-4 Big-bang merge non-buildability | med | high | Branch protection requires green CI per commit; FR-16 deletes legacy code only after FR-15 tests pass |
| R-5 Constitutional drift (agents revert to FastAPI) | med | med | FR-1 first commit lands ADR + constitution + AGENTS edits; AC-8 grep gate |
| R-6 Celery worker env divergence from web container | low | med | Single image build; identical env in compose; smoke task in container healthcheck |
| R-7 Settings split import-order bugs | med | low | `tests/test_settings.py` imports each variant |
| R-8 Frontend silent breakage from header/cookie changes | low | high | NFR-PARITY-2 + AC-9; CORS allow-list copied verbatim |
| R-9 Hidden FastAPI-specific patterns in agent code (e.g. `Depends`) | low | high | Pre-flight `grep -RIn "from fastapi" backend/app/agents backend/app/ingestion backend/app/lsat` is empty today; documented in plan §10 readiness check |

## 10. Estimated Effort

Story points are agent-hours, not calendar time:

| Phase | Effort | Notes |
|-------|--------|-------|
| Phase 0: Spec + ADR + constitution + AGENTS/PRD/copilot edits | 4 | This PR's scope |
| Phase 1: Skeleton + dep swap + relocate | 12 | Mostly mechanical moves + import rewrites |
| Phase 2: Auth + audit + ORM models + migrations | 10 | New code; carefully tested |
| Phase 3: Port routers (5 routers, 18 endpoints) | 14 | One PR per router on the feature branch |
| Phase 4: Celery + Channels + ready() + ensure_checkpointer | 8 | Small but cross-cutting |
| Phase 5: Test rewrite + tooling | 12 | Conftest churn + ~15 test files |
| Phase 6: Delete legacy + verification + LegalBench | 4 | Final commit + smoke |

**Pairing flag:** Phase 1's relocation commit should be human-paired because it is a giant `git mv` and `ruff --fix` pass; mechanical errors here cascade. Phase 6 (legacy deletion) also requires human sign-off (Constitution §10 Level-2 approval gate).
