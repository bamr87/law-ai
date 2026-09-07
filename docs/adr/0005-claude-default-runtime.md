# ADR 0005 — Claude-default LLM provider chain

- **Status**: accepted
- **Date**: 2026-08-11
- **Spec**: [specs/034-claude-default-runtime](../../specs/034-claude-default-runtime/spec.md)
- **Constitution clauses amended**: [§1 Mission Alignment — product-runtime LLM policy](../constitution.md#1-mission-alignment)

## Context

Constitution §1 previously rejected any spec that wired a closed-source model into the product runtime; the runtime was pinned to a local 7B open-weights model served by Ollama. A Claude transport already existed ([backend/law_ai/core/claude_code.py](../../backend/law_ai/core/claude_code.py)) but was deliberately unreachable in production — gated on `is_development()` — because of that rule. The result was a two-tier product (good answers on a laptop, degraded answers everywhere else) and three separate ad-hoc `if claude_code.is_active(): … else: ollama` branches in the analyst, tutor, and content-author agents, each reimplementing provider selection slightly differently.

The owner decided the answer-quality gain on IRAC analysis, issue-spotting, and LSAT item authoring was worth sending prompt text to a third party, and authorised the corresponding constitution amendment. This is exactly the case [docs/adr/README.md](README.md) requires an ADR for: a spec amending a locked constitution clause.

This decision revises an assumption stated as present fact in two earlier ADRs — [0001](0001-adopt-django-backend.md)'s line "the product runtime LLM remains Ollama … per §1" and [0003](0003-autonomy-orchestrator.md)'s compliance-check row "all LLM calls go through the existing local Ollama client, no closed-source fallback." Neither ADR's own decision (Django adoption; the autonomy orchestrator's design) is affected — both stand unchanged — but a reader following either forward should land here for the current §1 text rather than treat those sentences as still accurate.

## Decision

Replace the single local-model runtime with an **ordered provider chain**, configured by `LLM_PROVIDER_CHAIN` and implemented in [backend/law_ai/core/llm/](../../backend/law_ai/core/llm/) (`router.py` resolves the chain and writes the `llm_call` provenance event; `providers.py` holds the three transports):

1. `claude_code` — Claude over a subscription OAuth token.
2. `anthropic_api` — Claude over `ANTHROPIC_API_KEY`.
3. `ollama` — the local open-weights model.

Claude is the **default product runtime**; this repeals the prior closed-source-rejection rule outright (superseded, not merely unenforced). Routing tries each tier in order, records skips and failures, and falls through; total failure degrades to an honest refusal rather than a fabricated answer. `LegalAnalyst`, the LSAT tutor and content author, `LegalWorkflow`, `TopicFrontier`, and `TestSynthesizer` all move from their per-agent branch onto the one chain.

Four rules survive the amendment unchanged, and a spec violating any of them is still rejected:

- **Local-first stays reachable.** `ollama` remains a first-class provider and the chain's last tier; `LLM_PROVIDER_CHAIN=ollama` is a fully supported pin, and is **required** for matters under a confidentiality obligation that forbids third-party processing.
- **Provenance is unchanged.** Every call is logged through `core.provenance`, naming the provider and model that actually served it and every tier that was skipped or failed.
- **No silent fabrication.** Refusal and truncation raise rather than return as if they were answers.
- **No third vendor.** Only Anthropic and Ollama are sanctioned; adding OpenAI, Gemini, or any other provider needs a further amendment to §1. *(Superseded 2026-09-04 by [ADR 0007](0007-xai-runtime-provider.md), which took exactly that route and sanctioned xAI as a third vendor. The other three retained rules stand unchanged.)*

The dev-orchestration layer (which AI edits this repo — Copilot / Claude Code) is explicitly independent of this decision and untouched by it; §1 says so directly to prevent the two from being conflated.

The LegalBench harness stays pinned to Ollama regardless of the default chain — routing eval through a provider that can change over time would make benchmark numbers non-comparable (constitution §1, reproducibility clause).

## Consequences

**Positive**

- One router owns every model call; the three duplicated per-agent fallback branches are deleted.
- Answer quality on the platform's core reasoning work is no longer capped by a 7B local model, while every deployment keeps a fully local, zero-egress option available by pinning the chain.
- `GET /api/agents/health/local-ai` and the agent dashboard now show the ordered chain and which tier is live, closing a visibility gap the old single-provider setup never had.
- Provenance gets a new event type (`llm_call`) carrying provider, model, latency, and the full attempt chain — auditable per-request, not just per-deployment-config.

**Negative / Risks**

- Legal text sent to the Claude tiers leaves the machine — the trade this ADR exists to authorise. Named explicitly in §1, [AGENTS.md](../../AGENTS.md), [CLAUDE.md](../../CLAUDE.md), and `.env.example`; the `ollama` pin is the documented mitigation for confidentiality-bound data.
- Reproducibility becomes provider-dependent; mitigated by pinning LegalBench to Ollama (spec 034 NG2) and by the chain's `providers=`/`models=` override for other reproducibility-sensitive callers.
- Cost/rate-limit exposure on hosted tiers; mitigated by operator-tunable `CLAUDE_EFFORT`/`CLAUDE_CODE_MAX_TOKENS` and by the chain degrading to local rather than failing outright.
- Six follow-ups were opened rather than folded into this change: doc updates to [docs/architecture.md](../architecture.md)/[docs/agent-roles.md](../agent-roles.md) (`BL-20260811-19`), no streaming path through the chain yet (`BL-20260811-20`), no per-tier token/cost accounting (`BL-20260811-21`), a vestigial `LSAT_LLM_PROVIDER` setting to fold in (`BL-20260811-22`), no permanent-vs-transient failure classification before falling to Ollama (`BL-20260811-23`), and no integration test asserting the privileged-data guarantee end-to-end (`BL-20260811-24`). See [BACKLOG.md](../../BACKLOG.md).

## Alternatives Considered

| Alternative | Why rejected |
| ----------- | ------------ |
| **Stay Ollama-only (status quo)** | Model quality is the binding constraint on IRAC analysis and issue-spotting; no amount of retrieval or prompt work moves a 7B local model past its ceiling. The three ad-hoc `is_active()` branches already showed operators reaching for Claude anyway, just inconsistently and only in development. |
| **Swap to Claude-only, no local fallback** | Breaks the retained "local-first must remain reachable" rule outright and removes the only option for confidentiality-bound deployments. Rejected without discussion — not a live option under the mission in AGENTS.md. |
| **Add OpenAI or Gemini as further tiers** | Multiplies the audit and compliance surface for a gain the owner didn't ask for. Constitution §1 keeps this closed pending its own future amendment (spec 034 NG1). |
| **Per-call `provider=` setting instead of an ordered chain** | Cannot express "prefer Claude, but keep answering when Claude is down" — the exact behavior the three pre-existing ad-hoc branches were each trying to hand-roll. Ordering is the feature (spec 034 plan.md, "Key decisions"). |
| **Two separate Claude clients for OAuth vs. API-key auth** | The two auth modes differ only in credential, one header, and the identity system block; one transport ([core/claude_code.py](../../backend/law_ai/core/claude_code.py)) with two auth paths avoids two places to get the Messages API shape wrong (spec 034 plan.md). |
| **Route the LegalBench harness through the chain too** | A benchmark whose model can silently change over time measures nothing; kept pinned to Ollama (spec 034 NG2). |

## Supersedes / Superseded by

- **Supersedes**: the prior text of [docs/constitution.md](../constitution.md) §1 rejecting any closed-source model as product runtime. Revises — without editing — the local-only assumption stated as present fact in [ADR 0001](0001-adopt-django-backend.md) ("the product runtime LLM remains Ollama … per §1") and [ADR 0003](0003-autonomy-orchestrator.md)'s compliance-check row ("all LLM calls go through the existing local Ollama client, no closed-source fallback"); neither ADR's own decision is superseded, only that incidental sentence in each is now stale.
- **Superseded by**: [ADR 0007](0007-xai-runtime-provider.md), in part — only the "No third vendor" retained rule above. This ADR's own decision (the ordered chain, Claude as default runtime, Ollama as the last tier) is untouched.

## References

- [specs/034-claude-default-runtime/spec.md](../../specs/034-claude-default-runtime/spec.md), [plan.md](../../specs/034-claude-default-runtime/plan.md), [tasks.md](../../specs/034-claude-default-runtime/tasks.md) — full requirements, architecture, and the risk register this ADR draws on.
- [docs/constitution.md](../constitution.md) §1 — amended in the same PR as this ADR.
- [BACKLOG.md](../../BACKLOG.md) — `BL-20260811-19` through `BL-20260811-24`, the follow-ups this decision opened.
