# Spec: Local AI Stack (Ollama + LangGraph + Checkpointers + Phoenix)

- **ID**: 010-local-ai-stack
- **Status**: draft
- **Owner**: @copilot
- **Created**: 2026-05-02
- **Roadmap Epic**: [local-ai-plan.md](../../local-ai-plan.md)
- **Constitution Compliance**: confirmed against [docs/constitution.md](../../docs/constitution.md) §1 (open-source, privacy-first, local), §2 (tech stack: Ollama + LangGraph), §3 (provenance), §11 (continuous evolution). Phase 7 of the source plan (Continue.dev / PearAI / Aider) is explicitly removed because [AGENTS.md](../../AGENTS.md) "Development Orchestration" forbids non-Copilot coding agents.

## 1. Problem & Motivation

[local-ai-plan.md](../../local-ai-plan.md) sketches a fully local, agent-orchestrated stack (Ollama → LangGraph → Postgres/Redis checkpointers → self-hosted API/Studio → Phoenix). Today the repo only ships the Ollama container in [docker-compose.yml](../../docker-compose.yml) and lists `langgraph` + `ollama` in [backend/pyproject.toml](../../backend/pyproject.toml) but no LangGraph workflow runs against a real Ollama model with durable state. Agents in `backend/app/agents/crews/` carry TODOs (BL-20260430-03, BL-20260430-04) precisely because the local LLM substrate is incomplete.

This spec lands the **smallest defensible local-AI substrate** so the rest of the roadmap (LegalAnalyst, PrecedentHunter, IngestionScout HITL) can stop stubbing LLM calls.

## 2. Goals

- **G1**: A LangGraph workflow runs end-to-end against the local Ollama container with durable state (Postgres checkpointer) and survives a backend restart.
- **G2**: Default model set is fixed and machine-pullable for Apple Silicon laptops (32–64 GB unified memory): `llama3.1:8b-instruct-q4_K_M`, `mistral:7b-instruct-q4_K_M`, `nomic-embed-text`.
- **G3**: Every LLM call from a LangGraph node logs through `app.core.provenance` with model name, prompt template id, latency, and token counts — same contract CrewAI crews already use.
- **G4**: A self-hosted Arize Phoenix instance receives OpenTelemetry traces from every LangGraph + CrewAI run; trace ids are returned in agent responses.
- **G5**: One repeatable command (`make local-ai-up`) brings the entire stack online and pulls the default models on first boot.

## 3. Non-Goals

- **NG1**: Self-hosted LangGraph Cloud API + Studio container (Phase 5 of the source plan). Deferred to BACKLOG — adds a heavy image and is not required for any current spec.
- **NG2**: vLLM / multi-GPU / Linux server tier. Apple Silicon laptop is the default target; other tiers are documented but not configured.
- **NG3**: IDE integration with Continue.dev / PearAI / Aider (Phase 7 of source plan). **Forbidden** by [AGENTS.md](../../AGENTS.md) "Development Orchestration"; GitHub Copilot is the only sanctioned dev surface.
- **NG4**: Replacing existing CrewAI crews with LangGraph rewrites. CrewAI stays; LangGraph runs alongside for stateful, resumable workflows.
- **NG5**: Air-gapped deployment hardening, Prometheus/Grafana dashboards. BACKLOG.

## 4. User Stories

- As a **LawGraph backend developer**, I want `from app.agents.graphs import legal_workflow` to invoke a real LangGraph that calls Ollama and persists state to Postgres, so I can stop stubbing `_call_llm()` in crew tests.
- As an **ops engineer**, I want `make local-ai-up` to start Ollama + Postgres + Redis + Phoenix + backend in one command and warm-pull the default models, so onboarding fits in a single coffee.
- As a **legal analyst** using `/api/analysis`, I want every response to include a `phoenix_trace_url` so I can audit the exact retrieval + LLM steps that produced an answer.

## 5. Functional Requirements

- **FR-1**: Add `langchain-ollama>=0.2.0`, `langgraph-checkpoint-postgres>=2.0.0`, `langgraph-checkpoint-redis>=0.0.5`, `arize-phoenix-otel>=0.6.0`, `opentelemetry-instrumentation-fastapi>=0.48b0` to [backend/pyproject.toml](../../backend/pyproject.toml) under a new `[project.optional-dependencies].local-ai` extra plus the base `dependencies` for the runtime pieces (`langchain-ollama`, `arize-phoenix-otel`, OTEL instrumentation).
- **FR-2**: Introduce `backend/app/agents/graphs/runtime.py` exposing `build_checkpointer() -> BaseCheckpointSaver` that returns `PostgresSaver` when `LANGGRAPH_CHECKPOINTER=postgres` (default), `RedisSaver` when `=redis`, and `MemorySaver` when `=memory` (test-only).
- **FR-3**: Introduce `backend/app/agents/graphs/legal_workflow.py` — a 3-node LangGraph (`retrieve` → `analyze` → `cite_check`) that uses `ChatOllama(base_url=settings.OLLAMA_BASE_URL, model=settings.OLLAMA_DEFAULT_MODEL)` and the checkpointer from FR-2. Returns a Pydantic `LegalWorkflowOutput` with `answer`, `citations`, `trace_id`, `phoenix_trace_url`, `human_approval_required`.
- **FR-4**: Add `backend/app/core/telemetry.py` that registers an OpenTelemetry tracer provider exporting to Phoenix (`PHOENIX_COLLECTOR_ENDPOINT`, default `http://phoenix:6006/v1/traces`) at FastAPI lifespan startup; instrument FastAPI + httpx; instrument LangGraph runs via the LangChain OpenTelemetry callback.
- **FR-5**: Extend `backend/app/core/provenance.py` (or its successor) so every LangGraph node decorator `@logged_node(name=...)` records `{node, model, prompt_id, prompt_version, input_hash, output_hash, latency_ms, token_in, token_out, trace_id}` to the existing provenance store.
- **FR-6**: Add a `phoenix` service to [docker-compose.yml](../../docker-compose.yml) (`arizephoenix/phoenix:latest`, port 6006), wire `PHOENIX_COLLECTOR_ENDPOINT` into the `backend` service env, and add a depends_on edge.
- **FR-7**: Replace the inline `command:` in the `ollama` service with a `backend/scripts/ollama-bootstrap.sh` that pulls the FR-1 default model set (`llama3.1:8b-instruct-q4_K_M`, `mistral:7b-instruct-q4_K_M`, `nomic-embed-text`) idempotently and is safe to re-run; mount it into the container.
- **FR-8**: Add `make local-ai-up`, `make local-ai-down`, `make local-ai-pull` targets to [Makefile](../../Makefile) and a `Start Local AI Stack` task to [.vscode/tasks.json](../../.vscode/tasks.json).
- **FR-9**: Add `GET /api/agents/health/local-ai` returning `{ollama: {reachable, models}, checkpointer: {kind, reachable}, phoenix: {reachable, ui_url}}` so the existing Agent Ops dashboard (spec 003) can surface stack health.
- **FR-10**: Document the stack in `docs/local-ai.md` (architecture diagram, env vars, model matrix for laptop / workstation / server tiers, troubleshooting).

## 6. Non-Functional Requirements

- **NFR-PERF-1**: `legal_workflow.invoke({...})` returns within p95 < 30 s on an Apple Silicon laptop with `llama3.1:8b-instruct-q4_K_M` and a single-document context (≤ 4 k tokens). Slow paths are surfaced as Phoenix spans.
- **NFR-RESILIENCE-1**: `legal_workflow` resumes from the last checkpoint on backend restart; an integration test kills the process mid-run and asserts `state.values == prior_values` after `.get_state(config)`.
- **NFR-PRIVACY-1**: No outbound HTTP calls to non-localhost destinations during workflow execution. Enforced by a test that monkey-patches `httpx.AsyncClient` and asserts only `localhost`/`ollama`/`phoenix` hosts are hit.
- **NFR-AUDIT-1**: Every LangGraph node call appears in both `app.core.provenance` storage *and* Phoenix; trace ids match across stores. Verified by an integration test.
- **NFR-OSS-1**: All new dependencies are MIT/Apache-2.0/AGPL-3.0 (Phoenix is Elastic 2.0 / Apache-2.0 — confirm and pin). No proprietary services.
- **NFR-HITL-1**: `LegalWorkflowOutput.human_approval_required` is `True` whenever the `cite_check` node flags any citation as `unverified` (`source: "ollama-hallucination-check"`).
- **NFR-TEST-COV-1**: New modules under `backend/app/agents/graphs/` and `backend/app/core/telemetry.py` reach ≥ 80% line coverage in `pytest --cov=app`.

## 7. Data Model Impact

No new Neo4j nodes. Adds Postgres tables owned by `langgraph-checkpoint-postgres`:

- `checkpoints`, `checkpoint_writes`, `checkpoint_blobs` — created idempotently by `PostgresSaver.setup()` on lifespan startup.

Migration is handled by the library; we expose it via `app.db.checkpointer.ensure_schema()` called from `app.main` lifespan. Documented in [docs/data-model.md](../../docs/data-model.md) §"LangGraph Checkpointer Tables" (new subsection — author it as part of FR-10).

## 8. API Surface

- `GET /api/agents/health/local-ai` (FR-9) — response `LocalAIHealth` Pydantic model:

  ```python
  class LocalAIHealth(BaseModel):
      ollama: OllamaHealth          # reachable: bool, models: list[str]
      checkpointer: CheckpointerHealth  # kind: Literal["postgres","redis","memory"], reachable: bool
      phoenix: PhoenixHealth        # reachable: bool, ui_url: str
  ```

- `POST /api/analysis` and `POST /api/agents/run` responses gain optional `phoenix_trace_url: str | None` and `langgraph_thread_id: str | None` fields (additive, backwards-compatible). Existing Pydantic models in `backend/app/models/` are extended, not replaced.

## 9. Agent / Crew Impact

- **New**: `LegalWorkflow` (LangGraph) under `backend/app/agents/graphs/legal_workflow.py`. Documented in [docs/agent-roles.md](../../docs/agent-roles.md) under a new "Stateful Workflows" subsection (FR-10).
- **Modified**: `LegalAnalyst` crew (`backend/app/agents/crews/legal_analyst.py`) gains an opt-in `use_langgraph: bool = False` flag that, when true, delegates to `LegalWorkflow.invoke(...)`. Default behavior unchanged so other specs do not break.
- **No changes** to `IngestionScout`, `PrecedentHunter` in this spec — they continue to log via `core.provenance` and now automatically appear in Phoenix once FR-4 lands.

## 10. Acceptance Criteria

- **AC-1**: Given `make local-ai-up` on a clean machine, when the script finishes, then `curl localhost:11434/api/tags` lists all three default models, `curl localhost:6006` returns Phoenix's UI HTML, and `curl localhost:8000/api/agents/health/local-ai` returns all three subsystems `reachable: true`.
- **AC-2**: Given the backend is running, when I `POST /api/analysis` with `{"question": "What is the holding of Marbury v. Madison?", "use_langgraph": true}`, then I receive a 200 with non-empty `answer`, ≥ 1 `citations`, a non-null `phoenix_trace_url`, and a non-null `langgraph_thread_id`.
- **AC-3**: Given a workflow run completed at thread `T`, when I restart the backend container and call `LegalWorkflow.get_state(config={"configurable":{"thread_id":"T"}})`, then state values equal the pre-restart snapshot. (NFR-RESILIENCE-1)
- **AC-4**: Given a workflow run, when I open `phoenix_trace_url`, then I see one root span per node (`retrieve`, `analyze`, `cite_check`) with model name, prompt id, and latency attributes; the trace id matches the row stored by `app.core.provenance`. (NFR-AUDIT-1)
- **AC-5**: Given the test suite runs with no network access (`pytest -m "not network"`), when `tests/agents/graphs/test_legal_workflow.py` executes against a `MemorySaver`-backed graph and a fake `ChatOllama`, then it passes and reports ≥ 80% coverage for the new modules. (NFR-TEST-COV-1)
- **AC-6**: Given `cite_check` flags an unverified citation, when the workflow returns, then `human_approval_required is True` and the response surfaces the offending citation with `source: "ollama-hallucination-check"`. (NFR-HITL-1)
- **AC-7**: Given a run is in progress, when an outbound `httpx` call targets any host other than `localhost`, `ollama`, or `phoenix`, then the test in `tests/core/test_local_ai_privacy.py` fails. (NFR-PRIVACY-1)

## 11. LegalBench Impact

- Tasks affected: `core_reasoning`, `precedent_retrieval` (smoke set used by [Run LegalBench Eval] task).
- Expected delta: **≥ 0 pp**. This spec swaps the LLM substrate, not the reasoning logic, so we expect parity. Regression > 2 pp blocks the PR; cause is a model/quantization mismatch and the fix is to pin `OLLAMA_DEFAULT_MODEL` in `.env.example` to whatever the eval was run against.

## 12. Risks & Open Questions

- **R-1**: Phoenix container image footprint and license. *Mitigation*: pin a specific tag, confirm Apache-2.0 of the OSS components, document the upstream license terms in `docs/local-ai.md`. If license ambiguity surfaces, fall back to Langfuse (also self-hostable) and re-record in BACKLOG.
- **R-2**: `langgraph-checkpoint-postgres` requires Postgres ≥ 13 with `pg_trgm`; our compose uses `postgres:16-alpine` so we are fine, but the `init-db.sh` must `CREATE EXTENSION IF NOT EXISTS pg_trgm;`.
- **R-3**: First-boot model pulls (≈ 9 GB) make `make local-ai-up` slow. *Mitigation*: pulls are backgrounded by `ollama-bootstrap.sh`; readiness probe waits only for `mistral:7b-instruct-q4_K_M` (smallest) before declaring success; rest stream in.
- **R-4**: `ChatOllama` token-count reporting is best-effort. *Mitigation*: when missing, log `token_in=None, token_out=None` rather than `0` so dashboards can distinguish "unknown" from "actually zero".

## 13. Out of Scope / Follow-ups

Tracked in `tasks.md` `## Follow-ups Discovered` and mirrored to [BACKLOG.md](../../BACKLOG.md):

- Self-hosted LangGraph API + Studio container (Phase 5 of source plan).
- Linux + NVIDIA workstation tier (GPU runtime in compose, vLLM optional).
- Server / multi-GPU tier with Prometheus + Grafana.
- Backfill `LegalAnalyst` and `PrecedentHunter` (BL-20260430-03, BL-20260430-04) onto `LegalWorkflow` once it has parity.
- Air-gapped deployment hardening + offline model bundle.
