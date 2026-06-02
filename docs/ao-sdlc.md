
# AO-SDLC in LawGraph AI

This page maps the [AI Agent-Orchestrated SDLC framework](ao-sdlc-guide.md) onto the concrete files, agents, and tools in this repository. The framework guide is the **reference**; this page is the **implementation**.

LawGraph currently operates at **Autonomy Level 2 (Collaborative)** per [docs/constitution.md](constitution.md) §10.

Each step is routed to a model tier per [docs/model-routing.md](model-routing.md) — the Reasoning tier (Claude Opus 4.8) authors specs/plans, the Execution tier (Claude Sonnet 4.6) decomposes and implements them.

## Phase Mapping

| AO-SDLC Phase | LawGraph Implementation | Entry Point | Model tier |
|---|---|---|---|
| **0. Roadmap & Portfolio** | GitHub Projects + [PRD.md](../PRD.md). Roadmap-agent crew is **planned**, not yet built. | Manual today | n/a |
| **1. Spec / Requirements** | [specs/](../specs/) directory using the Spec Kit pattern (`spec.md` + `plan.md` + `tasks.md`). | [/specify](../prompts/specify.md) → [/clarify](../prompts/clarify.md) | Reasoning (Opus 4.8) |
| **2. Architecture & Design** | `plan.md` per spec + ADRs under `docs/adr/`. System-wide diagram in [docs/architecture.md](architecture.md). | [/plan](../prompts/plan.md) | Reasoning (Opus 4.8) |
| **3. Implementation** | CrewAI crews in [backend/lawgraph/agents_runtime/crews/](../backend/lawgraph/agents_runtime/crews) and LangGraph workflows in [backend/lawgraph/agents_runtime/graphs/](../backend/lawgraph/agents_runtime/graphs). | [/tasks](../prompts/tasks.md) → [/implement](../prompts/implement.md) | Execution (Sonnet 4.6) |
| **4. Testing & QA** | pytest + Vitest (see [.vscode/tasks.json](../.vscode/tasks.json) `Run All Tests`) and LegalBench harness in `backend/lawgraph/eval/`. | `Run All Tests` task / `Run LegalBench Eval` task | n/a (deterministic) |
| **5. Deployment** | [docker-compose.yml](../docker-compose.yml) for local. Production CD pipeline is **planned**. CI is in [.github/workflows/ci.yml](../.github/workflows/ci.yml). | `make dev` | n/a (deterministic) |
| **6. Operations / SRE** | `app.core.provenance` audit log is the foundation. Langfuse-style agent tracing and SRE feedback loops are **planned**. | n/a yet | n/a |

## Agent Role Mapping

The framework's generic agent roles correspond to LawGraph crews documented in [docs/agent-roles.md](agent-roles.md). Concrete classes live in [backend/lawgraph/agents_runtime/crews/](../backend/lawgraph/agents_runtime/crews) and are wired in [backend/lawgraph/agents_runtime/registry.py](../backend/lawgraph/agents_runtime/registry.py).

| AO-SDLC Role | LawGraph Crew |
|---|---|
| Spec Writer / Clarifier | Prompts in [prompts/specify.md](../prompts/specify.md) and [prompts/clarify.md](../prompts/clarify.md) (no dedicated runtime agent yet) |
| System Architect | Prompt [/plan](../prompts/plan.md) (no runtime agent yet) |
| Implementation Agent | GitHub Copilot coding agent or Claude Code, driven by [prompts/implement.md](../prompts/implement.md) |
| Test Generator | Pytest fixtures in [backend/tests/conftest.py](../backend/tests/conftest.py); generation is **planned** |
| Security / DevSecOps | CodeQL + dep scanning in [.github/workflows/ci.yml](../.github/workflows/ci.yml) — **planned**, currently only ruff + mypy |
| Domain Specialists | `LegalAnalyst`, `PrecedentHunter`, future `IngestionScout`, `LogicWeaver`, `Educator` (see [agent-roles.md](agent-roles.md)) |
| SRE / Monitor | **Planned**. `app.core.provenance` provides the audit substrate. |
| Roadmap / Portfolio | **Planned** crew. |

## CI/CD Backbone

[.github/workflows/ci.yml](../.github/workflows/ci.yml) encodes the AO-SDLC "deterministic core + intelligent gates" principle:

1. **Spec gate** — [scripts/spec_validator.py](../scripts/spec_validator.py) blocks any PR whose specs are inconsistent (unresolved open questions, requirements with no task coverage).
2. **Backend lint + types** — `ruff`, `black --check`, `mypy --strict`.
3. **Backend tests** — pytest with real Neo4j + Postgres service containers.
4. **Frontend lint + tests** — `npm run lint`, `tsc --noEmit`, Vitest.
5. **LegalBench regression** — runs only on PRs labelled `reasoning-change` (cost control).

AI-augmented review (per AO-SDLC §11.3) is **planned** as a future job, gated behind the constitution's open-source LLM rule.

## What's Intentionally Not Built Yet

These are listed in the framework but are **not** part of this iteration:

- Roadmap-agent crew (Phase 0 automation).
- Langfuse / Phoenix tracing for agent runs.
- SRE feedback loop (production incident → auto-issue → coding agent).
- Multi-agent debate via AutoGen.
- Auggie / GitHub AI quality-review job in CI.

Each will land via its own spec under `specs/`. See [docs/constitution.md](constitution.md) §10 for the gate that promotes us to Autonomy Level 3.
