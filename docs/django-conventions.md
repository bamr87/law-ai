# Django Conventions

> Closes [BL-20260503-18](../BACKLOG.md). Conventions for working inside the `backend/law_ai/` Django package introduced by [ADR 0001](adr/0001-adopt-django-backend.md). Read alongside [docs/architecture.md](architecture.md) and [AGENTS.md](../AGENTS.md) §"Coding Standards".

## 1. Settings split

Settings live in [backend/law_ai/settings/](../backend/law_ai/settings/), one module per environment:

| Module                     | Loaded by                                        | Purpose |
|----------------------------|--------------------------------------------------|---------|
| `settings/base.py`         | every other module via `from .base import *`     | Shared defaults; reads env via `django-environ` (`Env(...)` declarations at the top). Also where `LLM_PROVIDER_CHAIN` / `LSAT_LLM_PROVIDER` and the Claude/Ollama credential settings are declared (spec 034/035). |
| `settings/dev.py`          | `manage.py runserver`, `make dev`                | `DEBUG=True`, `ENVIRONMENT="development"`, `ALLOWED_HOSTS=["*"]`. Nothing else — CORS (a fixed 2-origin allowlist), DRF throttling, and the API-key default-open fallback are all inherited unchanged from `base.py`; see [docs/security.md](security.md). |
| `settings/test.py`         | `pytest.ini` `--ds=law_ai.settings.test`       | SQLite in-memory DB by default (override `DATABASE_URL` for Postgres-backed integration tests), in-process Celery (`task_always_eager`), in-memory Channels layer, DRF throttling relaxed to `100000/min`. **Also hard-blanks every LLM provider credential** — `CLAUDE_CODE_OAUTH_TOKEN=""`, `ANTHROPIC_API_KEY=""`, `OLLAMA_BASE_URL` pointed at a closed port — so `make test` can never issue a real, billed Claude call or block on a live Ollama, even if those creds are set in your shell/`.env`. |
| `settings/prod.py`         | `DJANGO_SETTINGS_MODULE=law_ai.settings.prod`  | `DEBUG=False`, `ENVIRONMENT="production"`, plus the `SECURE_*`/HSTS/`X-Frame-Options` hardening block (see [docs/security.md](security.md)). Whitenoise's compressed-manifest static storage is actually a `base.py` default shared by *every* environment, not prod-specific. There is no Django cache backend (`CACHES`) configured anywhere yet, in any environment. |

**Rules:**

- Never read `os.environ` outside `base.py`. All reads go through the `Env(...)` declaration at the top of `base.py` so types and defaults are explicit.
- Do not import from `dev.py` / `prod.py` from application code — only `law_ai.core.settings_proxy` (see §2).
- Adding a new setting: declare it in `Env(...)`, assign it in `base.py`, override per-env only when the value must differ.

## 2. `settings_proxy` usage

`law_ai.core.settings_proxy` is a thin lazy wrapper that lets domain modules read settings without importing `django.conf` directly. This keeps services unit-testable without booting Django.

```python
from law_ai.core.settings_proxy import settings_proxy as settings

def ollama_configured() -> bool:
    return bool(str(getattr(settings, "OLLAMA_BASE_URL", "") or "").strip())
```

(This mirrors the real pattern in `law_ai.core.llm.providers.OllamaProvider` — there is no wrapping client class; providers read `settings_proxy` directly and make their own `httpx` calls.)

- Use `settings_proxy` in **services, agents, tools, tasks** — anywhere outside Django's HTTP/admin/ORM layer.
- Use `from django.conf import settings` only inside views, middleware, management commands, or migrations.
- Never cache the proxy values at import time (`X = settings.FOO` at module top); always read inside the function so test overrides via `override_settings` apply.
- Import it as `settings_proxy as settings` — `settings_proxy` exports only the `settings_proxy` instance, not a bare `settings` name. All real call sites in the codebase use this alias.

## 3. Async ORM discipline

Django 5's ORM is async-capable, but **this codebase does not currently use the async-native entry points anywhere** — a repo-wide search for `.acreate(`, `.asave(`, `.aget(`, or `async for ... in Model.objects` outside tests returns zero hits. The established pattern instead is to keep the ORM out of async code paths entirely:

- **`core/provenance.py` is the reference case.** Its `_persist()` helper explicitly detects whether it's running inside an event loop (`_in_async_context()`) and, if so, *skips the direct Django ORM write* — the comment notes plain ORM calls raise `SynchronousOnlyOperation` there — and instead dispatches to the `persist_audit_event` Celery task, which runs in a genuine sync worker context.
- **`ingestionapp/services/approval.py::commit_approved_review` is the other real pattern**: `await sync_to_async(review.save)(update_fields=[...])` — a one-off `sync_to_async` wrap around a single-row save, called from async code. This is the codebase's actual convention for a single-row write that must happen from within an async function, not `await instance.asave()`.
- **If you're writing new async code that needs the ORM**: prefer handing the write to a Celery task (matches `provenance.py`) when the caller doesn't need the result inline; fall back to `sync_to_async(...)` around a single call (matches `approval.py`) when it does. `await Model.objects.acreate(...)` / `await instance.asave()` / `await Model.objects.aget(...)` are valid Django 5 APIs and fine to introduce, but doing so establishes a *new* pattern for this codebase, not an existing one — don't assume they're already the norm.
- **Multi-row transactions**: wrap in `sync_to_async` because `transaction.atomic` is sync-only. Keep the transaction body small.
- **No async signals**: `post_save` / `pre_save` handlers are sync; do heavy work via Celery instead of in a signal.
- **Connection lifetime**: if you do call the ORM's async entry points directly from a long-running async task or Channels consumer, close the connection in teardown (`await connection.aclose()`) to avoid leaks — but note no code in this repo does this today, because (per above) nothing calls the ORM directly from async context; the Celery-dispatch pattern sidesteps the question by never opening an async-context connection in the first place.

LangGraph's checkpointer uses raw `asyncpg`/`psycopg` outside the ORM (`AsyncPostgresSaver.from_conn_string`). That is the only sanctioned non-ORM path; everything else routes through Django.

## 4. Channels routing

WebSocket routing is split across two files:

- [backend/law_ai/asgi.py](../backend/law_ai/asgi.py) builds the `ProtocolTypeRouter` and imports `websocket_urlpatterns`.
- [backend/law_ai/agentsapi/routing.py](../backend/law_ai/agentsapi/routing.py) is where the actual `re_path` list lives — **add new consumers here**, not inline in `asgi.py`.

```python
# asgi.py
from law_ai.agentsapi.routing import websocket_urlpatterns

application = ProtocolTypeRouter({
    "http": django_asgi_app,
    "websocket": AuthMiddlewareStack(URLRouter(websocket_urlpatterns)),
})
```

```python
# agentsapi/routing.py
websocket_urlpatterns = [
    re_path(r"^ws/agents/(?P<run_id>[\w\-]+)/?$", AgentRunConsumer.as_asgi()),
]
```

- One consumer per top-level resource. Consumers live next to their REST router (e.g. `law_ai.agentsapi.consumers.AgentRunConsumer`).
- **Auth is not `self.scope["user"]`.** `AgentRunConsumer` doesn't use Channels' session/user auth at all — it reads `?api_key=`/`?token=` from the query string (browsers can't set headers on a WS handshake) or an `X-API-Key` handshake header for non-browser clients, and compares it against `AGENT_API_KEY` directly. With that setting unset, the socket accepts any connection. See [docs/security.md](security.md#scope-matrix) for the full picture, including that per-router keys (`ANALYSIS_API_KEY`, etc.) don't apply to WS connections.
- Always use channel groups for fan-out (`await self.channel_layer.group_add(...)`) so multiple subscribers see the same trace stream.
- Never block the consumer loop on Neo4j or LLM calls — fan out to a Celery task and stream results back via the channel layer.

## 5. Celery task naming

Celery app: `law_ai.celery.app` (`Celery("law_ai")`).

- **Module location**: tasks live in `<app>/tasks.py` (e.g. `law_ai.ingestionapp.tasks`, `law_ai.core.tasks`). One file per Django app.
- **Naming**: the `name=` argument is required, dotted, and lowercase. Real examples: `law_ai.core.persist_audit_event`, `law_ai.core.tasks.autonomy_cycle`, `law_ai.ingestionapp.quarantine_extraction`, `law_ai.ingestionapp.commit_approved_reviews`. Note the prefix isn't perfectly uniform yet — some names include the `.tasks` module segment, some don't — so match whichever pattern the file you're editing already uses rather than inventing a third variant.

```python
@shared_task(name="law_ai.ingestionapp.quarantine_extraction", ignore_result=True)
def quarantine_extraction(payload: dict) -> str:
    ...
```

- **`ignore_result`**: set `True` for fire-and-forget tasks (ingestion, audit fallback writes) and `False` when a caller needs the return value (e.g. `autonomy_cycle`, invoked by the beat schedule and by `make autonomy-run`).
- **Queues**: there is currently **one** worker and **two** queues, not a per-family scheme — `docker-compose.yml`'s `worker` service runs `celery -A law_ai worker --beat -l info -Q autonomy,celery`. No task in the codebase passes a `queue=` kwarg to `@shared_task`; everything not explicitly routed to `autonomy` lands on the default `celery` queue. A per-family queue split (`ingestion`, `analysis`, `audit`, …) is a reasonable future direction but is not implemented — don't write code that assumes it exists.
- **Idempotency**: every task body must be safe to re-run. The real tasks do this with `update_or_create` (`quarantine_extraction`) or by explicitly skipping already-committed rows (`commit_approved_reviews`, per its docstring). Celery retries are on by default.
- **No ORM transactions inside `apply_async` callbacks** — write the row first, dispatch the task with the row's PK, let the task fetch.

## 6. Migration gotchas

These come from real incidents shipped against `backend/law_ai/`:

1. **SQLite test DB vs. Postgres prod DDL.** `pytest.ini` runs migrations against SQLite in-memory. Postgres-only DDL (`jsonb`, `timestamptz`, `pg_trgm`, multi-statement `RunSQL`) breaks `migrate` during test setup. **Workaround**: gate inside a `RunPython` op on `schema_editor.connection.vendor == "postgresql"` and provide a portable SQLite-compatible DDL fallback. Reference example: [backend/law_ai/ingestionapp/migrations/0001_initial.py](../backend/law_ai/ingestionapp/migrations/0001_initial.py).
2. **SQLite refuses multi-statement strings in `cursor.execute`.** Always split on `;` before calling `schema_editor.execute(stmt)` even when targeting both backends from one DDL blob.
3. **`RunPython`'s `apps` arg uses `from_state.apps`** — the model declared in the *same* migration's `state_operations` is **not** yet visible. Don't call `apps.get_model("ingestionapp", "PendingReview")` from a `RunPython` paired via `SeparateDatabaseAndState` with a `CreateModel`. Use raw SQL or import the real model class instead.
4. **Adopting a legacy raw-SQL table without dropping rows**: wrap with `migrations.SeparateDatabaseAndState(state_operations=[CreateModel(...)], database_operations=[RunPython(_create_via_legacy_ddl, _drop)])` and make the legacy DDL idempotent (`CREATE TABLE IF NOT EXISTS`, `ADD COLUMN IF NOT EXISTS`).
5. **LangGraph checkpointer schema isolation is only half-wired.** `LANGGRAPH_CHECKPOINTER_SCHEMA` (default `"langgraph"`) exists, and `make migrate` runs `manage.py ensure_checkpointer`, which does `CREATE SCHEMA IF NOT EXISTS "langgraph"`. But `build_checkpointer()` ([agents_runtime/graphs/runtime.py](../backend/law_ai/agents_runtime/graphs/runtime.py)) calls `AsyncPostgresSaver.from_conn_string(settings.POSTGRES_URL)` with **no schema qualifier** (no `options=-c search_path=langgraph` on the connection string), so `AsyncPostgresSaver.setup()` creates its tables in whatever schema the connection defaults to — `public`. `docker-compose.yml` points `POSTGRES_URL` and `DATABASE_URL` at the same `law_ai` database, so today checkpoint tables and Django ORM tables land in the same `public` schema: the collision this setup is meant to prevent isn't actually prevented yet. Treat this as a known latent risk, not a solved problem, when adding new Django models — check for name collisions with LangGraph's `checkpoints`/`checkpoint_blobs`/`checkpoint_writes`/`checkpoint_migrations` tables manually.

## 7. Code review checklist (Django-specific)

- [ ] New settings declared in `Env(...)` and assigned in `base.py`.
- [ ] No `os.environ` reads outside `settings/base.py`.
- [ ] Domain code uses `law_ai.core.settings_proxy.settings_proxy` (imported `as settings`), not `django.conf.settings`.
- [ ] Async code doesn't call the ORM directly without either a Celery dispatch or an explicit `sync_to_async` wrap (see §3) — and if it introduces `acreate`/`asave`/`aget`, that's a new pattern for this codebase, called out as such in the PR.
- [ ] New WS consumers attached to a channel group; no blocking I/O inside the consumer; auth reviewed against the real query-string/header check in §4, not an assumed `scope["user"]`.
- [ ] New Celery tasks have an explicit, correctly-prefixed `name=` and an idempotent body.
- [ ] Migrations gate Postgres-only DDL on `vendor == "postgresql"`.
- [ ] `python manage.py check --deploy` still exits 0.

## Related docs

- [ADR 0001](adr/0001-adopt-django-backend.md) — why Django.
- [docs/architecture.md](architecture.md) — where each layer lives.
- [docs/security.md](security.md) — token + scope details for views and consumers.
- [docs/local-ai.md](local-ai.md) — Channels + Celery interplay with the LangGraph runtime.
