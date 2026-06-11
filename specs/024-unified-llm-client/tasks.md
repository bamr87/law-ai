# Tasks: Unified LLM Client & Prompt Registry

> Each task must reference one or more `FR-*` / `NFR-*` / `AC-*` IDs from `spec.md`. CI's [spec_validator.py](../../scripts/spec_validator.py) enforces that every requirement in `spec.md` is referenced by at least one task.

## Conventions

- Status: `[ ]` todo / `[~]` in-progress / `[x]` done.
- Owner: GitHub handle or `@copilot` / `@agent:<role>`.
- Each task lists exact files to touch and how to verify.

---

## T-001 — Build the unified `core/llm` client package

- **Refs**: FR-1, FR-4, NFR-AUDIT-1, NFR-RESIL-1, AC-1, AC-2, AC-3, AC-4
- **Owner**: @claude
- **Status**: `[x]`
- **Files**:
  - `backend/lawgraph/core/llm/client.py` (new)
  - `backend/lawgraph/core/llm/__init__.py` (new)
  - `backend/lawgraph/settings/base.py` (add `OLLAMA_MAX_RETRIES`, `OLLAMA_EMBED_MODEL`)
- **Steps**:
  1. Wrap `ollama.AsyncClient`/`ollama.Client` (lazy imports) with `generate`, `generate_stream`, `chat`, `embed`, `generate_sync`.
  2. Add exponential-backoff retry on transient failures only; normalise errors to `LLMError`/`LLMUnavailableError`/`LLMResponseError`.
  3. Record an `llm_call` audit event per call (hashes, latency, retries, caller, prompt id+version) and open an OTEL span when available.
  4. Provide `get_llm_client()`/`reset_llm_client()` plus `async_client_factory`/`sync_client_factory` DI seams for tests.
- **Verify**:
  - `docker compose run --rm backend pytest tests/core/test_llm_client.py -q` passes.
  - `make typecheck` clean on the new package.

## T-002 — Adapter for LegalWorkflow (`_LLMLike` protocol)

- **Refs**: FR-2, NFR-COMPAT-1, AC-6
- **Owner**: @claude
- **Status**: `[x]`
- **Files**:
  - `backend/lawgraph/core/llm/adapter.py` (new)
  - `backend/lawgraph/agents_runtime/graphs/legal_workflow.py` (`_default_llm_factory`)
- **Steps**:
  1. Implement `LLMClientAdapter.ainvoke(prompt) -> str` delegating to `LLMClient.generate` (temperature 0.0, caller `legal_workflow`).
  2. Swap `_default_llm_factory` from `ChatOllama` to the adapter; drop the `langchain_ollama` import.
- **Verify**:
  - Existing `tests/agents/graphs/test_legal_workflow.py` passes unchanged (fakes still injected via `llm_factory`).
  - `grep -rn "ChatOllama\|langchain_ollama" backend/lawgraph --include="*.py"` → only `core/llm` (none today).

## T-003 — Migrate the five legacy Ollama call sites

- **Refs**: FR-3, NFR-COMPAT-1, AC-4, AC-6
- **Owner**: @claude
- **Status**: `[x]`
- **Files**:
  - `backend/lawgraph/agents_runtime/crews/lsat_content_author.py`
  - `backend/lawgraph/lsat/services/tutor.py`
  - `backend/lawgraph/agents_runtime/graphs/topic_frontier.py`
  - `backend/lawgraph/agents_runtime/crews/test_synthesizer.py`
  - `backend/lawgraph/eval/legalbench.py`
  - `backend/tests/agents/graphs/test_topic_frontier.py` (re-point urllib patch to the new seam)
- **Steps**:
  1. Reimplement each module-level seam (`_ollama_generate` / `_call_ollama`) on `LLMClient`, preserving signatures so existing test patches keep working.
  2. Preserve error contracts: `RuntimeError` from `topic_frontier`/`test_synthesizer`/`legalbench` seams; add `LLMError` to the graceful-fallback `except` tuples in the LSAT author and tutor.
  3. Remove the now-dead urllib/httpx plumbing and unused imports.
- **Verify**:
  - `make test-backend` green (LSAT author, tutor/proposals, TopicFrontier, TestSynthesizer, LegalBench CLI suites).
  - `grep -rn "api/generate" backend/lawgraph --include="*.py"` → empty outside `core/llm`.

## T-004 — Versioned prompt registry + externalised workflow prompts

- **Refs**: FR-5, NFR-COMPAT-1, AC-5
- **Owner**: @claude
- **Status**: `[x]`
- **Files**:
  - `backend/lawgraph/agents_runtime/prompts/loader.py` (new)
  - `backend/lawgraph/agents_runtime/prompts/legal_workflow/{retrieve,analyze}.md` (converted to templates; metadata kept in a leading HTML comment)
  - `backend/lawgraph/agents_runtime/graphs/legal_workflow.py` (`_node_prompt` helper replaces inline strings)
  - prompt loading in `lsat_content_author.py`, `topic_frontier.py`, `test_synthesizer.py`
- **Steps**:
  1. Implement `load_prompt(name, version)` → `PromptTemplate` (text, sha256, `{{placeholder}}` render), resolving `.vN.md` then unversioned files, highest version when unspecified.
  2. Convert the two LLM-backed legal_workflow prompt files into literal templates whose rendered output matches the legacy inline strings.
  3. Route all file-based prompt loads through the loader.
- **Verify**:
  - `docker compose run --rm backend pytest tests/agents/test_prompt_loader.py -q` passes (includes render-parity assertions).

## T-005 — Tests for client + loader

- **Refs**: AC-1, AC-2, AC-3, AC-4, AC-5, NFR-AUDIT-1, NFR-RESIL-1
- **Owner**: @claude
- **Status**: `[x]`
- **Files**:
  - `backend/tests/core/test_llm_client.py` (new — 13 tests: success/audit, options forwarding, retry, 4xx no-retry, exhaustion, stream, chat, embed, sync retry, sync error, adapter, singleton)
  - `backend/tests/agents/test_prompt_loader.py` (new — 7 tests)
- **Verify**:
  - `make test-backend` green; coverage stays ≥75%.

## T-006 — Roadmap doc + backlog mirror

- **Refs**: AC-6 (documents the grep gate and follow-on phases)
- **Owner**: @claude
- **Status**: `[x]`
- **Files**:
  - `docs/roadmap-framework-ai-integration.md` (new)
  - `BACKLOG.md` (new `BL-20260611-*` entries)
- **Steps**:
  1. Commit the 6-phase framework/AI-integration roadmap with phase→spec/backlog mapping.
  2. Mirror this spec's follow-ups into BACKLOG.md.
- **Verify**:
  - `make lint-specs` (spec_validator + backlog_lint) exits 0.

---

## Done-When (Definition of Done)

- All tasks `[x]`.
- All `AC-*` from `spec.md` covered by passing tests.
- `make lint && make test` green.
- LegalBench delta recorded in PR description (if §11 of spec applies) — N/A: transport-only, no reasoning change.
- Provenance logging verified manually for new agent paths.
- **`## Follow-ups Discovered` section below populated** — at minimum, every implementer must record one of: a new BACKLOG entry, a refactor candidate, a missing test, or `_none_` (must be justified in the PR).

---

## Follow-ups Discovered

> Append-only. Mirror each item into [BACKLOG.md](../../BACKLOG.md) with a `BL-YYYYMMDD-NN` id. CI ([scripts/spec_validator.py](../../scripts/spec_validator.py)) checks this section exists. CI ([scripts/backlog_lint.py](../../scripts/backlog_lint.py)) checks the BACKLOG mirror.

- BL-20260611-01 — refactor, low — Drop `langchain-ollama` from the `[local-ai]` extra once the `LLMClientAdapter` has soaked; `legal_workflow` no longer imports `ChatOllama`.
- BL-20260611-02 — feature, med — Wire `LLMClient.generate_stream` into the analysis WS path for token-level `agent_token` events (extends BL-20260602-05/-06; roadmap Phase 4).
- BL-20260611-03 — refactor, low — Remove the unused `chromadb` dependency when Phase-2 GraphRAG lands on Neo4j native vector indexes (roadmap Phase 2; specs 025–026).
- BL-20260611-04 — doc-gap, low — Keep `docs/roadmap-framework-ai-integration.md` phase markers current as specs 025–030 ship.
- BL-20260611-05 — test-gap, low — Add an integration test exercising `LLMClient.generate` against the real Ollama container (`-m integration`) to catch ollama-package response-shape drift.
