# Spec: Unified LLM Client & Prompt Registry

- **ID**: 024-unified-llm-client
- **Status**: shipped
- **Owner**: @bamr87
- **Created**: 2026-06-11
- **Roadmap Epic**: [docs/roadmap-framework-ai-integration.md](../../docs/roadmap-framework-ai-integration.md) — Phase 1
- **Constitution Compliance**: confirmed against [docs/constitution.md](../../docs/constitution.md) (§1 local-first Ollama unchanged; §4 every LLM call audited)

## 1. Problem & Motivation

The repo review behind the framework/AI-integration roadmap found **five separate hand-rolled Ollama call paths**: LangChain `ChatOllama` in `legal_workflow.py`, httpx in `lsat_content_author.py` and `lsat/services/tutor.py`, and urllib in `topic_frontier.py`, `test_synthesizer.py`, and `eval/legalbench.py`. None retried transient failures, none pooled connections, all hard-coded `"stream": False`, and provenance coverage varied per site. The LegalWorkflow node prompts were hardcoded inline even though versioned prompt files already existed (unwired) under `agents_runtime/prompts/legal_workflow/`. This blocks the roadmap's later phases (GraphRAG embeddings need an `embed()` API; progressive streaming needs `stream=True`).

## 2. Goals

- G1: One audited, retrying, streaming-capable client wrapping the official `ollama` package, used by every agent/eval/tutor path.
- G2: A versioned prompt registry so no prompt text lives inline in node code, and provenance can pin the exact prompt that produced an output.

## 3. Non-Goals

- NG1: No retrieval/embedding pipeline (roadmap Phase 2, specs 025–026).
- NG2: No change to which model answers user queries — Ollama with `OLLAMA_DEFAULT_MODEL` stays the runtime LLM.
- NG3: No wiring of token streaming into Channels/WS yet (roadmap Phase 4); this spec only makes streaming *possible*.

## 4. User Stories

- As a platform operator, I want every LLM call to retry transient Ollama failures and log a uniform provenance event, so that agent runs are resilient and fully auditable from one event shape.
- As an agent developer, I want a single client with `generate/chat/embed/stream`, so that new agents never re-implement HTTP plumbing.
- As a prompt engineer, I want prompts resolved from versioned files with content hashes, so that I can iterate on prompt text without touching workflow code and trace any output back to its exact prompt.

## 5. Functional Requirements

- **FR-1**: New `backend/lawgraph/core/llm/` package exposing `LLMClient` with `generate`, `generate_stream`, `chat`, `embed`, and `generate_sync`, defaulting host/model/timeout/retries from Django settings (`OLLAMA_BASE_URL`, `OLLAMA_DEFAULT_MODEL`, `OLLAMA_REQUEST_TIMEOUT_S`, `OLLAMA_MAX_RETRIES`), plus a shared `get_llm_client()` instance. Errors normalise to an `LLMError` hierarchy (`LLMUnavailableError` transient / `LLMResponseError` non-transient).
- **FR-2**: `LegalWorkflow._default_llm_factory` returns an `LLMClientAdapter` satisfying the existing `_LLMLike` (`ainvoke`) protocol — no node code changes, no `langchain_ollama` import.
- **FR-3**: All five legacy call sites (`lsat_content_author._ollama_generate`, `tutor._ollama_generate`, `topic_frontier._call_ollama`, `test_synthesizer._call_ollama`, `eval/legalbench._call_ollama`) delegate to `LLMClient`, preserving their module-level patch seams and error contracts (RuntimeError where callers expect it; graceful offline fallbacks intact).
- **FR-4**: Every client call records an `llm_call` audit event (endpoint, model, caller, prompt/response hashes, latency, retry count, ok/error, optional prompt id+version) via `core/audit_jsonl.py`, and opens an OTEL span when the `local-ai` extra is installed.
- **FR-5**: New `agents_runtime/prompts/loader.py` resolving `<name>[.vN].md` files to `PromptTemplate` objects (text + sha256 + `{{placeholder}}` rendering, leading HTML-comment metadata stripped). LegalWorkflow's inline retrieve/analyze prompts move to the existing `prompts/legal_workflow/*.md` files; `lsat_content_author`, `topic_frontier`, and `test_synthesizer` load their prompts through the same loader.

## 6. Non-Functional Requirements

- **NFR-AUDIT-1**: No LLM call path bypasses the audit layer; audit-write failures never break the calling agent (swallowed, per `audit_jsonl.record`).
- **NFR-RESIL-1**: Transient failures (connection refused, timeout, 5xx) retry with exponential backoff up to `OLLAMA_MAX_RETRIES`; 4xx errors never retry.
- **NFR-COMPAT-1**: Existing test suites that patch `_ollama_generate` / `_call_ollama` keep passing unchanged (seams preserved); rendered workflow prompts are byte-equivalent in substance to the previous inline strings.

## 7. Data Model Impact

None. No Neo4j/Postgres schema changes. New settings keys `OLLAMA_MAX_RETRIES` (default 2) and `OLLAMA_EMBED_MODEL` (default "", Phase-2 seam) added to `settings/base.py`.

## 8. API Surface

No HTTP API changes. New internal Python API: `lawgraph.core.llm.{LLMClient, LLMClientAdapter, LLMError, LLMResponseError, LLMUnavailableError, get_llm_client, reset_llm_client}` and `lawgraph.agents_runtime.prompts.loader.{load_prompt, PromptTemplate}`.

## 9. Agent / Crew Impact

LegalWorkflow, LSATContentAuthor, LsatTutor, TopicFrontier, TestSynthesizer, and the LegalBench harness all switch transport to `LLMClient`. No agent contract (`run(input) -> dict`/Pydantic) changes; `human_approval_required` flags untouched.

## 10. Acceptance Criteria

- **AC-1**: `LLMClient.generate` returns the response text and records exactly one `llm_call` event with prompt/response hashes, caller label, and `ok=True`.
- **AC-2**: A transient failure followed by success returns the success result with `retries=1`; a 4xx error raises `LLMResponseError` after a single attempt; exhausted retries raise `LLMUnavailableError` with `ok=False` logged.
- **AC-3**: `generate_stream` yields text chunks in order and records a `generate_stream` event with the chunk count.
- **AC-4**: `generate_sync` provides the same retry/provenance semantics for the non-async call sites (LegalBench CLI, TopicFrontier prioritize).
- **AC-5**: `load_prompt` resolves explicit and highest-version files, strips metadata comments, and the rendered `legal_workflow/{retrieve,analyze}` templates reproduce the legacy inline prompt strings.
- **AC-6**: `grep` finds no `api/generate`, `ChatOllama`, or `langchain_ollama` references in `backend/lawgraph/` outside `core/llm/`.

## 11. LegalBench Impact

- Tasks affected: none semantically — the harness's transport changes but prompts/scoring are untouched.
- Expected delta: 0 pp (transport-only change). The retry path can only reduce spurious failures.

## 12. Risks & Open Questions

- **R-1**: The `ollama` package's response objects differ across versions (pydantic model vs dict) — mitigated by the `_extract` helper handling both shapes.
- **R-2**: Retries lengthen worst-case latency on hard outages (~`backoff_base * (2^n - 1)`) — bounded by `OLLAMA_MAX_RETRIES=2` default (≈1.5 s added).

## 13. Out of Scope / Follow-ups

- Dropping the now-unused `langchain-ollama` extra dependency (soak first).
- Wiring `generate_stream` into the analysis WS path (roadmap Phase 4).
- Removing the unused `chromadb` dependency (roadmap Phase 2).
