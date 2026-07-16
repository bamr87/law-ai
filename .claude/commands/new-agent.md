---
description: "Scaffold a new LawGraph agent crew member with run() + Pydantic output + test"
argument-hint: "<agent name and one-line responsibility>"
---

Scaffold a new LawGraph agent following repo conventions.

Read [prompts/new-agent.md](../../prompts/new-agent.md) now and follow it exactly.

Agent to add: $ARGUMENTS

Non-negotiables: the agent implements `run(input: dict) -> dict` with a Pydantic output model, logs every LLM call / tool use / retrieval through `core.provenance`, and ships a test under `backend/tests/agents/`. The product runtime LLM stays Ollama — never wire a closed-source model as the product LLM.
