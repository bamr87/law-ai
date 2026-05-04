---
description: "Use when creating, modifying, or reviewing agent crews, LangGraph workflows, agent tools, or agent prompts under backend/app/agents/. Enforces run() signature, provenance logging, prompt versioning, and LegalBench regression test requirements."
applyTo: "backend/app/agents/**"
---

# Agent Development Rules

These rules are mandatory for every file under [backend/app/agents/](../../backend/app/agents/). They derive from [AGENTS.md](../../AGENTS.md) "Agent Development Rules" and [docs/constitution.md](../../docs/constitution.md).

## Required Structure

- **Crews** (CrewAI role-based) live in [backend/app/agents/crews/](../../backend/app/agents/crews/).
- **Workflows** (LangGraph stateful) live in [backend/app/agents/graphs/](../../backend/app/agents/graphs/).
- **Tools** (Neo4j, CourtListener, etc.) live in [backend/app/agents/tools/](../../backend/app/agents/tools/).
- **Prompts** are versioned `.md` or `.txt` files in [backend/app/agents/prompts/](../../backend/app/agents/prompts/). Never inline prompt strings in Python code.

## Every Agent Must Implement

```python
class MyAgent:
    human_approval_required: bool = False  # True for ingestion / high-stakes analysis

    def run(self, input: dict) -> MyAgentOutput:  # Pydantic model, never raw dict
        ...
```

- `run(input: dict) -> <PydanticModel>` — structured output only. No `Any`, no untyped dicts.
- Every LLM call and tool invocation **must** be logged through `app.core.provenance` with `source`, `confidence`, `agent_version`, and `prompt_version`.
- Set `human_approval_required = True` for any agent that ingests new sources or produces high-stakes legal analysis.

## Prompts

- One file per prompt; filename encodes version: `precedent_retriever.v3.md`.
- Reference the LegalBench task in a frontmatter or top comment when the prompt targets one.
- Load prompts via a single helper (do not duplicate file-loading logic across agents).

## LLM Provider

- Default to **Ollama** (open-source models). Never hardcode a closed-source provider as primary.
- Provider selection goes through `app.core.config`, never direct env reads inside an agent.

## Tools (`agents/tools/`)

- All Neo4j writes must include `source`, `confidence`, `ingest_timestamp`, `agent_version` properties.
- Never delete graph nodes — soft-delete with `archived_at`.
- No direct Neo4j access from anywhere outside `app.db` or `app.agents.tools`.

## Mandatory Tests

For every new or modified agent, add **all** of the following under [backend/tests/agents/](../../backend/tests/agents/):

1. Unit test with mocked LLM + tools (fast).
2. Integration test using docker-compose Neo4j/Postgres.
3. LegalBench regression test on the relevant subset when reasoning logic changed. Record the score delta in the PR description.

Coverage for new agent code must keep total backend coverage ≥75%.

## Forbidden

- Inline prompts as Python string literals.
- Bypassing `core.provenance` (silent LLM/tool calls).
- Returning unstructured `dict[str, Any]` from `run()`.
- Hardcoding API keys, model names, or endpoints (use `app.core.config`).
- Creating graph nodes without `source` and `confidence`.
