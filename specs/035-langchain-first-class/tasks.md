# Tasks: LangChain/LangGraph first-class + AO-SDLC guide reimplementation

- **Spec**: [spec.md](spec.md) · **Plan**: [plan.md](plan.md)

## Tasks

- [x] **T-001** — Move LangChain/checkpointer deps from `local-ai` extra to core `dependencies`; shrink the extra to Phoenix/OTel. (**FR-1**, **NFR-COMPAT-1**)
- [x] **T-002** — `ChatProviderChain(BaseChatModel)` in `core/llm/langchain.py`, exported from `law_ai.core.llm`. (**FR-2**, **NFR-AUDIT-1**)
- [x] **T-003** — `LegalWorkflow._default_llm_factory` returns `ChatProviderChain`. (**FR-3**)
- [x] **T-004** — docker-compose: explicit `POSTGRES_URL` on backend + worker (checkpointer wiring). (**FR-4**)
- [x] **T-005** — Refresh `validate_claude_code`, `run_legal_analyst`, `run_lsat_author` gate output for the chain era. (**FR-5**)
- [x] **T-006** — Rebuild the backend image; verify langchain-core/langgraph/checkpointers import in the fresh container. (**FR-1**)
- [x] **T-007** — Live OAuth validation: probe, tutor E2E, IRAC analyst, LangGraph+checkpointer E2E, chain health endpoint. (**NFR-VALID-1**)
- [x] **T-008** — Reimplement `AO-SDLC_Outline_Guide.md` (now `docs/ao-sdlc-guide.md`) as v2.0, grounded in the implemented system, with the validation playbook. (**FR-6**)
- [x] **T-009** — Tests: `tests/core/test_llm_langchain.py` (9 cases). 
- [x] **T-010** — Gates: ruff/format clean on changed files; mypy no new errors; backend suites green; spec_validator + backlog_lint pass.

## Follow-ups Discovered

- **BL-20260811-25** — *tech-debt, med* — Checkpointer schema isolation is claimed but not real: `ensure_checkpointer` creates a `langgraph` schema, but the saver's connection string sets no `search_path`, so LangGraph tables land in `public`. Either pass `options=-csearch_path=langgraph` in the conn string or drop the schema claim (spec 011 FR-13).
- **BL-20260811-26** — *feature, low* — `ChatProviderChain` has no `_astream`; LangChain streaming falls back to buffered generation. Fold into the chain-streaming work (BL-20260811-20).
- **BL-20260811-27** — *tech-debt, low* — Boot-time `ensure_schema()` is log-only; a broken checkpointer URL degrades silently until first workflow use. Health probes cover detection, but boot should at least surface a visible warning counter or fail fast behind a flag.
- **BL-20260811-28** — *tech-debt, low* — CrewAI crews call the chain directly while LangGraph consumes it via `ChatProviderChain`; consolidate on the LangChain model where it simplifies (or document why not).
- **BL-20260811-29** — *doc-gap, low* — `.env.example`'s host-oriented `POSTGRES_URL` needs a comment stating containers override it (compose) and stale copies (e.g. old `lawgraph` credentials) break host-side checkpointer use.
