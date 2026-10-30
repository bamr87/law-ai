<!-- kit: sdlc v0.1.0 · AGENTS.md is the CANONICAL agent instructions file (decision D4, UPS-AGENT-07/08). CLAUDE.md is a pointer to this file and carries no rules of its own. -->

# Law AI — Agent Coding Instructions

> How to build Law AI — an open-source, agent-orchestrated legal-intelligence platform — with the exact commands, layout, rules and gates every agent and contributor follows.

**This file is the single source of truth for every coding agent and every human working on Law AI.** Update it when architecture or standards evolve. Claude Code loads it through [CLAUDE.md](CLAUDE.md); GitHub Copilot through [.github/copilot-instructions.md](.github/copilot-instructions.md); both defer here.

## What this repo is

Law AI is an open-source, agent-orchestrated legal-intelligence platform for three audiences: **prospective law students** (LSAT preparation — a practice lab, solving aids and playbooks, a continuous curriculum, a knowledge library, also published as a static site), **current law students** (the legal-journey platform: matters, scanned-page intake, an analysis studio and agent traces that show how an argument is built), and **practicing lawyers** (IRAC analysis grounded in retrieved authority, precedent mapping, a citation knowledge graph, an audit trail, and a local-only mode for privileged data). Multi-agent workflows (CrewAI crews and LangGraph graphs), a Neo4j knowledge graph with GraphRAG retrieval, and interactive visualisations do the work; every output is grounded in a retrieved source, carries provenance, and keeps a human in the loop on the high-stakes paths.

"Done" for a change here means: the spec package it came from is consistent (`make lint-specs`), the Docker gates are green (`make lint`, `make typecheck`, `make test`), the LegalBench score did not regress when reasoning changed, anything a user could see ships with a screenshot, and the follow-ups it discovered are in [BACKLOG.md](BACKLOG.md).

**The development loop is the fleet's, not this repo's.** Law AI follows the spec-driven SDLC loop (AO-SDLC) that the bamr87 fleet hub owns and consumes it by reference: the `/specify → /clarify → /plan → /tasks → /implement` chain and the `/evolve` autopilot are the hub's `spec-driven` Claude Code plugin (enabled in [.claude/settings.json](.claude/settings.json)); the spec and backlog gates are the hub's reusable `spec-gate.yml` workflow in CI and run locally through [tools/fleet-kit.sh](tools/fleet-kit.sh) as `make lint-specs`; this repo carries only its content — [specs/](specs/), [BACKLOG.md](BACKLOG.md), [docs/constitution.md](docs/constitution.md), [specs/_review_questions.json](specs/_review_questions.json). [docs/spec-driven.md](docs/spec-driven.md) maps the loop onto this repo; the hub's [docs/SPEC-DRIVEN.md](https://github.com/bamr87/bamr87/blob/main/docs/SPEC-DRIVEN.md) is the operating guide. Every non-trivial change starts with a spec under `specs/`, and all specs and PRs must satisfy [docs/constitution.md](docs/constitution.md).

## Development orchestration (GitHub Copilot + Claude Code)

**The sanctioned AI development surfaces for this repo are GitHub Copilot and Claude Code.** They cover:

- **Claude Code** — the CLI / IDE extensions and the Claude Agent SDK. Runs the fleet's spec-driven chain and autopilot through the `spec-driven` plugin, plus this repo's own commands (`/new-agent`, `/implement-feature`, `/ux-review`) and the `constitution-reviewer` agent.
- **Copilot Chat** in VS Code — Ask, Edit, and Agent modes. Copilot cannot load a Claude plugin; when it drives a spec by hand it follows [docs/spec-driven.md](docs/spec-driven.md) and the same gates check the result.
- **Inline Copilot completions** in any JetBrains/VS/VS Code surface authenticated to the same GitHub account.
- **GitHub Copilot coding agent** — the cloud agent that picks up issues assigned to `@copilot`.
- **Copilot Code Review** and the `@claude` mention handler ([.github/workflows/claude.yml](.github/workflows/claude.yml)) on pull requests.
- **Dev-time MCP** — [.mcp.json](.mcp.json) wires `law-ai-postgres` (read-only SQL) and `law-ai-neo4j` (Cypher) to the running compose stack with the local compose defaults. The product runtime takes no MCP dependency (constitution §1).

Repo-level instructions for Copilot live in [.github/copilot-instructions.md](.github/copilot-instructions.md); path-scoped Copilot overrides go in `*.instructions.md` files following [Copilot custom instructions docs](https://docs.github.com/copilot). Both defer to this file.

**Forbidden in this repo**: Cursor, Continue.dev, Aider, Codex, Gemini CLI, or any other third-party coding agent. Do not commit their config files (`.cursorrules`, `.continuerc.json`, `.aider.conf.yml`, etc.). The only sanctioned agent configs are Copilot's `.github/copilot-instructions.md` / `*.instructions.md` and Claude Code's [CLAUDE.md](CLAUDE.md) / `.claude/` / [.mcp.json](.mcp.json).

**Dev-time MCP servers.** [.mcp.json](.mcp.json) wires project-scoped Model Context Protocol servers into the sanctioned dev surfaces so the *dev* agent can introspect the local Docker stack directly: `law-ai-postgres` (read-only SQL against the compose Postgres) and `law-ai-neo4j` (Cypher against the compose Neo4j). These are development tooling — the **product runtime** takes no MCP dependency (constitution §1). The credentials in that file are the local docker-compose dev defaults, not secrets. Start the stack (`make dev` or `docker compose up -d postgres neo4j`) before using them.

**Important distinction**: this section is about **how the codebase is built**. Which model *serves end users* is a separate, independently configured decision — since the 2026-08-11 amendment to [docs/constitution.md](docs/constitution.md) §1, the product runtime is an ordered provider chain that defaults to Claude and falls back to local Ollama. Changing your dev surface does not change the runtime, and vice versa.

| Layer | Tool | Why |
|-------|------|-----|
| Dev orchestration (writing/refactoring this repo) | GitHub Copilot or Claude Code; the fleet's spec-driven plugin for the loop | Sanctioned surfaces; shared instructions; the loop versioned once in the hub |
| Product runtime (what the deployed app uses to answer legal questions) | `LLM_PROVIDER_CHAIN` — Claude (OAuth), then Claude (API key), then xAI Grok (subscription OAuth, `make xai-login`), then Ollama | Constitution §1 as amended: highest-capability answers by default, a hosted fallback before the quality cliff, local-first still reachable by pinning `ollama` |

**Privileged data caveat**: the Claude tiers and the xAI tier send prompt text to a third party. `LLM_PROVIDER_CHAIN=ollama` is the only configuration that keeps prompt text on the host, and deployments handling data under a confidentiality obligation that forbids third-party processing must pin it (constitution §1).

## Jurisprudential stance — the premise underneath the principles

> "Justice is nothing else than the interest of the stronger." — Thrasymachus, Plato, *Republic* I.338c

We hold this **descriptively, about our data** — the legal record is the record of what the stronger parties have gotten courts to say (opinions are written by the side that won; settlement selection and repeat-player advantage skew which disputes ever get published; citation counts measure litigation resources before they measure correctness) — and we **reject it normatively, as a goal for the system**. A craft serves its subject, not its practitioner (*Republic* I.341c–342e): Law AI serves its user, especially the under-resourced one. The job is to make legal asymmetry **visible and contestable**, never to launder it as neutral truth and never to exploit it.

Full argument in [docs/philosophy.md](docs/philosophy.md); enforced as [docs/constitution.md](docs/constitution.md) §13 and, at the spec gate, as the review question in [specs/_review_questions.json](specs/_review_questions.json) that every feature ranking, scoring or summarising authority must answer: **who is the stronger here, and what does this feature do for them?**

## Core principles for all code changes

- **Open source first**: every *code* dependency must be MIT/AGPL compatible — no proprietary libraries in the codebase itself. This governs what we build with, not which model answers end users: the product-runtime LLM vendor is a separate, independently governed decision (constitution §1), and its default tier is the closed-source Claude API.
- **Privacy by choice**: local DBs always; the LLM tier is operator-selected via `LLM_PROVIDER_CHAIN`. Claude is the default for answer quality, with xAI Grok as a further hosted tier before the local fallback; a fully local run (`LLM_PROVIDER_CHAIN=ollama`) stays a first-class, supported configuration.
- **Auditability**: every agent decision, prompt, tool call, and retrieval is logged with full provenance.
- **Legal accuracy**: all outputs are grounded in retrieved sources + citations. LegalBench is the regression harness.
- **Power-aware output**: attribute every legal proposition to its issuing authority (court, jurisdiction, date, binding/persuasive). Never present citation counts or centrality as a correctness score, and never let "no results in our corpus" read as "no such law." Label asymmetry; do not filter by it.
- **Graph-native thinking**: prefer Neo4j Cypher traversals over pure vector search when relationships matter (precedents, citations, doctrines).
- **Human-in-the-loop (HITL)**: critical paths (ingestion of new cases, high-stakes analysis) require explicit approval gates. The gate is where decision power deliberately sits with a human.

## Docker-first workflow (mandatory — the rule you will trip on)

**Every dev/test/lint/typecheck/eval command runs inside Docker via the [Makefile](Makefile)**, which wraps `docker compose run --rm <service>`. Agents and humans MUST NOT run `cd backend && pytest …`, `cd frontend && npm …`, `python manage.py …`, `pip install …`, `ruff …`, `mypy …`, `black …`, or `npm install` on the host. The only sanctioned host-level commands are:

- `make …` (Docker wrappers — preferred) and `docker compose …` (raw control)
- `tools/fleet-kit.sh` and the stdlib gate tools it resolves (the hub's spec validator and backlog lint, run by `make lint-specs`), plus this repo's own stdlib `scripts/ux_audit.py`
- `git`, `gh`, and editor-driven tools

Why: every contributor and every agent gets the same Python 3.12, the same Node 24, the same Neo4j 5, the same Postgres 16, the same Ollama, the same C deps for `eyecite`/`spaCy`. No "works on my machine", no host venv drift; it is what makes an agent-run gate reproducible. Aligns with constitution §1 (reproducibility) and §4 (auditability of every run). The `host-*` make targets exist for emergency fallback only and MUST NOT be used in CI, prompts, or docs.

## Stack & commands

```bash
# install / run
cp .env.example .env
make dev                      # full stack: frontend :3000, API :8000 (/api/agents, /api/analysis, /api/graph, /api/lsat)
make down · make logs · make ps
make debug                    # debugger ports: backend 5678, worker 5679, frontend 9229 (.vscode/launch.json)
make shell-backend · make shell-frontend
make manage CMD='migrate'     # any Django management command
make migrate                  # migrations + the LangGraph checkpointer

# test
make test                     # backend pytest + frontend vitest, in containers
make test-backend             # excludes `integration` + `legalbench` markers
make test-frontend · make test-integration · make test-legalbench · make test-e2e · make test-coverage
docker compose run --rm backend pytest tests/agents/test_foo.py::test_bar -q    # one test
docker compose run --rm backend pytest -k "citation" -q                         # keyword filter

# lint / types
make lint · make format · make typecheck   # ruff + black + eslint; mypy --strict (ratcheted) + tsc

# the spec gate (host, stdlib — the hub's spec-driven kit through tools/fleet-kit.sh)
make lint-specs               # spec_validator.py --strict, backlog_lint.py, scripts/ux_audit.py
make fleet-kit                # refresh the cached kit when this repo is not inside the hub checkout

# build
docker compose build backend  # the proof the dependency graph resolves
```

**Two separate pytest configs — don't confuse them.** The root [pytest.ini](pytest.ini) drives the repo-wide `tests/` orchestrator (structure, configs, docs, the spec gate as tests; markers `smoke`/`specs`/`backend`/`frontend`) and deliberately does *not* collect `backend/` or `frontend/`. [backend/pyproject.toml](backend/pyproject.toml) drives the real backend suite under `backend/tests/` with `--cov-fail-under=75` and markers `unit`/`integration`/`legalbench` (`asyncio_mode=auto`).

Every make target is listed in [docs/reference/make-targets.md](docs/reference/make-targets.md) and every backend route in [docs/reference/http-routes.md](docs/reference/http-routes.md) — both generated by `scripts/gen_make_reference.py` / `scripts/gen_route_reference.py`; never hand-edit them.

The same commands are VS Code tasks in [.vscode/tasks.json](.vscode/tasks.json) (`Docker: Start Full Stack`, `Docker: Run All Tests`, `Docker: LegalBench Eval`, `Docker: Spec & Backlog Validators`, …). Reset only Postgres with `make reset-db && make dev && make migrate`; reset every local DB with `docker compose down -v && make dev`.

## Tech stack (non-negotiable)

**Backend**
- Python 3.12+
- Django 5 (ASGI via daphne) + Django REST Framework + Channels + Celery + Pydantic v2 (domain layer)
- **CrewAI** (role-based crews) + **LangChain** + **LangGraph** (stateful workflows) — core dependencies since spec 035, not extras. `ChatProviderChain` (`backend/law_ai/core/llm/langchain.py`) is a real LangChain `BaseChatModel` fronting the provider chain below and is `LegalWorkflow`'s default LLM factory (`agents_runtime/graphs/legal_workflow.py`). The chain has two sanctioned entry points and both write the same `llm_call` event: `core.llm.agenerate`/`generate` for plain agent classes (they need `response_schema` and `LLMResult`), `ChatProviderChain` for LangGraph nodes and LCEL chains — see [docs/architecture.md](docs/architecture.md) § Technology Choices Rationale for why the two are not consolidated. `langgraph-checkpoint-postgres`/`-redis` persist `StateGraph` state via `AsyncPostgresSaver` against `settings.POSTGRES_URL`, provisioned by `manage.py ensure_checkpointer` (wired into `make migrate`)
- Neo4j Community + official Python driver
- PostgreSQL + asyncpg
- `chromadb` is a declared dependency but not yet wired into any retrieval path — the planned vector leg for GraphRAG is a native Neo4j vector index blended with the existing lexical retriever, not a separate vector store (open: BL-20260810-17)
- Anthropic Claude (default LLM, via OAuth token or `ANTHROPIC_API_KEY`); xAI Grok (subscription OAuth, spec 050)
- Ollama (local fallback LLM, `LLM_PROVIDER_CHAIN=ollama` tier) — bootstraps `mistral:7b-instruct` and `llama3.1:8b-instruct` per `OLLAMA_BOOTSTRAP_MODELS`/`OLLAMA_DEFAULT_MODEL` (`.env.example`, `docker-compose.yml`); change those env vars to run other models
- Eyecite + Blackstone (spaCy) for legal NLP

**Frontend**
- Next.js App Router + TypeScript (apps are on Next 16; constitution §2 still says 15)
- Tailwind v4. **shadcn/ui is constitution-listed and not installed** — current surfaces, tokens, and the replacement kit are documented in [docs/ui-ux.md](docs/ui-ux.md). Spec [039](specs/039-design-system/spec.md) + [ADR 0006](docs/adr/0006-first-party-design-system.md) propose a first-party system at `frontend/ui/`.
- Cytoscape.js for graphs (`@xyflow/react` was removed by BL-20260830-01; re-add it only in the commit that imports it)
- WebSockets for real-time agent streaming; data fetching is plain `fetch` in `frontend/lib/api.ts` (TanStack Query was removed by BL-20260830-01)

**Infrastructure**
- Docker Compose (full local stack)
- GitHub Actions for CI (lint, type-check, tests, LegalBench harness check); the fleet hub's reusable workflows for the spec gate

## Layout

This is the canonical layout, mirroring the actual `backend/law_ai/` Django package and the `frontend/` Next.js app — what exists on disk today, not a future target. When adding new code, place it in the matching directory; do not invent new top-level locations.

```
law-ai/                                 # workspace root (GitHub slug stays `law-ai`)
├── backend/
│   ├── manage.py
│   ├── pyproject.toml
│   └── law_ai/                         # Django project package
│       ├── asgi.py                     # ASGI entrypoint (daphne) + Channels routing
│       ├── celery.py                   # Celery("law_ai") app + beat schedule
│       ├── urls.py                     # Root URLConf, mounts every Django app below
│       ├── settings/                   # Split settings: base / dev / test / prod
│       ├── core/                       # config, security, Neo4j driver, provenance, telemetry, the LLM provider chain (core/llm/)
│       ├── audit/                      # AuditEvent model + provenance writers
│       ├── agents_runtime/             # All agent definitions + crews + workflows
│       │   ├── crews/                  # CrewAI crew definitions
│       │   ├── graphs/                 # LangGraph workflows (LegalWorkflow, …)
│       │   ├── tools/                  # Custom tools (GraphRAG retriever in graph_rag.py)
│       │   └── prompts/                # Versioned prompt templates (`*.v<N>.md`)
│       ├── agentsapi/                  # DRF routers + Channels consumers under /api/agents/*
│       ├── analysis/                   # /api/analysis router (Analysis Studio backend)
│       ├── graph/                      # /api/graph/* router (Knowledge Graph backend)
│       ├── ingestionapp/               # Quarantine ORM models + Celery tasks + source clients + the ocrmd plug-in
│       ├── lsat/                       # /api/lsat/* router + question banks (services/data/)
│       ├── matters/                    # the legal-journey platform (matters, scanned intake)
│       └── eval/                       # LegalBench harness
│   ├── scripts/                        # Operator scripts (ingest_sample.py, init-db.sh, ollama-bootstrap.sh)
│   └── tests/                          # pytest suite mirroring the package layout
├── frontend/
│   ├── app/                            # Next.js App Router (agents, analysis, graph, lsat, matters pages)
│   ├── components/                     # Screen-level UI (GraphViewer, AgentDashboard, LsatLab, …)
│   ├── ui/                             # Spec 039 target — tokens + primitives
│   ├── lib/                            # Typed API client + utils
│   ├── mocks/                          # MSW handlers for tests
│   └── __tests__/                      # Vitest + RTL component tests
├── lsat-static/                        # Serverless LSAT practice (GitHub Pages, no Tailwind)
├── lawmode/                            # Imported bamr87/lawmode (its own README and tooling)
├── docs/                               # Architecture, data model, agent roles, ADRs (docs/adr/), runbooks, the PRD, history/
├── specs/                              # Spec packages (NNN-feature-slug/{spec,plan,tasks}.md), _template/, _review_questions.json
├── scripts/                            # Repo-level stdlib scripts: ux_audit, visual_evidence_gate, mypy_ratchet, LegalBench + Ollama helpers
├── tools/                              # Hub-vendored tooling: fleet-kit.sh (resolves the spec-driven kit), unwrap-prose.py
├── tests/                              # Repo-wide structural tests (configs, docs, the spec gate)
├── infra/, docker-compose*.yml         # Local stack: Postgres, Redis, Neo4j, Ollama, observability
├── .env.example
├── components/, features/, verify/     # Fleet kits: feedback widget, the feature index, verify scenarios
├── BACKLOG.md                          # The backlog of record (append-only)
└── AGENTS.md                           # This file; CLAUDE.md points here
```

**Architecture in one paragraph.** Each Django app owns one `/api/*` router. `agents_runtime/` holds all agent logic — `crews/` (CrewAI), `graphs/` (LangGraph, incl. the `ChatProviderChain`-backed `LegalWorkflow`), `tools/` (`GraphRAGRetriever`: hybrid lexical fulltext + `CITES` graph-expansion retrieval) — with `core/neo4j/` holding the citation resolver and raw Cypher the tools build on. `agentsapi/` streams agent runs over WebSockets. **The ocrmd plug-in** (spec 055; `ingestionapp/services/ocrmd_plugin.py`) receives scanned book pages from [ocrmd](https://github.com/bamr87/ocrmd) through a small descriptor/envelope contract and opens two doors: `POST /api/lsat/intake/ocr` (questions transcribed out of the page go through the same factory gates and HITL queue as generated ones, dropped below a 0.75 grounding score) and `POST /api/matters/<slug>/intake/ocrmd` (the page becomes a `document` artifact on the caller's matter, idempotent on page id + region, never authority). Frontend graph data flows client → typed API route → backend → Neo4j; **never query Neo4j from the client**. Deeper detail: [docs/architecture.md](docs/architecture.md), [docs/agent-roles.md](docs/agent-roles.md), [docs/data-model.md](docs/data-model.md).

## Coding standards

### Python
- Use `ruff` + `black` (line length 88)
- `make lint` and `make format` cover **`backend/` and `frontend/` only** — they run inside those containers, so repo-root Python (`scripts/*.py`, `tests/*.py`) is deliberately out of scope (BL-20260906-36). Those trees are stdlib-only host tooling; `make lint-root` reports their ruff/black drift on demand and never gates.
- Strict type hints + `mypy --strict`. The strict run is a real CI gate, ratcheted: `scripts/mypy_ratchet.py` compares per-file error counts against `backend/mypy-baseline.txt` and fails on any growth. **A file that is not already in that baseline must be strict-clean** — that includes every file you create. To clear a legacy file, fix it and re-bank with `make mypy-baseline` (the baseline may only shrink).
- All public functions must have docstrings with examples
- Agent prompts must be in `backend/law_ai/agents_runtime/prompts/` as `.md` or `.txt` files (versioned)

### TypeScript / React
- Strict TypeScript (`"strict": true`)
- Prefer server components + React Server Actions where possible
- All graph interactions must go through typed API routes (no direct Neo4j from client)
- UI tokens and primitives live under `frontend/ui/` once spec 039 lands. Until then, do not add shadcn or a second palette — read [docs/ui-ux.md](docs/ui-ux.md) first.

### Markdown
- **One paragraph per line.** Do not hard-wrap prose. The [markdown-oneline](.github/workflows/markdown-oneline.yml) workflow unwraps soft-wrapped paragraphs and pushes the repair back onto the PR branch, so a hard-wrapped paragraph costs a bot commit and a head SHA that CI did not run against. Tables, code fences, front-matter and HTML are left alone.
- Fix locally before pushing with `python3 tools/unwrap-prose.py --write`.

### Neo4j / Graph
- Use Cypher for all relationship-heavy queries
- Always return provenance (`source_url`, `ingest_timestamp`, `agent_version`)
- Never delete nodes — use soft-delete + `archived_at` for audit

### Agent development rules
1. **New agent role** → create in `backend/law_ai/agents_runtime/crews/` or `graphs/` (`/new-agent` scaffolds it)
2. **Must implement**:
   - `run(input: dict) -> dict` with structured output (Pydantic)
   - Logging of every LLM call + tool use via `core.provenance`
   - Optional `human_approval_required: bool`
3. **Prompts** must reference LegalBench tasks when applicable
4. **Evaluation** — every new agent must have at least one test in `backend/tests/agents/` that runs against the LegalBench subset

### Testing standards (mandatory)
- **All tests run in Docker.** Use `make test`, `make test-backend`, `make test-frontend`, `make test-coverage`, `make test-integration`, `make test-legalbench`. Do not run `pytest`, `vitest`, or `npm test` on the host.
- **Backend**: pytest + pytest-asyncio + pytest-cov (≥75% coverage) — invoked via `docker compose run --rm backend pytest …`
- **Frontend**: Vitest + React Testing Library + MSW — invoked via `docker compose run --rm frontend npm test`
- **All new features** must include a unit test (fast, mocked — `make test-backend`), an integration test against real Neo4j/Postgres (`make test-integration`), and a LegalBench regression test if reasoning changes (`make test-legalbench`)
- Coverage reports are written to `htmlcov/` and `frontend/coverage/` via the bind mount.

## How to implement common tasks

1. **Add a new agent crew member** → `/new-agent <name and responsibility>` ([.claude/commands/new-agent.md](.claude/commands/new-agent.md); the checklist works from any surface).
2. **Extend the knowledge graph schema** → update [docs/data-model.md](docs/data-model.md), add a migration in `backend/law_ai/core/neo4j/migrations/`, update `backend/law_ai/core/models.py`, add the Cypher helper in `backend/law_ai/core/neo4j/queries.py`.
3. **Add a new public data source** → a client in `backend/law_ai/ingestionapp/`, wired into the `IngestionScout` crew ([docs/agent-roles.md](docs/agent-roles.md)), documented in [docs/data-sources.md](docs/data-sources.md).
4. **Improve GraphRAG retrieval** → edit `backend/law_ai/agents_runtime/tools/graph_rag.py`, add the retriever strategy, run `make test-legalbench` before and after and record the delta in the PR.
5. **Add a feature to the frontend** → `/implement-feature <description>` ([.claude/commands/implement-feature.md](.claude/commands/implement-feature.md)): the API route in the matching backend module first, loading states + error boundaries, a Vitest test under `frontend/__tests__/`, screenshots in the PR (the visual-evidence gate below).
6. **Anything non-trivial** → the spec-driven chain first: `/spec-driven:specify` → `:clarify` → `:plan` → `:tasks`, then `/spec-driven:implement` per task ([docs/spec-driven.md](docs/spec-driven.md)).

## Evaluation & quality gates (mandatory)

Before any PR — every command runs in Docker:
1. `make lint` (ruff + black + frontend eslint, all in containers) and `make typecheck` (mypy --strict behind the `backend/mypy-baseline.txt` ratchet + tsc --noEmit)
2. `make test` (backend pytest + frontend vitest in containers) — must clear the configured coverage floors: backend ≥75% (`backend/pyproject.toml` `--cov-fail-under=75`), frontend ≥65-70% by category (`frontend/vitest.config.ts` thresholds)
3. `make test-legalbench` when reasoning logic changed
4. `make test-e2e` when you touch the app shell, the agent stream, the admin HITL flow, or the API surface — the browser suite is nightly, not part of `make test`, so a change to any of those needs one deliberate run. See [docs/e2e-testing.md](docs/e2e-testing.md). The API contract gate it depends on (`manage.py export_api_schema` → `frontend/__tests__/lib/apiContract.test.ts`) *is* in `make test`: regenerate the fixture with `make manage CMD=export_api_schema` whenever a request/response model changes.
5. Manual smoke test of Analysis Studio + Knowledge Graph in the browser (against `make dev`)
6. **Visual evidence gate** — any change to `frontend/` or `lsat-static/` that a user could *see* ships with screenshots. See [docs/ui-ux-review.md](docs/ui-ux-review.md) § "Visual evidence" for what to capture and how. A passing `ux_audit.py` is not evidence: it checks landmarks and contracts, not whether the screen reads correctly. **Enforced in CI**: the `Visual Evidence Gate` job fails a PR touching those paths unless the body carries an image or the diff adds a file under `docs/images/`; label the PR `no-visual-change` to opt out when there is genuinely nothing to see.
7. **Continuous-evolution gate** ([docs/constitution.md](docs/constitution.md) §11):
   - `tasks.md` for the spec must end with a populated `## Follow-ups Discovered` section.
   - Each follow-up is mirrored into [BACKLOG.md](BACKLOG.md) with a `BL-YYYYMMDD-NN` id (`python3 "$(tools/fleet-kit.sh)/tools/next_backlog_id.py" --root .` mints the next one).
   - `make lint-specs` (the fleet's `spec_validator.py --strict` and `backlog_lint.py` through `tools/fleet-kit.sh`, then `scripts/ux_audit.py`) exits 0. CI runs the same gate by reference as `Spec Drift Gate`.
   - PR description copies the new BACKLOG bullets so reviewers can see what the next agent is set up to inherit.

**LegalBench integration.** We maintain a living evaluation harness. New reasoning capabilities must improve or maintain score on relevant LegalBench tasks; the scored, gated run is weekly in [nightly-tests.yml](.github/workflows/nightly-tests.yml).

**Self-evolution loop.** This repo is designed to grow itself: every `/spec-driven:implement` cycle ends by recording follow-ups; every `/spec-driven:specify` cycle starts by claiming items from [BACKLOG.md](BACKLOG.md); `/spec-driven:evolve` runs one whole cycle unattended and stops at every question a human must answer. See §11 of the constitution and [docs/spec-driven.md](docs/spec-driven.md).

## Conventions

- **Backlog of record:** [BACKLOG.md](BACKLOG.md) — append-only, `BL-YYYYMMDD-NN` ids, `## Open` / `## Claimed` / `## Done` — declared in [.github/sdlc.yml](.github/sdlc.yml) (`backlog.mode: file`) and linted by the fleet's spec gate in CI and `make lint-specs` locally. Resolved items move to `## Done`; nothing is deleted. Cross-repo initiatives live in the hub's `_data/roadmap.yml`.
- **Definition of Done:** the checklist in [.github/pull_request_template.md](.github/pull_request_template.md) — what and why, visual evidence, the gates you actually ran, the follow-ups copied from BACKLOG.md. Every section is filled before merge.
- **Decisions:** ADRs in [docs/adr/](docs/adr/) as `NNNN-slug.md`, indexed in [docs/adr/README.md](docs/adr/README.md). Add one for anything hard to reverse; a deviation from the locked stack (constitution §2) needs one before the plan.
- **Specs:** `specs/NNN-slug/{spec,plan,tasks}.md` per non-trivial change, from the repo-owned [specs/_template/](specs/_template/); specs are code — never edit a merged spec in place, open an amendment.
- **Commits:** Conventional Commits (`feat fix docs style refactor test chore perf ci build`), `type(scope): subject` ≤72 chars. The PR title is the squash subject.
- **Branches:** `feature/`, `fix/`, `docs/`, `refactor/`, `test/`, `spec/` or `chore/` off `main`; never push to `main` directly, never force-push a shared branch.
- **Changelog:** [CHANGELOG.md](CHANGELOG.md) in Keep a Changelog form; versions are not tagged yet and no release-please caller runs here.
- **Never:** bypass `LLM_PROVIDER_CHAIN` to call a provider transport directly, or add a model vendor beyond Anthropic / xAI / Ollama to the product runtime without a constitution §1 amendment; bypass the provenance/audit layer; create graph nodes without `source` and `confidence`; hard-delete graph nodes; ignore HITL requirements for ingestion or high-stakes analysis (`ENABLE_HUMAN_APPROVAL_GATES`); route the LegalBench harness through the chain (it stays pinned to Ollama so scores stay comparable); run autonomy targets without `AUTONOMY_ENABLED=true` and a source in `AUTONOMY_ALLOWED_SOURCES`; rank or assert legal authority by citation volume as if it measured correctness; state a legal proposition without naming the authority that issued it; suppress type errors (`as any`, `# type: ignore` without a reason) or leave empty exception handlers; commit lockfile churn, secrets, or generated artifacts; hand-edit a generated file — `docs/reference/*`, the `docs/README.md` index span, the `features:start`/`features:end` block in [docs/prd.md](docs/prd.md), `frontend/__tests__/fixtures/api-schema.json` (`make manage CMD=export_api_schema`), `lsat-static/content.json` (`make lsat-export`); vendor the spec-driven machinery back into this repo.

## Important context files (read these first)

When starting work, read in this order:
1. [docs/philosophy.md](docs/philosophy.md) — what we believe legal data is + the P1–P7 obligations that follow
2. [docs/architecture.md](docs/architecture.md) — full system diagram + component responsibilities
3. [docs/agent-roles.md](docs/agent-roles.md) — responsibilities + tool requirements for each agent
4. [docs/prd.md](docs/prd.md) — full product requirements
5. [docs/spec-driven.md](docs/spec-driven.md) — how the fleet's spec-driven loop runs here, and which checks block a merge
6. [docs/related-github-repos.md](docs/related-github-repos.md) — upstream OSS we integrate with
7. [docs/ui-ux.md](docs/ui-ux.md) — every user-facing surface, the two styling idioms, and the design-system contract

`docs/data-model.md`, `docs/data-sources.md`, `docs/legalbench.md`, `docs/llm-provider-chain.md`, [docs/lsat-library.md](docs/lsat-library.md) (the LSAT knowledge library's authoring dialect and maintenance loop), [docs/lsat-synthesis.md](docs/lsat-synthesis.md) (the deterministic item-synthesis engine and its proof gates), and [docs/django-conventions.md](docs/django-conventions.md) (Django app-layout and coding conventions) all exist — keep them current as the schema, sources, eval harness, and conventions evolve rather than skipping the documentation step. [docs/history/](docs/history/) holds the original technical proposal and the raw local-AI planning note as historical records; neither is a living reference.

## Communication style for AI agents

When responding to user requests:
- Always start with **"Understood. Implementing [feature] following Law AI principles..."**
- Reference the exact file paths you will modify
- Show the key code change (diff style) before writing files
- End with **"Ready for review. LegalBench delta: +X% on relevant tasks"** when applicable

## Fleet context

Member of the [bamr87 fleet](https://github.com/bamr87/bamr87): the hub's [Universal Project Standard](https://github.com/bamr87/bamr87/tree/main/specs) is what this repo is measured against, and its kits are consumed by reference — the `spec-driven` plugin and the reusable `spec-gate.yml` for the development loop, `tools/unwrap-prose.py` for the prose gate, the `@claude` mention workflow. The repo's SDLC declaration is [.github/sdlc.yml](.github/sdlc.yml). This repo is checked out inside the hub as the submodule `projects/law-ai`: commit here first (on a branch, PR into `main`), then the hub bumps its submodule pointer. `tools/fleet-kit.sh` finds the hub's kit in that parent checkout; on a standalone clone it caches a sparse clone under `.fleet/`.

## Standard deviations

none
