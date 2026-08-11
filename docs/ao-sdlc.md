
# AO-SDLC in Law AI

This page maps the [AO-SDLC operating guide](../AO-SDLC_Outline_Guide.md) (v2.0, 2026-08-11) onto the concrete files, agents, and tools in this repository. The v2.0 guide is the **reference**; this page is the **implementation** summary.

Law AI currently operates at **Autonomy Level 2 (Collaborative)** per [docs/constitution.md](constitution.md) §10.

## Phase Mapping

| AO-SDLC Phase | Law AI Implementation | Entry Point |
|---|---|---|
| **0. Roadmap & Portfolio** | GitHub Projects + [PRD.md](../PRD.md). Roadmap-agent crew is **planned**, not yet built. | Manual today |
| **1. Spec / Requirements** | [specs/](../specs/) directory using the Spec Kit pattern (`spec.md` + `plan.md` + `tasks.md`). | [/specify](../prompts/specify.md) → [/clarify](../prompts/clarify.md) |
| **2. Architecture & Design** | `plan.md` per spec + ADRs under `docs/adr/`. System-wide diagram in [docs/architecture.md](architecture.md). | [/plan](../prompts/plan.md) |
| **3. Implementation** | CrewAI crews in [backend/law_ai/agents_runtime/crews/](../backend/law_ai/agents_runtime/crews) and LangGraph workflows in [backend/law_ai/agents_runtime/graphs/](../backend/law_ai/agents_runtime/graphs). `LegalWorkflow` (a checkpointed LangGraph `StateGraph`) is the default analysis engine; LangChain/LangGraph are core backend dependencies, not an optional extra (spec 035). | [/tasks](../prompts/tasks.md) → [/implement](../prompts/implement.md) |
| **4. Testing & QA** | pytest + Vitest (see [.vscode/tasks.json](../.vscode/tasks.json) `Run All Tests`) and LegalBench harness in `backend/law_ai/eval/`. | `Run All Tests` task / `Run LegalBench Eval` task |
| **5. Deployment** | [docker-compose.yml](../docker-compose.yml) for local. Production CD pipeline is **planned**. CI is in [.github/workflows/ci.yml](../.github/workflows/ci.yml). | `make dev` |
| **6. Operations / SRE** | `law_ai.core.provenance` audit log is the foundation. Arize Phoenix + OpenTelemetry tracing is implemented (optional `local-ai` extra, degrades cleanly when unset). An SRE feedback loop (production incident → auto-issue → coding agent) remains **planned**. | n/a yet |

## Agent Role Mapping

The framework's generic agent roles correspond to Law AI crews documented in [docs/agent-roles.md](agent-roles.md). Concrete classes live in [backend/law_ai/agents_runtime/crews/](../backend/law_ai/agents_runtime/crews) and are wired in [backend/law_ai/agents_runtime/registry.py](../backend/law_ai/agents_runtime/registry.py).

| AO-SDLC Role | Law AI Crew |
|---|---|
| Spec Writer / Clarifier | Prompts in [prompts/specify.md](../prompts/specify.md) and [prompts/clarify.md](../prompts/clarify.md) (no dedicated runtime agent yet) |
| System Architect | Prompt [/plan](../prompts/plan.md) (no runtime agent yet) |
| Implementation Agent | GitHub Copilot coding agent or Claude Code, driven by [prompts/implement.md](../prompts/implement.md) |
| Test Generator | `TestSynthesizer` ([backend/law_ai/agents_runtime/crews/test_synthesizer.py](../backend/law_ai/agents_runtime/crews/test_synthesizer.py)) proposes pytest files for uncovered modules today, `human_approval_required = True`; proposals never land directly in the tree |
| Security / DevSecOps | [.github/dependabot.yml](../.github/dependabot.yml) does grouped weekly npm dependency scanning (frontend only). CodeQL and backend/pip dependency scanning in [.github/workflows/ci.yml](../.github/workflows/ci.yml) are **planned**; CI otherwise runs ruff + mypy |
| Domain Specialists | `LegalAnalyst`, `PrecedentHunter`, `IngestionScout`, `TopicFrontier`, `LSATContentAuthor` are live; `LogicWeaver` and `Educator` remain future (see [agent-roles.md](agent-roles.md)) |
| SRE / Monitor | **Planned**. `law_ai.core.provenance` provides the audit substrate. |
| Roadmap / Portfolio | **Planned** crew. |

## CI/CD Backbone

[.github/workflows/ci.yml](../.github/workflows/ci.yml) encodes the AO-SDLC "deterministic core + intelligent gates" principle:

1. **Spec gate** — [scripts/spec_validator.py](../scripts/spec_validator.py) blocks any PR whose specs are inconsistent (unresolved open questions, requirements with no task coverage).
2. **Repo structural tests** — root pytest orchestrator checks docs/specs/config consistency.
3. **Clean-install import smoke** — the package imports with no extras; catches dependency-layout regressions (this is the job that guards spec 035's core-deps move).
4. **Backend lint + types** — `ruff`, `black --check`, `mypy --strict`.
5. **Backend tests** — pytest with real Neo4j + Postgres service containers.
6. **Frontend lint + tests** — `npm run lint`, `tsc --noEmit`, Vitest.
7. **LegalBench harness check** — runs on PRs labelled `reasoning-change`; verifies the eval harness itself is sound (paths, scoring, regression gate), not a scored regression run. The actual scored LegalBench run lives in [nightly-tests.yml](../.github/workflows/nightly-tests.yml) — PR runners can't host the multi-GB Ollama model the harness requires (`BL-20260810-04`).

AI-augmented review is **planned** as a future job. Nothing in the constitution blocks it today — the prior rule against wiring a closed-source model into the runtime was repealed 2026-08-11 (spec 034); see [AO-SDLC_Outline_Guide.md](../AO-SDLC_Outline_Guide.md) §7 for the current CI job table.

## What's Intentionally Not Built Yet

These are listed in the framework but are **not** part of this iteration:

- Roadmap-agent crew (Phase 0 automation).
- Langfuse tracing for agent runs (Arize Phoenix + OpenTelemetry tracing is implemented — see [AO-SDLC_Outline_Guide.md](../AO-SDLC_Outline_Guide.md) §8).
- SRE feedback loop (production incident → auto-issue → coding agent).
- Multi-agent debate via AutoGen.
- Auggie / GitHub AI quality-review job in CI.

Each will land via its own spec under `specs/`. See [docs/constitution.md](constitution.md) §10 for the gate that promotes us to Autonomy Level 3.
