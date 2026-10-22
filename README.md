# Law AI

> Open legal intelligence platform: Django, CrewAI and LangGraph agents and a Neo4j knowledge graph, answering with Claude by default and runnable fully local on Ollama.

[![CI](https://github.com/bamr87/law-ai/actions/workflows/ci.yml/badge.svg)](https://github.com/bamr87/law-ai/actions/workflows/ci.yml) [![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE) [![Live site](https://img.shields.io/badge/live-bamr87.github.io%2Flaw--ai-2ea44f)](https://bamr87.github.io/law-ai/)

## Overview

Law AI is an open-source, agent-orchestrated legal-intelligence platform that helps lawyers and law students analyse and master legal content. Agents reason over a Neo4j knowledge graph of cases, statutes and citations with graph-aware retrieval, every model call and retrieval is logged with provenance, and high-stakes steps wait for a human. The design premise is that the legal record reflects who had the resources to shape it, so the system attributes every proposition to its authority and makes that asymmetry visible ([docs/philosophy.md](docs/philosophy.md)).

The model that answers users is an ordered provider chain (`LLM_PROVIDER_CHAIN`, `backend/law_ai/core/llm/`): Claude over a subscription OAuth token, then `ANTHROPIC_API_KEY`, then xAI Grok (after `make xai-login`), then local Ollama. Pin `LLM_PROVIDER_CHAIN=ollama` to keep prompt text on your machine — required for data under a confidentiality obligation that forbids third-party processing ([docs/constitution.md](docs/constitution.md) §1). Which AI tool edits this code is a separate decision: GitHub Copilot and Claude Code are the sanctioned development surfaces.

## Features

- **Analysis Studio** — IRAC-style legal analysis by the LegalAnalyst agent, with persisted runs, LangGraph thread inspection and public share links.
- **Knowledge Graph** — cases and `CITES` edges in Neo4j, explored in a Cytoscape.js viewer; hybrid lexical + graph-expansion retrieval (GraphRAG).
- **Agents and autonomy** — a registry of CrewAI crews and LangGraph workflows, live run streams over WebSockets, and a kill-switched autonomy loop whose drafts wait for review.
- **Matters** — a user-owned workspace for a legal journey: artifacts, authorities, tasks, a calendar, a draft memo and export, including pages scanned with [ocrmd](https://github.com/bamr87/ocrmd).
- **Ingestion with human review** — CourtListener opinions, Colorado statutes and the Denver municipal code land in a quarantine queue that a person approves.
- **LSAT module** — practice drills, a knowledge library, step-by-step solve guides, Argumentative Writing evaluation and a deterministic question-synthesis engine, also published as the static [LSAT practice site](https://bamr87.github.io/law-ai/).
- **Evaluation** — a LegalBench harness with a tracked baseline and a regression gate.
- **Local AI stack** — Ollama tiers from laptop to multi-GPU server, optional vLLM, Phoenix tracing, Prometheus/Grafana and an air-gapped install bundle.

## Quick start

Needs Docker with Compose. Every command runs in containers through the Makefile.

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

Without Claude credentials in `.env`, the chain falls through to the local Ollama tier, so you still get answers from the local model. `http://localhost:8000/` returns a status banner; the API lives under `/api/` — every route is listed in [docs/reference/http-routes.md](docs/reference/http-routes.md), with curl examples in [docs/api-examples.md](docs/api-examples.md).

## Working with AI agents

Open the repo in GitHub Copilot (Chat in Agent mode, or assign an issue to `@copilot`) or Claude Code and start with: "Read AGENTS.md, docs/constitution.md and docs/architecture.md first. Then implement [feature] following Law AI standards." Non-trivial work follows the spec-driven chain `/specify` → `/clarify` → `/plan` → `/tasks` → `/implement`, or `/evolve` to pick the next backlog item and ship it; the prompts are in [prompts/](prompts/) and the loop is described in [docs/ao-sdlc.md](docs/ao-sdlc.md). Other AI coding tools (Cursor, Continue.dev, Aider, Codex, Gemini CLI) are not supported. The rules both surfaces follow are in [AGENTS.md](AGENTS.md).

## LawMode (imported)

[`lawmode/`](lawmode/) is the former [bamr87/lawmode](https://github.com/bamr87/lawmode) repository, imported with its history: an always-on AI legal reviewer for developers that checks code, prompts and commits and gates non-compliant pull requests. It keeps its own README and commands, which run from inside `lawmode/`. Its `LawMode Legal Review` workflow (`lawmode/.github/workflows/lawmode.yml`) does not run from this path and is kept as the reference for porting.

## Documentation

The documentation index is [docs/README.md](docs/README.md): architecture, data model, agent roles, the constitution and philosophy, the LSAT runbooks, the generated [Make-target](docs/reference/make-targets.md) and [route](docs/reference/http-routes.md) references, and the ADRs. What has shipped is recorded in the numbered spec packages under [specs/](specs/); what is next is the `## Open` section of [BACKLOG.md](BACKLOG.md).

## Project structure

| Path | What it is |
|---|---|
| `backend/` | Django (ASGI) API, agents, LLM provider chain and ingestion |
| `frontend/` | Next.js App Router frontend |
| `lsat-static/` | Static LSAT study site published to GitHub Pages |
| `lawmode/` | The imported LawMode legal reviewer |
| `specs/`, `prompts/` | Spec packages and the AO-SDLC prompt chain |
| `docs/` | Architecture, constitution, runbooks, generated reference and ADRs |
| `infra/`, `docker-compose*.yml` | Local stack: Postgres, Redis, Neo4j, Ollama and observability |
| `tests/`, `scripts/`, `tools/` | Repo-level structural tests and operator scripts |

## Development

Everything runs in Docker via `make` — no host Python or Node toolchain is supported for `backend/` or `frontend/`. For editor tooling, open a Dev Container: **Law AI (backend)** ([.devcontainer/devcontainer.json](.devcontainer/devcontainer.json)) for the Python interpreter, pytest and ruff/mypy, or **Law AI (frontend)** ([.devcontainer/frontend/devcontainer.json](.devcontainer/frontend/devcontainer.json)) for ESLint and TypeScript. Every target, with the VS Code task that runs it, is in [docs/reference/make-targets.md](docs/reference/make-targets.md); commands, conventions and gates for humans and agents are in [AGENTS.md](AGENTS.md).

Pull requests pass `make lint`, `make typecheck`, `make test` (backend coverage ≥ 75%) and `make lint-specs`; reasoning changes also run LegalBench (CI runs it on the `reasoning-change` label and nightly in [nightly-tests.yml](.github/workflows/nightly-tests.yml)).

## Contributing

Read [AGENTS.md](AGENTS.md) and [docs/constitution.md](docs/constitution.md), then follow the fleet's [contributing guide](https://github.com/bamr87/bamr87/blob/main/CONTRIBUTING.md) (this repo has no `CONTRIBUTING.md` of its own). Pull requests fill in [.github/pull_request_template.md](.github/pull_request_template.md): what and why, visual evidence for anything a user can see, the gates you ran, and the follow-ups mirrored into `BACKLOG.md`.

## Changelog

Notable changes are recorded in [CHANGELOG.md](CHANGELOG.md); the full history is the [commit log](https://github.com/bamr87/law-ai/commits/main).

## License

[MIT](LICENSE) © 2026 Amr Abdel-Motaleb.

---

<!-- bamr87-portfolio-footer -->
Part of the [bamr87 portfolio](https://github.com/bamr87) — browse every project on [Amr's GitHub profile](https://github.com/bamr87).
