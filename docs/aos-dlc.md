# AOS-DLC in LexGraph AI

This page maps the [AI Agent-Orchestrated SDLC framework](aos-dlc-guide.md) onto the concrete files, agents, and tools in this repository. The framework guide is the **reference**; this page is the **implementation**.

LexGraph currently operates at **Autonomy Level 2 (Collaborative)** per [docs/constitution.md](constitution.md) §10.

## Phase Mapping

| AOS-DLC Phase | LexGraph Implementation | Entry Point |
|---|---|---|
| **0. Roadmap & Portfolio** | GitHub Projects + [PRD.md](../PRD.md). Roadmap-agent crew is **planned**, not yet built. | Manual today |
| **1. Spec / Requirements** | [specs/](../specs/) directory using the Spec Kit pattern (`spec.md` + `plan.md` + `tasks.md`). | [/specify](../prompts/specify.md) → [/clarify](../prompts/clarify.md) |
| **2. Architecture & Design** | `plan.md` per spec + ADRs under `docs/adr/`. System-wide diagram in [docs/architecture.md](architecture.md). | [/plan](../prompts/plan.md) |
| **3. Implementation** | CrewAI crews in [backend/app/agents/crews/](../backend/app/agents/crews) and LangGraph workflows in [backend/app/agents/graphs/](../backend/app/agents/graphs). | [/tasks](../prompts/tasks.md) → [/implement](../prompts/implement.md) |
| **4. Testing & QA** | pytest + Vitest (see [.vscode/tasks.json](../.vscode/tasks.json) `Run All Tests`) and LegalBench harness in `backend/app/eval/`. | `Run All Tests` task / `Run LegalBench Eval` task |
| **5. Deployment** | [docker-compose.yml](../docker-compose.yml) for local. Production CD pipeline is **planned**. CI is in [.github/workflows/ci.yml](../.github/workflows/ci.yml). | `make dev` |
| **6. Operations / SRE** | `app.core.provenance` audit log is the foundation. Langfuse-style agent tracing and SRE feedback loops are **planned**. | n/a yet |

## Agent Role Mapping

The framework's generic agent roles correspond to LexGraph crews documented in [docs/agent-roles.md](agent-roles.md). Concrete classes live in [backend/app/agents/crews/](../backend/app/agents/crews) and are wired in [backend/app/agents/registry.py](../backend/app/agents/registry.py).

| AOS-DLC Role | LexGraph Crew |
|---|---|
| Spec Writer / Clarifier | Prompts in [prompts/specify.md](../prompts/specify.md) and [prompts/clarify.md](../prompts/clarify.md) (no dedicated runtime agent yet) |
| System Architect | Prompt [/plan](../prompts/plan.md) (no runtime agent yet) |
| Implementation Agent | GitHub Copilot Coding Agent driven by [prompts/implement.md](../prompts/implement.md) |
| Test Generator | Pytest fixtures in [backend/tests/conftest.py](../backend/tests/conftest.py); generation is **planned** |
| Security / DevSecOps | CodeQL + dep scanning in [.github/workflows/ci.yml](../.github/workflows/ci.yml) — **planned**, currently only ruff + mypy |
| Domain Specialists | `LegalAnalyst`, `PrecedentHunter`, future `IngestionScout`, `LogicWeaver`, `Educator` (see [agent-roles.md](agent-roles.md)) |
| SRE / Monitor | **Planned**. `app.core.provenance` provides the audit substrate. |
| Roadmap / Portfolio | **Planned** crew. |

## CI/CD Backbone

[.github/workflows/ci.yml](../.github/workflows/ci.yml) encodes the AOS-DLC "deterministic core + intelligent gates" principle:

1. **Spec gate** — [scripts/spec_validator.py](../scripts/spec_validator.py) blocks any PR whose specs are inconsistent (unresolved open questions, requirements with no task coverage).
2. **Backend lint + types** — `ruff`, `black --check`, `mypy --strict`.
3. **Backend tests** — pytest with real Neo4j + Postgres service containers.
4. **Frontend lint + tests** — `npm run lint`, `tsc --noEmit`, Vitest.
5. **LegalBench regression** — runs only on PRs labelled `reasoning-change` (cost control).

AI-augmented review (per AOS-DLC §11.3) is **planned** as a future job, gated behind the constitution's open-source LLM rule.

## What's Intentionally Not Built Yet

These are listed in the framework but are **not** part of this iteration:

- Roadmap-agent crew (Phase 0 automation).
- Langfuse / Phoenix tracing for agent runs.
- SRE feedback loop (production incident → auto-issue → coding agent).
- Multi-agent debate via AutoGen.
- Auggie / GitHub AI quality-review job in CI.

Each will land via its own spec under `specs/`. See [docs/constitution.md](constitution.md) §10 for the gate that promotes us to Autonomy Level 3.
