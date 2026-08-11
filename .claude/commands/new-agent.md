---
description: "Scaffold a new Law AI agent crew member with run() + Pydantic output + test"
argument-hint: "<agent name and one-line responsibility>"
---

Scaffold a new Law AI agent following repo conventions.

Read [prompts/new-agent.md](../../prompts/new-agent.md) now and follow it exactly.

Agent to add: $ARGUMENTS

Non-negotiables: the agent implements `run(input: dict) -> dict` with a Pydantic output model, logs every LLM call / tool use / retrieval through `core.provenance`, and ships a test under `backend/tests/agents/`. Call the LLM only through `law_ai.core.llm` (the `LLM_PROVIDER_CHAIN` router) — never a provider transport directly, and never a third vendor beyond Anthropic/Ollama without a constitution §1 amendment.
