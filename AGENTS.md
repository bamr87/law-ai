# LawGraph AI — Agent Coding Instructions

**Project Mission**  
Build the world's first fully open-source, agent-orchestrated legal intelligence platform that combines multi-agent workflows, Neo4j knowledge graphs, GraphRAG, and interactive visualizations to help lawyers and law students master complex legal content.

**Workflow & Standards**
- This repo follows a spec-driven workflow ([AO-SDLC](docs/AO-SDLC.md) Level 2). Every non-trivial change starts with a spec under [specs/](specs/) using [/specify](prompts/specify.md) → [/clarify](prompts/clarify.md) → [/plan](prompts/plan.md) → [/tasks](prompts/tasks.md) → [/implement](prompts/implement.md). For autonomous "pick the next thing and ship it" runs, use [/evolve](prompts/evolve.md).
- All specs and PRs must satisfy [docs/constitution.md](docs/constitution.md). CI enforces spec consistency via [scripts/spec_validator.py](scripts/spec_validator.py).

## Development Orchestration (GitHub Copilot Only)

**The only sanctioned AI development surface for this repo is GitHub Copilot.** This covers:

- **Copilot Chat** in VS Code — Ask, Edit, and Agent modes. Agent mode runs the AO-SDLC chain and `/evolve`.
- **Inline Copilot completions** in any JetBrains/VS/VS Code surface authenticated to the same GitHub account.
- **GitHub Copilot coding agent** — the cloud agent that picks up issues assigned to `@copilot` (used by [.github/workflows/evolve.yml](.github/workflows/evolve.yml)).
- **Copilot Code Review** on pull requests.

All repo-level instructions for these surfaces live in [.github/copilot-instructions.md](.github/copilot-instructions.md) and the prompt templates under [prompts/](prompts/). Path-scoped overrides go in `*.instructions.md` files following [Copilot custom instructions docs](https://docs.github.com/copilot).

**Forbidden in this repo**: Cursor, Continue.dev, Claude Code, Aider, Codex, Gemini CLI, or any other third-party coding agent. Do not commit their config files (`.cursorrules`, `.continuerc.json`, `.aider.conf.yml`, etc.).

**Important distinction**: This restriction applies to **how the codebase is built**. The **product runtime LLM** that serves end users is still Ollama (local-first, open weights) per [docs/constitution.md](docs/constitution.md) §1. The two layers are independent:

| Layer | Tool | Why |
|-------|------|-----|
| Dev orchestration (writing/refactoring this repo) | GitHub Copilot only | Single sanctioned surface; consistent custom instructions; CI integration |
| Product runtime (what the deployed app uses to answer legal questions) | Ollama (open-source models) | Constitution §1: open-source, privacy-first, local-first |


**Core Principles for All Code Changes**
- **Open Source First**: Every component must be MIT/AGPL compatible. No proprietary dependencies.
- **Privacy by Default**: Local-first (Ollama + local DBs). Cloud is optional.
- **Auditability**: Every agent decision, prompt, tool call, and retrieval must be logged with full provenance.
- **Legal Accuracy**: All outputs must be grounded in retrieved sources + citations. Use LegalBench for regression testing.
- **Graph-Native Thinking**: Prefer Neo4j Cypher traversals over pure vector search when relationships matter (precedents, citations, doctrines).
- **Human-in-the-Loop (HITL)**: Critical paths (ingestion of new cases, high-stakes analysis) require explicit approval gates.

---

## Quick Reference (Run These, Don't Reinvent)

Use the [Makefile](Makefile) targets or VS Code tasks in [.vscode/tasks.json](.vscode/tasks.json) — do not invent ad-hoc commands.

| Goal | Command | VS Code Task |
|------|---------|--------------|
| Full stack (Docker) | `make dev` | `Start Full Stack (Docker)` |
| Backend only | `python manage.py runserver 0.0.0.0:8000` (in `backend/`) | `Start Backend (Dev)` |
| All tests | `make test` | `Run All Tests` |
| Backend tests + coverage | `cd backend && pytest --cov=app` | `Run Coverage Report` |
| Lint + format | `make lint` | `Format & Lint All` |
| Type-check | — | `Type Check (Python + TS)` |
| LegalBench eval | — | `Run LegalBench Eval` |
| Reset local DBs | — | `Reset Local DBs (Dangerous)` |

Project status, tooling rationale, and onboarding live in [README.md](README.md). Do not duplicate that content here.

---

## Tech Stack (Non-Negotiable)

**Backend**
- Python 3.11+
- Django 5 (ASGI via daphne) + Django REST Framework + Channels + Celery + Pydantic v2 (domain layer)
- **CrewAI** (role-based crews) + **LangGraph** (stateful workflows)
- Neo4j Community + official Python driver
- PostgreSQL + asyncpg
- Chroma or Weaviate (vector)
- Ollama (primary LLM) — support Llama 3.1 70B, Mistral, Phi-3, Qwen2.5
- Eyecite + Blackstone (spaCy) for legal NLP

**Frontend**
- Next.js 15 (App Router) + TypeScript
- Tailwind + shadcn/ui
- Cytoscape.js + React Flow for graphs
- TanStack Query + WebSockets for real-time agent streaming

**Infrastructure**
- Docker Compose (full local stack)
- GitHub Actions for CI (LegalBench eval, lint, type-check)

---

## Project Structure (Target — Some Subdirs Are Planned)

This is the canonical layout, mirroring the actual `backend/lawgraph/` Django package and the `frontend/` Next.js app. When adding new code, place it in the matching directory; do not invent new top-level locations.

```
law-ai/                                 # workspace root (GitHub slug stays `law-ai`)
├── backend/
│   ├── manage.py
│   ├── pyproject.toml
│   └── lawgraph/                       # Django project package (was `app/` pre-rebrand)
│       ├── __init__.py
│       ├── asgi.py                     # ASGI entrypoint (daphne) + Channels routing
│       ├── wsgi.py
│       ├── celery.py                   # Celery("lawgraph") app
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
│   ├── components/                     # Reusable UI (GraphViewer, AgentTrace, AgentDashboard, …)
│   ├── lib/                            # Typed API client + utils
│   ├── mocks/                          # MSW handlers for tests
│   └── __tests__/                      # Vitest + RTL component tests
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
- Strict type hints + `mypy --strict`
- All public functions must have docstrings with examples
- Agent prompts must be in `backend/lawgraph/agents_runtime/prompts/` as `.md` or `.txt` files (versioned)

### TypeScript / React
- Strict TypeScript (`"strict": true`)
- Prefer server components + React Server Actions where possible
- All graph interactions must go through typed API routes (no direct Neo4j from client)

### Neo4j / Graph
- Use Cypher for all relationship-heavy queries
- Always return provenance (`source_url`, `ingest_timestamp`, `agent_version`)
- Never delete nodes — use soft-delete + `archived_at` for audit

### Agent Development Rules
1. **New Agent Role** → Create in `backend/lawgraph/agents_runtime/crews/` or `graphs/`
2. **Must implement**:
   - `run(input: dict) -> dict` with structured output (Pydantic)
   - Logging of every LLM call + tool use via `core.provenance`
   - Optional `human_approval_required: bool`
3. **Prompts** must reference LegalBench tasks when applicable
4. **Evaluation** — every new agent must have at least one test in `backend/tests/agents/` that runs against LegalBench subset

### Testing Standards (Mandatory)
- **Backend**: pytest + pytest-asyncio + pytest-cov (≥75% coverage)
- **Frontend**: Vitest + React Testing Library + MSW for API mocking
- **All new features** must include:
  - Unit test (fast, mocked)
  - Integration test (uses real Neo4j/Postgres via docker)
  - LegalBench regression test (if reasoning changes)
- Run `Run All Tests` task or `pytest && npm test` before every PR
- Coverage reports are generated in `htmlcov/` and `coverage/`

---

## How to Implement Common Tasks (Prompt Templates)

### 1. Add a New Agent Crew Member
See `prompts/new-agent.md` for the exact prompt template.

### 2. Extend the Knowledge Graph Schema
- Update `docs/data-model.md` (create if it does not yet exist)
- Add migration in `backend/lawgraph/core/neo4j/migrations/`
- Update `backend/lawgraph/core/models.py`
- Add corresponding Cypher helper in `backend/lawgraph/core/neo4j/queries.py`

### 3. Add New Public Data Source
- Create new client in `backend/lawgraph/ingestionapp/`
- Add to the `Ingestion Scout` crew (see [docs/agent-roles.md](docs/agent-roles.md))
- Document the source in `docs/data-sources.md`

### 4. Improve GraphRAG Retrieval
- Edit `backend/lawgraph/agents_runtime/tools/graph_rag.py`
- Add new retriever strategy
- Run `Run LegalBench Eval` task before and after; record the delta in the PR description

### 5. Add Feature to Frontend
- Use [prompts/implement-feature.md](prompts/implement-feature.md)
- Always add the corresponding API route in the matching backend module first (`backend/lawgraph/{agentsapi,analysis,graph,lsat}/`)
- Include loading states + error boundaries
- Co-locate a Vitest test under `frontend/__tests__/`

---

## Evaluation & Quality Gates (Mandatory)

Before any PR:
1. `make lint` (ruff + black + frontend lint) and `Type Check (Python + TS)` task
2. `make test` (backend pytest + frontend vitest) — must keep ≥65% coverage
3. `Run LegalBench Eval` task when reasoning logic changed
4. Manual smoke test of Analysis Studio + Knowledge Graph in the browser
5. **Continuous-evolution gate** ([docs/constitution.md](docs/constitution.md) §11):
   - `tasks.md` for the spec must end with a populated `## Follow-ups Discovered` section.
   - Each follow-up is mirrored into [BACKLOG.md](BACKLOG.md) with a `BL-YYYYMMDD-NN` id.
   - `python scripts/spec_validator.py` and `python scripts/backlog_lint.py` exit 0.
   - PR description copies the new BACKLOG bullets so reviewers can see what the next agent is set up to inherit.

**LegalBench Integration**  
We maintain a living evaluation harness. New reasoning capabilities must improve or maintain score on relevant LegalBench tasks.

**Self-Evolution Loop**  
This repo is designed to grow itself. Every `/implement` cycle ends by recording follow-ups; every `/specify` cycle starts by claiming items from [BACKLOG.md](BACKLOG.md). See §11 of the constitution.

---

## Important Context Files (Read These First)

When starting work, read in this order:
1. [docs/architecture.md](docs/architecture.md) — Full system diagram + component responsibilities
2. [docs/agent-roles.md](docs/agent-roles.md) — Responsibilities + tool requirements for each agent
3. [PRD.md](PRD.md) — Full product requirements
4. [LawGraph_AI_Proposal.md](LawGraph_AI_Proposal.md) — Original technical proposal with Mermaid diagrams
5. [docs/related-github-repos.md](docs/related-github-repos.md) — Upstream OSS we integrate with

`docs/data-model.md`, `docs/data-sources.md`, and `docs/legalbench.md` are referenced throughout this file but may not yet exist — create them when you do work that warrants them rather than skipping the documentation step.

---

## Communication Style for AI Agents

When responding to user requests:
- Always start with **"Understood. Implementing [feature] following LawGraph principles..."**
- Reference the exact file paths you will modify
- Show the key code change (diff style) before writing files
- End with **"Ready for review. LegalBench delta: +X% on relevant tasks"** when applicable

**Never**:
- Suggest closed-source models or services as primary
- Bypass the provenance/audit layer
- Create nodes without `source` and `confidence` properties
- Ignore HITL requirements for ingestion or high-stakes analysis

---

**This file is the single source of truth for all coding agents working on LawGraph AI.**  
Update it when architecture or standards evolve.