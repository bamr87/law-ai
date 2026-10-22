# AI Agent-Orchestrated SDLC (AO-SDLC)
## As Implemented in Law AI — Operating Guide

**Version 2.0 — 2026-08-11** **Supersedes:** v1.0 (2026-04-29, Grok xAI research synthesis — a generic aspirational template) **Status:** This is no longer an outline. Every mechanism described below exists in this repository, is enforced by a script or CI job, and was validated live on 2026-08-11 (see §9).

---

## What changed from v1.0

Version 1 was a vendor-neutral template: hypothetical agent crews, Azure/Jira/Aha! integrations, sample CrewAI snippets, and projected ROI figures. Version 2 is the operating manual for the AO-SDLC **this repo actually runs**. Every claim points at a file, a command, or a gate that will fail if the claim stops being true. Two v1 statements are formally retired:

1. *"Ollama is the product runtime LLM; Claude must never be wired in as the product runtime."*
   Repealed by the 2026-08-11 amendment to [docs/constitution.md](constitution.md) §1 (spec 034). The product runtime is now an ordered **provider chain** — Claude over a subscription OAuth token, then Claude over `ANTHROPIC_API_KEY`, then local Ollama — implemented in [backend/law_ai/core/llm/](../backend/law_ai/core/llm/). Local-first remains a supported, pinnable configuration, and is **required** for data under confidentiality obligations that forbid third-party processing.
2. *Aspirational metrics ("10-20x velocity", "81% review improvement").*
   Replaced by the measurable gates in §7. This guide makes no claim a script cannot check.

---

## 1. The Loop at a Glance

Law AI's AO-SDLC is one closed loop. Work enters as a `BL-*` item, exits as a merged PR, and re-enters as the follow-ups that PR discovered. Constitution §11 makes the re-entry mandatory; `make lint-specs` makes it mechanical.

```
                 ┌────────────────────────────────────────────────┐
                 │                 BACKLOG.md                     │
                 │   append-only register of BL-YYYYMMDD-NN items │
                 └───────┬────────────────────────────▲───────────┘
        pick (human      │                            │  mirror follow-ups
        or /evolve)      ▼                            │  (constitution §11)
   ┌──────────┐   ┌──────────┐   ┌────────┐   ┌───────┴───┐   ┌────────────┐
   │ /specify │──▶│ /clarify │──▶│ /plan  │──▶│  /tasks   │──▶│ /implement │
   └──────────┘   └──────────┘   └────────┘   └───────────┘   └─────┬──────┘
     spec.md       resolves        plan.md      tasks.md            │
     (draft)       every OQ-N                   (FR-linked)         ▼
                                                        ┌───────────────────┐
                                                        │  Gates (Docker):  │
                                                        │  make lint        │
                                                        │  make typecheck   │
                                                        │  make test        │
                                                        │  make lint-specs  │
                                                        └─────────┬─────────┘
                                                                  ▼
                                                            PR → CI → merge
```

- **Prompt chain**: [prompts/](../prompts/) holds the canonical prompt per phase (`specify.md`, `clarify.md`, `plan.md`, `tasks.md`, `implement.md`, plus `new-agent.md` for scaffolding and `evolve.md` for autonomous cycles). Both sanctioned dev surfaces — GitHub Copilot and Claude Code — run the same chain from the same files.
- **Spec packages**: `specs/NNN-feature-slug/{spec,plan,tasks}.md`. The spec is the persistent memory v1 theorized about: agents re-derive context from it, CI validates against it, and `git blame` on it answers "why is the code like this."
- **Autopilot**: [/evolve](../prompts/evolve.md) runs the whole loop unattended — picks the highest-priority open `BL-*` item (severity, then owed refactor budget, then age), runs the chain, closes the §11 loop, and stops only for questions a human must answer (data sources, licensing, HITL gates).

## 2. Governance Layer

Three documents govern everything; two scripts and a CI job enforce them.

| Artifact | Role | Enforced by |
|---|---|---|
| [docs/constitution.md](constitution.md) | Non-negotiable rules a spec/PR must satisfy: mission alignment (§1), locked tech stack (§2), quality gates (§3), provenance (§4), HITL (§5), testing (§6), spec workflow (§7), autonomy invariants (§10–12), jurisprudential honesty (§13) | [scripts/spec_validator.py](../scripts/spec_validator.py), CI `spec-gate` job, reviewer agents |
| [AGENTS.md](../AGENTS.md) | Canonical engineering guide: standards, structure, Docker-first workflow, dev-surface policy | Convention + review; CLAUDE.md and copilot-instructions defer to it |
| [BACKLOG.md](../BACKLOG.md) | Append-only work register (`BL-YYYYMMDD-NN — kind, severity — text`) with Open/Claimed/Done sections | [scripts/backlog_lint.py](../scripts/backlog_lint.py) (format + append-only vs. git history) |

**Dev-surface policy** (constitution §1): GitHub Copilot and Claude Code are the only sanctioned AI dev surfaces. Cursor, Continue.dev, Aider, Codex, Gemini CLI — and their config files — are rejected at review. Dev-time MCP servers ([.mcp.json](../.mcp.json)) give the dev agent read access to the local Postgres/Neo4j; the **product** takes no MCP dependency.

**The two-layer rule**: which model *edits this code* (dev orchestration) and which model *serves users* (runtime chain, §4 below) are independent decisions, configured in different places. Changing one never changes the other.

## 3. Spec-Driven Core (Phase 1 of every cycle)

What v1 called "Spec Kit" is implemented natively:

- `/specify` turns a `BL-*` item into `specs/NNN-slug/spec.md` with stable `FR-*`/`NFR-*` IDs and explicit `OPEN QUESTION OQ-N` blocks.
- `/clarify` must resolve every OQ before planning — `spec_validator.py` fails any non-draft spec with unresolved questions.
- `/plan` records architecture decisions and their *why*; `/tasks` breaks the plan into ordered tasks, each naming the FR it satisfies.
- `spec_validator.py` (stdlib-only, runs on the host and in CI) enforces: all three files exist, no template placeholders, every spec FR-ID is referenced by a task, a `shipped` status means every task is `[x]`, and `tasks.md` ends with a populated **`## Follow-ups Discovered`** section.
- `backlog_lint.py` enforces the mirror: each follow-up becomes a fresh `BL-*` bullet in `BACKLOG.md`, which is append-only (verified against the previous git revision).

This is the context-preservation mechanism in practice: a year of decisions is recoverable from `specs/` without asking anyone.

## 4. Runtime Architecture (the product the loop builds)

Django 5 (ASGI/daphne) + DRF + Channels + Celery backend; Next.js 15 frontend; Neo4j knowledge graph + Postgres + Redis + Chroma. Deeper detail: [docs/architecture.md](architecture.md).

### 4.1 The LLM provider chain (constitution §1, spec 034)

Every model call in the product flows through [backend/law_ai/core/llm/](../backend/law_ai/core/llm/):

```
LLM_PROVIDER_CHAIN = claude_code, anthropic_api, xai, ollama   (default order)

 1. claude_code    Claude via subscription OAuth token (`claude setup-token`)
 2. anthropic_api  Claude via ANTHROPIC_API_KEY
 3. xai            Grok via subscription OAuth token (`make xai-login`;
                   SuperGrok / X Premium+, no API-key mode). Spec 050.
 4. ollama         local open-weights model (last resort; also the privacy pin)
```

- The router tries tiers in order; unconfigured tiers are skipped with a recorded reason, failing tiers fall through, and total failure raises `LLMUnavailableError` so callers degrade to an **honest refusal** (§13) — never a fabricated answer.
- Every routed call writes an `llm_call` provenance event (provider, model, latency, full attempt chain) through `core.provenance` (§4/§5). A fallback is always visible in the audit trail.
- `LLM_PROVIDER_CHAIN=ollama` pins the runtime fully local — the required configuration for privileged client data.
- Anthropic, xAI and Ollama are the sanctioned providers (xAI added 2026-09-04, [ADR 0007](adr/0007-xai-runtime-provider.md), implemented in spec 050); adding any further vendor requires a constitution amendment.
- Two of the four default tiers send prompt text to a third party. `LLM_PROVIDER_CHAIN=ollama` is the only zero-egress configuration.
- The LegalBench eval harness deliberately bypasses the chain and stays pinned to Ollama: a benchmark that silently changes model measures nothing.

### 4.2 LangChain + LangGraph as core stack (spec 035)

LangGraph and the LangChain layer are **core dependencies**, not optional extras ([backend/pyproject.toml](../backend/pyproject.toml)) — the default analysis engine is a LangGraph `StateGraph` and its Postgres checkpointer is provisioned at container boot. The pieces:

- **[ChatProviderChain](../backend/law_ai/core/llm/langchain.py)** — a genuine LangChain `BaseChatModel` fronting the provider chain. Anything built on LangChain or LangGraph gets Claude-first routing, provider metadata on every `AIMessage`, and chain-level provenance, without knowing the chain exists.
- **[LegalWorkflow](../backend/law_ai/agents_runtime/graphs/legal_workflow.py)** — the default engine (spec 027): a checkpointed StateGraph doing GraphRAG retrieval → grounded IRAC drafting → citation verification, with an honest refusal path when retrieval returns nothing.
- **Checkpointing** — `AsyncPostgresSaver` (Redis and in-memory alternates) via [agents_runtime/graphs/runtime.py](../backend/law_ai/agents_runtime/graphs/runtime.py); `ensure_checkpointer` runs in the container boot chain, and docker-compose wires `POSTGRES_URL` to the compose Postgres explicitly (the checkpointer reads it directly, not via `DATABASE_URL`).
- **Docker** — one image ([backend/Dockerfile](../backend/Dockerfile)) installs the full stack; `docker compose build backend` is the proof the dependency graph resolves.

### 4.3 The agent roster (implemented, not aspirational)

| Agent | Kind | What it does | HITL |
|---|---|---|---|
| LegalAnalyst | crew | IRAC analysis via the chain (structured outputs) or via LegalWorkflow | flags `requires_review`; degraded output forces review |
| PrecedentHunter | crew | precedent retrieval | — |
| LegalWorkflow | LangGraph | retrieval-grounded analysis, checkpointed | refusal path on empty retrieval |
| TopicFrontier | LangGraph | scans the knowledge graph for orphan citations / thin jurisdictions, proposes ingestion targets | ingestion quarantine (§5) |
| IngestionScout | crew | source scouting → quarantine models | approval gates before commit |
| LSAT tutor / LSATContentAuthor / factory | service + crew | tutoring and content generation; factory executors are provider-pinned so generated banks stay attributable | proposals require approval before entering the bank |
| TestSynthesizer | crew | proposes pytest files for uncovered modules | `human_approval_required = True`; output lands in a proposals dir, never directly in the tree |

Contract for new agents (constitution + [prompts/new-agent.md](../prompts/new-agent.md)): implement `run(input: dict) -> dict` with Pydantic output, log through `core.provenance`, ship a test under `backend/tests/agents/`.

## 5. Autonomy Levels — mapped to real mechanisms

v1's four-level maturity model, with this repo's actual position:

| Level | v1 description | Law AI implementation |
|---|---|---|
| 1 — Assisted | AI suggests, human executes | Copilot completions |
| 2 — Collaborative | Agents draft, humans gate | The prompt chain run interactively; human reviews spec, PR, merge. **Default mode.** |
| 3 — Supervised autonomous | Agents run end-to-end with oversight gates | `/evolve` (picks work, runs the chain, opens the PR); the autonomy loop `make autonomy-run KIND=… SOURCE=…` for corpus growth and test-pillar cycles. Hard gates: `AUTONOMY_ENABLED=true`, `AUTONOMY_ALLOWED_SOURCES` allowlist, ingestion quarantine + HITL approval (`ENABLE_HUMAN_APPROVAL_GATES`), TestSynthesizer proposals never auto-merge. `/evolve` must stop on questions touching data sources, licensing, or HITL gates. |
| 4 — Fully autonomous | Minimal human touch | **Deliberately not implemented.** Constitution §5 requires HITL on ingestion and high-stakes analysis; §12 pins autonomy-loop invariants. Raising autonomy is a constitution amendment, not a config flag. |

Guardrails that hold at every level: provenance on every LLM call, source+confidence on every graph node, soft-delete only (`archived_at`), honest-refusal degradation, and append-only BACKLOG.

## 6. Docker-First Execution

Every dev/test/lint/typecheck/eval command runs inside Docker via `make` (wrapping `docker compose run --rm`). The only sanctioned host commands: `make …`, `docker compose …`, the two stdlib validators, and `git`/`gh`. This is what makes agent-run gates reproducible — an agent and a human running `make test` get the same containers, same deps, same result. See [AGENTS.md](../AGENTS.md) § Docker-First Workflow for the full table; the high-traffic targets:

```
make dev / down / logs            # full stack up (frontend :3000, API :8000)
make test | test-backend | test-frontend | test-integration
make lint | format | typecheck    # ruff / eslint / mypy --strict / tsc
make lint-specs                   # spec_validator + backlog_lint (host, stdlib)
make manage CMD='…'               # Django management inside the container
make autonomy-run KIND=… SOURCE=… # supervised-autonomous cycles
```

## 7. Quality Gates & CI

**Local gates** (every `/implement` must end green): `make lint`, `make typecheck`, `make test`, `make lint-specs`.

**CI** ([.github/workflows/ci.yml](../.github/workflows/ci.yml)) — the deterministic backbone around non-deterministic agents:

| Job | What it proves |
|---|---|
| Spec Drift Gate | `spec_validator.py` + `backlog_lint.py` — the §11 loop is closed |
| Repo Structural Tests | root pytest orchestrator: docs/specs/config consistency |
| Clean-Install Import Smoke | the package imports with **no extras** — catches dependency-layout regressions (this is the job that guards spec 035's core-deps move) |
| Backend Lint + Type-check / Backend Test | ruff, mypy, pytest with coverage floor (≥75% backend) |
| Frontend | tsc, eslint, vitest |

Plus [nightly-tests.yml](../.github/workflows/nightly-tests.yml) (full matrix + LegalBench regression policy), [integration-tests.yml](../.github/workflows/integration-tests.yml) (real Neo4j/Postgres/Redis), and [evolve.yml](../.github/workflows/evolve.yml) (scheduled autonomous cycles via the Copilot coding agent).

Two pytest configs, deliberately separate: root [pytest.ini](../pytest.ini) drives the repo-wide structural suite; [backend/pyproject.toml](../backend/pyproject.toml) drives the real backend suite. Don't conflate them.

**Test-isolation invariant** (spec 034): [backend/law_ai/settings/test.py](../backend/law_ai/settings/test.py) hard-blanks every LLM credential and points Ollama at a closed port. The suite must never bill a hosted API or depend on a live local model.

## 8. Observability & Audit

- **Provenance** ([core/provenance.py](../backend/law_ai/core/provenance.py)): every agent call, LLM call, tool use, and graph query — reproducible input hashes, trace IDs, `llm_call` events with the full provider-attempt chain. Bypassing it is a constitution violation (§4).
- **Audit sinks**: JSONL stream + `AuditEvent` ORM rows (Celery-persisted), surfaced in the Agent Ops dashboard.
- **Tracing**: Arize Phoenix + OpenTelemetry (the `local-ai` extra — genuinely optional; the app degrades cleanly without it).
- **Health**: `GET /api/agents/health/local-ai` reports Ollama, checkpointer, Phoenix, the Claude OAuth tier, and the full ordered `llm_chain` with per-tier configured/reachable state. The dashboard renders the chain and names the tier that will serve the next request.

## 9. Validation Playbook (run 2026-08-11, all green)

The runtime claims above were validated end-to-end against the **live Anthropic API over the Claude Code OAuth token** (tier 1 of the chain), inside the Docker stack:

| # | Check | Command | Green looks like |
|---|---|---|---|
| 1 | OAuth reachability probe | `make manage CMD='validate_claude_code --skip-tutor'` | `status: reachable`, `sample: 'pong'` |
| 2 | LSAT tutor end-to-end | `make manage CMD='validate_claude_code'` | `used_llm: True`, `model: claude_code/claude-opus-5` |
| 3 | IRAC analyst via the chain | `make manage CMD='run_legal_analyst --question "…"'` | full IRAC, confidence ≈0.85, trace_id logged, authorities flagged for human verification |
| 4 | LangGraph + LangChain + checkpointer | StateGraph with `ChatProviderChain` + `AsyncPostgresSaver` (see spec 035) | answer from `claude_code/…`, state persisted and re-readable by `thread_id` |
| 5 | Chain health | `curl :8000/api/agents/health/local-ai` | `llm_chain[0] = claude_code, configured+reachable`; checkpointer `reachable: true`; Ollama fallback listed |

Re-run this table after any change to the provider chain, the LangChain layer, the checkpointer wiring, or the Docker image. Steps 1–3 and 5 are one command each; step 4's script lives in spec 035's plan.

## 10. Extending the System

- **New feature** → append a `BL-*` item, then `/specify` (or let `/evolve` pick it up).
- **New agent** → [prompts/new-agent.md](../prompts/new-agent.md) scaffolds the `run()` contract, Pydantic output, provenance logging, and test.
- **New LLM provider** → constitution amendment first (§1 names Anthropic, xAI and Ollama only), then a provider class in [core/llm/providers.py](../backend/law_ai/core/llm/providers.py) registered in `PROVIDER_REGISTRY`, then a `settings/test.py` blank so the suite can't reach it.
- **Raising autonomy** → constitution amendment (§5/§10–12), not a config change.
- **This guide** → update it in the same PR as the mechanism it describes; CI's structural suite checks doc/spec consistency, and a guide that drifts from the gates is worse than no guide.

## Appendix A. File Map

```
docs/constitution.md         non-negotiable rules (§1 runtime chain, §11 evolution loop)
AGENTS.md                    engineering canon; dev-surface policy
BACKLOG.md                   append-only BL-* register
prompts/                     the AO-SDLC prompt chain (+ evolve autopilot)
specs/NNN-slug/              spec packages: spec / plan / tasks
scripts/spec_validator.py    spec gate (host, stdlib)
scripts/backlog_lint.py      backlog gate (host, stdlib)
backend/law_ai/core/llm/     provider chain: base / providers / router / langchain
backend/law_ai/agents_runtime/   crews, LangGraph graphs, checkpointer, registry
backend/law_ai/core/provenance.py   audit layer (never bypass)
.github/workflows/           deterministic CI backbone
```

## Appendix B. Glossary

- **AO-SDLC** — this loop: BACKLOG → prompt chain → gates → PR → follow-ups → BACKLOG.
- **Provider chain** — the ordered runtime LLM tiers in `LLM_PROVIDER_CHAIN` (constitution §1).
- **Spec package** — `specs/NNN-slug/{spec,plan,tasks}.md`; the persistent memory of a change.
- **§11 loop** — the constitutional requirement that every implement cycle mirrors its discovered follow-ups into BACKLOG.md.
- **HITL** — human-in-the-loop gates on ingestion and high-stakes analysis (constitution §5).
- **Honest refusal** — the mandated degradation mode: when the system cannot ground an answer, it says so at confidence 0.0 and forces review (§13); it never fabricates.
