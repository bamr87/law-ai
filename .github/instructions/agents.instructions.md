---
description: "Use when creating, modifying, or reviewing agent crews, LangGraph workflows, agent tools, or agent prompts under backend/law_ai/agents_runtime/. Enforces run() signature, provenance logging, prompt versioning, and LegalBench regression test requirements."
applyTo: "backend/law_ai/agents_runtime/**"
---

# Agent Development Rules

These rules are mandatory for every file under [backend/law_ai/agents_runtime/](../../backend/law_ai/agents_runtime/). They derive from [AGENTS.md](../../AGENTS.md) "Agent Development Rules" and [docs/constitution.md](../../docs/constitution.md).

## Required Structure

- **Crews** (CrewAI role-based) live in [backend/law_ai/agents_runtime/crews/](../../backend/law_ai/agents_runtime/crews/).
- **Workflows** (LangGraph stateful) live in [backend/law_ai/agents_runtime/graphs/](../../backend/law_ai/agents_runtime/graphs/).
- **Tools** (currently Neo4j graph retrieval, `graph_rag.py`) live in [backend/law_ai/agents_runtime/tools/](../../backend/law_ai/agents_runtime/tools/). Ingestion source clients (CourtListener, statute scouts, etc.) live under `ingestionapp/sources/` and `ingestionapp/services/` instead — outside this directory's scope.
- **Prompts** are versioned `.md` or `.txt` files in [backend/law_ai/agents_runtime/prompts/](../../backend/law_ai/agents_runtime/prompts/). Never inline prompt strings in Python code.

## Every Agent Must Implement

```python
class MyAgent:
    human_approval_required: bool = False  # True for ingestion / high-stakes analysis

    def run(self, input: dict) -> MyAgentOutput:  # Pydantic model, never raw dict
        ...
```

- `run(input: dict) -> <PydanticModel>` — structured output only. No `Any`, no untyped dicts.
- Every LLM call and tool invocation **must** be logged through `law_ai.core.provenance` with `source`, `confidence`, `agent_version`, and `prompt_version`.
- Set `human_approval_required = True` for any agent that ingests new sources or produces high-stakes legal analysis.

## Prompts

- One file per prompt; filename encodes version: `precedent_retriever.v3.md`.
- Reference the LegalBench task in a frontmatter or top comment when the prompt targets one.
- Load prompts via a single helper (do not duplicate file-loading logic across agents).

## LLM Provider

- Product-runtime model calls go through the ordered chain in `law_ai.core.llm` (`LLM_PROVIDER_CHAIN`, default `claude_code,anthropic_api,ollama`): Claude over OAuth, then Claude over `ANTHROPIC_API_KEY`, then local Ollama. **Claude is the default** (constitution §1, amended 2026-08-11 for spec 034) — this repeals the older "Ollama-default, no closed-source primary" rule; do not reintroduce it.
- Never call a provider transport (Claude Code SDK, Anthropic API client, Ollama client) directly. Use `law_ai.core.llm.agenerate()` for plain calls, or `law_ai.core.llm.ChatProviderChain` (a LangChain `BaseChatModel`, spec 035) as the model for LangGraph nodes — see `graphs/legal_workflow.py`'s `_default_llm_factory()` for the canonical pattern. `law_ai.core.llm` is the sole choke point that writes the `llm_call` provenance event; bypassing it is rejected at review regardless of which provider is involved.
- `law_ai.agents_runtime.llm` is a separate, **Ollama-only** transport (`ChatOllama` + retry) — it is not the default engine. It backs `crews/legal_analyst.py`'s explicit `use_langgraph=false` escape hatch and the LSAT crews specifically, not new agents in general. Reach for `law_ai.core.llm` unless you have a concrete reason to force Ollama-only.
- Provider/model selection goes through `law_ai.core.llm` (or `law_ai.core.settings_proxy` for non-LLM settings) — never direct env reads inside an agent. There is no `law_ai.core.config` module; do not reference it.
- LegalBench evals stay pinned to Ollama for reproducibility (constitution §1) — do not route eval runs through the chain.
- Deployments handling data under a confidentiality obligation that forbids third-party processing MUST pin `LLM_PROVIDER_CHAIN=ollama` (constitution §1). `ollama` remains a first-class, fully supported local-only configuration, not a deprecated fallback.

## Tools (`agents_runtime/tools/`)

- All Neo4j writes must include `source`, `confidence`, `ingest_timestamp`, `agent_version` properties.
- Never delete graph nodes — soft-delete with `archived_at`.
- Within `agents_runtime/`, no direct Neo4j access outside `law_ai.core` (Neo4j driver) or `law_ai.agents_runtime.tools` — go through `tools/graph_rag.py` rather than opening a driver session in a crew or graph node. (`ingestionapp/` has its own Neo4j call sites for scouting/ingestion; that's a different directory's rules.)

## Mandatory Tests

For every new or modified agent, add **all** of the following under [backend/tests/agents/](../../backend/tests/agents/) and run them **inside Docker** (never on the host):

1. Unit test with mocked LLM + tools (fast). Run via `make test-backend`.
2. Integration test using docker-compose Neo4j/Postgres. Run via `make test-integration`.
3. LegalBench regression test on the relevant subset when reasoning logic changed. Run via `make test-legalbench` and record the score delta in the PR description.

Coverage for new agent code must keep total backend coverage ≥75% (`make test-coverage`).

## Forbidden

- Inline prompts as Python string literals.
- Bypassing `core.provenance` (silent LLM/tool calls).
- Returning unstructured `dict[str, Any]` from `run()`.
- Hardcoding API keys, model names, or endpoints (use `law_ai.core.llm` for provider/model selection, `law_ai.core.settings_proxy` for other settings).
- Creating graph nodes without `source` and `confidence`.
