---
description: "Use when creating, modifying, or reviewing agent crews, LangGraph workflows, agent tools, or agent prompts under backend/lawgraph/agents_runtime/. Enforces run() signature, provenance logging, prompt versioning, and LegalBench regression test requirements."
applyTo: "backend/lawgraph/agents_runtime/**"
---

# Agent Development Rules

These rules are mandatory for every file under [backend/lawgraph/agents_runtime/](../../backend/lawgraph/agents_runtime/). They derive from [AGENTS.md](../../AGENTS.md) "Agent Development Rules" and [docs/constitution.md](../../docs/constitution.md).

## Required Structure

- **Crews** (CrewAI role-based) live in [backend/lawgraph/agents_runtime/crews/](../../backend/lawgraph/agents_runtime/crews/).
- **Workflows** (LangGraph stateful) live in [backend/lawgraph/agents_runtime/graphs/](../../backend/lawgraph/agents_runtime/graphs/).
- **Tools** (Neo4j, CourtListener, etc.) live in [backend/lawgraph/agents_runtime/tools/](../../backend/lawgraph/agents_runtime/tools/).
- **Prompts** are versioned `.md` or `.txt` files in [backend/lawgraph/agents_runtime/prompts/](../../backend/lawgraph/agents_runtime/prompts/). Never inline prompt strings in Python code.

## Every Agent Must Implement

```python
class MyAgent:
    human_approval_required: bool = False  # True for ingestion / high-stakes analysis

    def run(self, input: dict) -> MyAgentOutput:  # Pydantic model, never raw dict
        ...
```

- `run(input: dict) -> <PydanticModel>` — structured output only. No `Any`, no untyped dicts.
- Every LLM call and tool invocation **must** be logged through `lawgraph.core.provenance` with `source`, `confidence`, `agent_version`, and `prompt_version`.
- Set `human_approval_required = True` for any agent that ingests new sources or produces high-stakes legal analysis.

## Prompts

- One file per prompt; filename encodes version: `precedent_retriever.v3.md`.
- Reference the LegalBench task in a frontmatter or top comment when the prompt targets one.
- Load prompts via a single helper (do not duplicate file-loading logic across agents).

## LLM Provider

- Default to **Ollama** (open-source models). Never hardcode a closed-source provider as primary.
- Provider selection goes through `lawgraph.core.config`, never direct env reads inside an agent.

## Tools (`agents_runtime/tools/`)

- All Neo4j writes must include `source`, `confidence`, `ingest_timestamp`, `agent_version` properties.
- Never delete graph nodes — soft-delete with `archived_at`.
- No direct Neo4j access from anywhere outside `lawgraph.core` (Neo4j driver) or `lawgraph.agents_runtime.tools`.

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
- Hardcoding API keys, model names, or endpoints (use `lawgraph.core.config`).
- Creating graph nodes without `source` and `confidence`.
