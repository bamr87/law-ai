# Law AI — Agent Coding Instructions

**Project Mission**  
Build the world's first fully open-source, agent-orchestrated legal intelligence platform that combines multi-agent workflows, Neo4j knowledge graphs, GraphRAG, and interactive visualizations to help lawyers and law students master complex legal content.

**Workflow & Standards**
- This repo follows a spec-driven workflow ([AO-SDLC](docs/ao-sdlc.md) Level 2). Every non-trivial change starts with a spec under [specs/](specs/) using [/specify](prompts/specify.md) → [/clarify](prompts/clarify.md) → [/plan](prompts/plan.md) → [/tasks](prompts/tasks.md) → [/implement](prompts/implement.md). For autonomous "pick the next thing and ship it" runs, use [/evolve](prompts/evolve.md).
- All specs and PRs must satisfy [docs/constitution.md](docs/constitution.md). CI enforces spec consistency via [scripts/spec_validator.py](scripts/spec_validator.py).

## Development Orchestration (GitHub Copilot + Claude Code)

**The sanctioned AI development surfaces for this repo are GitHub Copilot and Claude Code.** They cover:

- **Copilot Chat** in VS Code — Ask, Edit, and Agent modes. Agent mode runs the AO-SDLC chain and `/evolve`.
- **Inline Copilot completions** in any JetBrains/VS/VS Code surface authenticated to the same GitHub account.
- **GitHub Copilot coding agent** — the cloud agent that picks up issues assigned to `@copilot` (used by [.github/workflows/evolve.yml](.github/workflows/evolve.yml)).
- **Copilot Code Review** on pull requests.
- **Claude Code** — the Claude Code CLI / IDE extensions and the Claude Agent SDK, which run the same AO-SDLC chain and `/evolve` from the shared [prompts/](prompts/).

Repo-level instructions for Copilot live in [.github/copilot-instructions.md](.github/copilot-instructions.md); for Claude Code they live in [CLAUDE.md](CLAUDE.md). Both defer to this file as the source of truth and share the prompt templates under [prompts/](prompts/). Path-scoped Copilot overrides go in `*.instructions.md` files following [Copilot custom instructions docs](https://docs.github.com/copilot).

**Forbidden in this repo**: Cursor, Continue.dev, Aider, Codex, Gemini CLI, or any other third-party coding agent. Do not commit their config files (`.cursorrules`, `.continuerc.json`, `.aider.conf.yml`, etc.). The only sanctioned agent configs are Copilot's `.github/copilot-instructions.md` / `*.instructions.md` and Claude Code's [CLAUDE.md](CLAUDE.md) / `.claude/` / [.mcp.json](.mcp.json).

**Dev-time MCP servers.** [.mcp.json](.mcp.json) wires project-scoped Model Context Protocol servers into the sanctioned dev surfaces so the *dev* agent can introspect the local Docker stack directly: `law-ai-postgres` (read-only SQL against the compose Postgres) and `law-ai-neo4j` (Cypher against the compose Neo4j). These are development tooling — the **product runtime** takes no MCP dependency (constitution §1). The credentials in that file are the local docker-compose dev defaults, not secrets. Start the stack (`make dev` or `docker compose up -d postgres neo4j`) before using them.

**Important distinction**: This section is about **how the codebase is built**. Which model *serves end users* is a separate, independently configured decision — since the 2026-08-11 amendment to [docs/constitution.md](docs/constitution.md) §1, the product runtime is an ordered provider chain that defaults to Claude and falls back to local Ollama. The two layers stay independent: changing your dev surface does not change the runtime, and vice versa.

| Layer | Tool | Why |
|-------|------|-----|
| Dev orchestration (writing/refactoring this repo) | GitHub Copilot or Claude Code | Sanctioned surfaces; shared custom instructions + prompt templates; CI integration |
| Product runtime (what the deployed app uses to answer legal questions) | `LLM_PROVIDER_CHAIN` — Claude (OAuth), then Claude (API key), then xAI Grok (subscription OAuth, `make xai-login`), then Ollama | Constitution §1 as amended: highest-capability answers by default, a hosted fallback before the quality cliff, local-first still reachable by pinning `ollama` |

**Privileged data caveat**: the Claude tiers — and the xAI tier, once it ships — send prompt text to a third party. `LLM_PROVIDER_CHAIN=ollama` is the only configuration that keeps prompt text on the host, and deployments handling data under a confidentiality obligation that forbids third-party processing must pin it (constitution §1).


**Jurisprudential Stance** — *the premise underneath the principles*

> "Justice is nothing else than the interest of the stronger." — Thrasymachus, Plato, *Republic* I.338c

We hold this **descriptively, about our data** — the legal record is the record of what the stronger parties have gotten courts to say (opinions are written by the side that won; settlement selection and repeat-player advantage skew which disputes ever get published; citation counts measure litigation resources before they measure correctness) — and we **reject it normatively, as a goal for the system**. A craft serves its subject, not its practitioner (*Republic* I.341c–342e): Law AI serves its user, especially the under-resourced one. The job is to make legal asymmetry **visible and contestable**, never to launder it as neutral truth and never to exploit it.

Full argument in [docs/philosophy.md](docs/philosophy.md); enforced as [docs/constitution.md](docs/constitution.md) §13. The review question it puts on every feature that ranks, scores, or summarizes authority: **who is the stronger here, and what does this feature do for them?**

**Core Principles for All Code Changes**
- **Open Source First**: Every *code* dependency must be MIT/AGPL compatible — no proprietary libraries in the codebase itself. This governs what we build with, not which model answers end users: the product-runtime LLM vendor is a separate, independently governed decision (see Development Orchestration above and constitution §1), and its default tier is the closed-source Claude API.
- **Privacy by Choice**: local DBs always; the LLM tier is operator-selected via `LLM_PROVIDER_CHAIN`. Claude is the default for answer quality, with xAI Grok as a further hosted tier before the local fallback; a fully local run (`LLM_PROVIDER_CHAIN=ollama`) stays a first-class, supported configuration.
- **Auditability**: Every agent decision, prompt, tool call, and retrieval must be logged with full provenance.
- **Legal Accuracy**: All outputs must be grounded in retrieved sources + citations. Use LegalBench for regression testing.
- **Power-Aware Output**: Attribute every legal proposition to its issuing authority (court, jurisdiction, date, binding/persuasive). Never present citation counts or centrality as a correctness score, and never let "no results in our corpus" read as "no such law." Label asymmetry; do not filter by it.
- **Graph-Native Thinking**: Prefer Neo4j Cypher traversals over pure vector search when relationships matter (precedents, citations, doctrines).
- **Human-in-the-Loop (HITL)**: Critical paths (ingestion of new cases, high-stakes analysis) require explicit approval gates. The gate is where decision power deliberately sits with a human.

---

## Docker-First Workflow (Mandatory)

**All development, testing, linting, and one-off commands run inside Docker containers via the [Makefile](Makefile).** Agents (and humans) MUST NOT invoke `cd backend && pytest …`, `cd frontend && npm …`, `python manage.py …`, `pip install …`, `ruff …`, `mypy …`, `black …`, or any other tool directly on the host. The only sanctioned host-level commands are:

- `make …` (Docker wrappers — preferred)
- `docker compose …` (when you need raw control)
- `python3 scripts/spec_validator.py` and `python3 scripts/backlog_lint.py` (stdlib-only, no deps)
- `git`, `gh`, and editor-driven tools

Why: every contributor — and every agent — gets the same Python 3.12, the same Node 22, the same Neo4j 5, the same Postgres 16, the same Ollama, the same C deps for `eyecite`/`spaCy`. No "works on my machine". No host venv drift. Aligns with constitution §1 (reproducibility) and §4 (auditability of every run).

Legacy `host-*` make targets exist for emergency fallback only and MUST NOT be used in CI, prompts, or docs.

## Quick Reference (Run These, Don't Reinvent)

Use the [Makefile](Makefile) targets or VS Code tasks in [.vscode/tasks.json](.vscode/tasks.json) — do not invent ad-hoc commands.

| Goal | Command (Docker) | VS Code Task |
|------|------------------|--------------|
| Full stack | `make dev` | `Docker: Start Full Stack` |
| Stack with debugger attach | `make debug` | `Docker: Start Full Stack (Debug)` |
| Stop stack | `make down` | `Docker: Stop Stack` |
| Tail logs | `make logs` | `Docker: Tail Logs` |
| Backend shell | `make shell-backend` | `Docker: Backend Shell` |
| Frontend shell | `make shell-frontend` | `Docker: Frontend Shell` |
| Run Django command | `make manage CMD='migrate'` | `Docker: Migrate` |
| All tests | `make test` | `Docker: Run All Tests` |
| Backend tests | `make test-backend` | `Docker: Backend Tests` |
| Frontend tests | `make test-frontend` | `Docker: Frontend Tests` |
| Coverage | `make test-coverage` | `Docker: Coverage Report` |
| Integration tests | `make test-integration` | `Docker: Integration Tests (real DBs)` |
| Browser end-to-end | `make test-e2e` | — |
| Lint + format | `make lint` | `Docker: Format & Lint All` |
| Type-check | `make typecheck` | `Docker: Type Check (mypy + tsc)` |
| LegalBench eval | `make test-legalbench` | `Docker: LegalBench Eval` |
| Spec/backlog gates | `make lint-specs` | `Docker: Spec & Backlog Validators` |
| Reset local DBs | `docker compose down -v && make dev` | `Docker: Reset Local DBs (Dangerous)` |
| Reset **only** Postgres | `make reset-db && make dev && make migrate` | — |

**Debugging.** Use `make debug` to expose `5678` (backend debugpy), `5679` (worker debugpy), and `9229` (frontend node --inspect). Then attach via [.vscode/launch.json](.vscode/launch.json) ("Docker: Attach to backend / worker / frontend").

Project status, tooling rationale, and onboarding live in [README.md](README.md). Do not duplicate that content here.

---

## Tech Stack (Non-Negotiable)

**Backend**
- Python 3.12+
- Django 5 (ASGI via daphne) + Django REST Framework + Channels + Celery + Pydantic v2 (domain layer)
- **CrewAI** (role-based crews) + **LangChain** + **LangGraph** (stateful workflows) — core dependencies since spec 035, not extras. `ChatProviderChain` (`backend/law_ai/core/llm/langchain.py`) is a real LangChain `BaseChatModel` fronting the provider chain below and is `LegalWorkflow`'s default LLM factory (`agents_runtime/graphs/legal_workflow.py`). The chain has two sanctioned entry points and both write the same `llm_call` event: `core.llm.agenerate`/`generate` for plain agent classes (they need `response_schema` and `LLMResult`), `ChatProviderChain` for LangGraph nodes and LCEL chains — see [docs/architecture.md](docs/architecture.md) § Technology Choices Rationale for why the two are not consolidated.  `langgraph-checkpoint-postgres`/`-redis` persist `StateGraph` state via `AsyncPostgresSaver` against `settings.POSTGRES_URL`, provisioned by `manage.py ensure_checkpointer` (wired into `make migrate`)
- Neo4j Community + official Python driver
- PostgreSQL + asyncpg
- `chromadb` is a declared dependency but not yet wired into any retrieval path — the planned vector leg for GraphRAG is a native Neo4j vector index blended with the existing lexical retriever, not a separate vector store (open: BL-20260810-17)
- Anthropic Claude (default LLM, via OAuth token or `ANTHROPIC_API_KEY`)
- Ollama (local fallback LLM, `LLM_PROVIDER_CHAIN=ollama` tier) — bootstraps `mistral:7b-instruct` and `llama3.1:8b-instruct` per `OLLAMA_BOOTSTRAP_MODELS`/`OLLAMA_DEFAULT_MODEL` (`.env.example`, `docker-compose.yml`); change those env vars to run other models
- Eyecite + Blackstone (spaCy) for legal NLP

**Frontend**
- Next.js App Router + TypeScript (apps are on Next 16; constitution §2 still says 15)
- Tailwind v4. **shadcn/ui is constitution-listed and not installed** — current surfaces, tokens, and the replacement kit are documented in [docs/ui-ux.md](docs/ui-ux.md). Spec [039](specs/039-design-system/spec.md) + [ADR 0006](docs/adr/0006-first-party-design-system.md) propose a first-party system at `frontend/ui/`.
- Cytoscape.js for graphs (`@xyflow/react` was removed by BL-20260830-01; re-add it only in the commit that imports it)
- WebSockets for real-time agent streaming; data fetching is plain `fetch` in `frontend/lib/api.ts` (TanStack Query was removed by BL-20260830-01)

**Infrastructure**
- Docker Compose (full local stack)
- GitHub Actions for CI (LegalBench eval, lint, type-check)

---

## Project Structure

This is the canonical layout, mirroring the actual `backend/law_ai/` Django package and the `frontend/` Next.js app — it matches what exists on disk today, not a future target. When adding new code, place it in the matching directory; do not invent new top-level locations.

```
law-ai/                                 # workspace root (GitHub slug stays `law-ai`)
├── backend/
│   ├── manage.py
│   ├── pyproject.toml
│   └── law_ai/                       # Django project package (was `app/` pre-rebrand)
│       ├── __init__.py
│       ├── asgi.py                     # ASGI entrypoint (daphne) + Channels routing
│       ├── wsgi.py
│       ├── celery.py                   # Celery("law_ai") app
│       ├── urls.py                     # Root URLConf, mounts every Django app below
│       ├── settings/                   # Split settings: base / dev / test / prod
│       ├── core/                       # config, security, Neo4j driver, provenance, telemetry
│       ├── audit/                      # AuditEvent model + provenance writers
│       ├── agents_runtime/             # All agent definitions + crews + workflows
│       │   ├── crews/                  # CrewAI crew definitions
│       │   ├── graphs/                 # LangGraph workflows (LegalWorkflow, …)
│       │   ├── tools/                  # Custom tools (Neo4j, CourtListener, GraphRAG)
│       │   └── prompts/                # Versioned prompt templates (`*.v<N>.md`)
│       ├── agentsapi/                  # DRF routers + Channels consumers under /api/agents/*
│       ├── analysis/                   # /api/analysis router (Analysis Studio backend)
│       ├── graph/                      # /api/graph/* router (Knowledge Graph backend)
│       ├── ingestionapp/               # Quarantine ORM models + Celery tasks + ingestion services
│       ├── lsat/                       # /api/lsat/* router + question banks (data/)
│       └── eval/                       # LegalBench harness + custom evals
│   ├── scripts/                        # Operator scripts (ingest_sample.py, init-db.sh, ollama-bootstrap.sh)
│   └── tests/                          # pytest suite mirroring the package layout
├── frontend/
│   ├── app/                            # Next.js App Router (agents, analysis, graph, lsat pages)
│   ├── components/                     # Screen-level UI (GraphViewer, AgentDashboard, LsatLab, …)
│   ├── ui/                             # Spec 039 target (not landed) — tokens + primitives
│   ├── lib/                            # Typed API client + utils
│   ├── mocks/                          # MSW handlers for tests
│   └── __tests__/                      # Vitest + RTL component tests
├── lsat-static/                        # Serverless LSAT practice (GitHub Pages, no Tailwind)
├── docs/                               # Architecture, data model, agent roles, ADRs, runbooks
│   └── adr/                            # Architecture Decision Records
├── prompts/                            # Spec-driven workflow templates (/specify, /plan, …)
├── specs/                              # Spec packages (NNN-feature-slug/{spec,plan,tasks}.md)
├── scripts/                            # Repo-level scripts (spec_validator, backlog_lint, evolve_audit)
├── tests/                              # Repo-wide structural tests (configs, docs, specs, backlog)
├── docker-compose.yml
├── .env.example
├── BACKLOG.md
└── AGENTS.md
```

---

## Coding Standards

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

### Agent Development Rules
1. **New Agent Role** → Create in `backend/law_ai/agents_runtime/crews/` or `graphs/`
2. **Must implement**:
   - `run(input: dict) -> dict` with structured output (Pydantic)
   - Logging of every LLM call + tool use via `core.provenance`
   - Optional `human_approval_required: bool`
3. **Prompts** must reference LegalBench tasks when applicable
4. **Evaluation** — every new agent must have at least one test in `backend/tests/agents/` that runs against LegalBench subset

### Testing Standards (Mandatory)
- **All tests run in Docker.** Use `make test`, `make test-backend`, `make test-frontend`, `make test-coverage`, `make test-integration`, `make test-legalbench`. Do not run `pytest`, `vitest`, or `npm test` on the host.
- **Backend**: pytest + pytest-asyncio + pytest-cov (≥75% coverage) — invoked via `docker compose run --rm backend pytest …`
- **Frontend**: Vitest + React Testing Library + MSW — invoked via `docker compose run --rm frontend npm test`
- **All new features** must include:
  - Unit test (fast, mocked) — `make test-backend`
  - Integration test against real Neo4j/Postgres — `make test-integration`
  - LegalBench regression test (if reasoning changes) — `make test-legalbench`
- Coverage reports are written to `htmlcov/` and `frontend/coverage/` via the bind mount.

---

## How to Implement Common Tasks (Prompt Templates)

### 1. Add a New Agent Crew Member
See `prompts/new-agent.md` for the exact prompt template.

### 2. Extend the Knowledge Graph Schema
- Update `docs/data-model.md` (create if it does not yet exist)
- Add migration in `backend/law_ai/core/neo4j/migrations/`
- Update `backend/law_ai/core/models.py`
- Add corresponding Cypher helper in `backend/law_ai/core/neo4j/queries.py`

### 3. Add New Public Data Source
- Create new client in `backend/law_ai/ingestionapp/`
- Add to the `Ingestion Scout` crew (see [docs/agent-roles.md](docs/agent-roles.md))
- Document the source in `docs/data-sources.md`

### 4. Improve GraphRAG Retrieval
- Edit `backend/law_ai/agents_runtime/tools/graph_rag.py`
- Add new retriever strategy
- Run `Run LegalBench Eval` task before and after; record the delta in the PR description

### 5. Add Feature to Frontend
- Use [prompts/implement-feature.md](prompts/implement-feature.md)
- Always add the corresponding API route in the matching backend module first (`backend/law_ai/{agentsapi,analysis,graph,lsat}/`)
- Include loading states + error boundaries
- Co-locate a Vitest test under `frontend/__tests__/`
- Capture screenshots of the result and put them in the PR — see the visual-evidence gate below

---

## Evaluation & Quality Gates (Mandatory)

Before any PR — every command runs in Docker:
1. `make lint` (ruff + black + frontend eslint, all in containers) and `make typecheck` (mypy --strict behind the `backend/mypy-baseline.txt` ratchet + tsc --noEmit)
2. `make test` (backend pytest + frontend vitest in containers) — must clear the configured coverage floors: backend ≥75% (`backend/pyproject.toml` `--cov-fail-under=75`), frontend ≥65-70% by category (`frontend/vitest.config.ts` thresholds)
3. `make test-legalbench` when reasoning logic changed
4. `make test-e2e` when you touch the app shell, the agent stream, the admin HITL flow, or the API surface — the browser suite is nightly, not part of `make test`, so a change to any of those needs one deliberate run. See [docs/e2e-testing.md](docs/e2e-testing.md). The API contract gate it depends on (`manage.py export_api_schema` → `frontend/__tests__/lib/apiContract.test.ts`) *is* in `make test`: regenerate the fixture with `make manage CMD=export_api_schema` whenever a request/response model changes.
5. Manual smoke test of Analysis Studio + Knowledge Graph in the browser (against `make dev`)
6. **Visual evidence gate** — any change to `frontend/` or `lsat-static/` that a user could
*see* ships with screenshots. See [docs/ui-ux-review.md](docs/ui-ux-review.md) §"Visual evidence" for what to capture and how. A passing `ux_audit.py` is not evidence: it checks landmarks and contracts, not whether the screen reads correctly. **Enforced in CI**: the `Visual Evidence Gate` job fails a PR touching those paths unless the body carries an image or the diff adds a file under `docs/images/`; label the PR `no-visual-change` to opt out when there is genuinely nothing to see.
7. **Continuous-evolution gate** ([docs/constitution.md](docs/constitution.md) §11):
   - `tasks.md` for the spec must end with a populated `## Follow-ups Discovered` section.
   - Each follow-up is mirrored into [BACKLOG.md](BACKLOG.md) with a `BL-YYYYMMDD-NN` id.
   - `make lint-specs` (host — `spec_validator.py`, `backlog_lint.py`, `ux_audit.py`, then `pytest tests/test_evolve_audit.py`) exits 0.
   - PR description copies the new BACKLOG bullets so reviewers can see what the next agent is set up to inherit.

**LegalBench Integration**  
We maintain a living evaluation harness. New reasoning capabilities must improve or maintain score on relevant LegalBench tasks.

**Self-Evolution Loop**  
This repo is designed to grow itself. Every `/implement` cycle ends by recording follow-ups; every `/specify` cycle starts by claiming items from [BACKLOG.md](BACKLOG.md). See §11 of the constitution.

---

## Important Context Files (Read These First)

When starting work, read in this order:
1. [docs/philosophy.md](docs/philosophy.md) — What we believe legal data is + the P1–P7 obligations that follow
2. [docs/architecture.md](docs/architecture.md) — Full system diagram + component responsibilities
3. [docs/agent-roles.md](docs/agent-roles.md) — Responsibilities + tool requirements for each agent
4. [PRD.md](PRD.md) — Full product requirements
5. [Law_AI_Proposal.md](Law_AI_Proposal.md) — Original technical proposal with Mermaid diagrams
6. [docs/related-github-repos.md](docs/related-github-repos.md) — Upstream OSS we integrate with
7. [docs/ui-ux.md](docs/ui-ux.md) — Every user-facing surface, the two styling idioms, and the design-system contract

`docs/data-model.md`, `docs/data-sources.md`, `docs/legalbench.md`, [docs/lsat-library.md](docs/lsat-library.md) (the LSAT knowledge library's authoring dialect and maintenance loop), [docs/lsat-synthesis.md](docs/lsat-synthesis.md) (the deterministic item-synthesis engine and its proof gates), and [docs/django-conventions.md](docs/django-conventions.md) (Django app-layout and coding conventions) all exist — keep them current as the schema, sources, eval harness, and conventions evolve rather than skipping the documentation step.

---

## Communication Style for AI Agents

When responding to user requests:
- Always start with **"Understood. Implementing [feature] following Law AI principles..."**
- Reference the exact file paths you will modify
- Show the key code change (diff style) before writing files
- End with **"Ready for review. LegalBench delta: +X% on relevant tasks"** when applicable

**Never**:
- Bypass `LLM_PROVIDER_CHAIN` to call a provider transport directly, or add a model vendor beyond Anthropic / xAI / Ollama (OpenAI, Gemini, …) to the product runtime without a constitution §1 amendment
- Bypass the provenance/audit layer
- Create nodes without `source` and `confidence` properties
- Ignore HITL requirements for ingestion or high-stakes analysis
- Rank or assert legal authority by citation volume as if it measured correctness
- State a legal proposition without naming the authority that issued it

---

**This file is the single source of truth for all coding agents working on Law AI.**  
Update it when architecture or standards evolve.
## Claude Code notes

Moved verbatim from the former `CLAUDE.md` on 2026-10-20 (decision D4: one canonical agent file). Fold these into the sections above when you next touch them.


This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Canonical guide

[AGENTS.md](AGENTS.md) is the single source of truth for coding standards, tech stack, project structure, and quality gates. Read it before non-trivial work. This file only captures the operational essentials and the things that are easy to get wrong. Do not duplicate AGENTS.md content here.

> Orchestration policy: GitHub Copilot and Claude Code are both sanctioned dev surfaces ([AGENTS.md](AGENTS.md) § "Development Orchestration", [docs/constitution.md](docs/constitution.md) §1). Cursor, Continue.dev, Aider, Codex, and Gemini CLI remain forbidden.
>
> Runtime LLM policy (constitution §1, amended 2026-08-11 and 2026-09-04): the product runtime is the ordered chain in `LLM_PROVIDER_CHAIN` — Claude over OAuth, then Claude over `ANTHROPIC_API_KEY`, then xAI Grok over a subscription OAuth token, then local Ollama — implemented in `law_ai.core.llm`. Claude is the default. Local-first remains supported by pinning `LLM_PROVIDER_CHAIN=ollama`, which is **required** for data under a confidentiality obligation that forbids third-party processing — note the default chain now has **two** third-party tiers. The xAI tier ([ADR 0007](docs/adr/0007-xai-runtime-provider.md), spec 050) is inert until an operator runs `make xai-login`; it has no API-key mode. Adding any further vendor (OpenAI, Gemini, …) needs a further constitution amendment.

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
| Spec/backlog gates | `make lint-specs` (host, no container; needs `pytest` on the host interpreter) |

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

Multi-agent legal-intelligence platform. Django 5 (ASGI/daphne) + DRF + Channels + Celery backend; Next.js 15 (App Router) frontend; Neo4j knowledge graph + Postgres + Redis; **the runtime LLM is the provider chain in `law_ai/core/llm/`** — Claude first, local Ollama last (independent from whatever agent edits the code).

Backend lives in `backend/law_ai/` (the Django project package). Each Django app owns one `/api/*` router:
- `agents_runtime/` — all agent logic: `crews/` (CrewAI), `graphs/` (LangGraph workflows, incl. `ChatProviderChain`-backed `LegalWorkflow`), `tools/` (`GraphRAGRetriever` in `graph_rag.py` — hybrid lexical fulltext + `CITES` graph-expansion retrieval), `prompts/` (versioned `*.v<N>.md`). `core/neo4j/` holds the lower-level citation resolver + raw Cypher queries the tools build on.
- `agentsapi/` — DRF routers + Channels consumers at `/api/agents/*` (real-time agent streaming over WebSockets).
- **The ocrmd plug-in** (spec 055; `ingestionapp/services/ocrmd_plugin.py`): [ocrmd](https://github.com/bamr87/ocrmd)
  is a webcam scanner that reads a book page twice (local OCR + a vision model) and reconciles the two; it hands pages to receivers through a small contract — `GET` a *descriptor* of the options a door takes, `POST` an *envelope* (reconciled text + provenance + the book's catalogue entry + options). Law AI opens two doors, both answering `summary`/`items`/`warnings`: **`POST /api/lsat/intake/ocr`** (`lsat/services/ocr_intake.py`) — `LSATSourceExtractor` transcribes questions out of the text and they go through the **same** factory gates and into the same HITL queue as generated ones, no shortcut to the bank; the extractor leaves a field empty rather than write the part that was not captured, and every draft is scored for **grounding** (share of its content words in the page text, the *minimum* over stem and all five choices) — below 0.75 it is dropped before a reviewer sees it. **`POST /api/matters/<slug>/intake/ocrmd`** (`matters/services/scanned.py`) — the page becomes a `document` artifact on the caller's own matter, `source=ocrmd`, idempotent on page id + region, never authority. Every proposal and artifact carries the page id (the sha256 of the processed image), so a reviewer can always get back to the photograph. The scanner also installs as an optional library (`INSTALL_OCRMD=1`, `ENABLE_OCRMD`): `POST /api/ingestion/ocrmd/scan` OCRs an upload here **OCR-only** — the embedded scanner never calls a model, because that call would bypass `core.llm` — and says so on every page it routes.
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

- Log every LLM call, tool use, and retrieval through `core.provenance` — never bypass the audit layer. Model calls go through `law_ai.core.llm` (which writes the `llm_call` event); never call a provider transport directly from a feature module.
- The LegalBench harness stays pinned to Ollama — routing eval through the chain would make benchmark numbers non-comparable.
- Graph nodes always carry `source` + `confidence`; never hard-delete (soft-delete with `archived_at`).
- HITL approval gates are required on ingestion and high-stakes analysis (`ENABLE_HUMAN_APPROVAL_GATES`).
- New agents implement `run(input: dict) -> dict` (Pydantic output) and ship a test under `backend/tests/agents/`.
- Autonomy targets (`make autonomy-run KIND=… SOURCE=…`) require `AUTONOMY_ENABLED=true` and a source in `AUTONOMY_ALLOWED_SOURCES`.
