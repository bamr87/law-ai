# LawGraph AI — Constitution

> Org-wide, non-negotiable standards for every spec, plan, and implementation produced by humans or AI agents in this repo. This is the **first** document any agent reads when running [/specify](../prompts/specify.md), [/plan](../prompts/plan.md), or [/implement](../prompts/implement.md).
>
> Higher-level principles, mission, and tech-stack rationale live in [AGENTS.md](AGENTS.md). This file encodes only the **rules a spec or PR must satisfy to be valid**.

## 1. Mission Alignment

Every feature must trace to the mission in [AGENTS.md](AGENTS.md): open-source, privacy-first, auditable, graph-native legal intelligence with HITL on high-stakes paths.

If a proposed feature requires a closed-source LLM as **product runtime**, breaks local-first operation, or removes provenance, the spec **must be rejected**.

**Development orchestration is a separate layer.** GitHub Copilot is the sole sanctioned AI dev surface (Copilot Chat in VS Code + the GitHub Copilot coding agent in the cloud). Specs proposing alternative coding agents (Cursor, Continue.dev, Claude Code, Aider, Codex, Gemini CLI, etc.) or their config files **must be rejected**. See [AGENTS.md](AGENTS.md) § "Development Orchestration".

## 2. Tech Stack (Locked)

- Backend: Python 3.12+, Django 5 (ASGI via daphne), Django REST Framework, Channels, Celery (Redis broker), Pydantic v2 (domain layer), CrewAI + LangGraph, Neo4j, Postgres (Django ORM async + raw asyncpg where required), Chroma, Ollama.
- Frontend: Next.js 15 App Router, TypeScript strict, Tailwind, shadcn/ui, Cytoscape.js, TanStack Query.
- Infra: Docker Compose for local; GitHub Actions for CI.

No new top-level frameworks (e.g. Vue, LlamaIndex as primary) without an ADR in `docs/adr/` and explicit approval. The Django adoption itself is recorded in [docs/adr/0001-adopt-django-backend.md](adr/0001-adopt-django-backend.md), which supersedes the previous FastAPI lock established in earlier revisions of this section.

## 3. Code Quality Gates

A spec **must** declare and a PR **must** pass:

- `ruff check` + `black --check` clean (line length 88).
- `mypy app/ --strict` clean for any touched module.
- Frontend: `npm run lint` + `npx tsc --noEmit` clean.
- Pytest + Vitest green; combined coverage **≥ 75%** on changed files.
- LegalBench regression run (`Run LegalBench Eval` task) when reasoning logic changes — score must not regress more than 1 pp on listed tasks.

## 4. Provenance & Audit (Non-Negotiable)

- Every agent LLM call, tool call, and retrieval must go through `app.core.provenance`.
- Every Neo4j node/edge created or updated must carry `source`, `source_url` (when applicable), `ingest_timestamp`, `agent_version`, and `confidence` (0–1).
- Nodes are **never** hard-deleted. Use `archived_at` soft-delete.

## 5. Human-in-the-Loop (HITL) Requirements

Spec **must** declare `human_approval_required: true` for any of:

- Ingestion of a new public data source.
- Schema migration (Neo4j or Postgres).
- Any agent output rated `high_stakes` (criminal, immigration, life-safety, regulatory filings).
- Production deployment of a new agent role.

## 6. Testing Standards

Every new feature ships with:

- ≥ 1 unit test (mocked external deps).
- ≥ 1 integration test (real Neo4j/Postgres via `docker compose`).
- For new agents: ≥ 1 LegalBench-subset test in `backend/tests/agents/`.
- For new frontend components: ≥ 1 Vitest + RTL test in `frontend/__tests__/`.

## 7. Spec-Driven Workflow (AO-SDLC Phase 1)

Every change larger than a typo follows the spec workflow:

1. Author creates `specs/NNN-feature-slug/` from [specs/_template](../specs/_template).
2. Run [/specify](../prompts/specify.md) → fills `spec.md`.
3. Run [/clarify](../prompts/clarify.md) → resolves open questions in-place.
4. Run [/plan](../prompts/plan.md) → fills `plan.md`.
5. Run [/tasks](../prompts/tasks.md) → fills `tasks.md`.
6. Open PR with all four files. CI runs [scripts/spec_validator.py](../scripts/spec_validator.py) drift gate.
7. Run [/implement](../prompts/implement.md) per task; PRs reference `specs/NNN-...` in description.

See [docs/AO-SDLC.md](AO-SDLC.md) for how phases map onto LawGraph and [docs/AO-SDLC-guide.md](AO-SDLC-guide.md) for the full framework reference.

## 8. Security Baselines

- No secrets in repo. `.env.example` only.
- All external HTTP via `httpx` + `tenacity` retries; no raw `requests`.
- Input validation with Pydantic at every API boundary.
- LLM tool calls run through provenance — never give an agent shell or unsandboxed `eval`.
- Dependency additions require a brief license + security note in the spec.

## 9. Documentation

- Architecture changes update [docs/architecture.md](architecture.md).
- New agent roles update [docs/agent-roles.md](agent-roles.md).
- New external data sources update `docs/data-sources.md` (create if missing).
- Graph schema changes update `docs/data-model.md` (create if missing).

## 10. Autonomy Level

This repo currently operates at **AO-SDLC Level 2 (Collaborative)**: agents draft, humans approve at the spec gate and the PR gate. Promotion to Level 3 requires:

- LegalBench baseline established and tracked in CI.
- Langfuse (or equivalent) traces wired up.
- ADR documenting which classes of change may auto-merge.

## 11. Continuous Evolution (Self-Improving Repo)

The repo must always grow forward. Every implementation cycle MUST end with explicit follow-ups so future agents and humans inherit a richer task graph than they started with.

- **Every `tasks.md`** ends with a `## Follow-ups Discovered` section. CI ([scripts/spec_validator.py](../scripts/spec_validator.py)) enforces this.
- **Every follow-up** is mirrored into [BACKLOG.md](../BACKLOG.md) with a `BL-YYYYMMDD-NN` id. CI ([scripts/backlog_lint.py](../scripts/backlog_lint.py)) enforces format and forbids deletion of historical entries (move to `## Done` instead).
- **Every `/specify`** must first scan `BACKLOG.md` and reference any matching `BL-*` items in spec §2; matched items move from `## Open` to `## Claimed`.
- **"No follow-ups"** is allowed only with an explicit justification line (`_none — justified: <reason>_`) preserved in the PR description.
- **Mission drift guard.** Follow-ups MUST be consistent with §1 Mission Alignment, §2 Tech Stack, and §4 Provenance. Items proposing closed-source LLMs, frameworks not listed in §2, or removal of provenance must be rejected at triage.
- **Refactor budget.** At least one `refactor` or `tech-debt` BACKLOG item should be promoted into `specs/` for every three feature specs shipped, to prevent rot.
- **Tests stay aligned.** When a `BL-*` item is promoted into a spec, the new `tasks.md` must add or extend tests covering the BACKLOG'd concern — self-evolution never lowers coverage.

## 12. Autonomy Loop Invariants

Recorded by [docs/adr/0003-autonomy-orchestrator.md](adr/0003-autonomy-orchestrator.md). The `AutonomyOrchestrator` and any future autonomous loop in this repo MUST satisfy all of the following — CI and code-review reject violations:

- **I1 — No auto-merge.** Every loop ends in either a draft PR (code) or a `PendingReview` row (data). No GitHub Actions workflow may be granted permissions sufficient to merge a PR; no Celery task may write to a `:Case`/`:Statute` node outside `IngestionScout.run_and_commit`.
- **I2 — Closed source registry.** Recursion expands within `lawgraph.ingestionapp.sources.SOURCE_REGISTRY` whose member name appears in `AUTONOMY_ALLOWED_SOURCES`. Adding a new adapter is its own `/specify` cycle (preserves §5).
- **I3 — Kill-switch.** A single settings flag (`AUTONOMY_ENABLED`, default `False`) short-circuits every loop with one provenance event (`event_type='autonomy_disabled'`). Operators must explicitly opt-in per environment.
- **I4 — One audited entry point.** Every cycle is invoked through `lawgraph.core.autonomy.run_cycle()` and emits paired `autonomy_cycle.start` + `autonomy_cycle.end` provenance events. The daily digest under `AUTONOMY_DIGEST_DIR` is the canonical human-review surface.
- **I5 — Propose-only test synthesis.** Autonomy-generated tests land as `*.proposed.py` decorated with `@pytest.mark.skip("autonomy-proposed")`. Reviewers must explicitly un-skip.
- **I6 — Provenance preserved.** Every adapter dispatch records `{adapter_name, query, items_returned, items_quarantined}`; every LLM call goes through `lawgraph.core.provenance` (preserves §4).

Promotion to Level 3 — even for narrow change classes — requires a separate ADR amending §10 and these invariants.

---

**Amendments to this constitution require an ADR in `docs/adr/` and review by a human maintainer.**
