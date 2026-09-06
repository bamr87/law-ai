
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

### Why evolve.yml is still hand-authored

Three workflows here are compiled from blueprints in `.factory/` and carry a `GENERATED BY GITFACTORY` header with a drift hash (`factory--evolve-pilot.yml`, `factory--backlog-triage.yml`, `factory--issue-concierge.yml`). [evolve.yml](../.github/workflows/evolve.yml) is not, and `BL-20260817-08` asks for it to be — so all orchestration shares one governance story.

It is blocked upstream, in the sibling `gitorio` repo that owns the compiler, not on anything in this repo. Two concrete gaps, re-verified 2026-09-05:

- **No deterministic step node.** The node catalogue is `trigger.*`, `gate.*`, `rate.limiter`, `agent.claude`, `run.*` and `sink.*`. There is nothing that runs a granted command like `python scripts/evolve_audit.py`, which is the entire body of this audit.
- **Sinks require an agent.** `sink.commit_files` / `sink.open_pr` / `sink.create_issue` emit `"<sink> requires a Claude agent upstream in v0 (deterministic emission lands with belt mode)"` when no `agent.claude` is on the path (`app/src/compiler/compile.ts`, and the `no deterministic emission in v0` case in `compile.test.ts`).

The tempting shortcut — drop an `agent.claude` node in to satisfy the compiler — is the one thing not to do. It would turn a deterministic audit into a model-dependent one and put Claude auth on a job that today needs none, which defeats the point of compiling it. gitorio tracks the compiler work as its own `BL-20260816-34`; gitorio's own `evolve.yml` is hand-authored for the same reason.

When that lands, the blueprint here is: `trigger.cron('0 13 * * 1')` + `trigger.manual` → `gate.enablement(EVOLVE_ENABLED)` (the switch documented below) → deterministic step running `evolve_audit.py` with the two stdlib validators as checks → `sink.open_pr(branch evolve/weekly-backlog-audit, add-paths BACKLOG.md)` → `sink.create_issue(label evolve, idempotent)`. Regenerate, commit `factory--evolve-audit.yml` with its drift hash, delete `evolve.yml`, and drop the non-goal from [specs/037-gitfactory-orchestration](../specs/037-gitfactory-orchestration/spec.md).

### Idling the weekly autopilot

[evolve.yml](../.github/workflows/evolve.yml) runs the headless half of `/evolve` every Monday at 13:00 UTC. Its `audit` job carries an **opt-out** kill switch:

```
if: ${{ vars.EVOLVE_ENABLED != 'false' }}
```

Set the repository variable `EVOLVE_ENABLED=false` (Settings → Secrets and variables → Actions → Variables) to idle it; unset it, or set any other value, to resume. Unset evaluates to the empty string, which is `!= 'false'`, so nothing changes for an existing checkout.

It is deliberately opt-out rather than gitorio's default-OFF `*_ENABLED` convention. [specs/038-framework-hardening](../specs/038-framework-hardening/plan.md) declined to backport the default-OFF form (NG1) because it would have silently idled a live weekly automation — and a workflow that quietly does nothing looks identical, in the runs list, to one that is working. Flipping the default is a one-word change and is the part that needs a maintainer's decision, not an implementation detail (`BL-20260818-02`).

### Smoke-testing a workflow locally

Scheduled workflows are awkward to iterate on: the feedback loop is a push, a dispatch, and several minutes of hosted-runner time. [nightly-tests.yml](../.github/workflows/nightly-tests.yml) therefore takes a `dry_run` input that skips every Docker-heavy step (coverage, LegalBench, e2e, autonomy synthesis) while still running the spec/backlog gates, the stale-backlog reporter and the discovery audit.

Two ways to exercise it:

```bash
gh workflow run nightly-tests.yml -f dry_run=true    # on the real runner
make nightly-dry-run                                 # locally, via nektos/act
```

`make nightly-dry-run` needs [act](https://github.com/nektos/act) on the host (`brew install act`) — the one sanctioned exception to the Docker-first `make` rule, because act *is* the Docker runner and installs no host toolchain. Its defaults (runner image, architecture, artifact path) live in [.actrc](../.actrc). act sets `ACT=true`, and the "Open draft PR" step is guarded by `!env.ACT`, so a local run can never push a branch or open a PR against the real repo (`BL-20260511-18`).

Only the `dry_run` path is expected to work under act: the `docker compose` steps want a Docker socket inside the job container, and the disk-cleanup step is specific to GitHub's hosted runner image.

### Which checks block a merge

Running a gate and *enforcing* it are different things. `markdown-oneline` went red on `main` when #73 merged and stayed red across four stacked PRs before anyone noticed, because nothing on this repository blocked a merge on a failing check (`BL-20260815-01`).

The enforcement lives in a **repository ruleset**, versioned at [.github/rulesets/main-required-checks.json](../.github/rulesets/main-required-checks.json) so it is reviewable in a diff rather than buried in repo settings. It targets the default branch and requires four contexts:

| Required context | Produced by |
|---|---|
| `Spec Drift Gate` | [ci.yml](../.github/workflows/ci.yml) job `spec-gate` |
| `Backend Lint + Type-check` | ci.yml job `backend-lint` |
| `Backend Tests + Coverage` | ci.yml job `backend-test` |
| `oneline` | [markdown-oneline.yml](../.github/workflows/markdown-oneline.yml) job `oneline` (no `name:`, so the job id is the context) |

Two things to know about the semantics:

- **A skipped job satisfies a required check.** The `changes` job path-filters most of ci.yml, so a docs-only PR reports `skipped` for the backend jobs — GitHub treats that as satisfied, which is the intended behaviour here rather than a loophole.
- **A check context is the job's `name:`, falling back to its job id.** Renaming a job therefore silently orphans the protection: the ruleset would wait forever on a context nothing reports. `test_required_status_checks_match_real_jobs` in [tests/test_configs.py](../tests/test_configs.py) fails on the rename instead.

Applying or updating the ruleset is a repo-settings write, so it is done deliberately by a maintainer rather than by CI:

```bash
gh api -X POST repos/{owner}/{repo}/rulesets \
  --input .github/rulesets/main-required-checks.json
# already applied? update in place with the ruleset id:
gh api repos/{owner}/{repo}/rulesets --jq '.[] | "\(.id) \(.name)"'
gh api -X PUT repos/{owner}/{repo}/rulesets/<id> \
  --input .github/rulesets/main-required-checks.json
```

The repo-admin role keeps an `always` bypass so the bot PR flows (`evolve.yml`, the factory lines) can still be merged by the owner when a path-filtered check never reports.

AI-augmented review is **planned** as a future job. Nothing in the constitution blocks it today — the prior rule against wiring a closed-source model into the runtime was repealed 2026-08-11 (spec 034); see [AO-SDLC_Outline_Guide.md](../AO-SDLC_Outline_Guide.md) §7 for the current CI job table.

## What's Intentionally Not Built Yet

These are listed in the framework but are **not** part of this iteration:

- Roadmap-agent crew (Phase 0 automation).
- Langfuse tracing for agent runs (Arize Phoenix + OpenTelemetry tracing is implemented — see [AO-SDLC_Outline_Guide.md](../AO-SDLC_Outline_Guide.md) §8).
- SRE feedback loop (production incident → auto-issue → coding agent).
- Multi-agent debate via AutoGen.
- Auggie / GitHub AI quality-review job in CI.

Each will land via its own spec under `specs/`. See [docs/constitution.md](constitution.md) §10 for the gate that promotes us to Autonomy Level 3.
