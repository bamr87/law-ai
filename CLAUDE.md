# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Canonical guide

[AGENTS.md](AGENTS.md) is the single source of truth for coding standards, tech stack, project structure, and quality gates. Read it before non-trivial work. This file only captures the operational essentials and the things that are easy to get wrong. Do not duplicate AGENTS.md content here.

> Orchestration policy: GitHub Copilot and Claude Code are both sanctioned dev surfaces ([AGENTS.md](AGENTS.md) § "Development Orchestration", [docs/constitution.md](docs/constitution.md) §1). Cursor, Continue.dev, Aider, Codex, and Gemini CLI remain forbidden. Claude is a **dev-time** tool only — the product runtime LLM stays Ollama / local-first; never wire Claude in as the product LLM.

## Docker-first (the rule you will trip on)

Every dev/test/lint/typecheck/eval command runs **inside Docker via `make`** (which wraps `docker compose run --rm <service>`). Do **not** run `pytest`, `npm test`, `python manage.py`, `pip install`, `ruff`, `mypy`, `black`, or `npm install` on the host. The only sanctioned host commands are `make …`, `docker compose …`, `python3 scripts/spec_validator.py`, `python3 scripts/backlog_lint.py`, and `git`/`gh`. The `host-*` make targets exist for emergency fallback only — never use them in CI, prompts, or docs.

## Common commands

| Goal | Command |
|------|---------|
| Start full stack | `make dev` (frontend :3000, API :8000/docs) |
| Stop / logs / status | `make down` · `make logs` · `make ps` |
| Attach a debugger | `make debug` (backend 5678, worker 5679, frontend 9229) |
| Backend / frontend shell | `make shell-backend` · `make shell-frontend` |
| Django management cmd | `make manage CMD='migrate'` |
| Migrations + checkpointer | `make migrate` |
| All tests | `make test` (backend pytest + frontend vitest) |
| Backend unit tests | `make test-backend` (excludes `integration` + `legalbench`) |
| Frontend tests | `make test-frontend` |
| Integration (real DBs) | `make test-integration` (spins up neo4j/postgres/redis) |
| LegalBench eval | `make test-legalbench` |
| Coverage | `make test-coverage` → `htmlcov/`, `frontend/coverage/` |
| Lint / format / types | `make lint` · `make format` · `make typecheck` (mypy --strict + tsc) |
| Spec/backlog gates | `make lint-specs` (host stdlib, no container) |

**Run a single backend test** (the make targets run the whole suite):
```bash
docker compose run --rm backend pytest tests/agents/test_foo.py::test_bar -q
docker compose run --rm backend pytest -k "citation" -q        # keyword filter
docker compose run --rm backend pytest -m integration -v       # by marker
```

**Two separate pytest configs** — don't confuse them:
- Root [pytest.ini](pytest.ini) drives the repo-wide `tests/` orchestrator (structure, configs, docs, spec/backlog lint; markers `smoke`/`specs`/`backend`/`frontend`). It deliberately does *not* collect `backend/`/`frontend/`.
- [backend/pyproject.toml](backend/pyproject.toml) drives the real backend suite under `backend/tests/` with `--cov-fail-under=75` and markers `unit`/`integration`/`legalbench` (`asyncio_mode=auto`).

## Architecture (big picture)

Multi-agent legal-intelligence platform. Django 5 (ASGI/daphne) + DRF + Channels + Celery backend; Next.js 15 (App Router) frontend; Neo4j knowledge graph + Postgres + Redis; **Ollama is the product runtime LLM** (local-first, open-weights — independent from whatever agent edits the code).

Backend lives in `backend/lawgraph/` (the Django project package). Each Django app owns one `/api/*` router:
- `agents_runtime/` — all agent logic: `crews/` (CrewAI), `graphs/` (LangGraph workflows), `tools/` (Neo4j, CourtListener, GraphRAG), `prompts/` (versioned `*.v<N>.md`).
- `agentsapi/` — DRF routers + Channels consumers at `/api/agents/*` (real-time agent streaming over WebSockets).
- `analysis/` `/api/analysis`, `graph/` `/api/graph/*`, `lsat/` `/api/lsat/*` — feature backends.
- `ingestionapp/` — quarantine ORM models + Celery ingestion tasks + source clients.
- `core/` — config, security, Neo4j driver, `provenance`, telemetry. `audit/` — `AuditEvent` model + provenance writers. `eval/` — LegalBench harness. `settings/` — split base/dev/test/prod.

Frontend `frontend/`: `app/` (App Router pages per feature), `components/` (GraphViewer, AgentTrace, …), `lib/` (typed API client), `mocks/` (MSW), `__tests__/` (Vitest + RTL). Graph data flows client → typed API route → backend → Neo4j; **never query Neo4j from the client**.

Deeper detail: [docs/architecture.md](docs/architecture.md), [docs/agent-roles.md](docs/agent-roles.md), [docs/data-model.md](docs/data-model.md).

## Spec-driven workflow + the continuous-evolution gate

Non-trivial changes follow AO-SDLC: a spec package under `specs/NNN-feature-slug/{spec,plan,tasks}.md` via the [prompts/](prompts/) chain (`specify → clarify → plan → tasks → implement`; `evolve` for autonomous runs). CI enforces consistency through [scripts/spec_validator.py](scripts/spec_validator.py).

Every `/implement` cycle MUST close the loop ([docs/constitution.md](docs/constitution.md) §11), and `make lint-specs` enforces it:
- `tasks.md` ends with a populated `## Follow-ups Discovered` section.
- Each follow-up is mirrored into [BACKLOG.md](BACKLOG.md) as `BL-YYYYMMDD-NN`.
- The PR description copies the new BACKLOG bullets.

## Non-negotiables

- Log every LLM call, tool use, and retrieval through `core.provenance` — never bypass the audit layer.
- Graph nodes always carry `source` + `confidence`; never hard-delete (soft-delete with `archived_at`).
- HITL approval gates are required on ingestion and high-stakes analysis (`ENABLE_HUMAN_APPROVAL_GATES`).
- New agents implement `run(input: dict) -> dict` (Pydantic output) and ship a test under `backend/tests/agents/`.
- Autonomy targets (`make autonomy-run KIND=… SOURCE=…`) require `AUTONOMY_ENABLED=true` and a source in `AUTONOMY_ALLOWED_SOURCES`.
