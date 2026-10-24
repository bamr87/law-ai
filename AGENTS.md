<!-- kit: sdlc v0.1.0 · AGENTS.md is the CANONICAL agent instructions file (decision D4, UPS-AGENT-07/08). -->

# law-ai

> How to build Law AI — an open-source, agent-orchestrated legal-intelligence platform — with the exact commands, layout, rules and gates every agent and contributor follows.

## What this repo is

Law AI combines multi-agent workflows, a Neo4j knowledge graph with GraphRAG retrieval, and interactive visualizations to help lawyers and law students master legal content, plus an LSAT practice module (in-app and the static `lsat-static/` site). A change is **done** when it satisfies [docs/constitution.md](docs/constitution.md), every gate in [Evaluation & Quality Gates](#evaluation--quality-gates) passes in Docker, its follow-ups are mirrored into `BACKLOG.md`, and the nearest docs say what changed.

## Stack & commands

Commands run in Docker through the [Makefile](Makefile); every target is listed in [docs/reference/make-targets.md](docs/reference/make-targets.md) (generated).

```bash
git clone https://github.com/bamr87/law-ai.git && cd law-ai
cp .env.example .env     # add CLAUDE_CODE_OAUTH_TOKEN or ANTHROPIC_API_KEY, or run on local Ollama
make dev                 # full stack: frontend http://localhost:3000, API http://localhost:8000
make migrate             # Django + Neo4j migrations + LangGraph checkpointer (second terminal)
make test                # backend pytest + frontend vitest + lsat-static vitest, in containers
make lint                # ruff + black + eslint --fix, in containers
make typecheck           # mypy --strict (ratcheted) + tsc --noEmit, in containers
make lint-specs          # host: spec_validator, backlog_lint, ux_audit, test_evolve_audit
```

`make debug` opens debugpy 5678/5679 (backend/worker) and node inspect 9229 for [.vscode/launch.json](.vscode/launch.json). One backend test:

```bash
docker compose run --rm backend pytest tests/agents/test_foo.py::test_bar -q
docker compose run --rm backend pytest -k "citation" -q
```

Two pytest configs: root [pytest.ini](pytest.ini) drives the dependency-light `tests/` suite and never collects `backend/` or `frontend/`; [backend/pyproject.toml](backend/pyproject.toml) drives `backend/tests/` (`--cov-fail-under=75`, markers `unit`/`integration`/`legalbench`). Backend routes: [docs/reference/http-routes.md](docs/reference/http-routes.md) (generated).

## Layout

| Path | What lives there |
| --- | --- |
| `backend/` | `tests/`, `scripts/`, and the Django package `law_ai/`: `core/` (auth, Neo4j, `provenance`, `llm/` chain), `audit/`, `agents_runtime/` (`crews/`, `graphs/`, `tools/`, versioned `prompts/`), one `/api/*` app each (`agentsapi`, `analysis`, `graph`, `lsat`, `matters`, `ingestionapp`), `eval/` (LegalBench), `settings/` |
| `frontend/` | Next.js app: `app/`, `components/`, `lib/` (typed API client), `mocks/`, `__tests__/`, `e2e/` |
| `lsat-static/` | Serverless LSAT practice site (GitHub Pages), fed by `make lsat-export` |
| `lawmode/` | The imported bamr87/lawmode repo; keeps its own README and commands |
| `specs/`, `prompts/` | AO-SDLC spec packages `NNN-slug/{spec,plan,tasks}.md` and the phase prompts |
| `docs/` | Depth, one topic per file; index at [docs/README.md](docs/README.md); ADRs in `docs/adr/`; generated reference in `docs/reference/` |
| `scripts/`, `tools/`, `tests/` | Stdlib host tooling and generators, vendored fleet tools, the root structural suite |
| `infra/`, `docker-compose*.yml` | The local stack and its GPU, debug and observability overlays |
| `components/`, `features/`, `verify/`, `.factory/` | Fleet kits: feedback widget, feature index, verify scenarios, GitFactory blueprints |

Put new code in the matching directory; invent no top-level locations.

## Conventions

- **Backlog of record:** [BACKLOG.md](BACKLOG.md) — append-only `BL-YYYYMMDD-NN` items, declared in `.github/sdlc.yml`, linted by `scripts/backlog_lint.py`. Mint ids with `python3 scripts/next_backlog_id.py`; never delete an entry.
- **Spec-driven (AO-SDLC Level 2):** non-trivial work starts as a spec via [/specify](prompts/specify.md) → `/clarify` → `/plan` → `/tasks` → [/implement](prompts/implement.md); [/evolve](prompts/evolve.md) runs the loop unattended ([docs/ao-sdlc.md](docs/ao-sdlc.md), [docs/ao-sdlc-guide.md](docs/ao-sdlc-guide.md)).
- **Definition of Done:** the checklist in [.github/pull_request_template.md](.github/pull_request_template.md) — what and why, visual evidence, the gates you actually ran, and the new BACKLOG bullets.
- **Decisions:** ADRs in `docs/adr/NNNN-slug.md`, indexed in [docs/adr/README.md](docs/adr/README.md). Add one for anything hard to reverse.
- **Commits:** Conventional Commits (`feat fix docs style refactor test chore perf ci build`); the PR title is the squash subject. `CHANGELOG.md` is release-please's.
- **Branches:** `feature/`, `fix/`, `docs/`, `refactor/`, `test/` or `chore/` off `main`.
- **README-First, README-Last:** read the nearest `README.md` before changing a directory, and update it after.
- **Never:** push to `main` directly, commit secrets, suppress type errors (`# type: ignore`, `as any`, `@ts-ignore`), leave empty exception handlers, or hand-edit generated files: `docs/reference/*`, the `docs/README.md` index span, `frontend/__tests__/fixtures/api-schema.json` (`make manage CMD=export_api_schema`), `lsat-static/content.json` (`make lsat-export`), and `factory--*.yml` (GitFactory).

## Development Orchestration

The sanctioned AI development surfaces are **GitHub Copilot** (Chat modes, inline completions, the coding agent that takes issues assigned to `@copilot`, Code Review) and **Claude Code** (CLI, IDE extensions, Agent SDK). Both run the AO-SDLC chain from [prompts/](prompts/) and defer to this file through [.github/copilot-instructions.md](.github/copilot-instructions.md) and [CLAUDE.md](CLAUDE.md).

- **Forbidden in this repo:** Cursor, Continue.dev, Aider, Codex, Gemini CLI, or any other third-party coding agent, and their config files (`.cursorrules`, `.continuerc.json`, `.aider.conf.yml`, …). The only agent configs are `.github/copilot-instructions.md`, `*.instructions.md`, `CLAUDE.md`, `.claude/` and `.mcp.json`.
- **Dev-time MCP:** [.mcp.json](.mcp.json) wires `law-ai-postgres` (read-only SQL) and `law-ai-neo4j` (Cypher) to the running compose stack, with local compose default credentials. The product runtime takes no MCP dependency (constitution §1).
- **Two layers:** the tool that edits this code and the model that serves users are independent decisions.

## Docker-First Workflow

All development, testing, linting and one-off commands run inside Docker via `make` (`docker compose run --rm <service>`), so everyone shares the toolchain pinned in the Dockerfiles and `docker-compose.yml`. Never run `pytest`, `npm`, `python manage.py`, `pip install`, `ruff`, `mypy` or `black` for `backend/` or `frontend/` on the host. Sanctioned on the host: `make …`, `docker compose …`, `git`/`gh`, and the stdlib tooling — `scripts/spec_validator.py`, `scripts/backlog_lint.py`, `scripts/gen_*_reference.py`, `tools/unwrap-prose.py`, `tools/docs_index.py`, and the root `tests/` suite (`python3 -m pytest tests -m "not backend and not frontend" -q`, what CI's repo-structural job runs). The `host-*` targets are emergency fallbacks, never for CI, prompts or docs. For editor tooling, use a [.devcontainer/](.devcontainer/) configuration.

## Tech Stack (Non-Negotiable)

- **Backend:** Python 3.12+, Django 5 (ASGI via daphne) + DRF + Channels + Celery, Pydantic v2 domain layer, Neo4j Community + official driver, PostgreSQL + asyncpg, Redis, Eyecite + Blackstone (spaCy).
- **Agents:** plain async agent classes (`crewai` is declared but never imported; `crews/` is a naming holdover) and LangGraph `StateGraph`s on LangChain (core since spec 035). The chain has two sanctioned entry points, both writing the same `llm_call` event: `core.llm.agenerate`/`generate` for plain agent classes, `ChatProviderChain` (`core/llm/langchain.py`) for LangGraph nodes and LCEL ([docs/architecture.md](docs/architecture.md) § Technology Choices Rationale).
- **Runtime LLM:** `LLM_PROVIDER_CHAIN` — Claude (OAuth), Claude (`ANTHROPIC_API_KEY`), xAI Grok (subscription OAuth, inert until `make xai-login`; [ADR 0007](docs/adr/0007-xai-runtime-provider.md)), then local Ollama ([docs/llm-provider-chain.md](docs/llm-provider-chain.md)).
- **Not wired yet:** `chromadb` (declared, unused); the planned vector leg is a Neo4j vector index (BL-20260810-17).
- **Frontend:** Next.js App Router (Next 16; constitution §2 still says 15), strict TypeScript, Tailwind v4, Cytoscape.js, WebSockets, plain `fetch` in `frontend/lib/api.ts`. shadcn/ui is constitution-listed but not installed — read [docs/ui-ux.md](docs/ui-ux.md) and [ADR 0006](docs/adr/0006-first-party-design-system.md) before adding UI primitives or a palette. Re-add a removed dependency (`@xyflow/react`, TanStack Query) only in the commit that imports it.

## Principles and non-negotiables

- **Jurisprudential stance:** Thrasymachus' "justice is nothing else than the interest of the stronger" holds **descriptively, about our data** — the record is what the stronger parties got courts to say — and is **rejected normatively** as a goal: Law AI makes legal asymmetry visible and contestable, never launders or exploits it ([docs/philosophy.md](docs/philosophy.md), constitution §13). Ask of anything that ranks, scores or summarises authority: *who is the stronger here, and what does this feature do for them?*
- **Grounded, power-aware output:** ground every output in retrieved sources and citations; attribute every legal proposition to its issuing authority (court, jurisdiction, date, binding/persuasive); never present citation counts or centrality as correctness; never let "no results in our corpus" read as "no such law"; label asymmetry, do not filter by it.
- **Provider chain only:** databases are always local; model calls go through `law_ai.core.llm`, never a provider transport, and no vendor beyond Anthropic / xAI / Ollama without a constitution §1 amendment. `LLM_PROVIDER_CHAIN=ollama` is the only configuration that keeps prompt text on the host, and is **required** for data under a confidentiality obligation forbidding third-party processing.
- **Provenance:** log every agent decision, prompt, LLM call, tool call and retrieval through `core.provenance`.
- **HITL:** ingestion and high-stakes analysis require approval gates (`ENABLE_HUMAN_APPROVAL_GATES`); ocrmd-scanned pages take the same gates, and the embedded scanner never calls a model ([docs/architecture.md](docs/architecture.md) § Scanned-page intake).
- **Graph:** prefer Cypher when relationships matter; every node carries `source` + `confidence`; return provenance (`source_url`, `ingest_timestamp`, `agent_version`); soft-delete with `archived_at`, never hard-delete.
- **Open source first:** every code dependency is MIT/AGPL compatible (this governs code, not the runtime model vendor).
- **LegalBench stays pinned to Ollama** — through the chain, scores would not be comparable.
- **Autonomy:** `make autonomy-run KIND=… SOURCE=…` requires `AUTONOMY_ENABLED=true` and a source in `AUTONOMY_ALLOWED_SOURCES`.

## Coding Standards

- **Python:** `ruff` + `black` (line length 88). `mypy --strict` is ratcheted: `scripts/mypy_ratchet.py` fails on growth over `backend/mypy-baseline.txt`, every new file must be strict-clean, and `make mypy-baseline` re-banks after a burn-down. `make lint`/`make format` cover `backend/` and `frontend/` only; `make lint-root` reports root `scripts/`/`tests/` drift without gating (BL-20260906-36). Public functions get docstrings with examples; Django layout: [docs/django-conventions.md](docs/django-conventions.md).
- **TypeScript/React:** `"strict": true`; prefer server components and Server Actions; graph data flows client → typed API route → backend → Neo4j, never Neo4j from the client.
- **Markdown:** one paragraph per line — run `python3 tools/unwrap-prose.py --write`, or [markdown-oneline](.github/workflows/markdown-oneline.yml) pushes a repair commit. Every doc opens with one H1 and a `>` summary, indexed in [docs/README.md](docs/README.md) by `python3 tools/docs_index.py --write`.

### Agent Development Rules

New agents live in `agents_runtime/crews/` or `graphs/`, implement `run(input: dict) -> dict` with Pydantic output, log every LLM and tool call via `core.provenance`, declare `human_approval_required` when it applies, keep prompts versioned in `agents_runtime/prompts/`, reference LegalBench tasks where applicable, and ship a test under `backend/tests/agents/` ([prompts/new-agent.md](prompts/new-agent.md), [docs/agent-roles.md](docs/agent-roles.md)).

### Testing Standards

All tests run in Docker: backend pytest + pytest-asyncio + pytest-cov, frontend Vitest + React Testing Library + MSW. A new feature ships a unit test, an integration test against real Neo4j/Postgres (`make test-integration`), and a LegalBench regression test when reasoning changes.

## Evaluation & Quality Gates

Before any PR:

1. `make lint` and `make typecheck`.
2. `make test`, clearing backend ≥75% and the frontend category floors.
3. `make test-legalbench` when reasoning logic changed: relevant scores must not drop; record the delta in the PR (CI runs it on the `reasoning-change` label and nightly; [docs/legalbench.md](docs/legalbench.md)).
4. `make test-e2e` when you touch the app shell, agent stream, admin HITL flow or API surface ([docs/e2e-testing.md](docs/e2e-testing.md)); after a request/response model change, `make manage CMD=export_api_schema` (the contract fixture `make test` checks).
5. A manual smoke of Analysis Studio and the Knowledge Graph against `make dev`.
6. **Visual evidence:** a visible change under `frontend/` or `lsat-static/` ships screenshots ([docs/ui-ux-review.md](docs/ui-ux-review.md) § "Visual evidence"); CI's `Visual Evidence Gate` enforces it unless the PR is labelled `no-visual-change`. A passing `ux_audit.py` is not evidence.
7. **Continuous evolution** (constitution §11): the spec's `tasks.md` ends with a populated `## Follow-ups Discovered`, each follow-up is mirrored into `BACKLOG.md`, `make lint-specs` exits 0, and the PR body copies the new BACKLOG bullets.

## How to Implement Common Tasks

- **Agent crew member:** [prompts/new-agent.md](prompts/new-agent.md).
- **Graph schema:** [docs/data-model.md](docs/data-model.md), a migration in `core/neo4j/migrations/`, `core/models.py`, and a Cypher helper in `core/neo4j/queries.py`.
- **Public data source:** a client in `backend/law_ai/ingestionapp/`, wired into the Ingestion Scout crew, documented in [docs/data-sources.md](docs/data-sources.md).
- **GraphRAG retrieval:** edit `agents_runtime/tools/graph_rag.py`; run LegalBench before and after and record the delta.
- **Frontend feature:** [prompts/implement-feature.md](prompts/implement-feature.md) — backend route first, loading states and error boundaries, a Vitest test, screenshots in the PR.

## Important Context Files (Read These First)

In order: [docs/philosophy.md](docs/philosophy.md), [docs/architecture.md](docs/architecture.md), [docs/agent-roles.md](docs/agent-roles.md), [PRD.md](PRD.md), [docs/related-github-repos.md](docs/related-github-repos.md), [docs/ui-ux.md](docs/ui-ux.md). Everything else is in the [docs index](docs/README.md); keep the doc for a schema, source, eval or convention current in the change that moves it.

## Communication Style for AI Agents

Start a response with "Understood. Implementing [feature] following Law AI principles…", name the exact files you will modify, show the key change before writing, and end with "Ready for review. LegalBench delta: +X% on relevant tasks" when reasoning changed.

## Fleet context

Member of the bamr87 fleet, vendored in the hub as `projects/law-ai`: commit and push here first; the hub bumps its pointer afterwards. Standards: <https://github.com/bamr87/bamr87/tree/main/specs>; SDLC declaration: `.github/sdlc.yml`. Loops: `evolve.yml` (weekly audit for `@copilot`, kill switch `EVOLVE_ENABLED`), GitFactory's `factory--*.yml` (from `.factory/`), `claude.yml` (`@claude`), and the hub's conformance and verify callers.

## Standard deviations

None waived in `.github/sdlc.yml` (`deviations: []`). Known gaps that are open work, not waivers: `frontend/` and `lsat-static/` commit `package-lock.json` because CI and the Makefile install with `npm ci` (UPS-QA-40, UPS-REPO-07), and `ci.yml` is bespoke rather than a thin caller of the hub's `standard-ci.yml` (UPS-QA-20).
