# Claude Code as a dev-time LLM (LSAT)

A **development-only** integration that lets the LSAT tutor borrow your local [Claude Code](https://claude.com/claude-code) OAuth subscription as an alternative to a running Ollama instance — handy when iterating on a laptop without the local model stack up.

## Boundary (read this first)

This is a **dev-time tool**, not a product runtime path. Per [docs/constitution.md](constitution.md) §1 and [AGENTS.md](../AGENTS.md) ("Development Orchestration"), **Claude must never be the product runtime LLM** — Ollama (local-first, open-weights) stays the default. The integration enforces this: it engages only when **all** of the following hold, and otherwise falls back to Ollama / the deterministic offline path:

1. `LSAT_LLM_PROVIDER=claude_code` (explicit operator opt-in), **and**
2. the process is in a development environment (`DEBUG=true` or
   `ENVIRONMENT=development`), **and**
3. a `CLAUDE_CODE_OAUTH_TOKEN` is present.

The gate lives in [`law_ai.core.claude_code`](../backend/law_ai/core/claude_code.py) (`is_active()`); production and test environments can never activate it.

## How it connects (OAuth, not an API key)

The backend talks to the Anthropic Messages API exactly the way the Claude Code CLI does: an **OAuth bearer token** plus the `oauth-2025-04-20` beta header — not an `x-api-key`. The first system block identifies the request as Claude Code, as OAuth tokens require.

```
Authorization: Bearer $CLAUDE_CODE_OAUTH_TOKEN
anthropic-beta: oauth-2025-04-20
anthropic-version: 2023-06-01
```

## Setup

1. Mint a long-lived token from your Claude Code subscription:

   ```bash
   claude setup-token   # prints an sk-ant-oat01-... OAuth token
   ```

2. Add it to `.env` (see [.env.example](../.env.example)) and opt in:

   ```dotenv
   LSAT_LLM_PROVIDER=claude_code
   CLAUDE_CODE_OAUTH_TOKEN=sk-ant-oat01-...
   CLAUDE_CODE_MODEL=claude-opus-4-8        # default
   ```

   Keep `LSAT_LLM_PROVIDER=ollama` (the default) to use the local model.

## Validate the connection

```bash
make validate-claude-code
```

The command (`backend/law_ai/lsat/management/commands/validate_claude_code.py`) prints the gate status, performs a near-free OAuth round-trip, and — when fully opted in — runs the LSAT tutor end-to-end through Claude Code to prove the app path works.

The dashboard health endpoint also reports it under `claude_code`:

```bash
make local-ai-health   # GET /api/agents/health/local-ai
```

## Run a live agent

With the gate active, run the `LSATContentAuthor` crew end-to-end against Claude Code — it builds a prompt, drafts a question, parses + validates it against the `DraftQuestion` contract, and logs provenance:

```bash
make lsat-author-demo
# or: make lsat-author-demo ARGS='--section RC --difficulty hard'
```

On the Claude Code path the draft is pinned with **structured outputs** (`output_config.format` + a JSON Schema) so Opus returns schema-valid JSON every time; the agent additionally normalizes the answer choices to the canonical A–E set and falls back to a deterministic offline draft if the provider is unreachable. Transient `429/5xx/529` responses are retried with exponential backoff (`CLAUDE_CODE_MAX_RETRIES`).

The **`LegalAnalyst`** crew (`agents_runtime`) shares the same gate: when Claude Code is active, its default (non-LangGraph) path produces a real IRAC analysis over OAuth instead of the static mock, degrading to a labeled placeholder on failure. Run it live:

```bash
make legal-analyst-demo
make legal-analyst-demo ARGS='--question "Is a browsewrap arbitration clause enforceable?"'
```

> `LegalAnalyst` IRAC authorities are model-generated and flagged unverified —
> they still require GraphRAG grounding / human review before any real use.

All four call sites — LSAT tutor, LSAT content author, and LegalAnalyst — share the one `law_ai.core.claude_code.is_active()` gate, so they all honor `LSAT_LLM_PROVIDER` and the dev-only rule together.

## Configuration reference

| Env var | Default | Purpose |
|---|---|---|
| `LSAT_LLM_PROVIDER` | `ollama` | `claude_code` opts the LSAT tutor in (dev only). |
| `CLAUDE_CODE_OAUTH_TOKEN` | _(unset)_ | OAuth token from `claude setup-token`. |
| `CLAUDE_CODE_MODEL` | `claude-opus-4-8` | Claude model id. |
| `CLAUDE_CODE_MAX_TOKENS` | `1024` | Max output tokens per tutor call. |
| `CLAUDE_CODE_REQUEST_TIMEOUT_S` | `60` | HTTP timeout. |
| `ANTHROPIC_BASE_URL` | `https://api.anthropic.com` | API base (override for proxies). |

Every tutor call is still recorded through the audit layer (the `model` field shows `claude_code/<model>`), so provenance is preserved regardless of provider.
