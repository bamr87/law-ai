# Spec: Claude-default LLM provider chain

- **ID**: 034-claude-default-runtime
- **Status**: shipped
- **Owner**: @bamr87
- **Created**: 2026-08-11
- **Roadmap Epic**: runtime quality — answer grade on legal analysis
- **Constitution Compliance**: **requires and includes an amendment to [docs/constitution.md](../../docs/constitution.md) §1** (see §3 and §10)

## 1. Problem & Motivation

The product runtime was pinned to a local 7B open-weights model. On the work this platform exists to do — IRAC analysis, issue spotting, LSAT item authoring — that model is the binding constraint on output quality, and no amount of retrieval or prompt work moves it past its ceiling.

A Claude path already existed but was deliberately unreachable in production: `law_ai.core.claude_code` refused to engage unless `DEBUG`/`ENVIRONMENT` named a development profile, because constitution §1 rejected any closed-source model as product runtime. The result was a two-tier product — good answers on a laptop, degraded answers everywhere else — and three separate ad-hoc `if claude_code.is_active(): … else: ollama` branches that each re-implemented provider selection slightly differently.

The owner has decided the quality gain is worth sending prompt text to a third party, and has authorised the corresponding constitution amendment.

## 2. Goals

- G1: One ordered provider chain owns every model call in the product.
- G2: Claude is the default runtime; the local model remains a fully supported pin.
- G3: Failure of any tier degrades to the next tier, and total failure degrades to an honest refusal.
- G4: Provenance records which provider actually served each call, including skipped and failed tiers.

## 3. Non-Goals

- NG1: Adding any vendor besides Anthropic and Ollama. Constitution §1 as amended still rejects that without a further amendment.
- NG2: Routing the LegalBench harness through the chain — benchmark numbers must stay comparable, so it stays pinned to Ollama.
- NG3: Changing which agent edits this codebase. Dev orchestration is a separate layer and is untouched.
- NG4: Streaming responses through the chain (the WebSocket consumer path keeps its current behaviour).

## 4. User Stories

- As a lawyer using Analysis Studio, I want the best available model to answer, so that the IRAC brief is worth reading.
- As an operator handling privileged client data, I want to force all inference on-premises, so that no client text leaves my infrastructure.
- As an auditor, I want to know which provider produced a given answer, so that I can assess and reproduce it.
- As a developer, I want one place that decides provider order, so that agents cannot each invent their own fallback rules.

## 5. Functional Requirements

- **FR-1**: A provider chain, ordered and configured by `LLM_PROVIDER_CHAIN`, defaulting to `claude_code,anthropic_api,ollama`.
- **FR-2**: `claude_code` authenticates with a subscription OAuth token (`Authorization: Bearer` + the `oauth-2025-04-20` beta header, with the Claude Code identity system block).
- **FR-3**: `anthropic_api` authenticates with `ANTHROPIC_API_KEY` via `x-api-key`, and must **not** send the beta header or the identity block.
- **FR-4**: `ollama` remains a first-class provider and the chain's last tier.
- **FR-5**: Routing tries each provider in order; an unconfigured provider is skipped with a recorded reason, a failing provider is recorded and the next is tried.
- **FR-6**: When every provider fails, the router raises an error carrying every per-provider reason; callers degrade to an honest refusal.
- **FR-7**: A caller may restrict the chain (`providers=`) and override a model per provider (`models=`), so reproducibility-sensitive paths can pin a tier.
- **FR-8**: The dev-only gate on the Claude provider is removed; `is_development()` survives only as reported diagnostic state.
- **FR-9**: The health endpoint reports every tier in order, with configured/reachable state and the model each would use.
- **FR-10**: The agent dashboard shows the chain in order and names the tier that will serve the next request.

## 6. Non-Functional Requirements

- **NFR-AUDIT-1**: Every routed call writes an `llm_call` provenance event with provider, model, latency, and the full attempt chain. A failure of the audit sink must not fail the request.
- **NFR-SEC-1**: Credentials are never logged and never sent to the wrong tier (an OAuth token must not be sent as `x-api-key`, or vice versa).
- **NFR-PRIV-1**: `LLM_PROVIDER_CHAIN=ollama` must be sufficient, on its own, to guarantee no prompt text leaves the host.
- **NFR-COMPAT-1**: The transport must not send `temperature`, `top_p`, or `top_k` — removed on current Claude models, and a 400 if sent.
- **NFR-COMPAT-2**: `stop_reason: "refusal"` and `stop_reason: "max_tokens"` must raise rather than return an empty or truncated string as if it were an answer.

## 7. Data Model Impact

None. No new graph nodes, tables, or collections. The `llm_call` provenance event is a new audit **event type**, written through the existing `ProvenanceLogger.log_event` sink.

## 8. API Surface

- `GET /api/agents/health/local-ai` — response gains an `llm_chain` array: `{provider, position, configured, reachable?, model?, reason?, error?}`, ordered by attempt position.

## 9. Agent / Crew Impact

`LegalAnalyst`, `LSATContentAuthor`, the LSAT tutor, `LegalWorkflow` (the default analysis engine), `TopicFrontier`, and `TestSynthesizer` all move from a per-agent provider branch to `law_ai.core.llm`. The LSAT content factory keeps explicitly-pinned executors by design: a generated bank must be attributable to one model.

## 10. Constitution Amendment

This spec is only valid alongside the §1 amendment it ships. The amendment repeals the closed-source-runtime rejection rule, names the sanctioned chain, and retains — explicitly — the local-first-reachable, provenance, no-fabrication, and no-third-vendor rules. It also records the two costs accepted: prompt text leaving the host, and provider-dependent reproducibility.

## 11. Risks

| Risk | Mitigation |
|---|---|
| Legal text sent to a third party | Documented in §1, AGENTS.md, CLAUDE.md, `.env.example`; `ollama` pin is a supported, tested configuration |
| Cost/rate-limit exposure on hosted tiers | `CLAUDE_EFFORT` and `CLAUDE_CODE_MAX_TOKENS` are operator-tunable; the chain degrades to local rather than failing |
| Silent quality change in evals | LegalBench stays pinned to Ollama (NG2) |
| Truncated/refused responses read as answers | NFR-COMPAT-2 raises on both, so the chain falls through |
