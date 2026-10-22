# Plan: LangChain + LangGraph as the Framework-Wide Engine

- **Spec**: [spec.md](spec.md) (027-langchain-langgraph-default)
- **Approach**: one shared transport module first, then route existing agents
through it, then flip defaults last (so every default-path consumer already sits on the resilient transport when the flip lands). All changes additive; the `use_langgraph=false` escape hatch preserves prior behavior.

## Steps

1. **Shared transport** — new `backend/law_ai/agents_runtime/llm.py`:
`build_chat_ollama()` (ChatOllama + `with_retry`: 3 attempts, exponential jitter, transient-error allowlist incl. `ollama.ResponseError`), `generate_text_sync()`, `coerce_text()`, TTL-cached `ollama_available()` + `ollama_available_async()` (shared cache, 1 s probe, 15 s TTL), `LLMUnavailableError` for bare installs, `reset_probe_cache()` test helper.
2. **LegalWorkflow** — `_default_llm_factory` delegates to `build_chat_ollama()` (drops its private ChatOllama construction).
3. **LegalAnalyst** — `_run_via_langgraph` gains the resilience boundary:
async availability probe → degraded `[ENGINE UNAVAILABLE]` refusal (logged `fallback/offline`), try/except around the workflow for ImportError/transport errors → same degraded contract. New module-level `_langgraph_fallback_irac()`.
4. **Default flip** — `AnalysisRequest.use_langgraph` default `true`;
frontend toggles (`AnalysisStudio`, `AgentDashboard`) default on, with `AnalysisStudio` sending the explicit boolean (omission would re-enable the engine server-side after user opt-out).
5. **TestSynthesizer** — `_call_ollama` internals swap to
`generate_text_sync`; name/signature/RuntimeError contract preserved (tests patch that seam).
6. **TopicFrontier** — `_build_graph()` compiles the real
`StateGraph(TopicFrontierState)` with async closures binding the DI collaborators; `run()` prefers `graph.ainvoke`, `_run_sequential()` fallback on ImportError; `_call_ollama` → shared transport; prioritize node logs its LLM call via `provenance.log_agent_call` (model, latency, prompt id/version).
7. **Review-driven fixes** (from the spec-026 adversarial review, applied in
this cycle since they touch the same files): phoenix healthcheck exec-form (distroless image has no `/bin/sh`), backend debug-override command folding (continuation indentation broke `sh -c` into two commands), de-vacuumed HITL threshold test, zero-citations conclusion branch.

## Test strategy

- New `tests/agents/test_llm_runtime.py`: retry wrapper shape, bare-model escape, JSON mode, probe caching (sync + async shared cache).
- New `TestLangGraphDefaultEngine` in `tests/agents/test_legal_analyst.py`: probe-fail degrade, workflow-crash degrade, request-default assertion.
- `tests/agents/graphs/test_topic_frontier.py`: transport-error contract via the LangChain seam; StateGraph compilation + run-through-graph tests.
- Existing suites must stay green unmodified except where they encoded the old defaults/transports.

## Rollback

Git revert; no migrations. Flipping `use_langgraph` default back restores the old routing without touching the transport layer.
