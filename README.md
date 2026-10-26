# Law AI

> An open legal-intelligence platform for prospective law students, current law students and practicing lawyers: LSAT preparation, guided legal study, and legal analysis grounded in a citation knowledge graph — with provenance on every answer and a human in the loop where it matters.

[![CI](https://github.com/bamr87/law-ai/actions/workflows/ci.yml/badge.svg)](https://github.com/bamr87/law-ai/actions/workflows/ci.yml) [![Live site](https://img.shields.io/badge/live-bamr87.github.io%2Flaw--ai-2ea44f)](https://bamr87.github.io/law-ai/)

## Who it is for

| Audience | What Law AI gives them |
|---|---|
| **Prospective law students** | The LSAT lab: logical reasoning, reading comprehension, logic games and argumentative writing, with solving aids and playbooks, a continuous curriculum, question diagnosis and a knowledge library. Also published as a zero-server static site ([bamr87.github.io/law-ai](https://bamr87.github.io/law-ai/), built from `lsat-static/`). |
| **Current law students** | The legal-journey platform: matters, scanned-page intake from a book (the [ocrmd](https://github.com/bamr87/ocrmd) plug-in), an analysis studio, and agent traces that show how an argument is built, step by step. |
| **Practicing lawyers** | IRAC analysis grounded in retrieved authority, precedent hunting, a Neo4j citation knowledge graph (GraphRAG: lexical retrieval plus `CITES` traversal), an audit trail for every model call and retrieval, human-approval gates on ingestion and high-stakes analysis, and a fully local mode (`LLM_PROVIDER_CHAIN=ollama`) for privileged data. |

Every output names the authority it rests on, labels asymmetry rather than filtering by it, and refuses honestly when it cannot ground an answer ([docs/philosophy.md](docs/philosophy.md), [docs/constitution.md](docs/constitution.md) §13).

## How it works

- **Backend** — Django 5 (ASGI via daphne), DRF, Channels (WebSocket agent streaming), Celery/Redis (async ingestion), Neo4j (knowledge graph) + Postgres + Redis. Each Django app owns one `/api/*` router: `agentsapi`, `analysis`, `graph`, `lsat`, `matters`, `ingestionapp`.
- **Agents** — CrewAI crews and LangGraph state graphs (`backend/law_ai/agents_runtime/`), running on `ChatProviderChain`, a LangChain `BaseChatModel` over the product's **LLM provider chain** (`backend/law_ai/core/llm/`): Anthropic Claude (subscription OAuth token, then `ANTHROPIC_API_KEY`), then xAI Grok (subscription OAuth, `make xai-login`), then local Ollama as the last tier. Pin `LLM_PROVIDER_CHAIN=ollama` for local-only operation — required for any data under a confidentiality obligation that forbids third-party processing ([docs/constitution.md](docs/constitution.md) §1, [docs/llm-provider-chain.md](docs/llm-provider-chain.md)).
- **Frontend** — Next.js 16 App Router, TypeScript strict, Tailwind v4, Cytoscape.js. Two UI apps (`frontend/`, `lsat-static/`) on a first-party design system ([docs/ui-ux.md](docs/ui-ux.md)).
- **Infra** — Docker Compose locally (Postgres, Neo4j, Redis, Ollama, Phoenix tracing), GitHub Actions in CI.

Full architecture: [docs/architecture.md](docs/architecture.md) · agents: [docs/agent-roles.md](docs/agent-roles.md) · data model: [docs/data-model.md](docs/data-model.md) · product requirements: [docs/prd.md](docs/prd.md).

## Quick start (5 minutes to running)

```bash
git clone https://github.com/bamr87/law-ai.git
cd law-ai
cp .env.example .env
make dev            # or: docker compose up --build
# frontend: http://localhost:3000   API: http://localhost:8000 (routes under /api/agents, /api/analysis, /api/graph, /api/lsat)
```

Without Claude credentials in `.env` the provider chain falls through to the local Ollama tier automatically — you still get answers, from the local model. Add `CLAUDE_CODE_OAUTH_TOKEN` (from `claude setup-token`) or `ANTHROPIC_API_KEY` to use Claude.

**Everything runs in Docker.** Every dev/test/lint command is `make …` or `docker compose …`; there is no supported host-native toolchain. To wire your editor's language server to the same environment CI uses, open the repo in one of the Dev Containers (**Law AI (backend)**: [.devcontainer/devcontainer.json](.devcontainer/devcontainer.json); **Law AI (frontend)**: [.devcontainer/frontend/devcontainer.json](.devcontainer/frontend/devcontainer.json)).

```bash
make test           # backend pytest + frontend vitest
make lint           # ruff + black + eslint
make typecheck      # mypy --strict (ratcheted) + tsc
make lint-specs     # the spec/backlog gate (the fleet's, via tools/fleet-kit.sh) + the UI shell audit
make test-legalbench
```

## Project structure

| Path | What it is |
|---|---|
| `backend/` | Django (ASGI) API, agents, the LLM provider chain, ingestion, the LSAT content factory |
| `frontend/` | Next.js App Router platform app |
| `lsat-static/` | Static LSAT study site published to GitHub Pages (`make lsat-export` snapshots the bank) |
| `lawmode/` | The imported [bamr87/lawmode](https://github.com/bamr87/lawmode) legal reviewer for developers (its own README and tooling; runs from inside `lawmode/`) |
| `specs/`, `BACKLOG.md` | The spec packages and the append-only backlog — the record of what shipped and what is next |
| `docs/` | Architecture, data model, agent roles, the constitution, ADRs, the PRD, runbooks; `docs/history/` keeps the original proposal and planning notes |
| `infra/`, `docker-compose*.yml` | Local stack: Postgres, Redis, Neo4j, Ollama and observability |
| `scripts/`, `tools/`, `tests/` | Repo-level stdlib scripts (UI audit, visual-evidence gate, mypy ratchet, LegalBench and Ollama helpers), hub-vendored tooling (`fleet-kit.sh`, `unwrap-prose.py`), and the repo-wide structural tests |

## Working on Law AI

[AGENTS.md](AGENTS.md) is the canonical guide for humans and AI agents alike: the locked stack, the layout, the Docker-first rule, the coding and testing standards, and the gates every PR must pass. GitHub Copilot and Claude Code are the sanctioned AI development surfaces; other coding agents (Cursor, Continue.dev, Aider, Codex, Gemini CLI) are not supported and their config files are rejected at review.

Development follows the **fleet's spec-driven loop** rather than a workflow of this repo's own: a non-trivial change starts as a spec package under `specs/` (`/spec-driven:specify` → `:clarify` → `:plan` → `:tasks` → `:implement`, the `spec-driven` Claude Code plugin from the [bamr87 hub](https://github.com/bamr87/bamr87/tree/main/templates/spec-driven)), the spec and backlog gates run by reference in CI (`Spec Drift Gate`) and locally as `make lint-specs`, and every cycle mirrors the follow-ups it discovered into `BACKLOG.md`. [docs/spec-driven.md](docs/spec-driven.md) maps the loop onto this repo and lists which checks block a merge.

All contributions, human or AI-generated, pass `make lint` + `make typecheck`, `make test` (backend coverage ≥75%), `make lint-specs`, the relevant LegalBench tasks (required on PRs labelled `reasoning-change`, weekly otherwise), screenshots for anything a user could see, and a review of the agent traces for auditability.

## Project status

Law AI is under active spec-driven development — there is no fixed roadmap snapshot here, because it drifts. For what is shipped, in flight, and planned:

- **Shipped features**: the numbered spec packages under [`specs/`](specs/) (each `spec.md` + `plan.md` + `tasks.md`), the source of truth for what exists.
- **What's next**: the `## Open` section of [BACKLOG.md](BACKLOG.md).
- **LegalBench regression gate**: `backend/law_ai/eval/legalbench.py`, run via `make test-legalbench` / `make legalbench-baseline`.
- **Changes**: [CHANGELOG.md](CHANGELOG.md) and the [commit history](https://github.com/bamr87/law-ai/commits/main).

## License

[MIT](LICENSE).

---

<!-- bamr87-portfolio-footer -->
Part of the [bamr87 portfolio](https://github.com/bamr87) — browse every project on [Amr's GitHub profile](https://github.com/bamr87).
