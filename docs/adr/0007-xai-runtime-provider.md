# ADR 0007 — xAI as a sanctioned runtime provider

- **Status**: accepted
- **Date**: 2026-09-04
- **Spec**: [specs/050-xai-oauth-provider](../../specs/050-xai-oauth-provider/spec.md) — implemented the same day; the OAuth-flow block below was resolved rather than waived
- **Constitution clauses amended**: [§1 Mission Alignment — product-runtime LLM policy](../constitution.md#1-mission-alignment), [§2 Tech Stack](../constitution.md#2-tech-stack-locked)

## Context

[ADR 0005](0005-claude-default-runtime.md) replaced the Ollama-only runtime with an ordered provider chain and, in the same breath, closed the door behind it: "Only Anthropic and Ollama are sanctioned; adding OpenAI, Gemini, or any other provider needs a further amendment to §1." That clause was restated verbatim in [CLAUDE.md](../../CLAUDE.md), [AGENTS.md](../../AGENTS.md), [docs/ao-sdlc-guide.md](../ao-sdlc-guide.md), and the `constitution-reviewer` agent, which was instructed to reject any spec adding a third vendor.

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
- **Latency.** Live measurement against `grok-4.6` (2026-09-05) put a full IRAC analysis at 56-103s and LSAT item authoring at 68s — 5-10x the Claude tiers — which is why `XAI_REQUEST_TIMEOUT_S` defaults to 240s. Acceptable for a fallback tier that only serves when both Anthropic tiers are down; poor on any interactive path that reaches it. `XAI_INTERACTIVE_MODEL` (BL-20260905-11) lets an operator pin a faster Grok id for user-facing calls only (the LSAT tutor and the `/api/analysis` IRAC pass it; the factory, eval and autonomy paths keep `XAI_MODEL`). It ships **blank on purpose**: choosing a non-reasoning variant trades answer quality on the fallback tier for latency, and the trade can only be judged against a real subscription, which spec 050 AC-5 forbids the test suite from touching. The complementary fix — making the wait visible rather than shorter — **shipped** with BL-20260905-11: both interactive paths this ADR measured now stream. The LSAT tutor streams coaching tokens, and `/api/analysis` relays the analyst's deltas to the run's WebSocket group as `analysis_token` events (buffered `agenerate` on the direct-LLM path, and the LangGraph analyze node through `ChatProviderChain.astream`), so a client subscribed with a `stream_id` sees the answer being written from the first token instead of a blank panel for a minute. Streaming is what closes BL-20260905-11; `XAI_INTERACTIVE_MODEL` remains available for an operator who would rather make the wait shorter and can measure a candidate against their own subscription.
- **Terms-of-service and data-retention review is drafted, not accepted.** ADR 0005 accepted Anthropic's terms for legal text; the equivalent xAI review is written up below ("Terms-of-service and data-retention review") and is **pending owner acceptance** — the primary legal pages could not be read from CI, and the acceptance is the owner's to give, not an engineer's to presume. `BL-20260904-03`.

## Terms-of-service and data-retention review

**Status: draft — pending owner acceptance (BL-20260904-03).** Nothing here records a decision. ADR 0005 §Context shows what acceptance looks like: the owner weighed the answer-quality gain against sending prompt text to a third party and authorised the amendment. That step has not happened for xAI, and the default chain has been shipping the `xai` tier since spec 050 — so this section is the material for that decision, gathered 2026-09-05, not the decision itself.

### What the tier actually does

Calls go to `https://api.x.ai/v1` (`XAI_BASE_URL`), authenticated with a **subscription OAuth token** obtained through `make xai-login` — a device-code grant against `https://auth.x.ai` reusing the public Grok-CLI desktop client id (`backend/law_ai/core/xai_oauth.py`). There is no API-key mode and no enterprise agreement behind it. That combination — a consumer subscription credential hitting the developer API endpoint — is what makes the governing terms ambiguous, and it is the first thing the review has to settle.

### What could be read from primary sources

[docs.x.ai — "FAQ · API Security"](https://docs.x.ai/developers/faq/security) (read 2026-09-05; the page carries no effective date):

- *"xAI never trains on your API inputs or outputs without your explicit permission."*
- *"All API requests and responses are stored on our servers (encrypted at rest) for 30 days for auditing purposes in the event of suspected abuse or misuse. xAI does not train on this data, and it is automatically deleted after 30 days."*
- A **Zero Data Retention** option exists for *"teams with stricter data handling needs"*: with ZDR, *"API request inputs (i.e., your prompt) and outputs (i.e., the tokens generated by the LLM) are never persisted to disk."* The same page says *"For most customers, we do not recommend enabling ZDR"* because it disables the Stateful Responses API, Files and Collections, and the Batch API.

So on the developer-API reading, this tier's exposure is: 30 days of encrypted-at-rest retention for abuse auditing, no training. ZDR would remove even that — but it is an account-level setting, and this tier has no xAI account of its own to set it on: it borrows a desktop client id under a personal subscription.

### What could not be read, and must be read by a human

`https://x.ai/legal/terms-of-service`, `https://x.ai/legal/privacy-policy`, `https://x.ai/legal`, and `https://grok.com/legal/privacy-policy` all returned **HTTP 403** to automated fetches on 2026-09-05 (the same allowlist behaviour spec 050 hit at the auth server). They are readable in a browser; they were not readable from this environment, so none of their text is quoted here and none of it is summarised second-hand. Specifically unresolved:

1. **Which agreement governs a subscription-OAuth call to `api.x.ai`** — the consumer Grok terms attached to the subscription, or the developer API terms whose FAQ carries the no-training and 30-day commitments quoted above. The FAQ's promise is scoped to *"your API inputs"*; whether a call authorised by a consumer subscription token counts as API usage for that purpose is exactly the question.
2. **Consumer-surface training defaults.** Widely-reported secondary sources say Grok consumer conversations feed training by default with an opt-out toggle; that is not a primary source and is deliberately not relied on here. It matters only if answer (1) lands on the consumer terms.
3. **Confidentiality / DPA posture.** No data-processing agreement exists for this path. If client material under a confidentiality obligation may reach it, a DPA — i.e. an enterprise relationship — is the normal answer, and this tier does not have one.
4. **Client-id revocation.** The reused Grok-CLI client id can be revoked by xAI at any time (ADR 0007 Decision §2). That is an availability risk already recorded, but it also means the terms accepted at login are xAI's for that client, not ours to pin.

### Options for the owner

- **Accept as-is** — record the decision here and in [docs/security.md](../security.md#the-xai-tier-draft-review), keeping the `ollama` pin as the only route for confidentiality-bound matters (unchanged from ADR 0005).
- **Accept with a narrower default** — drop `xai` from the default `LLM_PROVIDER_CHAIN` in `settings/base.py` and `router.DEFAULT_CHAIN`, leaving it opt-in per deployment. This restores the "no unpinned deployment routes to xAI by surprise" property the amendment traded away.
- **Reject** — remove the tier from the default chain and gate it behind an explicit `XAI_ENABLED`-style flag, or revert the amendment.

Whichever it is, the deciding text belongs in this section (replacing this draft) and the outcome belongs in the xAI amendment block of [docs/constitution.md](../constitution.md) §1. Until then `BL-20260904-03` stays open.

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
