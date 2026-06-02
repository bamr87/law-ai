# LawGraph AI — VS Code Workspace

**✅ FINALIZED — Ready for Development**

**AI-Native Development Environment for Building the Open Legal Intelligence Platform**

This workspace is configured for **GitHub Copilot and Claude Code** as the sanctioned AI development orchestrators (Copilot Chat / Copilot Edits / the GitHub Copilot coding agent, and the Claude Code CLI / IDE extensions). The product runtime LLM is still local-first via Ollama — see [docs/constitution.md](docs/constitution.md) §1.

> **Status**: Core scaffolding, testing framework, agent stubs, API layer, and frontend dashboard are complete. Run `docker compose up` to start developing immediately.

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

# 4. Open http://localhost:3000 (frontend) and http://localhost:8000/docs (API)
```

**Alternative (local without Docker)**:
```bash
make setup
make dev-backend   # in one terminal
make dev-frontend  # in another
```

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

> "Read AGENTS.md, docs/constitution.md, and docs/architecture.md first. Then implement [feature] following LawGraph standards."

Copilot Chat (Agent mode) auto-loads [.github/copilot-instructions.md](.github/copilot-instructions.md) and Claude Code auto-loads [CLAUDE.md](CLAUDE.md); both already point to those files.

## Workspace Highlights

- **AGENTS.md** — The constitution for all AI agents working on this project
- **`.vscode/tasks.json`** — One-click tasks for Docker, testing, LegalBench eval, ingestion
- **`.vscode/settings.json`** — Strict formatting + type checking enforced on save
- **`prompts/`** — Reusable prompt templates (`new-agent.md`, `implement-feature.md`)
- **`docs/`** — Architecture, data model, and agent specifications (Mermaid diagrams included)
- **Pre-configured Docker stack** — Postgres + Neo4j + Ollama + Redis + Backend + Frontend

## Common Workflows

| Goal                              | Command / Task |
|-----------------------------------|----------------|
| Full local environment            | `Start Full Stack (Docker)` task |
| Implement new agent role          | Use `prompts/new-agent.md` |
| Add new feature                   | Use `prompts/implement-feature.md` |
| **Run all tests + coverage**      | `Run All Tests` or `Run Coverage Report` task |
| Run legal reasoning eval          | `Run LegalBench Eval` task |
| Ingest 500 sample cases           | `Ingest Sample Data` task |
| Reset everything (fresh start)    | `Reset Local DBs (Dangerous)` task |

**Testing Philosophy**: Every PR must pass unit + integration + LegalBench tests with ≥75% coverage.

## Project Status (as of April 2026)

- **Current Phase**: MVP development (ingestion + core agent crews + basic graph UI)
- **LegalBench Baseline**: TBD (we will establish after first agents are implemented)
- **Target for v0.1**: 5 working agent roles + interactive Cytoscape graph + basic LSAT module

## Contributing

All contributions (human or AI-generated) must pass:
1. `ruff + black + mypy` checks
2. **Full test suite** (`Run All Tests` task) with ≥75% coverage
3. Relevant LegalBench tasks
4. Manual review of agent traces for auditability

See `AGENTS.md` → "Quality Gates" and "Testing Standards" sections.

---

**This workspace is designed so that a well-prompted AI coding agent can build 70-80% of LawGraph AI autonomously while maintaining legal-grade quality and auditability.**

Welcome to the future of open legal AI. Let's build it together.