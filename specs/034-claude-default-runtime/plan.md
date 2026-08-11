# Plan: Claude-default LLM provider chain

- **Spec**: [spec.md](spec.md)
- **Status**: shipped

## Architecture

One new package, `backend/law_ai/core/llm/`, owns provider selection. Nothing else in the product decides which model to call.

```
feature module (analyst, tutor, author, workflow, frontier, synthesizer)
        │  llm.agenerate(...) / llm.generate(...) / llm.build_runnable(...)
        ▼
core/llm/router.py ── resolves LLM_PROVIDER_CHAIN, tries tiers in order,
        │              records attempts, writes the llm_call provenance event
        ▼
core/llm/providers.py
        ├── ClaudeOAuthProvider   ─┐
        ├── AnthropicAPIProvider  ─┴─► core/claude_code.py  (one Messages API
        └── OllamaProvider ──────────► /api/generate            transport, two
                                                                 auth modes)
```

**Why a chain object rather than a `provider=` setting.** A single selector cannot express "prefer Claude, but keep answering when Claude is down". The three call sites that previously branched on `claude_code.is_active()` each had to re-derive that behaviour, and each got it slightly different. Ordering is the whole feature.

**Why `claude_code.py` stays the transport for both Claude tiers.** OAuth and API-key requests differ only in credential, one header, and the identity system block. Two clients would be two places to get the Messages API shape wrong.

**Why `LLMRequest.models` is a per-provider mapping.** Model ids are not portable: `claude-opus-5` means nothing to Ollama. A flat `model=` parameter would silently mean the wrong thing after a fallback, so callers name the provider they are pinning.

## Key decisions

| Decision | Rationale |
|---|---|
| `ollama` stays in the default chain | Keeps the product answering when hosted tiers are down, and keeps local-first reachable (constitution §1) |
| Ollama provider pre-checks reachability | The TTL-cached probe stops a dead local server from burning the full request timeout at the tail of the chain |
| Unknown chain tokens are dropped, not fatal | A typo in an env var must degrade to the recognised providers, not take the runtime down |
| Refusal + truncation raise | Both otherwise present as a successful empty/partial answer, which is the exact failure the constitution forbids |
| No `temperature` on Claude tiers | Removed on current Claude models; sending it is a 400 |
| LegalBench stays Ollama-pinned | A benchmark that silently changes model is measuring nothing |
| Sync `generate()` refuses inside a running loop | Blocking the event loop would stall every other request on the worker |

## Rollout

The chain defaults to Claude, but every tier is credential-gated: with no `CLAUDE_CODE_OAUTH_TOKEN` and no `ANTHROPIC_API_KEY`, the chain skips both Claude tiers and behaves exactly as before. Existing deployments therefore keep working untouched until an operator adds a credential.

## Test strategy

- Router: chain parsing, skip/fallthrough/total-failure, provenance events, audit-sink failure isolation — against provider doubles, no network.
- Transport: both auth modes' header and body shapes, refusal, truncation, and the absence of sampling params — respx-mocked.
- Call sites: existing agent tests re-pointed at the chain seam.
