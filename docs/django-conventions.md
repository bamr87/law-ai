# Django Conventions

> Closes [BL-20260503-18](../BACKLOG.md). Conventions for working inside the `backend/lawgraph/` Django package introduced by [ADR 0001](adr/0001-adopt-django-backend.md). Read alongside [docs/architecture.md](architecture.md) and [AGENTS.md](../AGENTS.md) §"Coding Standards".

## 1. Settings split

Settings live in [backend/lawgraph/settings/](../backend/lawgraph/settings/), one module per environment:

| Module                     | Loaded by                                        | Purpose |
|----------------------------|--------------------------------------------------|---------|
| `settings/base.py`         | every other module via `from .base import *`     | Shared defaults; reads env via `django-environ` (`Env(...)` declarations at the top). |
| `settings/dev.py`          | `manage.py runserver`, `make dev`                | DEBUG=True, console email, permissive CORS, default-open API. |
| `settings/test.py`         | `pytest.ini` `--ds=lawgraph.settings.test`       | SQLite in-memory DB, in-process Celery (`task_always_eager`), no telemetry. |
| `settings/prod.py`         | `DJANGO_SETTINGS_MODULE=lawgraph.settings.prod`  | DEBUG=False, `SECURE_*` middleware, whitenoise compressed manifest, Redis cache. |

**Rules:**

- Never read `os.environ` outside `base.py`. All reads go through the `Env(...)` declaration at the top of `base.py` so types and defaults are explicit.
- Do not import from `dev.py` / `prod.py` from application code — only `lawgraph.core.settings_proxy` (see §2).
- Adding a new setting: declare it in `Env(...)`, assign it in `base.py`, override per-env only when the value must differ.

## 2. `settings_proxy` usage

`lawgraph.core.settings_proxy` is a thin lazy wrapper that lets domain modules read settings without importing `django.conf` directly. This keeps services unit-testable without booting Django.

```python
from lawgraph.core.settings_proxy import settings

def build_client() -> OllamaClient:
    return OllamaClient(base_url=settings.OLLAMA_BASE_URL, timeout=settings.OLLAMA_REQUEST_TIMEOUT_S)
```

- Use `settings_proxy` in **services, agents, tools, tasks** — anywhere outside Django's HTTP/admin/ORM layer.
- Use `from django.conf import settings` only inside views, middleware, management commands, or migrations.
- Never cache the proxy values at import time (`X = settings.FOO` at module top); always read inside the function so test overrides via `override_settings` apply.

## 3. Async ORM discipline

Django 5's ORM is async-capable but has sharp edges. Conventions:

- **Single-row writes**: use `await Model.objects.acreate(...)`, `await instance.asave()`, `await Model.objects.aget(pk=...)`. Never wrap a sync call in `sync_to_async` for a single-row op.
- **Querysets**: use the async iteration protocol (`async for row in Model.objects.filter(...)`). Do not call `list(qs)` in async code.
- **Multi-row transactions**: wrap in `sync_to_async` because `transaction.atomic` is sync-only today. Keep the transaction body small.
- **No async signals**: `post_save` / `pre_save` handlers are sync; do heavy work via Celery instead of in a signal.
- **Connection lifetime**: Django's async ORM uses one connection per task; long-running async tasks (Celery, Channels consumers) **must** call `await connection.aclose()` in their teardown to avoid connection leaks.

LangGraph's checkpointer uses raw `asyncpg` outside the ORM. That is the only sanctioned non-ORM path; everything else routes through Django. [BL-20260503-15](../BACKLOG.md) tracks retiring the remaining raw `asyncpg` callers.

## 4. Channels routing

WebSocket routing lives in [backend/lawgraph/asgi.py](../backend/lawgraph/asgi.py). The pattern:

```python
application = ProtocolTypeRouter({
    "http": django_asgi_app,
    "websocket": AuthMiddlewareStack(
        URLRouter([
            re_path(r"^ws/agents/(?P<run_id>[\w-]+)/$", AgentRunConsumer.as_asgi()),
            # add new consumers here
        ])
    ),
})
```

- One consumer per top-level resource. Consumers live next to their REST router (e.g. `lawgraph.agentsapi.consumers.AgentRunConsumer`).
- Auth: WS connections must call `self.scope["user"]` / API-key middleware just like HTTP. See [docs/security.md](security.md).
- Always use channel groups for fan-out (`await self.channel_layer.group_add(...)`) so multiple subscribers see the same trace stream.
- Never block the consumer loop on Neo4j or LLM calls — fan out to a Celery task and stream results back via the channel layer.

## 5. Celery task naming

Celery app: `lawgraph.celery.app` (`Celery("lawgraph")`).

- **Module location**: tasks live in `<app>/tasks.py` (e.g. `lawgraph.ingestionapp.tasks`, `lawgraph.audit.tasks`). One file per Django app, no cross-app task imports.
- **Naming**: dotted, lowercase, verb-first. Example: `ingestionapp.quarantine_extraction`, `audit.flush_pending_events`. The `name=` argument is required so refactors don't silently rename queues.

```python
@shared_task(name="ingestionapp.quarantine_extraction", queue="ingestion")
def quarantine_extraction(payload: dict) -> str:
    ...
```

- **Queues**: declare a queue per task family (`ingestion`, `analysis`, `audit`, `default`). Workers in `docker-compose.yml` are pinned to specific queues so heavy ingestion never starves user-facing analysis traffic.
- **Idempotency**: every task body must be safe to re-run (use unique `(source, source_id)` keys, `update_or_create`, or explicit deduplication). Celery retries are on by default.
- **No ORM transactions inside `apply_async` callbacks** — write the row first, dispatch the task with the row's PK, let the task fetch.

## 6. Migration gotchas

These come from real incidents shipped against `backend/lawgraph/`:

1. **SQLite test DB vs. Postgres prod DDL.** `pytest.ini` runs migrations against SQLite in-memory. Postgres-only DDL (`jsonb`, `timestamptz`, `pg_trgm`, multi-statement `RunSQL`) breaks `migrate` during test setup. **Workaround**: gate inside a `RunPython` op on `schema_editor.connection.vendor == "postgresql"` and provide a portable SQLite-compatible DDL fallback. Reference example: [backend/lawgraph/ingestionapp/migrations/0001_initial.py](../backend/lawgraph/ingestionapp/migrations/0001_initial.py).
2. **SQLite refuses multi-statement strings in `cursor.execute`.** Always split on `;` before calling `schema_editor.execute(stmt)` even when targeting both backends from one DDL blob.
3. **`RunPython`'s `apps` arg uses `from_state.apps`** — the model declared in the *same* migration's `state_operations` is **not** yet visible. Don't call `apps.get_model("ingestionapp", "PendingReview")` from a `RunPython` paired via `SeparateDatabaseAndState` with a `CreateModel`. Use raw SQL or import the real model class instead.
4. **Adopting a legacy raw-SQL table without dropping rows**: wrap with `migrations.SeparateDatabaseAndState(state_operations=[CreateModel(...)], database_operations=[RunPython(_create_via_legacy_ddl, _drop)])` and make the legacy DDL idempotent (`CREATE TABLE IF NOT EXISTS`, `ADD COLUMN IF NOT EXISTS`).
5. **LangGraph checkpointer schema collision**: keep checkpointer DDL inside the `langgraph` Postgres schema (configured in `lawgraph.agents_runtime.checkpointer`) so Django migrations can never shadow it.

## 7. Code review checklist (Django-specific)

- [ ] New settings declared in `Env(...)` and assigned in `base.py`.
- [ ] No `os.environ` reads outside `settings/base.py`.
- [ ] Domain code uses `lawgraph.core.settings_proxy.settings`, not `django.conf.settings`.
- [ ] Async views/services use `acreate`/`asave`/`aget`, not `sync_to_async` for single rows.
- [ ] New WS consumers attached to a channel group; no blocking I/O inside the consumer.
- [ ] New Celery tasks have explicit `name=`, a queue, and idempotent bodies.
- [ ] Migrations gate Postgres-only DDL on `vendor == "postgresql"`.
- [ ] `python manage.py check --deploy` still exits 0.

## Related docs

- [ADR 0001](adr/0001-adopt-django-backend.md) — why Django.
- [docs/architecture.md](architecture.md) — where each layer lives.
- [docs/security.md](security.md) — token + scope details for views and consumers.
- [docs/local-ai.md](local-ai.md) — Channels + Celery interplay with the LangGraph runtime.
