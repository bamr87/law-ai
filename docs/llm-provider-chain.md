# The LLM provider chain (`law_ai.core.llm`)

Every product-runtime model call in Law AI goes through one ordered chain: [`law_ai.core.llm`](../backend/law_ai/core/llm/router.py) tries each provider named in `LLM_PROVIDER_CHAIN` until one is configured and answers, writes an `llm_call` audit event either way, and raises rather than fabricating when the whole chain fails. Per [docs/constitution.md](constitution.md) §1 (amended 2026-08-11, spec 034 and 2026-09-04, spec 050), **Claude is the default product runtime**; xAI Grok is tier 3; local Ollama is the last-tier fallback, not the default.

This page is the chain's reference. Most of it documents the **Claude transport** ([`law_ai.core.claude_code`](../backend/law_ai/core/claude_code.py)), which backs tiers 1–2 and is the fastest path for local dev because OAuth reuses your existing Claude Code subscription — but the chain, not that transport, is the subject. The other tiers have their own pages: xAI Grok in [ADR 0007](adr/0007-xai-runtime-provider.md) / [spec 050](../specs/050-xai-oauth-provider/spec.md), Ollama in [docs/local-ai.md](local-ai.md), which also covers pinning the runtime to Ollama-only when a matter requires it.

No gate exists anymore. Earlier revisions of the Claude transport required an explicit `LSAT_LLM_PROVIDER=claude_code` opt-in plus a development environment before Claude would run; that gate was **repealed** by spec 034. Every call site — the LSAT tutor, the LSAT content author, and `LegalAnalyst` — now calls [`law_ai.core.llm.agenerate()`](../backend/law_ai/core/llm/router.py) unconditionally, in every environment (dev, prod, and test — test settings blank the credentials instead of gating on environment, see `settings/test.py`). The router tries the chain in order and falls back automatically; nothing needs to be "activated."

## The four tiers

[`law_ai.core.llm.router`](../backend/law_ai/core/llm/router.py) reads `LLM_PROVIDER_CHAIN` (default `claude_code,anthropic_api,xai,ollama`) and tries each named provider in order until one is configured and answers:

1. `claude_code` — Claude via `CLAUDE_CODE_OAUTH_TOKEN` ([`core.claude_code`](../backend/law_ai/core/claude_code.py), `oauth` mode).
2. `anthropic_api` — Claude via `ANTHROPIC_API_KEY` (same module, `api_key` mode).
3. `xai` — Grok via a subscription OAuth token ([`core.xai`](../backend/law_ai/core/xai.py) / [`core.xai_oauth`](../backend/law_ai/core/xai_oauth.py), authorised with `make xai-login`; there is no API-key mode). The tier is **inert** until that login has been run, so a default chain on a fresh clone behaves exactly as it did before spec 050 ([ADR 0007](adr/0007-xai-runtime-provider.md)).
4. `ollama` — the local open-weights model ([docs/local-ai.md](local-ai.md)).

Tiers 1–3 send prompt text to a third party; only tier 4 keeps it on the host.

Every attempt — including the ones that failed before a later tier succeeded — is written to the audit layer via `ProvenanceLogger.log_event` (constitution §5), so a fallback is always visible after the fact. When every tier fails, the caller degrades to an honest refusal, never a fabricated answer (constitution §13).

**Run fully local.** Pin the chain to skip the hosted tiers entirely:

```dotenv
LLM_PROVIDER_CHAIN=ollama
```

Constitution §1 makes this **required**, not optional, for any matter under a confidentiality obligation that forbids third-party processing — prompts sent through either Claude tier or the xAI tier leave the machine, and the default chain now has **two** third-party vendors in front of the local one. Deployments that routinely handle privileged client data should default to this pin rather than opting in per request.

## The Claude transport (`law_ai.core.claude_code`)

Tiers 1 and 2 are one transport with two auth modes. Setting it up, validating it, and running a live agent through it are the three subsections below; the xAI tier and the shared configuration reference follow them.

### Two auth modes, one transport

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

### Setup (OAuth, for local dev)

1. Mint a long-lived token from your Claude Code subscription:

   ```bash
   claude setup-token   # prints an sk-ant-oat01-... OAuth token
   ```

2. Add it to `.env` (see [.env.example](../.env.example)):

   ```dotenv
   CLAUDE_CODE_OAUTH_TOKEN=sk-ant-oat01-...
   CLAUDE_CODE_MODEL=claude-opus-5-5    # default
   ```

   That's sufficient — no provider opt-in flag is needed; the chain tries `claude_code` first by default. To use an API key instead (e.g. no Claude Code subscription), set `ANTHROPIC_API_KEY` and skip the OAuth token; `ANTHROPIC_MODEL` overrides the model id for that tier only, otherwise it follows `CLAUDE_CODE_MODEL`.

   The former `LSAT_LLM_PROVIDER` single-provider pin was removed (BL-20260811-22); an `LSAT_LLM_PROVIDER` line left in a local `.env` is silently ignored. `LLM_PROVIDER_CHAIN` is the only selector; use the local-only pin above if you want to force Ollama instead of Claude.

### Validate the connection

```bash
make validate-claude-code
```

The command ([`validate_claude_code.py`](../backend/law_ai/lsat/management/commands/validate_claude_code.py)) proves tier 1 of the chain end-to-end: it performs a near-free OAuth round-trip against the Messages API, then runs the LSAT tutor through it to confirm the app path works.

The dashboard health endpoint reports the same thing plus the full chain status:

```bash
make local-ai-health   # GET /api/agents/health/local-ai
```

The response includes a `claude_code` object (the OAuth-tier probe) and an `llm_chain` array — every provider in `LLM_PROVIDER_CHAIN`, in try order, with reachability — answering "which provider will actually serve the next request, and why" in one payload.

### Run a live agent

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

## The xAI Grok tier (`law_ai.core.xai`)

Tier 3 is Grok over an xAI **subscription** OAuth token — a device-code flow against `XAI_AUTH_BASE_URL`, not an API key; there is no API-key mode by design ([ADR 0007](adr/0007-xai-runtime-provider.md), [spec 050](../specs/050-xai-oauth-provider/spec.md)).

```bash
make xai-login      # device-code authorisation; writes XAI_CREDENTIALS_PATH (.xai/credentials.json)
make validate-xai   # end-to-end tier probe
```

Until `make xai-login` has been run, the tier reports itself unconfigured and the router skips straight to Ollama. Its knobs (`XAI_MODEL`, `XAI_INTERACTIVE_MODEL`, `XAI_MAX_TOKENS`, `XAI_REQUEST_TIMEOUT_S`, `XAI_MAX_RETRIES`, `XAI_BASE_URL`, `XAI_AUTH_BASE_URL`, `XAI_CREDENTIALS_PATH`) are documented in [.env.example](../.env.example). Grok's terms-of-service and data-retention review is tracked separately (BL-20260904-03, [ADR 0007](adr/0007-xai-runtime-provider.md)) — read it before sending client material through this tier.

## Configuration reference

| Env var | Default | Purpose |
|---|---|---|
| `LLM_PROVIDER_CHAIN` | `claude_code,anthropic_api,xai,ollama` | Ordered provider list; pin to `ollama` for local-only. The `xai` tier is documented in [specs/050-xai-oauth-provider](../specs/050-xai-oauth-provider/spec.md). |
| `CLAUDE_CODE_OAUTH_TOKEN` | _(unset)_ | OAuth token from `claude setup-token` (tier 1). |
| `ANTHROPIC_API_KEY` | _(unset)_ | Standard API key (tier 2). |
| `CLAUDE_CODE_MODEL` | `claude-opus-5-5` | Model id for both Claude tiers. |
| `ANTHROPIC_MODEL` | _(unset)_ | Overrides the model id for tier 2 only; falls back to `CLAUDE_CODE_MODEL`. |
| `CLAUDE_EFFORT` | _(unset)_ | Optional reasoning-effort hint passed through `output_config.effort`. |
| `CLAUDE_CODE_MAX_TOKENS` | `8192` | Max output tokens per call. |
| `CLAUDE_CODE_REQUEST_TIMEOUT_S` | `60` | HTTP timeout. |
| `CLAUDE_CODE_MAX_RETRIES` | `3` | Retries on transient `429/5xx/529`. |
| `ANTHROPIC_BASE_URL` | `https://api.anthropic.com` | API base (override for proxies). |

Every call is recorded through the audit layer (the `model` field shows e.g. `claude_code/claude-opus-5-5` or `anthropic_api/claude-opus-5-5`), so provenance is preserved regardless of which tier served the request.

## See also

- [docs/local-ai.md](local-ai.md) — the Ollama tier, `ChatProviderChain`, and the LangGraph substrate this transport feeds as tiers 1–2.
- [docs/constitution.md](constitution.md) §1 — the runtime LLM policy this page implements.
