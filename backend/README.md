# Law AI — Backend

Django 5 (ASGI via daphne) + DRF + Channels + Celery backend for the Law AI
legal intelligence platform. Agent logic (CrewAI crews, LangGraph workflows,
versioned prompts) lives under `law_ai/agents_runtime/`; each other Django
app under `law_ai/` owns one `/api/*` router. See
[docs/architecture.md](../docs/architecture.md) for the full breakdown.

See the repo root [README.md](../README.md), [AGENTS.md](../AGENTS.md), and
[CLAUDE.md](../CLAUDE.md) for project-wide documentation, architecture, and
the Docker-first workflow — every command below runs in a container, never
directly on the host.

## Quick start

```bash
# From repo root — starts the full stack (backend :8000, frontend :3000)
make dev

# Django management commands go through the same wrapper
make manage CMD='migrate'
make shell-backend    # drop into a shell inside the backend container
```

The container's actual boot command (see [Dockerfile](Dockerfile)) is
`daphne -b 0.0.0.0 -p 8000 law_ai.asgi:application`, run after migrations
and `ensure_checkpointer` — there is no `uvicorn` or `app.main:app` here.

## Tests

```bash
# From repo root
make test-backend                                             # full backend suite (excludes integration + legalbench)
docker compose run --rm backend pytest tests/agents/test_foo.py -q  # single test
docker compose run --rm backend pytest -k "citation" -q       # keyword filter
make test-integration                                          # against real Neo4j/Postgres/Redis
make test-legalbench                                            # LegalBench eval (pinned to Ollama)
make test-coverage                                              # --cov=law_ai, htmlcov/
```

`backend/pyproject.toml` drives this suite (`--cov-fail-under=75`, markers
`unit`/`integration`/`legalbench`, `asyncio_mode=auto`) — distinct from the
repo-root [tests/](../tests) orchestrator described in [tests/README.md](../tests/README.md).
