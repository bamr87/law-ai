# Tasks: LangChain + LangGraph as the Framework-Wide Engine

Spec: [spec.md](spec.md) · Plan: [plan.md](plan.md)

- [x] **T-001** — Shared LangChain transport module (FR-1, FR-2, AC-4, AC-6, NFR-SEC-1)
  - `agents_runtime/llm.py`: `build_chat_ollama` (retry-wrapped ChatOllama), `generate_text_sync`, `coerce_text`, TTL-cached sync+async availability probes, `LLMUnavailableError`, `reset_probe_cache`.
- [x] **T-002** — LegalWorkflow on the shared transport (FR-4)
  - `_default_llm_factory` → `build_chat_ollama()`.
- [x] **T-003** — LangGraph as default engine with resilience boundary (FR-3, AC-1, AC-2, AC-3, NFR-PERF-1, NFR-AUDIT-1)
  - `AnalysisRequest.use_langgraph=true`; probe-first degrade; engine exceptions caught → `[ENGINE UNAVAILABLE]` refusal logged `fallback/offline`; new `TestLangGraphDefaultEngine` suite.
- [x] **T-004** — TestSynthesizer via shared transport (FR-5)
  - `_call_ollama` internals swapped; seam + RuntimeError contract kept.
- [x] **T-005** — TopicFrontier real StateGraph + provenance (FR-6, FR-7, AC-5)
  - `_build_graph()` compiled StateGraph; sequential fallback; `_call_ollama` via shared transport; prioritize LLM call through `provenance.log_agent_call`; compilation + run-through-graph tests.
- [x] **T-006** — Frontend default flip (FR-8)
  - Both LangGraph toggles default on; `AnalysisStudio` sends explicit boolean; `AgentDashboard` mode label no longer calls the stub "legacy".
- [x] **T-007** — Review-driven fixes from the spec-026 adversarial pass (AC-2, NFR-AUDIT-1)
  - Phoenix healthcheck → exec-form `["CMD","python","-c",…]` (distroless image has no `/bin/sh`, so the CMD-SHELL probe could never pass and `up --wait` failed).
  - Backend debug-override command collapsed to one line (YAML folded-scalar indentation split it into two shell commands: debugpy exited with a usage error and `-m daphne` ran as a nonexistent command).
  - `test_low_confidence_triggers_hitl_flag` de-vacuumed: PrecedentHunter also patched non-degraded so ONLY the confidence-threshold branch can set the flag; inverse high-confidence case added.
  - Zero-citations conclusion branch: retrieval-backed answers citing no authorities now conclude "Pending human review" instead of "Analysis complete" (§13 attribution).

## Follow-ups Discovered

- Durable LangGraph checkpointer threads on the default `/api/analysis` path
(resume by `thread_id`), managing the AsyncPostgresSaver lifecycle per-request or via a pooled saver.
- Migrate the LSAT tutor, LSATContentAuthor, and factory executors onto
`agents_runtime.llm` so the dual-provider (claude_code/Ollama) agents share the retry-wrapped transport; reconcile with the PR #19 `LLMClient` rebase (BL-20260716-01).
- Share the Ollama availability-probe verdict across workers (Redis key with the same TTL) so multi-process deployments don't probe independently.
- Surface engine state in the Analysis Studio UI: distinguish "engine
unavailable (degraded)" responses from real LangGraph runs using `irac.degraded` + `irac.rule` markers, so users know Ollama is down rather than reading an empty-looking analysis.
