# Spec: LangChain/LangGraph first-class + AO-SDLC guide reimplementation

- **ID**: 035-langchain-first-class
- **Status**: shipped
- **Owner**: @bamr87
- **Created**: 2026-08-11
- **Roadmap Epic**: runtime coherence — one LLM stack, one documented SDLC
- **Constitution Compliance**: confirmed against [docs/constitution.md](../../docs/constitution.md) (§1 as amended by spec 034; no further amendment required)

## 1. Problem & Motivation

Spec 034 made the Claude-first provider chain the product runtime, but the LangChain/LangGraph layer around it was only half-implemented:

- LangGraph is the **default analysis engine** (spec 027) and its Postgres checkpointer is provisioned in the container boot chain — yet `langchain-core`, `langchain-ollama`, and both checkpointer packages lived in the *optional* `local-ai` extra. The shipped container only worked because the Dockerfile happened to install the extra; a bare `pip install` produced a package whose default engine could not run.
- The default engine's LLM was a duck-typed shim (`ChainRunnable`) — not a real LangChain `Runnable` — so LangGraph nodes ran outside LangChain's callback/tracing machinery and nothing else built on LangChain could use the chain.
- The LangGraph checkpointer was **silently broken in the dev stack**: docker-compose overrides `DATABASE_URL` but the checkpointer reads `POSTGRES_URL`, so the host-oriented `.env` value (localhost) leaked into containers and boot-time schema setup logged a warning and skipped.
- `AO-SDLC_Outline_Guide.md` was a generic v1 template that still asserted "Claude must never be the product runtime" — repealed by the spec-034 constitution amendment — and described aspirational mechanisms rather than the ones this repo enforces.
- None of the Claude-tier runtime paths had been validated against the live Anthropic API over the operator's OAuth token.

## 2. Goals

- G1: LangChain + LangGraph are core, non-optional stack in the package and the Docker image.
- G2: The provider chain is a first-class LangChain citizen — a real `BaseChatModel`, usable by any LangChain/LangGraph consumer.
- G3: The dev-stack checkpointer actually checkpoints (compose wiring fixed).
- G4: The AO-SDLC guide describes the implemented system, with a repeatable live-validation playbook.
- G5: Every Claude-tier path validated end-to-end over the live OAuth API.

## 3. Non-Goals

- NG1: Streaming through the chain/LangChain layer (tracked as BL-20260811-20).
- NG2: Moving Phoenix/OTel tracing into core deps — it remains the genuinely optional `local-ai` extra.
- NG3: Re-routing CrewAI crews through `ChatProviderChain` (they call the chain directly today; consolidation is a follow-up).
- NG4: Any constitution change — spec 034's amendment already covers this work.

## 4. User Stories

- As a developer building on LangGraph, I want a LangChain-native chat model for the runtime chain, so graphs get Claude-first routing without custom glue.
- As an operator, I want workflow state actually checkpointed in the dev stack, so a backend restart resumes in-flight workflows as documented.
- As a contributor, I want the AO-SDLC guide to describe the real system, so the doc and the gates never disagree.
- As the owner, I want proof the OAuth tier works live, not just under mocks.

## 5. Functional Requirements

- **FR-1**: `langchain-core`, `langchain-ollama`, `langgraph-checkpoint-postgres`, `langgraph-checkpoint-redis` move from the `local-ai` extra into core `dependencies`; the extra retains only Phoenix/OTel tracing.
- **FR-2**: `ChatProviderChain(BaseChatModel)` in `law_ai/core/llm/langchain.py`: system messages fold into the chain request's system prompt, a single human turn passes through verbatim, multi-turn history renders as an explicit transcript, and every `AIMessage` carries `provider` / `model` / `model_label` / `fell_back` in `response_metadata`.
- **FR-3**: `LegalWorkflow`'s default LLM factory returns `ChatProviderChain` (replacing the duck-typed shim).
- **FR-4**: docker-compose sets `POSTGRES_URL` on the backend and worker services so the checkpointer reaches the compose Postgres regardless of `.env`.
- **FR-5**: `validate_claude_code` and the run-agent commands report chain-era state (credentials per tier) instead of the repealed dev-gate fields.
- **FR-6**: `AO-SDLC_Outline_Guide.md` v2.0 documents the implemented loop, governance, runtime chain, LangChain/LangGraph stack, autonomy mapping, gates, observability, and the validation playbook.

## 6. Non-Functional Requirements

- **NFR-AUDIT-1**: `ChatProviderChain` routes through `router.aroute`, so `llm_call` provenance events are unchanged.
- **NFR-COMPAT-1**: The clean-install (no-extras) import smoke must pass — the package's public modules import with core deps only.
- **NFR-VALID-1**: Validation runs against the live Anthropic API over the OAuth token: probe, tutor E2E, IRAC analyst, LangGraph+checkpointer E2E, and the chain health endpoint.

## 7. Data Model Impact

None. The checkpointer tables were always intended (spec 011 FR-13); this spec makes them actually materialize in the dev stack.

## 8. API Surface

None changed.

## 9. Agent / Crew Impact

`LegalWorkflow` (default engine) now runs on a genuine LangChain chat model. Other agents unchanged.

## 10. Validation Evidence (2026-08-11, live OAuth)

| Check | Result |
|---|---|
| `validate_claude_code` probe | reachable, sample `'pong'` |
| LSAT tutor E2E | `used_llm=True`, `model=claude_code/claude-opus-5`, confidence 0.85 |
| `run_legal_analyst` IRAC | confidence 0.86, provenance trace logged, authorities flagged unverified |
| LangGraph StateGraph + `ChatProviderChain` + `AsyncPostgresSaver` | `model_label=claude_code/claude-opus-5`, state checkpointed and re-read by thread_id, `E2E_OK` |
| `GET /api/agents/health/local-ai` | `llm_chain[0]=claude_code` configured+reachable; checkpointer reachable; Ollama fallback listed |
