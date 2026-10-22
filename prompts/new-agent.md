# Prompt Template: Implement New Law AI Agent

You are an expert legal AI engineer building Law AI.

## Task
Implement a new agent role called **{AgentName}** (e.g., "ContractRiskAssessor", "CaseOutcomePredictor", "StatuteChangeDetector").

## Requirements

1. **Location**: Create files in `backend/law_ai/agents_runtime/crews/{agent_name}/` or `graphs/` if using LangGraph state machine.

2. **Must Include**:
   - `agent.py` — Main class with `async def run(self, input: dict) -> StructuredOutput`
   - `prompts/system.md` — Clear system prompt (include LegalBench task references if applicable)
   - `tools.py` — Any custom tools (Neo4j queries, external APIs, calculators)
   - `tests/test_{agent_name}.py` — At least 3 test cases (one using LegalBench subset)

3. **Structured Output** (use Pydantic):
   ```python
   class {AgentName}Output(BaseModel):
       result: ...
       confidence: float = Field(ge=0, le=1)
       sources: list[Source]  # must include url + snippet
       reasoning_trace: list[str]
       human_approval_required: bool = False
   ```

4. **Integration**:
   - Register in `backend/law_ai/agents_runtime/registry.py`
   - Add to Orchestrator if it should be part of default workflows
   - Update `docs/agent-roles.md` with new row in the table

5. **Evaluation Gate**: Before finishing, run:
   ```bash
   python -m backend.app.eval.legalbench --agent {agent_name}
   ```
   Report the delta on relevant LegalBench tasks.

## Context to Use
- Read `AGENTS.md` (root)
- Read `docs/agent-roles.md`
- Read `docs/data-model.md` for graph schema
- Use existing patterns from `LegalAnalyst` and `PrecedentHunter` agents

## Output Format
When done, respond with:
```
✅ Implemented {AgentName}
Files changed: ...
LegalBench delta: +X% on {relevant_tasks}
Follow-ups added: <BL-...>, <BL-...>
Ready for review.
```

Before the response, append at least one `BL-YYYYMMDD-NN` entry to [BACKLOG.md](../BACKLOG.md) (e.g. "add streaming variant", "profile cold-start latency", "missing prompt-injection regression test"). Run `python3 scripts/backlog_lint.py` and `python3 scripts/spec_validator.py` (or `make lint-specs`) — both must exit 0. Run the new agent's tests via `make test-backend` (or `make test-legalbench` for the LegalBench case) — never invoke `pytest` directly on the host. See [AGENTS.md](../AGENTS.md) § "Docker-First Workflow".

Start by reading the existing agent implementations for style consistency.