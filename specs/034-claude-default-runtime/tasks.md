# Tasks: Claude-default LLM provider chain

- **Spec**: [spec.md](spec.md) · **Plan**: [plan.md](plan.md)

## Tasks

- [x] **T-001** — Amend constitution §1: repeal the closed-source-runtime rejection, name the chain, retain local-first/provenance/no-fabrication/no-third-vendor. Mirror into AGENTS.md and CLAUDE.md. (spec §10)
- [x] **T-002** — Add `core/llm/base.py`: `LLMRequest`, `LLMResult`, `LLMAttempt`, `LLMProvider` protocol, `LLMUnavailableError`. (**FR-7**)
- [x] **T-003** — Add `core/llm/providers.py` with the three transports. (**FR-2**, **FR-3**, **FR-4**)
- [x] **T-004** — Add `core/llm/router.py`: chain resolution, ordered fallback, `llm_call` provenance, sync + runnable adapters. (**FR-1**, **FR-5**, **FR-6**, **NFR-AUDIT-1**)
- [x] **T-005** — Refactor `core/claude_code.py`: repeal the dev gate, add API-key auth, drop sampling params, raise on refusal/truncation. (**FR-8**, **NFR-SEC-1**, **NFR-COMPAT-1**, **NFR-COMPAT-2**)
- [x] **T-006** — Settings + `.env.example`: `LLM_PROVIDER_CHAIN`, `ANTHROPIC_API_KEY`, `ANTHROPIC_MODEL`, `CLAUDE_EFFORT`; model default `claude-opus-5`, `CLAUDE_CODE_MAX_TOKENS` 8192. (**FR-1**, **NFR-PRIV-1**)
- [x] **T-007** — Rewire agents onto the chain: analyst, tutor, content author, `LegalWorkflow`, `TopicFrontier`, `TestSynthesizer`; delete the dead per-agent Ollama clients. (**FR-1**)
- [x] **T-008** — Keep LegalBench pinned to Ollama and document why. (spec §3 NG2)
- [x] **T-009** — Health endpoint reports the ordered chain. (**FR-9**)
- [x] **T-010** — Dashboard renders the chain and names the serving tier. (**FR-10**)
- [x] **T-011** — Tests: router routing/provenance, both auth modes, refusal/truncation, no sampling params; update agent tests for the new seam.
- [x] **T-012** — Gates: ruff check + format clean on changed files; mypy --strict unchanged at the 202-error baseline (zero added); full backend pytest green; frontend tsc clean, vitest 35/35, eslint 0 errors; spec_validator + backlog_lint pass.

## Follow-ups Discovered

- **BL-20260811-19** — *doc-gap, med* — `docs/architecture.md` and `docs/agent-roles.md` still describe Ollama as the sole product runtime; they need the provider-chain diagram and the privileged-data pin.
- **BL-20260811-20** — *feature, med* — The chain has no streaming path; `agentsapi/consumers.py` still streams from its own transport, so WebSocket agent runs bypass chain fallback.
- **BL-20260811-21** — *feature, low* — No per-tier cost/token accounting. `llm_call` records latency and provider but not token usage, so hosted-tier spend is not attributable per agent.
- **BL-20260811-22** — *tech-debt, low* — `LSAT_LLM_PROVIDER` is now a vestigial single-provider pin that overlaps `LLM_PROVIDER_CHAIN`; fold it into the chain and remove the setting.
- **BL-20260811-23** — *feature, low* — The Ollama tier is reached even when a Claude tier failed for a non-transient reason (e.g. auth). A permanent-vs-transient classifier would avoid a pointless local fallback on a misconfigured key.
- **BL-20260811-24** — *test-gap, med* — No integration test asserts the privileged-data guarantee end-to-end (`LLM_PROVIDER_CHAIN=ollama` ⇒ zero outbound Anthropic requests).
