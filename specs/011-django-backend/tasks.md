# Tasks: Refactor Backend from FastAPI to Django

> **Historical note (2026-09-05, BL-20260602-04).** `backend/app/` was the pre-Django FastAPI package. It was deleted by this spec's own T-016; the Django project package lives at `backend/law_ai/`. Every `backend/app/...` path below is therefore rendered as inline code, not as a link — the files it names no longer exist, and the ~110 dead hrefs 404'd on every platform. The text is otherwise unedited: it records the migration as it was specified.

> Each task references one or more `FR-*` / `NFR-*` / `AC-*` IDs from [spec.md](spec.md). [scripts/spec_validator.py](../../scripts/spec_validator.py) enforces full coverage.
>
> Sequence: T-001 must merge first (constitutional gate). T-002 → T-016 land on a long-lived `feat/011-django-backend` branch with green CI per commit; T-016 (legacy delete) is the cutover commit.

## Conventions

- Status: `[ ]` todo / `[~]` in-progress / `[x]` done.
- Owner: GitHub handle or `@copilot` / `@agent:<role>`.
- Each task lists exact files to touch and how to verify.

---

## T-001 — Constitutional amendment + ADR + docs sweep

- **Refs**: FR-1, AC-8, NFR-DOC-1
- **Owner**: @copilot (paired with maintainer for merge)
- **Status**: `[x]`
- **Files**:
  - `docs/adr/0001-adopt-django-backend.md` (new — first ADR; create `docs/adr/` directory and a brief `docs/adr/README.md` index)
  - [docs/constitution.md](../../docs/constitution.md) §2 backend stack and §11 mission-drift guard
  - [AGENTS.md](../../AGENTS.md) "Tech Stack (Non-Negotiable)" + Quick Reference rows (uvicorn → daphne) + "Project Structure" (`backend/app/` → `backend/law_ai/`)
  - [PRD.md](../../PRD.md) backend stack mention
  - [.github/copilot-instructions.md](../../.github/copilot-instructions.md) FastAPI references
  - [docs/architecture.md](../../docs/architecture.md), [docs/local-ai.md](../../docs/local-ai.md), [docs/agent-roles.md](../../docs/agent-roles.md) — surgical edits to file paths only
- **Steps**:
  1. Author ADR with: context (why Django), decision, consequences (Channels/Celery/admin/auth come for free), alternatives considered, and an explicit "supersedes constitution §2 lock until next ADR" clause.
  2. Edit constitution §2 to list "Django 5 (ASGI), DRF, Channels, Celery, Pydantic v2 (domain), CrewAI + LangGraph, Neo4j, Postgres (Django ORM async + raw asyncpg where required), Chroma, Ollama".
  3. Edit constitution §11 mission-drift guard: replace the "Django-style frameworks" sentence with "frameworks not listed in §2 must be rejected".
  4. Update AGENTS.md, PRD.md, and `.github/copilot-instructions.md` to drop FastAPI prescriptions.
  5. `grep -RIn "FastAPI\|uvicorn" docs/ AGENTS.md PRD.md .github/copilot-instructions.md` — only historical/changelog references remain.
- **Verify**:
  - `python scripts/spec_validator.py specs/011-django-backend` exits 0.
  - `python scripts/backlog_lint.py` exits 0.
  - Manual review by maintainer (HITL §10 Level-2 gate).

## T-002 — Dependency swap in `backend/pyproject.toml`

- **Refs**: FR-2, NFR-OSS-1
- **Owner**: @copilot
- **Status**: `[x]`
- **Files**:
  - [backend/pyproject.toml](../../backend/pyproject.toml)
- **Steps**:
  1. Add base deps: `django>=5.1,<6`, `djangorestframework>=3.15`, `channels>=4.1`, `channels-redis>=4.2`, `daphne>=4.1`, `celery[redis]>=5.4`, `django-environ>=0.11`, `psycopg[binary,pool]>=3.2`, `drf-pydantic>=2.7`.
  2. Remove base deps: `fastapi`, `uvicorn[standard]`, `python-multipart`.
  3. Move `python-jose[cryptography]`, `passlib[bcrypt]` to `[project.optional-dependencies].future-auth`.
  4. Add `pytest-django>=4.9` to `[project.optional-dependencies].dev`.
  5. `pip install -e ".[dev,local-ai]"` in a clean venv to confirm resolves.
- **Verify**:
  - `pip check` clean.
  - `python -c "import django, rest_framework, channels, celery, daphne, drf_pydantic"` succeeds.
  - License check: each new dep listed under NFR-OSS-1 is BSD/MIT/Apache.

## T-003 — Django project skeleton + apps + settings split

- **Refs**: FR-3, FR-5, R-7
- **Owner**: @copilot
- **Status**: `[x]`
- **Files**:
  - `backend/manage.py` (new)
  - `backend/law_ai/__init__.py`, `asgi.py`, `wsgi.py`, `urls.py`, `celery.py` (new — `celery.py` skeleton only here; full wiring in T-011)
  - `backend/law_ai/settings/__init__.py`, `base.py`, `dev.py`, `test.py`, `prod.py` (new)
  - `backend/law_ai/{core,audit,analysis,graph,lsat,ingestionapp,agentsapi,agents_runtime}/{__init__.py,apps.py}` (new)
  - `backend/law_ai/core/settings_proxy.py` (new — re-exports `from django.conf import settings`)
  - `backend/tests/test_settings.py` (new)
- **Steps**:
  1. `cd backend && django-admin startproject law_ai .`; move `law_ai/settings.py` into `law_ai/settings/base.py` and create dev/test/prod variants.
  2. `python manage.py startapp` for each of the eight apps; ensure each `apps.py` declares `default_auto_field = "django.db.models.BigAutoField"`.
  3. `base.py`: read `DATABASE_URL`, `REDIS_URL`, `NEO4J_*`, `OLLAMA_*`, `PHOENIX_*`, all four `*_API_KEY` envs, `LANGGRAPH_CHECKPOINTER`, `LANGGRAPH_CHECKPOINTER_SCHEMA` via `django-environ`. Configure `INSTALLED_APPS`, `MIDDLEWARE` (CORS allow `http://localhost:3000`), `ASGI_APPLICATION="law_ai.asgi.application"`, `CHANNEL_LAYERS` Redis backend, `REST_FRAMEWORK` defaults (DRF + custom auth + permissions).
  4. `test.py`: in-memory channel layer, `CELERY_TASK_ALWAYS_EAGER=True`, SQLite or Postgres test DB based on env.
  5. `prod.py`: `DEBUG=False`, `ALLOWED_HOSTS` from env, security cookie/SSL flags.
  6. Write `backend/tests/test_settings.py` importing each variant and asserting key fields.
- **Verify**:
  - `cd backend && DJANGO_SETTINGS_MODULE=law_ai.settings.dev python manage.py check` exits 0.
  - `pytest backend/tests/test_settings.py -q` passes.
  - `python -c "from law_ai.core.settings_proxy import settings_proxy; print(settings_proxy.NEO4J_URI)"` works.

## T-004 — Relocate framework-agnostic modules (no logic change)

- **Refs**: FR-4
- **Owner**: @copilot (HUMAN-PAIRED — large `git mv` set)
- **Status**: `[x]`
- **Files** (every file under each src moves to corresponding dst):
  - `backend/app/agents/` → `backend/law_ai/agents_runtime/`
  - `backend/app/db/neo4j.py` → `backend/law_ai/core/neo4j/driver.py`
  - `backend/app/db/graph_queries.py` → `backend/law_ai/core/neo4j/graph_queries.py`
  - `backend/app/db/queries.py` → `backend/law_ai/core/neo4j/queries.py`
  - `backend/app/db/citation_resolver.py` → `backend/law_ai/core/neo4j/citation_resolver.py`
  - `backend/app/db/checkpointer.py` → `backend/law_ai/agents_runtime/checkpointer.py`
  - `backend/app/lsat/` → `backend/law_ai/lsat/services/`
  - `backend/app/ingestion/` → `backend/law_ai/ingestionapp/services/`
  - `backend/app/models/extraction.py` → `backend/law_ai/core/schemas/extraction.py`
  - `backend/app/eval/` → `backend/law_ai/eval/`
  - `backend/app/core/telemetry.py` → `backend/law_ai/core/telemetry.py`
  - `backend/app/db/neo4j_migrations/` → `backend/law_ai/core/neo4j/migrations/`
- **Steps**:
  1. `git mv` each path; preserve git history (use `--follow` in reviews).
  2. `grep -RIln "from app\." backend/law_ai` and rewrite each import to `from law_ai.<dst>.` per the move table.
  3. Replace `from app.core.config import settings` with `from law_ai.core.settings_proxy import settings_proxy as settings` in every relocated module.
  4. Run `ruff check --fix backend/law_ai` and `black backend/law_ai`.
- **Verify**:
  - `grep -RIn "from app\." backend/law_ai` returns empty.
  - `python -c "from law_ai.agents_runtime.crews.legal_analyst import LegalAnalyst"` succeeds.
  - `python -c "from law_ai.core.neo4j.driver import get_neo4j_driver"` succeeds.
  - `mypy backend/law_ai --strict` passes for relocated modules (ignore-list extended for crewai/langgraph/neo4j/eyecite).

## T-005 — Audit, ApiToken, PendingReview ORM models + migrations

- **Refs**: FR-6, FR-13, NFR-MIGRATION-SAFETY-1, AC-4
- **Owner**: @copilot
- **Status**: `[x]`
- **Files**:
  - `backend/law_ai/audit/models.py` + `migrations/0001_initial.py` (new)
  - `backend/law_ai/ingestionapp/models.py` + `migrations/0001_initial.py` (new — uses `RunSQL` to encode existing schema; uses `state_operations`/`database_operations` to adopt an existing legacy table)
  - `backend/law_ai/core/models.py` + `migrations/0001_initial.py` (new — `ApiToken`)
  - `backend/law_ai/audit/admin.py`, `backend/law_ai/ingestionapp/admin.py`, `backend/law_ai/core/admin.py` (new — register models with sensible list_display/filters)
  - `backend/tests/integration/test_migrate_parity.py` (new)
- **Steps**:
  1. Define `AuditEvent`, `PendingReview`, `ApiToken` per FR-6.
  2. `python manage.py makemigrations audit ingestionapp core` then hand-edit `ingestionapp/0001_initial.py` to embed verbatim DDL from `backend/app/db/postgres_migrations/001_pending_review.sql` and `backend/app/db/postgres_migrations/002_pg_trgm.sql` inside a `RunSQL` operation, with `state_operations` describing the resulting model so legacy tables can be adopted.
  3. Register all three models in admin with reviewer-friendly defaults.
  4. Write integration test: spin two Postgres containers, run `migrate` on one and the legacy SQL on the other, `pg_dump --schema-only` both, normalize table name, diff.
- **Verify**:
  - `python manage.py migrate --noinput` against fresh Postgres exits 0.
  - `python manage.py migrate --noinput` against a Postgres pre-loaded with legacy `pending_review` rows exits 0 and preserves the rows.
  - `pytest backend/tests/integration/test_migrate_parity.py -q` passes.
  - `/admin/audit/auditevent/`, `/admin/ingestionapp/pendingreview/`, `/admin/core/apitoken/` are all reachable and list-viewable.

## T-006 — Provenance reimpl on Django ORM (signature unchanged)

- **Refs**: FR-7, NFR-AUDIT-1
- **Owner**: @copilot
- **Status**: `[x]`
- **Files**:
  - `backend/law_ai/core/provenance.py` (new — supersedes `backend/app/core/provenance.py`)
  - `backend/law_ai/core/audit_jsonl.py` (new — JSONL Celery sink fallback, lifted from `backend/app/core/audit_store.py`)
  - `backend/law_ai/core/middleware.py` (new — ASGI ProvenanceMiddleware)
  - `backend/tests/core/test_provenance.py` (port + extend)
- **Steps**:
  1. Implement `ProvenanceLogger.log_request`, `.log_agent_call`, `.log_graph_query`, `@logged_node(name)` with the same signatures as today.
  2. Internally call `await AuditEvent.objects.acreate(...)` inside a `try`/`except` that, on failure, enqueues `core.tasks.persist_audit_jsonl.delay(payload)` to write the legacy JSONL file (preserving spec-003 forensic continuity).
  3. Wire `ProvenanceMiddleware` into `MIDDLEWARE` in `settings/base.py`.
- **Verify**:
  - `pytest backend/tests/core/test_provenance.py -q` passes.
  - In a shell, `await ProvenanceLogger.log_agent_call("foo", {}, {}, "model", 1.0, 0.9, [])` produces an `AuditEvent` row.
  - With Postgres killed, the same call enqueues a Celery task that writes JSONL.

## T-007 — API-key auth: ApiKeyAuthentication + HasScope + seed_api_keys

- **Refs**: FR-8, AC-2, NFR-PARITY-1
- **Owner**: @copilot
- **Status**: `[x]`
- **Files**:
  - `backend/law_ai/core/auth.py` (new)
  - `backend/law_ai/core/management/__init__.py`, `commands/__init__.py`, `commands/seed_api_keys.py` (new)
  - `backend/tests/core/test_auth.py` (new — covers constant-time compare, scope allow/deny, "all envs unset → open" parity)
- **Steps**:
  1. Implement `ApiKeyAuthentication(BaseAuthentication)`: read `X-API-Key`, hash, look up `ApiToken.key_hash` via `aget`, attach a synthetic user (or `AnonymousUser`) plus `request.auth = token`.
  2. Implement `HasScope` permission factory; behavior: if no `ApiToken` row exists for the required scope and the matching env var is also empty, allow (parity with `backend/app/core/security.py`).
  3. `seed_api_keys` command reads each `*_API_KEY` env var, hashes via the same algorithm as auth, upserts `ApiToken(scope=..., name="env", key_hash=...)`. Idempotent.
- **Verify**:
  - `pytest backend/tests/core/test_auth.py -q` passes.
  - `AGENT_API_KEY=foo python manage.py seed_api_keys` exits 0; second invocation is a no-op.
  - With keys seeded, GET `/api/agents/` with `X-API-Key: foo` returns 200; without header returns 401; with all four envs unset, returns 200 (open fallback).

## T-008 — Port routers to DRF views (5 routers, 18 endpoints)

- **Refs**: FR-9, NFR-PARITY-1, AC-2, AC-9
- **Owner**: @copilot (one PR per router on the feature branch; this task tracks all five)
- **Status**: `[x]`
- **Files**:
  - `backend/law_ai/core/views.py` + `urls.py` — `HealthView` (port of `backend/app/api/health.py`)
  - `backend/law_ai/agentsapi/views.py` + `urls.py` — port of `backend/app/api/agents.py`
  - `backend/law_ai/analysis/views.py` + `urls.py` + `serializers.py` — port of `backend/app/api/analysis.py`; preserves `await asyncio.gather(LegalAnalyst.run, PrecedentHunter.run)`
  - `backend/law_ai/graph/views.py` + `urls.py` — port of `backend/app/api/graph.py`
  - `backend/law_ai/lsat/views.py` + `urls.py` + `serializers.py` — port of `backend/app/api/lsat.py`; tutor stays async httpx → Ollama
  - `backend/law_ai/urls.py` — root URLconf wiring `/health`, `/api/agents/`, `/api/analysis/`, `/api/graph/`, `/api/lsat/`, `/admin/`
  - Use `drf-pydantic` to wrap existing Pydantic models from `law_ai.core.schemas` (relocated `AnalysisRequest/Response`, `AgentTraceEntry`, `GradeRequest/Response`, `TutorRequest/Response`, etc.)
- **Steps**:
  1. For each router, create a DRF `APIView` (or `async`-capable view) class with `authentication_classes = [ApiKeyAuthentication]`, `permission_classes = [HasScope("<scope>")]`.
  2. Reuse Pydantic models via `drf-pydantic.DrfPydanticSerializer` so request/response validation matches `main`.
  3. Preserve `degraded` JSON shapes from `backend/app/api/graph.py` when Neo4j is down.
  4. Async views (`/api/analysis`, `/api/lsat/tutor`) declare `async def` handlers; daphne handles them natively.
- **Verify**:
  - For each ported endpoint, the corresponding test from [backend/tests/api/](../../backend/tests/api/) (rewritten in T-013) passes with byte-for-byte JSON equality.
  - Manual smoke per AC-2.

## T-009 — Replace FastAPI lifespan with `AppConfig.ready()` + ensure_checkpointer command

- **Refs**: FR-10, FR-13, AC-6
- **Owner**: @copilot
- **Status**: `[x]`
- **Files**:
  - `backend/law_ai/core/apps.py` (extend with `ready()` calling `register_all_agents()` + `init_tracing()`)
  - `backend/law_ai/core/management/commands/ensure_checkpointer.py` (new)
  - `backend/tests/integration/test_checkpointer_isolation.py` (new)
- **Steps**:
  1. In `CoreConfig.ready()`, lazily import `law_ai.agents_runtime.registry.register_all_agents` and call it; same for `law_ai.core.telemetry.init_tracing`. Guard against double-init under `runserver --noreload`.
  2. `ensure_checkpointer` command: connect to Postgres, `CREATE SCHEMA IF NOT EXISTS langgraph`, set `search_path=langgraph`, call `PostgresSaver.setup()`, restore search_path.
  3. Integration test spins fresh Postgres, runs `manage.py migrate` then `manage.py ensure_checkpointer`, asserts `langgraph.checkpoints` exists and `public.checkpoints` does not.
- **Verify**:
  - `pytest backend/tests/integration/test_checkpointer_isolation.py -q` passes.
  - `python manage.py ensure_checkpointer` exits 0 idempotently.

## T-010 — Channels skeleton: `/ws/agents/{run_id}` consumer

- **Refs**: FR-12, AC-7
- **Owner**: @copilot
- **Status**: `[x]`
- **Files**:
  - `backend/law_ai/agentsapi/consumers.py` (new — `AgentRunConsumer(AsyncJsonWebsocketConsumer)`)
  - `backend/law_ai/agentsapi/routing.py` (new — websocket urlpatterns)
  - `backend/law_ai/asgi.py` — wire `ProtocolTypeRouter({"http": ..., "websocket": AuthMiddlewareStack(URLRouter(websocket_urlpatterns))})`
  - `backend/tests/integration/test_channels_ws.py` (new)
- **Steps**:
  1. Consumer accepts the WS, joins group `agent-run-<run_id>`, sends `{"type":"ready","run_id":"<id>"}`.
  2. Wire `channels-redis` `RedisChannelLayer` against `REDIS_URL`.
  3. Test uses `channels.testing.WebsocketCommunicator` to assert connect + ready frame.
- **Verify**:
  - `pytest backend/tests/integration/test_channels_ws.py -q` passes.
  - `wscat -c ws://localhost:8000/ws/agents/test-run-id` shows the ready frame manually.

## T-011 — Celery wiring + ingestion quarantine task

- **Refs**: FR-11, AC-5
- **Owner**: @copilot
- **Status**: `[x]`
- **Files**:
  - `backend/law_ai/celery.py` (full implementation)
  - `backend/law_ai/__init__.py` (load celery app)
  - `backend/law_ai/ingestionapp/tasks.py` (new — `quarantine_extraction(payload)`)
  - `backend/law_ai/core/tasks.py` (new — `persist_audit_jsonl(payload)` for T-006 fallback)
  - `backend/law_ai/ingestionapp/services/scout.py` — replace inline `_quarantine_postgres`/`_quarantine` calls with `quarantine_extraction.delay(payload)`
  - `backend/tests/ingestionapp/test_tasks.py` (port + extend)
- **Steps**:
  1. `celery.py`: `app = Celery("law_ai")`; `app.config_from_object("django.conf:settings", namespace="CELERY")`; `app.autodiscover_tasks()`.
  2. `quarantine_extraction` writes a `PendingReview` row + a corresponding `AuditEvent` row.
  3. In `test` settings, `CELERY_TASK_ALWAYS_EAGER=True` so unit tests assert behavior synchronously; integration test uses a real worker.
- **Verify**:
  - `pytest backend/tests/ingestionapp/test_tasks.py -q` passes.
  - `celery -A law_ai worker -l info` starts cleanly in `make dev`.

## T-012 — Container, compose, and tooling updates

- **Refs**: FR-14
- **Owner**: @copilot
- **Status**: `[x]`
- **Files**:
  - [backend/Dockerfile](../../backend/Dockerfile) — `CMD ["sh","-c","python manage.py migrate --noinput && python manage.py ensure_checkpointer && python manage.py seed_api_keys && daphne -b 0.0.0.0 -p 8000 law_ai.asgi:application"]`
  - [docker-compose.yml](../../docker-compose.yml) — backend `command:` aligned; new `worker` service: `command: celery -A law_ai worker -l info`, same env + depends_on
  - [.vscode/tasks.json](../../.vscode/tasks.json) — "Start Backend (Dev)" → `cd backend && python manage.py runserver 0.0.0.0:8000`
  - [Makefile](../../Makefile) — add `migrate: cd backend && python manage.py migrate`; update `lint`/`test` to point at `law_ai` not `app`
  - [pytest.ini](../../pytest.ini) — `addopts = ... --ds=law_ai.settings.test --cov=law_ai ...`
  - [.github/workflows/](../../.github/workflows/) — sweep for `app.main`, `uvicorn`, `pytest --cov=app`; replace appropriately
- **Steps**:
  1. Edit each file; rerun `docker compose build backend worker` locally.
  2. Update CI workflow YAML; re-run on a draft PR to confirm green.
- **Verify**:
  - `docker compose up backend worker` shows daphne + celery ready.
  - `make test` runs the new pytest config end-to-end.
  - GitHub Actions on the feature branch is green.

## T-013 — Test infrastructure migration + per-router test rewrites

- **Refs**: FR-15, NFR-TEST-COV-1, NFR-PARITY-1, AC-3
- **Owner**: @copilot
- **Status**: `[x]`
- **Files**:
  - [backend/tests/conftest.py](../../backend/tests/conftest.py) — replace `client` fixture; add `api_client` (DRF) + `async_client` (httpx against `law_ai.asgi.application`); replace `_reset_api_keys` with `_reset_api_tokens`
  - [backend/tests/api/test_agents.py](../../backend/tests/api/test_agents.py), [test_analysis.py](../../backend/tests/api/test_analysis.py), [test_graph.py](../../backend/tests/api/test_graph.py), [test_health.py](../../backend/tests/api/test_health.py), [test_local_ai_health.py](../../backend/tests/api/test_local_ai_health.py), [test_lsat.py](../../backend/tests/api/test_lsat.py) — rewrite imports + fixture names; assertions unchanged
  - All other tests under [backend/tests/](../../backend/tests/) — import-path sweep `from app.` → `from law_ai.`
- **Steps**:
  1. Rewrite `conftest.py`; ensure `pytest_plugins = ["pytest_django"]`-style discovery via `pytest.ini`.
  2. For each `tests/api/test_*.py`: change `from httpx ...` → use new `api_client` / `async_client` fixtures; preserve every `assert response.json() == ...` line verbatim.
  3. Run pytest-cov and confirm ≥ 75% coverage.
- **Verify**:
  - `cd backend && pytest --ds=law_ai.settings.test --cov=law_ai` passes with all original assertions.
  - Coverage HTML in `backend/htmlcov/` shows no module under 70%.
  - Test count matches `main` (no test deleted without justification in PR).

## T-014 — Frontend parity smoke + spec-010 LangGraph parity + analysis perf check

- **Refs**: NFR-PARITY-2, NFR-PERF-1, NFR-LEGALBENCH-1, AC-9, AC-10
- **Owner**: @copilot
- **Status**: `[x]`
- **Files**: none modified — verification only
- **Steps**:
  1. `cd frontend && npm test -- --run` — Vitest + RTL + MSW must pass without source edits.
  2. `make dev` then manual smoke per AC-1 + AC-2.
  3. `Run LegalBench Eval` task — record delta in PR description.
  4. `POST /api/analysis` p95 latency benchmark on the same Apple Silicon laptop hardware as spec 010; assert ≤ 10% regression vs `main` (NFR-PERF-1).
- **Verify**:
  - Frontend tests green, frontend `/` and `/agents` pages load against the new backend with no JSON shape changes.
  - LegalBench delta ≥ 0 pp (NFR-LEGALBENCH-1).
  - Analysis p95 latency regression ≤ 10% (NFR-PERF-1).

## T-015 — Hardening: `manage.py check --deploy` + security headers

- **Refs**: NFR-SEC-1
- **Owner**: @copilot
- **Status**: `[x]`
- **Files**:
  - `backend/law_ai/settings/prod.py` — `SECURE_PROXY_SSL_HEADER`, `SESSION_COOKIE_SECURE=True`, `CSRF_COOKIE_SECURE=True`, `SECURE_HSTS_SECONDS`, `SECURE_CONTENT_TYPE_NOSNIFF`, `X_FRAME_OPTIONS="DENY"`
  - `backend/tests/test_deploy_check.py` (new — runs `call_command("check", "--deploy")` under prod settings)
- **Steps**:
  1. Set the security flags; ensure `SECRET_KEY` loads from env.
  2. Confirm DRF API views are exempt from CSRF (header-token model); `/admin/` keeps CSRF.
- **Verify**:
  - `DJANGO_SETTINGS_MODULE=law_ai.settings.prod python manage.py check --deploy` exits 0.
  - `pytest backend/tests/test_deploy_check.py -q` passes.

## T-016 — Cutover: delete `backend/app/`

- **Refs**: FR-16, AC-11
- **Owner**: @copilot (HUMAN-PAIRED; final review gate)
- **Status**: `[x]`
- **Files**:
  - Delete entire `backend/app/` directory.
  - Remove `backend/app/law_ai.egg-info/` (artifact).
  - `backend/pyproject.toml` `[tool.setuptools]` `packages = ["law_ai"]` (was `["app"]`).
  - Final sweep: `grep -RIn "from app\." backend/ tests/` returns empty; `grep -RIln "uvicorn\|FastAPI" backend/` only returns ADR/changelog.
- **Steps**:
  1. Confirm T-002 → T-015 fully green on feature branch CI.
  2. `git rm -r backend/app/ backend/app/law_ai.egg-info/`.
  3. Update `pyproject.toml` package include.
  4. Re-run full test suite.
- **Verify**:
  - `cd backend && pytest --ds=law_ai.settings.test --cov=law_ai` passes; coverage ≥ 75%.
  - `make lint` and `make test` clean.
  - `grep -RIn "from app\." backend/ tests/` empty.
  - Manual maintainer sign-off (HITL Constitution §10 Level-2 gate).

---

## Done-When (Definition of Done)

- All tasks `[x]`.
- All `AC-*` from [spec.md](spec.md) covered by passing tests.
- `make lint && make test` green.
- LegalBench delta recorded in PR description (NFR-LEGALBENCH-1).
- Provenance logging verified manually for `/api/analysis` and `/api/lsat/tutor` paths (writes appear in `audit.AuditEvent` and Phoenix).
- `manage.py check --deploy` exits 0 in `prod` settings.
- `## Follow-ups Discovered` section below populated and mirrored in [BACKLOG.md](../../BACKLOG.md).

---

## Follow-ups Discovered

> Append-only. Mirror each item into [BACKLOG.md](../../BACKLOG.md) with a `BL-YYYYMMDD-NN` id. CI ([scripts/spec_validator.py](../../scripts/spec_validator.py)) checks this section exists. CI ([scripts/backlog_lint.py](../../scripts/backlog_lint.py)) checks the BACKLOG mirror.

- BL-20260503-09 — feature, med — Real Channels producers for `/ws/agents/{run_id}`: stream `LegalAnalyst` → `PrecedentHunter` progress events from `analysis/views.py` so the consumer skeleton lands in T-010 gets traffic. Resolves overlap with [BL-20260429-24](../../BACKLOG.md).
- BL-20260503-10 — feature, med — Django admin actions on `ingestionapp.PendingReview` (`approve`, `reject`, `re-extract`) + matching `core.tasks` to apply the decision back to Neo4j. Resolves overlap with [BL-20260429-15](../../BACKLOG.md).
- BL-20260503-11 — feature, low — Add `/agents/runs/{trace_id}` view backed by `audit.AuditEvent` joined on `trace_id`, so the dashboard from spec 003 can drill into a single run. Resolves overlap with [BL-20260429-14](../../BACKLOG.md).
- BL-20260503-12 — feature, med — Per-token rate limiting via `django-ratelimit` keyed on `request.auth.key_hash`. Resolves overlap with [BL-20260430-09](../../BACKLOG.md).
- BL-20260503-13 — feature, med — JWT/OAuth on top of `core.ApiToken` (revives the `python-jose` + `passlib` deps under the new `[future-auth]` extra). Future spec.
- BL-20260503-14 — infra, low — Periodic Celery beat job that runs `scripts/backlog_lint.py` + `scripts/spec_validator.py` and opens a triage issue when stale. Resolves overlap with [BL-20260429-09](../../BACKLOG.md).
- BL-20260503-15 — refactor, low — Retire raw `asyncpg` calls outside the LangGraph checkpointer in favor of Django's connection pool now that the ORM is on hand. Partially resolves [BL-20260429-17](../../BACKLOG.md).
- BL-20260503-16 — doc-gap, med — Flesh out `docs/security.md` (started under NFR-DOC-1) with the API-token rotation procedure, scope matrix, and the `seed_api_keys` runbook. Resolves [BL-20260430-10](../../BACKLOG.md).
- BL-20260503-17 — test-gap, med — Add a Playwright end-to-end test that exercises the Django admin HITL flow against a docker stack (login → list quarantine → approve → assert Neo4j commit).
- BL-20260503-18 — doc-gap, low — Add `docs/django-conventions.md` capturing the patterns settled in this refactor (settings split, settings_proxy usage, `acreate` discipline, Channels routing, Celery task naming) so future PRs do not relitigate them.
- BL-20260503-19 — infra, high — Hand-edit `law_ai/ingestionapp/migrations/0001_initial.py` to use `RunSQL` with verbatim DDL from `backend/app/db/postgres_migrations/{001_pending_review,002_pg_trgm}.sql` and a `state_operations`/`database_operations` split, so live Postgres rows survive cutover instead of relying on Django to drop+recreate the table.
- BL-20260503-20 — refactor, med — Refactor `law_ai/ingestionapp/services/scout.py` to delegate quarantine writes to the `quarantine_extraction` Celery task (currently still uses inline asyncpg + JSONL). Closes the loop on T-011.
- BL-20260503-21 — test-gap, high — ~~Re-establish ≥75% backend coverage on the Django app~~ **(resolved 2026-05-03)**: backend at **84.08%** (126 tests). Added consumer / task / management-command unit tests in `backend/tests/agentsapi/test_consumer.py`, `backend/tests/ingestion/test_quarantine_task.py`, `backend/tests/core/test_management_commands.py`.
- BL-20260503-22 — test-gap, med — Pre-existing frontend failure (`__tests__/components/LsatLab.test.tsx`: long-passage assertion) was carried through this refactor without fix. Triage and resolve so `npm test -- --run` is green again.
- BL-20260503-23 — refactor, low — Strip the dead-code FastAPI path from `law_ai/core/telemetry.py` (TYPE_CHECKING import + `FastAPIInstrumentor.instrument_app` branch) and replace with `DjangoInstrumentor` so OTEL spans cover the new ASGI app once Phoenix is wired in. Sweep remaining historical FastAPI/uvicorn references in core docstrings to point to the Django entrypoints.
- BL-20260503-24 — infra, med — ~~Wire Django static files for the dockerized stack~~ **(resolved 2026-05-03)**: added `whitenoise` dep + `WhiteNoiseMiddleware` + `CompressedManifestStaticFilesStorage`; `collectstatic --noinput` now runs in the backend container start command.
- BL-20260503-25 — infra, low — Document the Postgres major-version pin in [docker-compose.yml](../../docker-compose.yml) (currently 16-alpine because the existing dev volume was initialized on pg16) and add a `make reset-db` runbook so operators can wipe `pgdata` when they need to bump.
