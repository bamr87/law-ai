# Law AI — VS Code Workspace

**AI-Native Development Environment for Building the Open Legal Intelligence Platform**

This workspace is configured for **GitHub Copilot and Claude Code** as the sanctioned AI development orchestrators (Copilot Chat / Copilot Edits / the GitHub Copilot coding agent, and the Claude Code CLI / IDE extensions). That dev-orchestration layer is independent of the **product runtime** — the LLM that actually answers end users. The runtime is an ordered provider chain (`LLM_PROVIDER_CHAIN`), implemented in `backend/law_ai/core/llm/`: Anthropic Claude is the default (subscription OAuth token, then `ANTHROPIC_API_KEY`), with local Ollama as the last-tier fallback. Pin `LLM_PROVIDER_CHAIN=ollama` for local-only operation — required for any data under a confidentiality obligation that forbids third-party processing. See [docs/constitution.md](docs/constitution.md) §1 for the full policy.

## Stack

- **Backend** — Django 5 (ASGI via daphne), DRF, Channels (WebSocket agent streaming), Celery/Redis (async ingestion), Neo4j (knowledge graph) + Postgres + Redis.
- **Agents** — CrewAI crews and LangGraph state graphs (`backend/law_ai/agents_runtime/`), running on `ChatProviderChain`, a LangChain `BaseChatModel` wrapping the provider chain above.
- **Frontend** — Next.js 16 App Router, TypeScript strict, Tailwind v4, Cytoscape.js. Two UI apps (`frontend/`, `lsat-static/`); no shadcn/ui on disk — see [docs/ui-ux.md](docs/ui-ux.md) and [spec 039](specs/039-design-system/spec.md).
- **Infra** — Docker Compose locally, GitHub Actions in CI.

This is a quick orientation, not the authoritative reference — see [AGENTS.md](AGENTS.md) for the locked tech-stack table and standards.

## Quick Start (5 minutes to running)

```bash
# 1. Clone / open this folder
git clone https://github.com/bamr87/law-ai.git
cd law-ai

# 2. Copy environment
cp .env.example .env

# 3. Start everything (recommended)
make dev
# or: docker compose up --build

# 4. Open http://localhost:3000 (frontend) and http://localhost:8000 (API — see below)
```

Without Claude credentials in `.env`, the provider chain falls through to the local Ollama tier automatically — you'll still get answers, just from the local model. Add `CLAUDE_CODE_OAUTH_TOKEN` (from `claude setup-token`) or `ANTHROPIC_API_KEY` to `.env` to use Claude instead.

There's no interactive API schema/docs UI yet — `http://localhost:8000/` returns a root status JSON, and the real routes are under `/api/agents`, `/api/analysis`, `/api/graph`, `/api/lsat` (see `backend/law_ai/urls.py`).

**Editing without a local Python/Node toolchain**: every dev/test/lint command is sanctioned only via `make …` / `docker compose …` (see [AGENTS.md](AGENTS.md)'s Docker-First Workflow) — there is no supported host-native alternative. If you want your editor's language server wired to the same environment CI uses, open this repo in the provided [Dev Container](.devcontainer/devcontainer.json) ("Dev Containers: Reopen in Container").

## How to Work with AI Agents Here (Copilot or Claude Code)

### Supported Surfaces

| Surface | Best For | How to Use |
|---------|----------|------------|
| **Copilot Chat — Ask mode** | Q&A about the codebase | `@workspace` + reference [AGENTS.md](AGENTS.md) |
| **Copilot Chat — Edit / Agent mode** | Multi-file feature work, running [/specify](prompts/specify.md) → [/implement](prompts/implement.md) chains | Open the chat panel, select Agent mode, type `/specify <intent>` or `/evolve` |
| **GitHub Copilot Coding Agent** | Hands-off cloud cycles | Assign an issue (e.g. the one auto-filed by [.github/workflows/evolve.yml](.github/workflows/evolve.yml)) to `@copilot` |
| **Inline Copilot completions** | Local typing assistance | Always-on; respects [.github/copilot-instructions.md](.github/copilot-instructions.md) |
| **Claude Code (CLI / IDE)** | Multi-file feature work, running the AO-SDLC chain + `/evolve` | Open Claude Code in the repo; it auto-loads [CLAUDE.md](CLAUDE.md). Type `/specify <intent>` or `/evolve` |

Other AI coding tools (Cursor, Continue.dev, Aider, Codex, Gemini CLI) are **not supported** — do not add their config files. Agent prompting lives in [prompts/](prompts/), with surface-specific guides in [.github/copilot-instructions.md](.github/copilot-instructions.md) (Copilot) and [CLAUDE.md](CLAUDE.md) (Claude Code).

### The Golden Rule

**Always start by telling your agent:**

> "Read AGENTS.md, docs/constitution.md, and docs/architecture.md first. Then implement [feature] following Law AI standards."

Copilot Chat (Agent mode) auto-loads [.github/copilot-instructions.md](.github/copilot-instructions.md) and Claude Code auto-loads [CLAUDE.md](CLAUDE.md); both already point to those files.

## Workspace Highlights

- **AGENTS.md** — The constitution for all AI agents working on this project
- **`.vscode/tasks.json`** — One-click tasks for Docker, testing, LegalBench eval, ingestion
- **`.vscode/settings.json`** — Strict formatting + type checking enforced on save
- **`prompts/`** — Reusable prompt templates for the AO-SDLC chain (`specify`, `plan`, `tasks`, `implement`, `evolve`, `new-agent`)
- **`docs/`** — [architecture.md](docs/architecture.md), [data-model.md](docs/data-model.md), and [agent-roles.md](docs/agent-roles.md), plus the [constitution](docs/constitution.md) (Mermaid diagrams included)
- **`lsat-static/`** — A separate, independently-built Next.js static export of the LSAT practice module (deployed to GitHub Pages, zero server). It reads a `content.json` snapshot produced from the Dockerized backend via `make lsat-export`; it's not part of the `make dev` stack.
- **Pre-configured Docker stack** — `backend` + `worker` (Celery) + `frontend` + `postgres` + `neo4j` + `ollama` + `redis` + `phoenix` (OTEL tracing) — see `docker-compose.yml`

## Common Workflows

| Goal                              | Command / Task |
|-----------------------------------|----------------|
| Full local environment            | `make dev` (task: `Docker: Start Full Stack`) |
| Implement new agent role          | `/new-agent` (see [prompts/new-agent.md](prompts/new-agent.md)) |
| Add new feature                   | AO-SDLC chain — `/specify` → `/clarify` → `/plan` → `/tasks` → `/implement` |
| **Run all tests + coverage**      | `make test` / `make test-coverage` (task: `Docker: Run All Tests` / `Docker: Coverage Report`) |
| Run legal reasoning eval          | `make test-legalbench` (task: `Docker: LegalBench Eval`) |
| Ingest sample data                | task: `Docker: Ingest Sample Data` |
| Reset everything (fresh start)    | task: `Docker: Reset Local DBs (Dangerous)` |

**Testing Philosophy**: every PR must pass unit tests with ≥75% coverage. Integration tests (real Neo4j/Postgres) and the full LegalBench suite run nightly ([.github/workflows/nightly-tests.yml](.github/workflows/nightly-tests.yml)), or on-demand on a PR carrying the `reasoning-change` label.

## Project Status

Law AI is under active spec-driven development — there is no fixed roadmap snapshot maintained here, because it drifts. For what's shipped, in flight, and planned:

- **Shipped features**: numbered spec packages under [`specs/`](specs/) (each `spec.md` + `plan.md` + `tasks.md`), the actual source of truth for what exists.
- **What's next**: the `## Open` section of [BACKLOG.md](BACKLOG.md).
- **LegalBench regression gate**: `backend/law_ai/eval/legalbench.py`, run via `make test-legalbench` / `make legalbench-baseline`.

## Contributing

All contributions (human or AI-generated) must pass:
1. `ruff + black + mypy` checks (`make lint` / `make typecheck`)
2. **Full test suite** (`make test`, task: `Docker: Run All Tests`) with ≥75% coverage
3. Relevant LegalBench tasks — required on PRs labeled `reasoning-change`, nightly otherwise
4. Manual review of agent traces for auditability

See [AGENTS.md](AGENTS.md) → "Evaluation & Quality Gates (Mandatory)" and "Testing Standards (Mandatory)" sections.

---

**This workspace is designed so that a well-prompted AI coding agent can build 70-80% of Law AI autonomously while maintaining legal-grade quality and auditability.**

Welcome to the future of open legal AI. Let's build it together.