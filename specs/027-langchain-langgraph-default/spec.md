# Spec: LangChain + LangGraph as the Framework-Wide Engine

- **ID**: 027-langchain-langgraph-default
- **Status**: shipped
- **Owner**: @bamr87
- **Created**: 2026-08-10
- **Roadmap Epic**: continuous-evolution hardening (follow-on to spec 026)
- **Constitution Compliance**: confirmed against [docs/constitution.md](../../docs/constitution.md) — §2 (CrewAI + LangGraph locked stack; LangChain core already ships via `langchain-ollama`/`langchain-core`, no new framework), §4 (provenance), §8 (httpx + tenacity retries — LangChain's `with_retry` is tenacity-backed), §13 (honest refusals)

## 1. Problem & Motivation

The stack lock names LangGraph as the workflow engine, but before this spec it
was fringe: `LegalWorkflow` was opt-in (`use_langgraph=false` default, so the
flagship endpoint served the no-engine stub), `TopicFrontier` claimed to be a
LangGraph StateGraph while executing nodes sequentially, and three call sites
(`TestSynthesizer`, `TopicFrontier`, plus the workflow's own factory) each
hand-rolled their own Ollama transport (raw `urllib`, no retries — while the
dev-only Claude client had full backoff). Result: the constitutionally
mandated product runtime was reached through the least robust, least uniform
code paths, and the "LangGraph platform" claim was mostly aspiration.

## 2. Goals

- G1: One shared LangChain transport (`ChatOllama` + tenacity-backed retry)
  used by every Ollama-backed agent path (extends BL-20260810-05).
- G2: LangGraph (`LegalWorkflow`) is the DEFAULT engine for `/api/analysis`,
  wrapped in a resilience boundary that degrades honestly (never 500s) when
  Ollama or the langgraph stack is unavailable.
- G3: `TopicFrontier` becomes a real compiled `StateGraph` (fulfilling spec
  018's claim), with a sequential fallback for bare installs, and its LLM call
  logged through `core.provenance`.
- G4: Frontend defaults match the backend default (LangGraph toggles on).

## 3. Non-Goals

- NG1: Durable LangGraph checkpointer threads on the default API path
  (follow-up — requires checkpointer-schema lifecycle on every request).
- NG2: Migrating the LSAT tutor / LSATContentAuthor / factory executors onto
  the shared transport (follow-up; they carry dual-provider claude_code logic).
- NG3: Real GraphRAG retrieval (BL-20260810-01) — the default engine still
  refuses on an empty corpus, now visibly via the coverage envelope.
- NG4: LangChain agents/chains beyond the runnable transport — CrewAI remains
  the crew abstraction per §2.

## 4. User Stories

- As a user of Analysis Studio, I want the real retrieval-backed workflow by
  default, so that answers come from the local LLM + knowledge graph instead
  of a stub.
- As a developer, I want every agent LLM call to share one retrying LangChain
  transport, so that transient Ollama hiccups don't fail whole workflows.
- As a maintainer, I want TopicFrontier to be an actual StateGraph, so that
  the codebase matches its specs and gains LangGraph's execution semantics.

## 5. Functional Requirements

- **FR-1**: New `law_ai.agents_runtime.llm` module: `build_chat_ollama()`
  returns a `ChatOllama` runnable wrapped with `with_retry` (3 attempts,
  exponential jitter, transient-error allowlist); `generate_text_sync()` for
  sync call sites; `coerce_text()`; import-safe without the `local-ai` extra
  (`LLMUnavailableError`).
- **FR-2**: TTL-cached Ollama availability probes `ollama_available()` /
  `ollama_available_async()` (1 s timeout, 15 s cache, shared cache).
- **FR-3**: `AnalysisRequest.use_langgraph` defaults to `true`;
  `LegalAnalyst._run_via_langgraph` probes availability first and catches
  engine failures (ImportError, transport errors), returning a degraded
  `[ENGINE UNAVAILABLE]` refusal logged as `fallback/offline` instead of
  raising.
- **FR-4**: `LegalWorkflow._default_llm_factory` routes through
  `build_chat_ollama()`.
- **FR-5**: `TestSynthesizer._call_ollama` and `TopicFrontier._call_ollama`
  keep their signatures + `RuntimeError` contracts but transport via
  `generate_text_sync` (raw `urllib` removed).
- **FR-6**: `TopicFrontier.run` executes a compiled
  `StateGraph(TopicFrontierState)` (scan_graph → prioritize → dispatch →
  summarize) when langgraph is importable, sequential fallback otherwise;
  node functions keep DI-kwarg signatures for direct unit testing.
- **FR-7**: `TopicFrontier`'s prioritize LLM call is logged via
  `provenance.log_agent_call` with model, latency, prompt id + version (§4).
- **FR-8**: Frontend LangGraph toggles default ON; `AnalysisStudio` sends the
  explicit boolean (an omitted flag would silently re-enable the engine
  server-side after opt-out).

## 6. Non-Functional Requirements

- **NFR-PERF-1**: When Ollama is down, `/api/analysis` still responds fast:
  the probe fails in ≤1 s once per 15 s window (cached thereafter) — no
  retry-budget burn on the request path.
- **NFR-AUDIT-1**: All new logging goes through `core.provenance`; fallback
  outputs are logged as `fallback/offline`, never a real model name.
- **NFR-SEC-1**: LangChain `with_retry` is tenacity-backed and the probe uses
  `httpx` (constitution §8); no new dependencies added (langchain-core and
  langchain-ollama already ship in the `local-ai` extra).

## 7. Data Model Impact

None. No schema changes; API request default flip only (`use_langgraph`).

## 8. API Surface

`POST /api/analysis`: `use_langgraph` now defaults to `true`. Response shape
unchanged from spec 026 (degraded fallbacks reuse the spec-026 fields).
Explicit `use_langgraph: false` preserves the previous non-engine behavior.

## 9. Agent / Crew Impact

`LegalAnalyst` (default routing + resilience boundary), `LegalWorkflow`
(shared transport), `TopicFrontier` (real StateGraph + provenance + shared
transport), `TestSynthesizer` (shared transport). No new agents; no prompt
changes.

## 10. Acceptance Criteria

- **AC-1**: `AnalysisRequest(text="x").use_langgraph is True`, and a POST with
  no flag routes through the LangGraph path (verified by the probe/fallback
  unit tests).
- **AC-2**: With the availability probe returning False, `LegalAnalyst.run`
  returns `degraded=true`, `confidence=0.0`, `requires_review=true`, rule
  containing `ENGINE UNAVAILABLE` — and does not raise.
- **AC-3**: With the probe True and `LegalWorkflow.invoke` raising `OSError`,
  the same degraded contract holds (no exception escapes).
- **AC-4**: `build_chat_ollama()` returns a `RunnableRetry` with 3 attempts;
  `retries=1` returns the bare `ChatOllama`; `output_format="json"` sets
  Ollama JSON mode.
- **AC-5**: `TopicFrontier._build_graph()` compiles with nodes
  `{scan_graph, prioritize, dispatch, summarize}` and `run()` completes
  through `graph.ainvoke` with injected fakes.
- **AC-6**: The probe caches: two consecutive `ollama_available()` calls
  issue exactly one HTTP request; the async twin serves the shared cache.

## 11. LegalBench Impact

- Tasks affected: none directly (transport + routing change, prompts
  unchanged). The eval harness still calls its own path.
- Expected delta: 0 pp. Retries can only reduce spurious infra failures.

## 12. Risks & Open Questions

- **R-1**: Default-on LangGraph makes `/api/analysis` latency depend on the
  local Ollama when it IS up (real model inference, seconds). This is the
  intended product behavior; the UI toggle remains for the stub path.
- **R-2**: The probe adds one 1 s-bounded HTTP call per 15 s window per
  process — negligible, but a Redis-shared probe would suit multi-worker
  deployments (follow-up).

## 13. Out of Scope / Follow-ups

See `tasks.md` → `## Follow-ups Discovered` (mirrored into BACKLOG.md as
BL-20260810-13 … BL-20260810-16).
