---
description: "Implement a Law AI feature end to end — backend API, agent/tool, graph schema, frontend, tests, docs, follow-ups — in the order the stack requires"
argument-hint: "<brief feature description, e.g. 'support UK legislation via legislation.gov.uk'>"
---

Implement this feature in Law AI following the repo's standards: $ARGUMENTS

For a non-trivial feature, run the spec-driven chain first (`/spec-driven:specify` → `:clarify` → `:plan` → `:tasks`) and implement task by task with `/spec-driven:implement`; this command is the checklist for a feature that fits in one PR, or for one task of a spec.

## Mandatory steps, in order

1. **Understand the impact.** Read [AGENTS.md](../../AGENTS.md) (Coding Standards, Agent Development Rules), the relevant sections of [docs/prd.md](../../docs/prd.md) and [docs/architecture.md](../../docs/architecture.md). Name the layers affected: backend API (which Django app under `backend/law_ai/`), agent/tool, graph schema, frontend UI, eval.
2. **Design first.** Propose data-model changes (Neo4j / Postgres); define the API contract (DRF view + serializer or Pydantic models); decide whether a new agent/tool is needed or an existing one extends; sketch the UI component. Graph data flows client → typed API route → backend → Neo4j; never query Neo4j from the client.
3. **Implement in this order.** Backend API + models (so the frontend can call it) → agent/tool logic → migration / schema update → frontend page or component (loading states, error boundaries, a Vitest test under `frontend/__tests__/`) → tests and LegalBench eval when reasoning changed. Every model call goes through `law_ai.core.llm`; every agent action logs via `core.provenance`.
4. **Quality gates, all in Docker.**
   ```bash
   make lint && make typecheck && make test
   make test-legalbench      # only if reasoning logic changed
   make test-e2e             # if the app shell, the agent stream, the HITL flow or the API surface changed
   ```
   Never run `pytest`, `ruff`, `black`, `mypy` or `npm test` on the host. Regenerate the API contract fixture with `make manage CMD=export_api_schema` whenever a request/response model changes.
5. **Visual evidence.** Anything a user could see ships with screenshots in the PR body or under `docs/images/` ([docs/ui-ux-review.md](../../docs/ui-ux-review.md) § "Visual evidence"); label the PR `no-visual-change` only when there is genuinely nothing to see.
6. **Documentation and backlog (mandatory closing step).** Update `docs/` if the architecture or data model changed, add an example to [docs/api-examples.md](../../docs/api-examples.md) for a new route, update [docs/ui-ux.md](../../docs/ui-ux.md) for a new surface, update AGENTS.md for a new pattern. Append at least one `BL-YYYYMMDD-NN` bullet to [BACKLOG.md](../../BACKLOG.md) for any deferred refactor, missing test or stretch idea (or write `_none — justified: <reason>_` in the PR description), then run `make lint-specs` — it must exit 0.

## Output requirements

Use existing code style and patterns; docstrings with examples on every public function; at least one end-to-end test; follow-ups surfaced in BACKLOG.md. Start with "Understood. Implementing [Feature Name] following Law AI standards..." and end with "✅ Feature complete. All quality gates passed. Follow-ups added: <BL-...>. Ready for review."
