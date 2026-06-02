# Spec: Refactor Backend from FastAPI to Django

- **ID**: 011-django-backend
- **Status**: shipped
- **Owner**: @copilot
- **Created**: 2026-05-03
- **Roadmap Epic**: backend-platform-modernization (no upstream issue yet — created via this spec)
- **Constitution Compliance**: this spec is a **constitutional amendment**. It deliberately deviates from [docs/constitution.md](../../docs/constitution.md) §2 (which locks the backend to FastAPI) and §11 (which forbids "Django-style frameworks" in BACKLOG promotions). The amendment is recorded under `docs/adr/0001-adopt-django-backend.md` and the constitution + [AGENTS.md](../../AGENTS.md) + [PRD.md](../../PRD.md) + [.github/copilot-instructions.md](../../.github/copilot-instructions.md) are updated as part of FR-1 below. All other constitutional clauses (§1 mission, §3 quality gates, §4 provenance, §5 HITL, §6 testing, §7 spec-driven workflow, §8 security, §9 docs, §11 self-evolution) remain in force and this spec satisfies them.

## 1. Problem & Motivation

Today the backend is a FastAPI app under [backend/app/](../../backend/app/) wired together by [backend/app/main.py](../../backend/app/main.py) with five routers ([api/health.py](../../backend/app/api/health.py), [api/agents.py](../../backend/app/api/agents.py), [api/analysis.py](../../backend/app/api/analysis.py), [api/graph.py](../../backend/app/api/graph.py), [api/lsat.py](../../backend/app/api/lsat.py)), an env-driven API-key middleware in [core/security.py](../../backend/app/core/security.py), JSONL audit logging in [core/audit_store.py](../../backend/app/core/audit_store.py), and ad-hoc SQL/Cypher migrations in [db/postgres_migrations/](../../backend/app/db/postgres_migrations/) and [db/neo4j_migrations/](../../backend/app/db/neo4j_migrations/). FastAPI got us to feature parity with seven shipped specs (001 → 010), but the platform is now bumping into limits we keep paying for as the surface grows:

- **No first-class admin UI for HITL queues.** The async quarantine table from spec 004 ([backend/app/db/postgres_migrations/001_pending_review.sql](../../backend/app/db/postgres_migrations/001_pending_review.sql)) and the audit log have no review surface, and [BL-20260429-15](../../BACKLOG.md) (HITL approve/reject endpoints) and [BL-20260429-14](../../BACKLOG.md) (run drill-down) keep being deferred because we would have to hand-roll CRUD + auth + permissions for each.
- **Auth has plateaued at API keys.** Spec 008 + 009 shipped per-router env-keyed auth via [core/security.py](../../backend/app/core/security.py), but we cannot grow that into per-user roles, rotation, audit trails, or rate limits ([BL-20260430-09](../../BACKLOG.md)) without effectively re-implementing `django.contrib.auth`.
- **Background work has no home.** [IngestionScout.run_and_commit](../../backend/app/ingestion/scout.py) does its low-confidence quarantine inline in the request path, and spec 005's tutor + spec 010's LangGraph workflow have no broker for retries, scheduling, or fan-out — Celery is the obvious answer and would also satisfy [BL-20260429-09](../../BACKLOG.md) (periodic agent self-review).
- **Streaming is blocked.** Three open backlog items ([BL-20260503-03](../../BACKLOG.md) tutor SSE, [BL-20260429-24](../../BACKLOG.md) analysis trace SSE, [BL-20260429-16](../../BACKLOG.md) WebSocket push for the dashboard) all want real-time push. FastAPI can do SSE/WebSockets but we have nothing standardized; Django Channels gives us one ASGI consumer pattern repo-wide.
- **Migrations are unmanaged.** Both Postgres ([db/postgres_migrations/](../../backend/app/db/postgres_migrations/)) and the LangGraph checkpointer schema rely on hand-written SQL and library-internal `setup()` calls. Django's migration framework is the lowest-risk standard tool to converge on for the Postgres tier.

The bet: a **Django 5 + Django REST Framework + Channels + Celery** backend gives us admin, auth, ORM migrations, task queue, and WebSockets for free, while keeping the agent runtime (CrewAI crews, LangGraph workflows, Neo4j async driver, Pydantic domain models) framework-agnostic and 1:1 portable. The product runtime LLM (Ollama, per [docs/constitution.md](../../docs/constitution.md) §1) does not change. The frontend ([frontend/lib/api.ts](../../frontend/lib/api.ts)) does not change — endpoint paths, payloads, and `X-API-Key` semantics are preserved.

## 2. Goals

- **G1**: Django 5 ASGI app at `backend/lawgraph/` fully replaces the FastAPI app; every existing endpoint contract (`/health`, `/api/agents/*`, `/api/analysis`, `/api/graph/*`, `/api/lsat/*`) is preserved byte-for-byte at the JSON level so the frontend and downstream tests stay green.
- **G2**: Postgres tables (`pending_review`, audit log, future API tokens) are managed by Django migrations; the LangGraph checkpointer keeps its own self-managed schema in a dedicated Postgres schema (`langgraph`) to avoid collisions.
- **G3**: API-key auth shipped in specs 008/009 is preserved end-to-end via a custom DRF `ApiKeyAuthentication` + `HasScope` permission backed by an `ApiToken` model; an idempotent `manage.py seed_api_keys` command keeps the env-driven configuration story (`AGENT_API_KEY`, `ANALYSIS_API_KEY`, `GRAPH_API_KEY`, `LSAT_API_KEY`) working unchanged.
- **G4**: Django admin, `django.contrib.auth`, Celery (Redis broker), and Channels (Redis layer) are wired up and reachable so [BL-20260429-14](../../BACKLOG.md), [BL-20260429-15](../../BACKLOG.md), [BL-20260429-16](../../BACKLOG.md), [BL-20260429-24](../../BACKLOG.md), [BL-20260503-03](../../BACKLOG.md), and [BL-20260430-09](../../BACKLOG.md) all become small follow-on PRs instead of multi-spec efforts.
- **G5**: Constitution, AGENTS.md, PRD, and `.github/copilot-instructions.md` are updated in the same PR so future agents do not "correct" the new stack back to FastAPI on their next pass.

## 3. Non-Goals

- **NG1**: Rewriting CrewAI crews or LangGraph workflows. [backend/app/agents/crews/legal_analyst.py](../../backend/app/agents/crews/legal_analyst.py), [backend/app/agents/crews/precedent_hunter.py](../../backend/app/agents/crews/precedent_hunter.py), [backend/app/agents/graphs/legal_workflow.py](../../backend/app/agents/graphs/legal_workflow.py), and [backend/app/agents/graphs/runtime.py](../../backend/app/agents/graphs/runtime.py) move under `backend/lawgraph/agents_runtime/` with **no logic change**.
- **NG2**: Replacing the Neo4j async driver with `neomodel` or any OGM. [backend/app/db/neo4j.py](../../backend/app/db/neo4j.py), [graph_queries.py](../../backend/app/db/graph_queries.py), [queries.py](../../backend/app/db/queries.py), and [citation_resolver.py](../../backend/app/db/citation_resolver.py) move verbatim into `backend/lawgraph/core/neo4j/`.
- **NG3**: Frontend changes. `frontend/lib/api.ts`, `frontend/components/*`, and Next.js routes stay as-is. Endpoint contracts are preserved.
- **NG4**: JWT/OAuth migration. API-key auth parity is the bar; OAuth/JWT lands in a follow-up spec.
- **NG5**: Producing real WebSocket/SSE event streams. Channels is wired and one health-check consumer at `/ws/agents/{run_id}` is reachable, but actual producers for analysis traces and tutor tokens are deferred to follow-ups.
- **NG6**: Replacing CrewAI/LangGraph internals' own LLM calls with Django integrations. The agent runtime keeps its own httpx + ChatOllama paths.
- **NG7**: Migrating the `app.eval` and LSAT data-bank loaders to Django apps beyond a flat relocation. They stay as plain Python modules under `backend/lawgraph/lsat/services/` and `backend/lawgraph/eval/`.

## 4. User Stories

- As a **LawGraph backend developer**, I want `python manage.py runserver_plus` (or `daphne`) to start the same surface area `uvicorn app.main:app` did, so my local dev loop and the [.vscode/tasks.json](../../.vscode/tasks.json) "Start Backend (Dev)" task continue to work.
- As an **HITL reviewer**, I want a `/admin/` URL where I can browse and triage rows in `ingestionapp.PendingReview` (the spec-004 quarantine queue) and `audit.AuditEvent`, so I no longer need a JSONL tail or psql to do my job.
- As a **LawGraph frontend developer**, I want every existing call in [frontend/lib/api.ts](../../frontend/lib/api.ts) to keep returning the same JSON shape with the same status codes when I `POST` with the same `X-API-Key` header, so I don't ship a frontend refactor in lockstep.
- As an **AI coding agent** running [/specify](../../prompts/specify.md), I want [docs/constitution.md](../../docs/constitution.md) §2 + §11 and [AGENTS.md](../../AGENTS.md) "Tech Stack" to clearly say "Django + DRF + Channels + Celery" so I don't propose reverting to FastAPI on my next pass.
- As an **ops engineer**, I want `make dev` and `docker compose up` to bring up `backend` (daphne) + `worker` (celery) + existing services unchanged, so production-shaped local dev is one command.

## 5. Functional Requirements

- **FR-1**: Constitutional amendment — write `docs/adr/0001-adopt-django-backend.md` (new ADR directory + index). Update [docs/constitution.md](../../docs/constitution.md) §2 backend stack from "FastAPI, Pydantic v2, ..." to "Django 5 (ASGI), Django REST Framework, Channels, Celery, Pydantic v2 (domain layer), CrewAI + LangGraph, Neo4j, Postgres (Django ORM async + raw asyncpg where required), Chroma, Ollama"; update §11 mission-drift guard to drop the explicit "Django-style frameworks must be rejected" wording (replaced with "frameworks not listed in §2 must be rejected"). Update [AGENTS.md](../../AGENTS.md) "Tech Stack (Non-Negotiable)" and Quick Reference rows accordingly. Update [PRD.md](../../PRD.md) backend stack mention. Update [.github/copilot-instructions.md](../../.github/copilot-instructions.md) FastAPI references. CI gate [scripts/spec_validator.py](../../scripts/spec_validator.py) and [scripts/backlog_lint.py](../../scripts/backlog_lint.py) must continue to pass.

- **FR-2**: Dependency swap in [backend/pyproject.toml](../../backend/pyproject.toml). **Add** to base `dependencies`: `django>=5.1,<6`, `djangorestframework>=3.15`, `channels>=4.1`, `channels-redis>=4.2`, `daphne>=4.1`, `celery[redis]>=5.4`, `django-environ>=0.11`, `psycopg[binary,pool]>=3.2`, `drf-pydantic>=2.7`. **Remove** from base `dependencies`: `fastapi`, `uvicorn[standard]`, `python-multipart`, `python-jose[cryptography]`, `passlib[bcrypt]` (move the latter two to a `[project.optional-dependencies].future-auth` extra for use when JWT/OAuth lands). **Add** to `[project.optional-dependencies].dev`: `pytest-django>=4.9`. `pydantic`, `pydantic-settings`, `httpx`, `tenacity`, `redis`, `crewai`, `langgraph`, `neo4j`, `asyncpg`, `chromadb`, `ollama`, `eyecite`, `spacy` are unchanged.

- **FR-3**: Create Django project skeleton at `backend/lawgraph/` via `django-admin startproject lawgraph backend/` and per-feature apps via `python manage.py startapp` for: `core`, `audit`, `analysis`, `graph`, `lsat`, `ingestionapp`, `agentsapi`, `agents_runtime` (the last has `models = []` and is the home for the relocated CrewAI/LangGraph code). Settings split into `backend/lawgraph/settings/{base,dev,test,prod}.py` loaded via `DJANGO_SETTINGS_MODULE`; base reads env via `django-environ`. Add `backend/manage.py` and `backend/lawgraph/asgi.py` with the Channels-aware `ProtocolTypeRouter`. `INSTALLED_APPS` includes `django.contrib.{admin,auth,contenttypes,sessions,messages,staticfiles}`, `rest_framework`, `channels`, plus all eight LawGraph apps.

- **FR-4**: Relocate framework-agnostic modules **with no logic change** (verified by passing the existing test bodies after only import-path edits):
  - [backend/app/agents/](../../backend/app/agents/) → `backend/lawgraph/agents_runtime/` (preserving `crews/`, `graphs/`, `tools/`, `prompts/`, `registry.py`).
  - [backend/app/db/neo4j.py](../../backend/app/db/neo4j.py), [graph_queries.py](../../backend/app/db/graph_queries.py), [queries.py](../../backend/app/db/queries.py), [citation_resolver.py](../../backend/app/db/citation_resolver.py) → `backend/lawgraph/core/neo4j/`.
  - [backend/app/db/checkpointer.py](../../backend/app/db/checkpointer.py) → `backend/lawgraph/agents_runtime/checkpointer.py`.
  - [backend/app/lsat/](../../backend/app/lsat/) → `backend/lawgraph/lsat/services/`.
  - [backend/app/ingestion/](../../backend/app/ingestion/) → `backend/lawgraph/ingestionapp/services/`.
  - [backend/app/models/extraction.py](../../backend/app/models/extraction.py) → `backend/lawgraph/core/schemas/extraction.py` (kept as Pydantic).
  - [backend/app/eval/](../../backend/app/eval/) → `backend/lawgraph/eval/`.
  - [backend/app/core/telemetry.py](../../backend/app/core/telemetry.py) → `backend/lawgraph/core/telemetry.py`. Replace the FastAPI lifespan call site with an `AppConfig.ready()` invocation in `lawgraph.core.apps.CoreConfig.ready()`.

- **FR-5**: Replace [backend/app/core/config.py](../../backend/app/core/config.py) `Settings` (pydantic-settings) with Django `settings.py` reading every existing env var (`NEO4J_URI`, `NEO4J_USER`, `NEO4J_PASSWORD`, `DATABASE_URL`, `OLLAMA_BASE_URL`, `OLLAMA_DEFAULT_MODEL`, `REDIS_URL`, `LANGGRAPH_CHECKPOINTER`, `PHOENIX_COLLECTOR_ENDPOINT`, all four `*_API_KEY` envs, audit paths, etc.) via `django-environ`. Expose a `lawgraph.core.settings_proxy` module that re-exports `from django.conf import settings as _s` and provides attribute access (e.g. `settings_proxy.NEO4J_URI`) so relocated framework-agnostic code under `agents_runtime/`, `lsat/services/`, `ingestionapp/services/`, and `core/neo4j/` does not need to import `django.conf` directly.

- **FR-6**: Define ORM models and migrations:
  - `audit.AuditEvent(id, timestamp, kind, payload JSON, request_id, trace_id, agent, latency_ms)` with `Meta.indexes = [Index(fields=["timestamp"]), Index(fields=["kind"]), Index(fields=["request_id"])]`.
  - `ingestionapp.PendingReview(id, payload JSON, confidence, reason, status, created_at, reviewed_at, reviewer_id FK auth.User nullable)` mirroring [backend/app/db/postgres_migrations/001_pending_review.sql](../../backend/app/db/postgres_migrations/001_pending_review.sql) (existing rows, if any, are preserved by encoding the original schema as the initial Django migration).
  - `core.ApiToken(id, key_hash, scope, name, owner FK auth.User, created_at, last_used_at, revoked_at)` with `scope` ∈ `{"agents","analysis","graph","lsat"}` and `unique_together=("scope","name")`.
  - Existing raw SQL migrations under [backend/app/db/postgres_migrations/](../../backend/app/db/postgres_migrations/) (`001_pending_review.sql`, `002_pg_trgm.sql`) are encoded as `RunSQL` operations inside the initial Django migration so a fresh `make migrate` reproduces today's schema. The `langgraph-checkpoint-postgres` library keeps its own schema; FR-12 isolates it.

- **FR-7**: Reimplement [backend/app/core/provenance.py](../../backend/app/core/provenance.py) on top of `audit.AuditEvent`. Public surface unchanged: `ProvenanceLogger.log_request(...)`, `log_agent_call(...)`, `log_graph_query(...)`, and the `@logged_node(name=...)` decorator used by [backend/app/agents/graphs/legal_workflow.py](../../backend/app/agents/graphs/legal_workflow.py) keep their signatures so the relocated agent code does not change. Storage is `await AuditEvent.objects.acreate(...)`. JSONL fallback (current [backend/app/core/audit_store.py](../../backend/app/core/audit_store.py)) is preserved as a Celery sink (FR-11) for spec 003 compatibility and is the fallback when DB writes fail.

- **FR-8**: Auth parity — implement `lawgraph.core.auth.ApiKeyAuthentication(BaseAuthentication)` reading `X-API-Key`, hashing with `secrets.compare_digest()`-equivalent constant-time comparison, and looking up `ApiToken.key_hash`. Implement `lawgraph.core.auth.HasScope(required_scope: str)` permission. Provide `manage.py seed_api_keys` that reads `AGENT_API_KEY`, `ANALYSIS_API_KEY`, `GRAPH_API_KEY`, `LSAT_API_KEY` from env and upserts `ApiToken` rows (idempotent; safe to re-run; matches today's behavior in [backend/app/core/security.py](../../backend/app/core/security.py) including the "all scopes empty → route is open" local-first fallback).

- **FR-9**: Port every existing API endpoint to a DRF view. Endpoint contracts (path, method, status code, JSON body keys, `X-API-Key` semantics) are preserved 1:1 versus today's [backend/app/api/](../../backend/app/api/) implementations. Use `drf-pydantic` to reuse existing Pydantic request/response models (`AnalysisRequest`, `AnalysisResponse`, `AgentTraceEntry`, `GradeRequest/Response`, `TutorRequest/Response`, `ExtractionResult` echoes, etc.) as DRF serializers without rewriting them. Mapping:
  - `GET /health` → `core.views.HealthView` (open, no auth).
  - `GET /api/agents/{,runs,backlog,specs/{spec_id},status}` → `agentsapi/views.py` with `HasScope("agents")`.
  - `POST /api/analysis` → `analysis/views.AnalysisView` (async; preserves `asyncio.gather(LegalAnalyst.run, PrecedentHunter.run)`) with `HasScope("analysis")`.
  - `GET /api/graph/{stats,cases,neighborhood/{case_id},trail/{case_id}}` → `graph/views.py` with `HasScope("graph")`.
  - `GET /api/lsat/{sections,sections/{code},concepts,passages,questions}` + `POST /api/lsat/{grade,tutor}` → `lsat/views.py` with `HasScope("lsat")`.

- **FR-10**: Replace the FastAPI `lifespan` in [backend/app/main.py](../../backend/app/main.py) with `lawgraph.core.apps.CoreConfig.ready()` calling `register_all_agents()` (from `agents_runtime.registry`) and `init_tracing()` (from `core.telemetry`). LangGraph `ensure_schema()` (today in [backend/app/db/checkpointer.py](../../backend/app/db/checkpointer.py)) is exposed as a `python manage.py ensure_checkpointer` management command and invoked from the container entrypoint **before** daphne starts, so checkpointer DDL is not run inside an HTTP server lifespan. CORS is configured via `django-cors-headers` in `settings.MIDDLEWARE` with the same allow-origin list (`http://localhost:3000`) that [backend/app/main.py](../../backend/app/main.py) installs today.

- **FR-11**: Wire Celery — `backend/lawgraph/celery.py` defines `app = Celery("lawgraph", broker=settings.REDIS_URL, backend=settings.REDIS_URL)`; auto-discovers `tasks.py` in every installed app. Move the low-confidence quarantine path of [IngestionScout.run_and_commit](../../backend/app/ingestion/scout.py) (`_quarantine_postgres`, `_quarantine`) into a Celery task `ingestionapp.tasks.quarantine_extraction(payload: dict)` invoked via `.delay(...)`. Add a `worker` service to [docker-compose.yml](../../docker-compose.yml) running `celery -A lawgraph worker -l info` with the same env vars + `depends_on` as `backend`.

- **FR-12**: Wire Channels — `lawgraph/asgi.py` mounts a `ProtocolTypeRouter` exposing `agentsapi.consumers.AgentRunConsumer` at `/ws/agents/<run_id>`. The consumer accepts the connection, joins a Redis-backed group named `agent-run-<run_id>`, and echoes a `{"type": "ready"}` frame on connect. No producers are wired in this spec — they belong to the follow-ups in §13. Channels uses `channels-redis` against the existing `redis` service.

- **FR-13**: Isolate the LangGraph checkpointer schema — set `LANGGRAPH_CHECKPOINTER_SCHEMA=langgraph` (new env var, default `"langgraph"`); the `manage.py ensure_checkpointer` command runs `CREATE SCHEMA IF NOT EXISTS langgraph; SET search_path TO langgraph;` before invoking `PostgresSaver.setup()`. Django migrations run in the default `public` schema and never touch `langgraph.*`. Documented in [docs/local-ai.md](../../docs/local-ai.md) as an amendment to spec 010.

- **FR-14**: Container + tooling updates:
  - [backend/Dockerfile](../../backend/Dockerfile) `CMD` becomes `["sh", "-c", "python manage.py migrate --noinput && python manage.py ensure_checkpointer && python manage.py seed_api_keys && daphne -b 0.0.0.0 -p 8000 lawgraph.asgi:application"]`.
  - [docker-compose.yml](../../docker-compose.yml) `backend` service `command:` aligned with the above; new `worker` service for Celery (FR-11); both services share the same image build.
  - [.vscode/tasks.json](../../.vscode/tasks.json) "Start Backend (Dev)" command becomes `cd backend && python manage.py runserver 0.0.0.0:8000`.
  - [Makefile](../../Makefile) gains a `migrate: cd backend && python manage.py migrate` target. `make dev`, `make test`, `make lint`, `make local-ai-up`, `make local-ai-pull`, `make local-ai-health` continue to work end-to-end (their inner commands are updated to point at `lawgraph` instead of `app` where applicable).
  - [.github/workflows/](../../.github/workflows/) — every workflow that references `app.main`, `uvicorn`, or `pytest --cov=app` is updated to `lawgraph.asgi:application`, `daphne`, and `--cov=lawgraph` respectively.

- **FR-15**: Test infrastructure migration — rewrite [backend/tests/conftest.py](../../backend/tests/conftest.py) `client` fixture from `httpx.AsyncClient(transport=ASGITransport(app=app))` to a dual fixture: `api_client` (DRF `APIClient` for sync paths) + `async_client` (httpx `AsyncClient(transport=ASGITransport(app=django_asgi_application))` for async endpoints like `/api/analysis`). Configure `pytest-django` with `DJANGO_SETTINGS_MODULE=lawgraph.settings.test`. Convert each test under [backend/tests/api/](../../backend/tests/api/) one-to-one — payload assertions and status-code assertions stay identical; only the import paths and fixture names change. The existing autouse `_reset_api_keys` fixture is replaced with an autouse `_reset_api_tokens` that truncates `core.ApiToken` between tests and re-seeds via `seed_api_keys` when a test requests it.

- **FR-16**: After all of FR-3 through FR-15 land and tests pass, **delete** the entire [backend/app/](../../backend/app/) tree (including `app/main.py`, `app/api/`, `app/core/`, `app/db/`, `app/agents/`, `app/ingestion/`, `app/lsat/`, `app/models/`, `app/eval/`). The package is removed in a final commit so git history retains a clean cutover point. `LawGraph_ai.egg-info/` artifacts under [backend/app/LawGraph_ai.egg-info/](../../backend/app/LawGraph_ai.egg-info/) are regenerated.

## 6. Non-Functional Requirements

- **NFR-PARITY-1**: Zero behavioral regression at the HTTP layer. The exhaustive set of endpoint paths, HTTP methods, status codes, JSON body shapes, and `X-API-Key` semantics exposed by [backend/app/api/](../../backend/app/api/) on `main` is reproduced by the Django build. Verified by FR-15 tests, which assert response JSON equality (not just shape) for every endpoint that has a deterministic stub today.
- **NFR-PARITY-2**: Zero frontend changes required. [frontend/lib/api.ts](../../frontend/lib/api.ts) keeps the same hostnames, paths, headers, and payloads. Verified by running the existing Vitest suite under [frontend/__tests__/](../../frontend/__tests__/) against MSW handlers that target the same routes.
- **NFR-PERF-1**: `POST /api/analysis` p95 latency does not regress more than 10% versus `main` on a single Apple Silicon laptop with `llama3.1:8b-instruct-q4_K_M`. Measured via the same harness used for spec 010 NFR-PERF-1.
- **NFR-AUDIT-1**: Every LLM call, tool call, and HTTP request is logged via the Django-backed `ProvenanceLogger`; trace IDs match between `audit.AuditEvent` rows and Phoenix spans. Verified by extending the spec-010 audit-correlation integration test.
- **NFR-OSS-1**: All added dependencies are MIT/Apache-2.0/BSD: `django` (BSD-3), `djangorestframework` (BSD-3), `channels` (BSD-3), `channels-redis` (BSD-3), `daphne` (BSD-3), `celery` (BSD-3), `psycopg[binary,pool]` (LGPL with linking exception), `django-environ` (MIT), `drf-pydantic` (Apache-2.0), `pytest-django` (BSD-3). Constitution §1 satisfied.
- **NFR-SEC-1**: `manage.py check --deploy` exits 0 in `prod` settings. CSRF is disabled for DRF API views (header-token auth model), enabled for `/admin/`. `SECURE_PROXY_SSL_HEADER`, `SESSION_COOKIE_SECURE`, `CSRF_COOKIE_SECURE` are set in `prod` settings. Secrets remain env-driven; `SECRET_KEY` is loaded via `django-environ`.
- **NFR-MIGRATION-SAFETY-1**: `python manage.py migrate --noinput` is idempotent and produces a Postgres schema indistinguishable from today's `init-db.sh` + spec-004 SQL. Verified by a CI step that runs both paths against fresh Postgres containers and `pg_dump --schema-only`-diffs them; allowed differences are limited to Django metadata tables (`django_migrations`, `django_session`, `auth_*`, `django_content_type`, `django_admin_log`).
- **NFR-TEST-COV-1**: `pytest --cov=lawgraph` ≥ 75% combined coverage; no module under `lawgraph/core/`, `lawgraph/agents_runtime/`, `lawgraph/agentsapi/`, `lawgraph/analysis/`, `lawgraph/graph/`, or `lawgraph/lsat/` drops below 70% line coverage. Constitution §3 satisfied.
- **NFR-LEGALBENCH-1**: `Run LegalBench Eval` task delta is **≥ 0 pp** on `core_reasoning` and `precedent_retrieval` versus `main`. The agent runtime is unchanged code-wise (only relocated), so parity is the bar.
- **NFR-DOC-1**: [docs/architecture.md](../../docs/architecture.md), [docs/local-ai.md](../../docs/local-ai.md), [docs/agent-roles.md](../../docs/agent-roles.md), and [docs/AO-SDLC-guide.md](../../docs/AO-SDLC-guide.md) (where they reference FastAPI specifics) are updated. New sections in [docs/data-model.md](../../docs/data-model.md) cover `audit.AuditEvent`, `ingestionapp.PendingReview`, and `core.ApiToken`. New `docs/security.md` (resolves [BL-20260430-10](../../BACKLOG.md)) documents the API-token model and rotation procedure.

## 7. Data Model Impact

- **Postgres `public` schema (Django-managed)**:
  - `audit_auditevent` (FR-6) — supersedes the JSONL audit log shipped in spec 003. Contains `source`, `confidence` columns are not applicable here (this is platform metadata, not a Neo4j node) but `agent_version` and `trace_id` are required and indexed.
  - `ingestionapp_pendingreview` (FR-6) — replaces the raw `pending_review` table from [backend/app/db/postgres_migrations/001_pending_review.sql](../../backend/app/db/postgres_migrations/001_pending_review.sql). Initial Django migration ships a `RunSQL` block reproducing the exact column definitions (including `pg_trgm` extension from [002_pg_trgm.sql](../../backend/app/db/postgres_migrations/002_pg_trgm.sql)).
  - `core_apitoken` (FR-6) — new; replaces the env-only API-key model.
  - Standard Django metadata tables (`auth_user`, `django_session`, `django_admin_log`, `django_content_type`, `django_migrations`).
- **Postgres `langgraph` schema (library-managed)**: `checkpoints`, `checkpoint_writes`, `checkpoint_blobs` — owned by `langgraph-checkpoint-postgres`, isolated by FR-13, untouched by Django migrations.
- **Neo4j**: zero changes. All node properties (`source`, `source_url`, `ingest_timestamp`, `agent_version`, `confidence`) continue to be set by the relocated `IngestionScout` and `commit_extraction` paths. Constitution §4 satisfied.
- **Vector DB**: zero changes.

## 8. API Surface

The HTTP surface is preserved 1:1. Reference Pydantic models live under `lawgraph/core/schemas/` (relocated from [backend/app/models/](../../backend/app/models/)) and are wrapped by `drf-pydantic` for DRF compatibility:

| Method | Path                                   | Auth scope | Request                  | Response                       |
| ------ | -------------------------------------- | ---------- | ------------------------ | ------------------------------ |
| GET    | `/health`                              | open       | —                        | `HealthStatus`                 |
| GET    | `/api/agents/`                         | `agents`   | —                        | `list[AgentDescriptor]`        |
| GET    | `/api/agents/runs`                     | `agents`   | —                        | `list[AgentRun]`               |
| GET    | `/api/agents/backlog`                  | `agents`   | —                        | `list[BacklogItem]`            |
| GET    | `/api/agents/specs/{spec_id}`          | `agents`   | —                        | `SpecDetail`                   |
| GET    | `/api/agents/status`                   | `agents`   | —                        | `AgentStatus`                  |
| POST   | `/api/analysis`                        | `analysis` | `AnalysisRequest`        | `AnalysisResponse`             |
| GET    | `/api/graph/stats`                     | `graph`    | —                        | `GraphStats`                   |
| GET    | `/api/graph/cases`                     | `graph`    | `?q=&limit=`             | `list[CaseSummary]`            |
| GET    | `/api/graph/neighborhood/{case_id}`    | `graph`    | `?limit=`                | `Neighborhood`                 |
| GET    | `/api/graph/trail/{case_id}`           | `graph`    | —                        | `CitationTrail`                |
| GET    | `/api/lsat/sections`                   | `lsat`     | —                        | `list[Section]`                |
| GET    | `/api/lsat/sections/{code}`            | `lsat`     | —                        | `Section`                      |
| GET    | `/api/lsat/concepts`                   | `lsat`     | —                        | `list[Concept]`                |
| GET    | `/api/lsat/passages`                   | `lsat`     | —                        | `list[Passage]`                |
| GET    | `/api/lsat/questions`                  | `lsat`     | `?section=&limit=`       | `list[Question]`               |
| POST   | `/api/lsat/grade`                      | `lsat`     | `GradeRequest`           | `GradeResponse`                |
| POST   | `/api/lsat/tutor`                      | `lsat`     | `TutorRequest`           | `TutorResponse`                |
| WS     | `/ws/agents/{run_id}`                  | open       | —                        | `{"type": "ready"}` on connect |

`X-API-Key` semantics: when a scope's env key is unset, the scope is open (parity with [backend/app/core/security.py](../../backend/app/core/security.py)); when set, requests without a matching `ApiToken` row return `401`.

## 9. Agent / Crew Impact

- **No agent role added or removed.** [docs/agent-roles.md](../../docs/agent-roles.md) is updated only to amend file paths from `backend/app/agents/...` to `backend/lawgraph/agents_runtime/...`.
- **`@logged_node` decorator signature unchanged** so `legal_workflow.py` graph nodes need no edits beyond import paths (`from app.core.provenance` → `from lawgraph.core.provenance`).
- **`register_all_agents()` invocation site** moves from FastAPI lifespan to `CoreConfig.ready()`. Behavior unchanged.
- **No new tools.** No new prompt templates beyond the docs amendment.

## 10. Acceptance Criteria

- **AC-1**: Given a fresh checkout, when I run `make dev` (which now runs `docker compose up --build` against the updated [docker-compose.yml](../../docker-compose.yml)), then `curl localhost:8000/health` returns `200` with the same JSON shape as `main`, `curl localhost:8000/admin/login/` returns `200`, and `docker compose logs worker` shows `celery@worker ready`. (FR-3, FR-11, FR-14)
- **AC-2**: Given the backend is running with `AGENT_API_KEY=k1`, `ANALYSIS_API_KEY=k2`, `GRAPH_API_KEY=k3`, `LSAT_API_KEY=k4` in env, when I send `GET /api/agents/` with `X-API-Key: k1`, `GET /api/graph/stats` with `X-API-Key: k3`, and `POST /api/analysis` with `X-API-Key: k2` and a valid body, then I get `200` for each; when I omit or swap keys I get `401`; when I unset all four envs and restart, all four routes accept any request (parity with current local-first fallback). (FR-8, NFR-PARITY-1)
- **AC-3**: Given the existing test suite under [backend/tests/](../../backend/tests/) is rewritten per FR-15, when I run `cd backend && pytest --ds=lawgraph.settings.test --cov=lawgraph`, then every prior test (counted on `main`) passes with the same assertions and combined coverage is ≥ 75%. (FR-15, NFR-TEST-COV-1)
- **AC-4**: Given a fresh Postgres container, when I run `python manage.py migrate --noinput` against the new app and `psql -f init-db.sh` followed by the legacy SQL files against an identical container, then `pg_dump --schema-only` of `public.ingestionapp_pendingreview` matches `pg_dump --schema-only` of `public.pending_review` modulo table name. (FR-6, NFR-MIGRATION-SAFETY-1)
- **AC-5**: Given `IngestionScout` produces a low-confidence extraction, when `await scout.run_and_commit(payload)` is invoked from a Django view or shell, then a Celery task `ingestionapp.tasks.quarantine_extraction` is enqueued (verified via `app.control.inspect().reserved()` in a test using `task_always_eager=False`), the worker writes a `ingestionapp.PendingReview` row visible in `/admin/`, and a corresponding `audit.AuditEvent` row is recorded. (FR-7, FR-11)
- **AC-6**: Given the LangGraph checkpointer is configured for Postgres, when the container starts, then `python manage.py ensure_checkpointer` creates schema `langgraph` and the `langgraph.checkpoints` table without touching `public`; when `python manage.py migrate` runs again, no `langgraph.*` tables are touched and `pg_dump --schema=langgraph` is unchanged. (FR-13)
- **AC-7**: Given `wscat -c ws://localhost:8000/ws/agents/test-run-id`, when the client connects, then the server replies with `{"type":"ready","run_id":"test-run-id"}` and the connection stays open. (FR-12)
- **AC-8**: Given the constitutional amendment is merged, when I run `python scripts/spec_validator.py` and `python scripts/backlog_lint.py`, then both exit 0; when I `grep -RIl "FastAPI" docs/ AGENTS.md PRD.md .github/copilot-instructions.md`, the only matches are historical references (changelog, ADR explaining the migration) and no "must use FastAPI" prescriptions remain. (FR-1)
- **AC-9**: Given the frontend test suite under [frontend/__tests__/](../../frontend/__tests__/) targets the same MSW handlers, when I run `cd frontend && npm test -- --run`, then it passes with no source edits to [frontend/lib/api.ts](../../frontend/lib/api.ts) or any component. (NFR-PARITY-2)
- **AC-10**: Given the LangGraph workflow tests from spec 010 ([backend/tests/agents/graphs/](../../backend/tests/agents/graphs/)), when I run them under `pytest --ds=lawgraph.settings.test`, then they pass with imports updated only to `lawgraph.agents_runtime.graphs.*`. (FR-4, NFR-LEGALBENCH-1)
- **AC-11**: Given [backend/app/](../../backend/app/) is deleted (FR-16), when I run `cd backend && pytest`, then no `from app.` import remains anywhere in the repo (`grep -RIn "from app\." backend/ tests/` returns empty). (FR-16)

## 11. LegalBench Impact

- Tasks affected: `core_reasoning`, `precedent_retrieval` (the smoke set used by `Run LegalBench Eval`).
- Expected delta: **0 pp** (the agent runtime moves but does not change). NFR-LEGALBENCH-1 makes any regression > 1 pp blocking.

## 12. Risks & Open Questions

- **R-1**: **Async ORM maturity.** Django 5's async ORM (`acreate`, `aget`, `aupdate`) is solid for simple CRUD but has rough edges around transactions and `select_for_update`. *Mitigation*: keep the audit/quarantine writes simple (single-row `acreate`); use `sync_to_async(...)` wrappers for any complex transaction; this is the same containment pattern Django docs recommend.
- **R-2**: **`drf-pydantic` Pydantic-v2 + DRF compatibility.** `drf-pydantic` is the active Pydantic-v2 ↔ DRF bridge but is a small library. *Mitigation*: pin `drf-pydantic>=2.7`; keep a fallback path of hand-written serializers for the four POST endpoints; the GETs are pure read-models and are trivially serializable.
- **R-3**: **LangGraph checkpointer schema collision** with Django migrations on the same database. *Mitigation*: FR-13 isolates the checkpointer in its own schema with explicit `search_path` plumbing; AC-6 enforces this.
- **R-4**: **Big-bang cutover risk.** All tests must be ported in lockstep; a bad merge could leave the repo non-buildable. *Mitigation*: keep [backend/app/](../../backend/app/) intact through FR-3 → FR-15; only delete in the FR-16 commit; CI must be green at every commit on the feature branch (enforced by branch protection).
- **R-5**: **Constitutional churn.** This spec amends [docs/constitution.md](../../docs/constitution.md) §2 + §11. *Mitigation*: FR-1 lands the amendment + ADR in the very first commit so subsequent commits do not violate the (now-old) constitution; the ADR explicitly grants the `/specify` agent permission to keep landing this spec.
- **R-6**: **Celery + ASGI process model.** Daphne + Celery worker are separate processes; both need the same env. *Mitigation*: docker-compose `worker` service inherits from the same image build as `backend`; for local non-Docker dev, `Procfile` documented in [docs/local-ai.md](../../docs/local-ai.md).
- **R-7**: **Settings split breakage.** Splitting `settings.py` into `base/dev/test/prod` is a common source of subtle import-order bugs. *Mitigation*: settings tests under `backend/tests/test_settings.py` import each variant and assert `settings.configured is True` + key fields are populated.

There are **no `OPEN QUESTION OQ-N` blocks** — all forks were resolved at the planning interview stage (see `/memories/session/plan.md` decision matrix).

## 13. Out of Scope / Follow-ups

Tracked in `tasks.md` `## Follow-ups Discovered` and mirrored to [BACKLOG.md](../../BACKLOG.md):

- HITL approve/reject endpoints + admin actions for `PendingReview` (resolves [BL-20260429-15](../../BACKLOG.md) once the model lands).
- Single-run drill-down view `/agents/runs/{trace_id}` ([BL-20260429-14](../../BACKLOG.md)) — small follow-up given the new `audit.AuditEvent` model.
- Real Channels producers for `/ws/agents/{run_id}` (analysis trace SSE [BL-20260429-24](../../BACKLOG.md), tutor token SSE [BL-20260503-03](../../BACKLOG.md), dashboard WS [BL-20260429-16](../../BACKLOG.md)).
- Per-token rate limiting via `django-ratelimit` ([BL-20260430-09](../../BACKLOG.md)).
- JWT/OAuth on top of `core.ApiToken` (deferred; revives the `python-jose` + `passlib` deps under the `future-auth` extra).
- Periodic Celery beat job for spec-validator + backlog-lint ([BL-20260429-09](../../BACKLOG.md)).
- Async Postgres connection pool retired in favor of Django's connection pooling for non-LangGraph code ([BL-20260429-17](../../BACKLOG.md)) — partially resolved here for ORM paths; raw `asyncpg` calls outside ORM remain.
- Author `docs/security.md` ([BL-20260430-10](../../BACKLOG.md)) — partially completed in NFR-DOC-1; flesh out rotation procedure post-cutover.
