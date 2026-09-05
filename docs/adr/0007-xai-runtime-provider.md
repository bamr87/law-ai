# ADR 0007 — xAI as a sanctioned runtime provider

- **Status**: accepted
- **Date**: 2026-09-04
- **Spec**: [specs/050-xai-oauth-provider](../../specs/050-xai-oauth-provider/spec.md) — implemented the same day; the OAuth-flow block below was resolved rather than waived
- **Constitution clauses amended**: [§1 Mission Alignment — product-runtime LLM policy](../constitution.md#1-mission-alignment), [§2 Tech Stack](../constitution.md#2-tech-stack-locked)

## Context

[ADR 0005](0005-claude-default-runtime.md) replaced the Ollama-only runtime with an ordered provider chain and, in the same breath, closed the door behind it: "Only Anthropic and Ollama are sanctioned; adding OpenAI, Gemini, or any other provider needs a further amendment to §1." That clause was restated verbatim in [CLAUDE.md](../../CLAUDE.md), [AGENTS.md](../../AGENTS.md), [AO-SDLC_Outline_Guide.md](../../AO-SDLC_Outline_Guide.md), and the `constitution-reviewer` agent, which was instructed to reject any spec adding a third vendor.

The owner asked to wire xAI into the runtime. A repo-wide search confirmed **no xAI wiring exists** — the only `xai`/`grok` strings in the tree are two lines of document history recording that an early version of the AO-SDLC guide was drafted with Grok. So this is a policy question before it is an engineering one, and §1 named its own amendment as the way through. This ADR is that amendment.

One fact shaped the decision and is recorded here rather than discovered later: **xAI's published API authenticates with a bearer `XAI_API_KEY` against `https://api.x.ai/v1`. No xAI OAuth token flow analogous to `claude setup-token` is documented.** The owner was shown this and chose to write the amendment OAuth-first anyway, accepting that implementation waits on a flow they will supply.

## Decision

**xAI is a sanctioned product-runtime vendor.** `xai` becomes the third default tier of `LLM_PROVIDER_CHAIN` — below both Anthropic tiers, above `ollama`:

```
claude_code, anthropic_api, xai, ollama
```

Four terms bound it:

1. **OAuth-first auth.** The tier takes an xAI subscription OAuth token, mirroring `claude_code`'s auth mode rather than the API-key mode of `anthropic_api`. This is the authorised design, not a shipped one.
2. **The OAuth flow is the one Kilo Code ships in the open.** *(Resolved 2026-09-04, same day: this clause originally blocked implementation on an undocumented flow.)* xAI publishes no OAuth flow, but [Kilo-Org/kilocode](https://github.com/Kilo-Org/kilocode)'s `packages/opencode/src/plugin/xai.ts` implements one against `https://auth.x.ai`, reusing the public Grok-CLI desktop client that xAI's auth server allowlists. Spec 050 ports it: RFC 8628 device code as the primary (Docker-first — the loopback redirect is fixed at `127.0.0.1:56121` and cannot be re-pointed at the host) with the loopback PKCE grant as an opt-in. `BL-20260904-01` and `-02` closed with that spec.
3. **Ollama stays the last tier.** The local-first rule from ADR 0005 survives untouched: a change that makes the product unable to run wholly locally is still rejected. `LLM_PROVIDER_CHAIN=ollama` remains the required pin for confidentiality-bound matters — and now guards against two third parties, not one.
4. **No transport exemption.** `xai` is a provider class behind `law_ai.core.llm`; it writes the same `llm_call` provenance event and gets no direct-call carve-out from §4. LegalBench stays pinned to Ollama (§6) and gains no xAI mode.

The dev-orchestration layer is untouched. Copilot and Claude Code remain the only sanctioned surfaces for editing this repo; sanctioning xAI at runtime does not sanction a Grok coding agent.

## Consequences

**Positive**

- The chain gains a hosted fallback between "Anthropic is down/rate-limited" and "drop to a 7B local model," which is the gap ADR 0005 left: today an Anthropic outage costs the deployment most of its answer quality.
- The amendment is recorded before any code exists, so the implementing spec has a constitution clause to cite instead of arguing the policy inside a PR.

**Negative / Risks**

- **A second egress path.** Prompt text can now reach two third parties by default. Every deployment handling privileged data must pin `ollama`; the mitigation is unchanged but the exposure it mitigates has doubled. `BL-20260811-24` (no integration test asserting the zero-egress guarantee end-to-end) becomes more load-bearing, not less.
- **The OAuth premise may not hold.** If xAI never ships a subscription OAuth flow, the amendment as written cannot be implemented and a follow-up amendment will be needed to permit `XAI_API_KEY` instead. This is a known, accepted state — recorded rather than papered over.
- **Reproducibility surface grows.** Any eval or benchmark not pinned to a single provider becomes one tier less comparable. §1's pinning requirement already covers this; the enforcement burden rises.
- **Terms-of-service and data-retention review is outstanding.** ADR 0005 accepted Anthropic's terms for legal text; nobody has performed the equivalent review for xAI. `BL-20260904-03`.

## Alternatives Considered

| Alternative | Why rejected |
| ----------- | ------------ |
| **Keep §1 closed (status quo)** | The owner asked for xAI, was shown the amendment requirement, and reaffirmed. §1 named amendment as the sanctioned path; using it is the process working, not bypassing it. |
| **Sanction xAI opt-in only, default chain unchanged** | Offered and declined. Opt-in would have meant zero runtime behavior change on merge; the owner chose default tier 3 deliberately, accepting that unpinned deployments will route to xAI on Anthropic failure. |
| **Ship it API-key-first, add OAuth later** | Offered and declined. `XAI_API_KEY` is the auth mode xAI actually documents and would have unblocked implementation immediately; the owner chose OAuth-first and accepted the implementation block. |
| **Mirror the Anthropic pair as `xai_oauth` + `xai_api`** | Offered and declined. Would have hedged the OAuth-flow risk with a working key-based tier at the cost of two provider classes for one vendor. |
| **Put xAI at tier 1, above Claude** | Offered and declined. Would have superseded ADR 0005's core decision and required rewriting the "Claude is the default" claim across README, PRD, and AGENTS.md. Claude remains the default runtime. |

## Supersedes / Superseded by

- **Supersedes**: the "No third vendor" clause of [docs/constitution.md](../constitution.md) §1 and its restatement in [ADR 0005](0005-claude-default-runtime.md) ("Only Anthropic and Ollama are sanctioned"). ADR 0005's own decision — the ordered chain, Claude as default, Ollama as last tier — stands unchanged; only its vendor-closure clause is superseded. ADR 0005's "Add OpenAI or Gemini as further tiers" alternative is likewise narrowed: it remains rejected for OpenAI and Gemini, and this ADR does not reopen it.
- **Superseded by**: none.

## References

- [docs/constitution.md](../constitution.md) §1 — amended in the same PR as this ADR.
- [ADR 0005](0005-claude-default-runtime.md) — the chain this tier joins.
- [backend/law_ai/core/llm/](../../backend/law_ai/core/llm/) — `router.py` (chain resolution, provenance), `providers.py` (`PROVIDER_REGISTRY`, where the `xai` class will land).
- [BACKLOG.md](../../BACKLOG.md) — `BL-20260904-01` (OAuth flow block), `BL-20260904-02` (default-chain flip), `BL-20260904-03` (xAI terms/retention review).
