# GitHub Copilot Instructions

GitHub Copilot is a sanctioned AI development surface for this repo (Copilot Chat in VS Code — Ask / Edit / Agent modes — plus inline completions and the GitHub Copilot coding agent in the cloud); **Claude Code** is also sanctioned and reads its own guide at [CLAUDE.md](../CLAUDE.md). Cursor, Continue.dev, Aider, Codex, Gemini CLI, and any other third-party coding agents are forbidden. See [AGENTS.md](../AGENTS.md) § "Development Orchestration" and [docs/constitution.md](../docs/constitution.md) §1.

The canonical, repo-wide coding guide for AI agents lives in [AGENTS.md](../AGENTS.md).

**Always read [AGENTS.md](../AGENTS.md) before making changes.** It defines:

- Mission, core principles (open-source, privacy, auditability, HITL)
- Required tech stack (Django 5 + DRF + Channels + Celery + CrewAI + LangGraph + Neo4j + Ollama; Next.js 15 + Tailwind + Cytoscape)
- Project structure (`backend/law_ai/{agents_runtime,agentsapi,analysis,audit,core,eval,graph,ingestionapp,lsat,settings}`, `frontend/{app,components,lib}`)
- Coding standards (`ruff` + `black` + `mypy --strict` for Python; strict TS for frontend)
- Testing standards (pytest + Vitest, ≥75% coverage, LegalBench regression)
- Quick-reference commands ([Makefile](../Makefile)) and VS Code tasks ([.vscode/tasks.json](../.vscode/tasks.json))
- Quality gates required before every PR

**Docker-first, always.** Every dev/test/lint/typecheck/eval command in this repo runs inside Docker via `make <target>` (which wraps `docker compose run --rm <service>`). Never suggest or run `cd backend && pytest`, `cd frontend && npm test`, `python manage.py …`, `pip install …`, `ruff …`, `mypy …`, `black …`, or `npm install` directly on the host. The only sanctioned host commands are `make …`, `docker compose …`, `python3 scripts/spec_validator.py`, `python3 scripts/backlog_lint.py`, and `git`/`gh`. See AGENTS.md "Docker-First Workflow" for the full table.

Supporting docs:
- [docs/architecture.md](../docs/architecture.md)
- [docs/agent-roles.md](../docs/agent-roles.md)
- [PRD.md](../PRD.md)
- Prompt templates in [prompts/](../prompts/) (`new-agent.md`, `implement-feature.md`)

**Never** suggest closed-source LLMs as primary, bypass `core.provenance` logging, create graph nodes without `source` + `confidence`, skip HITL gates on ingestion / high-stakes analysis, **or finish a `/implement` cycle without appending follow-ups to [BACKLOG.md](../BACKLOG.md) and the spec's `## Follow-ups Discovered` section** (see [docs/constitution.md](../docs/constitution.md) §11).
