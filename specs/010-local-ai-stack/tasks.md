# Tasks: Local AI Stack (Ollama + LangGraph + Checkpointers + Phoenix)

> Each task references one or more `FR-*` / `NFR-*` / `AC-*` IDs from [spec.md](spec.md). [scripts/spec_validator.py](../../scripts/spec_validator.py) enforces full coverage.

## Conventions

- Status: `[ ]` todo / `[~]` in-progress / `[x]` done.
- Owner: `@copilot` unless a human handle is given.
- Each task lists exact files to touch and how to verify.

---

## T-001 — Add deps + settings for local-AI substrate

- **Refs**: FR-1, NFR-OSS-1
- **Owner**: @copilot
- **Status**: `[x]`
- **Files**:
  - `backend/pyproject.toml`
  - `backend/app/core/config.py`
  - `.env.example`
- **Steps**:
  1. Add to base `dependencies`: `langchain-ollama>=0.2.0`, `arize-phoenix-otel>=0.6.0`, `opentelemetry-instrumentation-fastapi>=0.48b0`, `opentelemetry-instrumentation-httpx>=0.48b0`.
  2. Add `[project.optional-dependencies].local-ai` with `langgraph-checkpoint-postgres>=2.0.0`, `langgraph-checkpoint-redis>=0.0.5`.
  3. Confirm each license (MIT / Apache-2.0 / Elastic-2.0) and record in PR description.
  4. Add `OLLAMA_DEFAULT_MODEL` (default `mistral:7b-instruct-q4_K_M`), `LANGGRAPH_CHECKPOINTER` (default `postgres`), `PHOENIX_COLLECTOR_ENDPOINT` (default `http://phoenix:6006/v1/traces`), `PHOENIX_UI_URL` (default `http://localhost:6006`) to `Settings`.
  5. Mirror new env vars into `.env.example` with comments.
- **Verify**:
  - `cd backend && pip install -e ".[dev,local-ai]"` succeeds.
  - `python -c "from app.core.config import get_settings; print(get_settings().PHOENIX_COLLECTOR_ENDPOINT)"` prints the default.

## T-002 — `build_checkpointer()` factory

- **Refs**: FR-2, NFR-RESILIENCE-1
- **Owner**: @copilot
- **Status**: `[x]`
- **Files**:
  - `backend/app/agents/graphs/__init__.py` (new)
  - `backend/app/agents/graphs/runtime.py` (new)
  - `backend/app/db/checkpointer.py` (new)
  - `backend/tests/agents/graphs/__init__.py` (new)
  - `backend/tests/agents/graphs/test_runtime.py` (new)
- **Steps**:
  1. Implement `build_checkpointer()` returning `PostgresSaver` / `RedisSaver` / `MemorySaver` based on `settings.LANGGRAPH_CHECKPOINTER`.
  2. `app.db.checkpointer.ensure_schema()` calls `PostgresSaver.from_conn_string(...).setup()` once and is safe to re-call.
  3. Unit test covers all three branches (Postgres + Redis branches mocked).
- **Verify**:
  - `pytest backend/tests/agents/graphs/test_runtime.py -q` green.
  - `mypy app/ --strict` clean for new modules.

## T-003 — Telemetry: Phoenix + OTEL wiring

- **Refs**: FR-4, NFR-AUDIT-1, NFR-PRIVACY-1
- **Owner**: @copilot
- **Status**: `[x]`
- **Files**:
  - `backend/app/core/telemetry.py` (new)
  - `backend/app/main.py` (lifespan)
  - `backend/tests/core/test_telemetry.py` (new)
  - `backend/tests/core/test_local_ai_privacy.py` (new)
- **Steps**:
  1. `init_tracing(app)` is a no-op when `PHOENIX_COLLECTOR_ENDPOINT` unset; otherwise registers tracer provider with OTLP/HTTP exporter, instruments FastAPI + httpx, registers LangChain OTEL callback.
  2. Call from `app.main` lifespan startup.
  3. Privacy test monkey-patches `httpx.AsyncClient.send` and asserts allowlist (`localhost`, `ollama`, `phoenix`).
- **Verify**:
  - `pytest backend/tests/core/test_telemetry.py backend/tests/core/test_local_ai_privacy.py -q` green.
  - With `PHOENIX_COLLECTOR_ENDPOINT` unset, no spans are exported (tested).

## T-004 — `@logged_node` provenance decorator

- **Refs**: FR-5, NFR-AUDIT-1
- **Owner**: @copilot
- **Status**: `[x]`
- **Files**:
  - `backend/app/core/provenance.py`
  - `backend/tests/core/test_provenance_logged_node.py` (new)
- **Steps**:
  1. Add `@logged_node(name: str)` decorator supporting both sync and async node functions.
  2. Compute `input_hash` / `output_hash` (blake2b 16-char hex) from JSON-serializable state diffs.
  3. Pull `trace_id` from current OTEL span; pass through to `record(...)`.
  4. Add nullable `trace_id` column to provenance store (back-compat).
- **Verify**:
  - Decorator round-trips state unchanged.
  - Recorded row contains all FR-5 fields including `trace_id` when an OTEL span is active.

## T-005 — `LegalWorkflow` LangGraph (3 nodes)

- **Refs**: FR-3, NFR-PERF-1, NFR-HITL-1, NFR-TEST-COV-1, AC-2, AC-5, AC-6
- **Owner**: @copilot
- **Status**: `[x]`
- **Files**:
  - `backend/app/agents/graphs/legal_workflow.py` (new)
  - `backend/app/agents/prompts/legal_workflow/{retrieve,analyze,cite_check}.md` (new, versioned)
  - `backend/app/models/analysis.py` (extend response models with `phoenix_trace_url`, `langgraph_thread_id`)
  - `backend/tests/agents/graphs/test_legal_workflow.py` (new)
- **Steps**:
  1. Define `LegalWorkflowState` TypedDict and `LegalWorkflowOutput` Pydantic model.
  2. Build graph: `retrieve` (Cypher + vector) → `analyze` (`ChatOllama`) → `cite_check` (verifies citations against `app.db.citation_resolver`).
  3. Wire each node with `@logged_node(...)` (T-004) and the checkpointer (T-002).
  4. Unit tests use a fake `ChatOllama` (returns canned tool calls) and `MemorySaver`; assert node order, output schema, HITL flag set when an unverified citation is injected (AC-6).
- **Verify**:
  - `pytest backend/tests/agents/graphs/test_legal_workflow.py -q --cov=app.agents.graphs --cov=app.core.telemetry` ≥ 80% (NFR-TEST-COV-1).
  - Manual: `POST /api/analysis {"question":"...","use_langgraph":true}` returns `phoenix_trace_url` + `langgraph_thread_id` (AC-2).

## T-006 — `LegalAnalyst` opt-in delegation

- **Refs**: FR-3, AC-2
- **Owner**: @copilot
- **Status**: `[x]`
- **Files**:
  - `backend/app/agents/crews/legal_analyst.py`
  - `backend/app/api/analysis.py` (or wherever `/api/analysis` lives)
  - `backend/tests/agents/crews/test_legal_analyst.py`
- **Steps**:
  1. Add `use_langgraph: bool = False` to request schema; default unchanged.
  2. When true, delegate to `LegalWorkflow.invoke(...)` and surface `phoenix_trace_url` + `langgraph_thread_id`.
  3. Update one existing test to cover the new path with mocked workflow.
- **Verify**:
  - All existing tests still pass.
  - New test asserts delegation occurs only when flag is true.

## T-007 — Postgres-backed resilience integration test

- **Refs**: NFR-RESILIENCE-1, AC-3
- **Owner**: @copilot
- **Status**: `[x]`
- **Files**:
  - `backend/tests/agents/graphs/test_legal_workflow_postgres.py` (new, `@pytest.mark.integration`)
  - `backend/scripts/init-db.sh` (add `CREATE EXTENSION IF NOT EXISTS pg_trgm;`)
- **Steps**:
  1. Spin up against `docker compose up postgres ollama phoenix`; skip when env vars unreachable.
  2. Run `LegalWorkflow.invoke` with thread `T`, capture state.
  3. Recreate `LegalWorkflow` instance (simulates restart) and assert `get_state(...)` matches snapshot.
- **Verify**:
  - `pytest -m integration backend/tests/agents/graphs/test_legal_workflow_postgres.py -q` green when stack is up.

## T-008 — Compose: Phoenix service + Ollama bootstrap script

- **Refs**: FR-6, FR-7, AC-1
- **Owner**: @copilot
- **Status**: `[x]`
- **Files**:
  - `docker-compose.yml`
  - `backend/scripts/ollama-bootstrap.sh` (new, `chmod +x`)
- **Steps**:
  1. Add `phoenix` service (`arizephoenix/phoenix:<pinned-tag>`, port `6006:6006`, named volume).
  2. Backend `depends_on: [..., phoenix]`; add env `PHOENIX_COLLECTOR_ENDPOINT`, `PHOENIX_UI_URL`.
  3. Replace inline Ollama `command:` with `command: ["/bin/sh", "/scripts/ollama-bootstrap.sh"]` and mount `./backend/scripts/ollama-bootstrap.sh:/scripts/ollama-bootstrap.sh:ro`.
  4. Bootstrap script idempotently pulls `mistral:7b-instruct-q4_K_M`, `llama3.1:8b-instruct-q4_K_M`, `nomic-embed-text`; smallest model gates readiness.
- **Verify**:
  - `docker compose up -d phoenix ollama` → both healthy in `docker compose ps`.
  - `curl localhost:6006` returns Phoenix HTML; `curl localhost:11434/api/tags` lists ≥ 1 model on first boot, all three after warm-up.

## T-009 — Health endpoint + Make/VS Code wiring

- **Refs**: FR-8, FR-9, AC-1
- **Owner**: @copilot
- **Status**: `[x]`
- **Files**:
  - `backend/app/api/agents.py`
  - `backend/app/models/health.py` (new or extend)
  - `backend/tests/api/test_local_ai_health.py` (new)
  - `Makefile`
  - `.vscode/tasks.json`
- **Steps**:
  1. Implement `GET /api/agents/health/local-ai` returning the `LocalAIHealth` schema (FR-9).
  2. Add `local-ai-up`, `local-ai-down`, `local-ai-pull` Make targets calling docker compose with the right service set.
  3. Add `Start Local AI Stack` VS Code task.
- **Verify**:
  - Unit test mocks subsystem probes and asserts response shape.
  - `make local-ai-up && curl -s localhost:8000/api/agents/health/local-ai | jq` shows all three subsystems `reachable: true` against a live stack (AC-1).

## T-010 — Documentation

- **Refs**: FR-10, NFR-OSS-1, AC-4
- **Owner**: @copilot
- **Status**: `[x]`
- **Files**:
  - `docs/local-ai.md` (new)
  - `docs/data-model.md` (append "LangGraph Checkpointer Tables" subsection)
  - `docs/agent-roles.md` (append "Stateful Workflows" subsection)
  - `README.md` (one-line pointer)
- **Steps**:
  1. `docs/local-ai.md` covers: architecture diagram (reuse plan §1), env var matrix, hardware tier table (laptop / workstation / server — only laptop is configured today; the other two link to BACKLOG items), Phoenix license summary, troubleshooting (model OOM, Phoenix port collision, checkpointer reset).
  2. Document how to read a Phoenix trace URL returned in API responses (AC-4).
  3. Cross-link from `README.md` "Local development" section.
- **Verify**:
  - `python tests/test_docs.py` (or whichever doc lint exists) passes.
  - Manual review: every env var introduced in T-001 appears in the docs.

---

## Done-When (Definition of Done)

- All tasks `[x]`.
- All `AC-1` … `AC-7` from `spec.md` covered by passing tests.
- `make lint && make test` green; `mypy app/ --strict` clean for new modules.
- `Run LegalBench Eval` shows ≥ 0 pp delta on `core_reasoning` and `precedent_retrieval`; recorded in PR description.
- Phoenix UI reachable at `http://localhost:6006` after `make local-ai-up`; trace ids in API responses resolve to a span tree (AC-4).
- Provenance rows for new LangGraph nodes include `trace_id` matching Phoenix.
- **`## Follow-ups Discovered` populated below** and mirrored to [BACKLOG.md](../../BACKLOG.md).

---

## Follow-ups Discovered

> Append-only. Mirror each item into [BACKLOG.md](../../BACKLOG.md) with a `BL-YYYYMMDD-NN` id.

- BL-20260502-01 — feature, med — Self-host LangGraph API + Studio container (`langchain/langgraph-api`) so designers can step through `LegalWorkflow` runs visually. Phase 5 of `local-ai-plan.md` (since deleted); deferred per NG1.
- BL-20260502-02 — infra, med — Linux + NVIDIA workstation tier: GPU runtime in compose, optional vLLM service, default model upgraded to `llama3.1:70b-q4_K_M`. Phase 2 / 3 of source plan; deferred per NG2.
- BL-20260502-03 — infra, low — Server / multi-GPU tier with Prometheus + Grafana for token/sec, GPU util, queue depth. Phase 8 of source plan; deferred per NG5.
- BL-20260502-04 — feature, med — Backfill `LegalAnalyst` (BL-20260430-03) and `PrecedentHunter` (BL-20260430-04) onto `LegalWorkflow` once parity proven on LegalBench.
- BL-20260502-05 — feature, low — `AgentTrace.tsx` surfaces `phoenix_trace_url` + `langgraph_thread_id` returned by `/api/analysis` so users can deep-link from the UI.
- BL-20260502-06 — infra, low — Air-gapped deployment hardening: bundle pre-pulled Ollama models into a tarball + offline install script. Phase 8 extension.
- BL-20260502-07 — feature, low — Langfuse fallback path if Phoenix license terms change; abstract the OTEL exporter behind `settings.OBSERVABILITY_BACKEND`.
- BL-20260502-08 — test-gap, low — CI matrix entry that runs the integration test from T-007 against a real Postgres + Ollama (currently only locally executable).
