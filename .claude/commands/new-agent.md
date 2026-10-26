---
description: "Scaffold a new Law AI agent crew member with run() + Pydantic output + provenance + test"
argument-hint: "<agent name and one-line responsibility>"
---

Scaffold a new Law AI agent following the repo's conventions. Agent to add: $ARGUMENTS

You are an expert legal AI engineer building Law AI. Read [AGENTS.md](../../AGENTS.md) (Agent Development Rules), [docs/agent-roles.md](../../docs/agent-roles.md), [docs/data-model.md](../../docs/data-model.md) for the graph schema, and the existing `LegalAnalyst` and `PrecedentHunter` implementations for style, before writing anything.

## Requirements

1. **Location.** `backend/law_ai/agents_runtime/crews/` for a CrewAI crew member, or `backend/law_ai/agents_runtime/graphs/` for a LangGraph state machine.
2. **Must include**:
   - the agent class with `run(input: dict) -> <PydanticOutput>` (async where the siblings are);
   - a versioned prompt file under `backend/law_ai/agents_runtime/prompts/` (`<name>.v1.md`; name the LegalBench task it targets, if any) — never an inline prompt string;
   - any custom tools in `backend/law_ai/agents_runtime/tools/`;
   - tests under `backend/tests/agents/test_<agent_name>.py` — at least three cases, one against the LegalBench subset when the agent reasons over law.
3. **Structured output** (Pydantic):
   ```python
   class {AgentName}Output(BaseModel):
       result: ...
       confidence: float = Field(ge=0, le=1)
       sources: list[Source]  # url + snippet
       reasoning_trace: list[str]
       human_approval_required: bool = False
   ```
4. **Non-negotiables.** Every LLM call, tool use and retrieval is logged through `law_ai.core.provenance`. Model calls go through `law_ai.core.llm` (`agenerate`/`generate`, or `ChatProviderChain` for LangGraph nodes) — never a provider transport directly, and never a vendor beyond Anthropic / xAI / Ollama without a constitution §1 amendment. Graph writes carry `source`, `confidence`, `ingest_timestamp`, `agent_version`; deletes are soft (`archived_at`). Set `human_approval_required = True` for ingestion or high-stakes analysis.
5. **Integration.** Register in `backend/law_ai/agents_runtime/registry.py`; add to the orchestrator if it belongs in a default workflow; add a row to [docs/agent-roles.md](../../docs/agent-roles.md).
6. **Gates (Docker).** `make test-backend` for the tests (`make test-legalbench` for the LegalBench case; record the delta), `make lint`, `make typecheck`. Never run `pytest`, `ruff`, `mypy` or `black` on the host.
7. **Follow-ups (constitution §11).** Append at least one `BL-YYYYMMDD-NN` bullet to [BACKLOG.md](../../BACKLOG.md) (e.g. "add streaming variant", "profile cold-start latency", "missing prompt-injection regression test"), minting the id with `python3 "$(tools/fleet-kit.sh)/tools/next_backlog_id.py" --root .`, then run `make lint-specs` — it must exit 0.

## Output

```
✅ Implemented {AgentName}
Files changed: …
LegalBench delta: +X% on {relevant_tasks} (or n/a)
Follow-ups added: <BL-...>, <BL-...>
Ready for review.
```
