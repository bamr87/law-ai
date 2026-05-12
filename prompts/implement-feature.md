# Prompt Template: Implement Feature in LawGraph AI

**Feature Request**: {Brief description of feature, e.g. "Add support for UK legislation via legislation.gov.uk API"}

## Mandatory Steps (Follow in Order)

1. **Understand Impact**
   - Read `AGENTS.md` (especially Coding Standards and Agent Development Rules)
   - Read relevant sections of `LawGraph_AI_PRD.md` and `docs/architecture.md`
   - Identify which layers are affected (Backend API, Agent, Graph Schema, Frontend UI, Eval)

2. **Design First (Think, then code)**
   - Propose data model changes (if any) in Neo4j / Postgres
   - Define new API contract (FastAPI router + Pydantic models)
   - Decide if new agent/tool or extension of existing one is needed
   - Sketch UI component (if frontend change)

3. **Implementation Order**
   - Backend API + models first (so frontend can call it)
   - Agent/tool logic (if applicable)
   - Database migration / schema update
   - Frontend page or component
   - Tests + LegalBench eval (if reasoning change)

4. **Quality Gates (Run Before Committing — all in Docker)**
   ```bash
   make lint           # ruff + black + frontend eslint --fix (in containers)
   make typecheck      # mypy --strict + tsc --noEmit (in containers)
   make test           # backend pytest + frontend vitest (in containers)
   make test-legalbench  # only if reasoning logic changed
   ```
   Never run `pytest`, `ruff`, `black`, `mypy`, or `npm test` directly on the host. See [AGENTS.md](../AGENTS.md) § "Docker-First Workflow".

5. **Documentation & Backlog (mandatory closing step)**
   - Update `docs/` if architecture or data model changed
   - Add example usage in `docs/api-examples.md`
   - Update AGENTS.md if new patterns introduced
   - Append at least one entry to [BACKLOG.md](../BACKLOG.md) under `## Open` for any deferred refactor, missing test, or stretch idea you noticed. If you genuinely have none, write an explicit `_none — justified: <reason>_` in the PR description.
   - Run `python3 scripts/spec_validator.py` and `python3 scripts/backlog_lint.py` (or `make lint-specs`) — both must exit 0.

## Output Requirements
- Use existing code style and patterns (copy from similar features)
- All new public functions must have docstrings + examples
- Every agent action must log via `core.provenance`
- Include at least one end-to-end test
- Surface follow-ups in BACKLOG.md (see step 5)

**Start by saying**: "Understood. Implementing [Feature Name] following LawGraph AI standards..."

End with: "✅ Feature complete. All quality gates passed. Follow-ups added: <BL-...>. Ready for review."