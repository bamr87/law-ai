# The Claude transport (`law_ai.core.claude_code`)

[`law_ai.core.claude_code`](../backend/law_ai/core/claude_code.py) is the Anthropic transport that backs tiers 1–2 of the product-runtime LLM chain — Claude over a subscription OAuth token, then Claude over a plain `ANTHROPIC_API_KEY`. Per [docs/constitution.md](constitution.md) §1 (amended 2026-08-11, spec 034), **Claude is the default product runtime**; local Ollama is the chain's last-tier fallback, not the default. This page covers how the transport works, how to configure it (OAuth is the fastest path for local dev, since it reuses your existing Claude Code subscription), and how to pin the runtime to Ollama-only when that's what a matter requires.

No gate exists anymore. Earlier revisions of this module required an explicit `LSAT_LLM_PROVIDER=claude_code` opt-in plus a development environment before Claude would run; that gate was **repealed** by spec 034. Every call site — the LSAT tutor, the LSAT content author, and `LegalAnalyst` — now calls [`law_ai.core.llm.agenerate()`](../backend/law_ai/core/llm/router.py) unconditionally, in every environment (dev, prod, and test — test settings blank the credentials instead of gating on environment, see `settings/test.py`). The router tries the chain in order and falls back automatically; nothing needs to be "activated."

## How Claude fits into the runtime chain

[`law_ai.core.llm.router`](../backend/law_ai/core/llm/router.py) reads `LLM_PROVIDER_CHAIN` (default `claude_code,anthropic_api,xai,ollama`) and tries each named provider in order until one is configured and answers:

1. `claude_code` — Claude via `CLAUDE_CODE_OAUTH_TOKEN` (this module, `oauth` mode).
2. `anthropic_api` — Claude via `ANTHROPIC_API_KEY` (this module, `api_key` mode).
3. `ollama` — the local open-weights model ([docs/local-ai.md](local-ai.md)).

Every attempt — including the ones that failed before a later tier succeeded — is written to the audit layer via `ProvenanceLogger.log_event` (constitution §5), so a fallback is always visible after the fact. When every tier fails, the caller degrades to an honest refusal, never a fabricated answer (constitution §13).

**Run fully local.** Pin the chain to skip the hosted tiers entirely:

```dotenv
LLM_PROVIDER_CHAIN=ollama
```

Constitution §1 makes this **required**, not optional, for any matter under a confidentiality obligation that forbids third-party processing — prompts sent through either Claude tier leave the machine. Deployments that routinely handle privileged client data should default to this pin rather than opting in per request.

## Two auth modes, one transport

| Mode | Credential | Header | Chain tier |
|---|---|---|---|
| `oauth` | `CLAUDE_CODE_OAUTH_TOKEN` (from `claude setup-token`) | `Authorization: Bearer …` + `anthropic-beta: oauth-2025-04-20` | 1 (tried first) |
| `api_key` | `ANTHROPIC_API_KEY` | `x-api-key: …` | 2 (tried when OAuth is absent or failing) |

Both modes hit the same Anthropic Messages API and the same model. OAuth tokens are scoped to the Claude Code CLI surface, so that mode additionally prepends a required identity system block (`"You are Claude Code, Anthropic's official CLI for Claude."`); the API-key mode does not, since a plain API request has no reason to claim to be a CLI.

```
Authorization: Bearer $CLAUDE_CODE_OAUTH_TOKEN
anthropic-beta: oauth-2025-04-20
anthropic-version: 2023-06-01
```

## Setup (OAuth, for local dev)

1. Mint a long-lived token from your Claude Code subscription:

   ```bash
   claude setup-token   # prints an sk-ant-oat01-... OAuth token
   ```

2. Add it to `.env` (see [.env.example](../.env.example)):

   ```dotenv
   CLAUDE_CODE_OAUTH_TOKEN=sk-ant-oat01-...
   CLAUDE_CODE_MODEL=claude-opus-5    # default
   ```

   That's sufficient — no provider opt-in flag is needed; the chain tries `claude_code` first by default. To use an API key instead (e.g. no Claude Code subscription), set `ANTHROPIC_API_KEY` and skip the OAuth token; `ANTHROPIC_MODEL` overrides the model id for that tier only, otherwise it follows `CLAUDE_CODE_MODEL`.

   `LSAT_LLM_PROVIDER` still exists in settings but no code path reads it today (`claude_code.is_selected()`, the function that would check it, has no callers) — it is vestigial. `LLM_PROVIDER_CHAIN` is the real selector; use the local-only pin above if you want to force Ollama instead of Claude.

## Validate the connection

```bash
make validate-claude-code
```

The command ([`validate_claude_code.py`](../backend/law_ai/lsat/management/commands/validate_claude_code.py)) proves tier 1 of the chain end-to-end: it performs a near-free OAuth round-trip against the Messages API, then runs the LSAT tutor through it to confirm the app path works.

The dashboard health endpoint reports the same thing plus the full chain status:

```bash
make local-ai-health   # GET /api/agents/health/local-ai
```

The response includes a `claude_code` object (the OAuth-tier probe) and an `llm_chain` array — every provider in `LLM_PROVIDER_CHAIN`, in try order, with reachability — answering "which provider will actually serve the next request, and why" in one payload.

## Run a live agent

```bash
make lsat-author-demo
# or: make lsat-author-demo ARGS='--section RC --difficulty hard'
```

This runs the `LSATContentAuthor` crew end-to-end through the provider chain — it builds a prompt, drafts a question, parses + validates it against the `DraftQuestion` contract, and logs provenance. On a Claude tier, the draft is pinned with **structured outputs** (`output_config.format` + a JSON Schema) so the model returns schema-valid JSON every time; the agent additionally normalizes the answer choices to the canonical A–E set and falls back to a deterministic offline draft if every tier is unreachable. Transient `429/5xx/529` responses are retried with exponential backoff (`CLAUDE_CODE_MAX_RETRIES`).

```bash
make legal-analyst-demo
make legal-analyst-demo ARGS='--question "Is a browsewrap arbitration clause enforceable?"'
```

`LegalAnalyst` ([`agents_runtime/crews/legal_analyst.py`](../backend/law_ai/agents_runtime/crews/legal_analyst.py)) has two internal paths, both chain-backed:

- **Default** (`use_langgraph=true`, the `AnalysisRequest` default): delegates to `LegalWorkflow` ([docs/local-ai.md](local-ai.md)), whose LLM is `ChatProviderChain` — a LangChain `BaseChatModel` over this same chain (spec 035).
- **Explicit escape hatch** (`use_langgraph=false`): calls `llm.agenerate()` directly for a real IRAC analysis, degrading to a labeled offline placeholder only if every tier fails.

Either way the analysis is Claude-generated by default, not a mock. Its authorities are model-generated and flagged unverified — they still require GraphRAG grounding / human review before any real use.

All three agents — LSAT tutor, LSAT content author, and `LegalAnalyst` — route through the same `law_ai.core.llm.agenerate()` entry point, which tries the chain in order and only degrades to an offline fallback once every tier has failed.

## Configuration reference

| Env var | Default | Purpose |
|---|---|---|
| `LLM_PROVIDER_CHAIN` | `claude_code,anthropic_api,xai,ollama` | Ordered provider list; pin to `ollama` for local-only. The `xai` tier is documented in [specs/050-xai-oauth-provider](../specs/050-xai-oauth-provider/spec.md). |
| `CLAUDE_CODE_OAUTH_TOKEN` | _(unset)_ | OAuth token from `claude setup-token` (tier 1). |
| `ANTHROPIC_API_KEY` | _(unset)_ | Standard API key (tier 2). |
| `CLAUDE_CODE_MODEL` | `claude-opus-5` | Model id for both Claude tiers. |
| `ANTHROPIC_MODEL` | _(unset)_ | Overrides the model id for tier 2 only; falls back to `CLAUDE_CODE_MODEL`. |
| `CLAUDE_EFFORT` | _(unset)_ | Optional reasoning-effort hint passed through `output_config.effort`. |
| `CLAUDE_CODE_MAX_TOKENS` | `8192` | Max output tokens per call. |
| `CLAUDE_CODE_REQUEST_TIMEOUT_S` | `60` | HTTP timeout. |
| `CLAUDE_CODE_MAX_RETRIES` | `3` | Retries on transient `429/5xx/529`. |
| `ANTHROPIC_BASE_URL` | `https://api.anthropic.com` | API base (override for proxies). |
| `LSAT_LLM_PROVIDER` | _(unset)_ | Vestigial — no code path reads it; kept in settings for backward compatibility only. |

Every call is recorded through the audit layer (the `model` field shows e.g. `claude_code/claude-opus-5` or `anthropic_api/claude-opus-5`), so provenance is preserved regardless of which tier served the request.

## See also

- [docs/local-ai.md](local-ai.md) — the Ollama tier, `ChatProviderChain`, and the LangGraph substrate this transport feeds as tiers 1–2.
- [docs/constitution.md](constitution.md) §1 — the runtime LLM policy this page implements.
