# Spec: Revert abortive LexGraph rebrand; canonical name remains LawGraph AI

- **ID**: 012-rebrand-lawgraph-ai
- **Status**: shipped
- **Owner**: @copilot (paired with maintainer)
- **Created**: 2026-05-03
- **Shipped**: 2026-05-05
- **Roadmap Epic**: N/A — repo hygiene
- **Constitution Compliance**: see [ADR 0002](../../docs/adr/0002-rebrand-lawgraph-ai.md) for the §1/§2 brand-text amendment.

## 1. Problem & Motivation

The repo entered a half-rebranded state in which the on-disk Python package directory was renamed `backend/lawgraph/` → `backend/lexgraph/` while every import (`from lawgraph.*`), every Django `apps.py` `name="lawgraph.<app>"`, `Celery("lawgraph")`, `DJANGO_SETTINGS_MODULE=lawgraph.settings.*`, the docker-compose Daphne command (`daphne ... lawgraph.asgi:application`), Postgres role/db, env vars, and Makefile targets continued to use `lawgraph`. The backend would not boot in that state (`ModuleNotFoundError: No module named 'lawgraph'`).

Doc/prompt drift compounded the confusion: a partial pass had also begun replacing "LawGraph AI" with "LexGraph AI" in `docs/`, `prompts/`, `AGENTS.md`, the constitution, and BACKLOG metadata.

We need a single audited cutover that aligns every surface on the original, working name.

## 2. Goals

- **G1**: Restore the Python package to `backend/lawgraph/` so the backend boots and tests collect again.
- **G2**: Re-establish "LawGraph AI" as the canonical user-visible brand across `docs/`, `prompts/`, `.github/`, top-level files, `specs/_template`, and this spec.
- **G3**: Record the decision in [ADR 0002](../../docs/adr/0002-rebrand-lawgraph-ai.md) so future agents do not re-attempt the rename.
- **G4**: Provide an operator runbook ([docs/operator-rebrand-runbook.md](../../docs/operator-rebrand-runbook.md)) for anyone who pulled the broken intermediate state.

## 3. Non-Goals

- **NG-1**: GitHub repo slug. Stays `law-ai` — renaming requires a separate roadmap decision and would break every existing clone URL.
- **NG-2**: Postgres role / database / password. Already `lawgraph` / `lawgraph` / `lawgraph-dev`; not touched.
- **NG-3**: Neo4j password. Unchanged.
- **NG-4**: Phoenix project name. Already `lawgraph`; unchanged.
- **NG-5**: Specs `001-*` … `011-*` are append-only history per [docs/constitution.md](../../docs/constitution.md) §11 and are not retroactively rewritten.
- **NG-6**: The `LexGraph_AI_Proposal.md` filename. Kept for `git log --follow` history; new writing references it as the historical proposal.

## 4. User Stories

- As a **maintainer**, I can `git pull && make dev` and have the backend boot, so that the half-rebranded state is unblocked.
- As a **new contributor**, every doc, prompt, and spec template I read says "LawGraph AI", so that I do not introduce fresh "LexGraph" drift.
- As an **operator** who pulled the broken intermediate, I have a runbook that takes me back to a healthy stack without losing data.

## 5. Functional Requirements

- **FR-1**: `backend/lexgraph/` is renamed to `backend/lawgraph/` via `git mv` (preserves history). Stale `__pycache__` directories under `backend/` are cleared.
- **FR-2**: All occurrences of `LexGraph AI` → `LawGraph AI` in docs/prompts/specs/template/`.github/`/top-level files.
- **FR-3**: All occurrences of `LexGraph` (PascalCase) → `LawGraph`.
- **FR-4**: All Python module references `backend/lexgraph/` and `lexgraph.*` → `backend/lawgraph/` and `lawgraph.*` in non-code surfaces (docs, prompts, specs).
- **FR-5**: ADR 0002 is created at [docs/adr/0002-rebrand-lawgraph-ai.md](../../docs/adr/0002-rebrand-lawgraph-ai.md) and indexed in [docs/adr/README.md](../../docs/adr/README.md).
- **FR-6**: Operator runbook authored at [docs/operator-rebrand-runbook.md](../../docs/operator-rebrand-runbook.md).
- **FR-7**: This spec, plan, and tasks are rewritten to describe the revert (not the rebrand-to-LexGraph that was originally drafted).
- **FR-8**: BACKLOG hygiene — entries that referenced `lexgraph/...` paths get corrected to `lawgraph/...`; historical entries stay struck-through.

## 6. Non-Functional Requirements

- **NFR-CONSISTENCY-1**: After this spec ships, `grep -rn "LexGraph\|backend/lexgraph" docs/ prompts/ specs/_template specs/012-rebrand-lawgraph-ai .github/ AGENTS.md README.md PRD.md BACKLOG.md` returns zero matches.
- **NFR-CONSISTENCY-2**: `grep -rn "LexGraph" backend/lawgraph/ frontend/app frontend/components frontend/lib` returns zero matches (excluding caches and `.next/`).
- **NFR-AUDIT-1**: ADR 0002 lists the alternatives considered (complete-the-LexGraph-rebrand vs. revert vs. third name vs. leave broken).
- **NFR-HISTORY-1**: Specs `001-*` … `011-*` are not modified.
- **NFR-OPS-1**: Operators following [docs/operator-rebrand-runbook.md](../../docs/operator-rebrand-runbook.md) lose zero data.

## 7. Data Model Impact

None. No Neo4j or Postgres schema changes. Postgres role/db/password unchanged.

## 8. API Surface

None. No HTTP/WS routes touched.

## 9. Agent / Crew Impact

None. Agent code under `backend/lawgraph/agents_runtime/` is unchanged because every import already used `from lawgraph...`.

## 10. Acceptance Criteria

- **AC-1**: `backend/lawgraph/` exists and `backend/lexgraph/` does not. `git log --follow backend/lawgraph/__init__.py` shows continuity from the original `lawgraph/` history.
- **AC-2**: `cd backend && python -c "import lawgraph; import lawgraph.celery; import lawgraph.urls"` succeeds with deps installed.
- **AC-3**: `pytest -q` collects without `ModuleNotFoundError`.
- **AC-4**: `grep -rn "LexGraph\|backend/lexgraph" docs/ prompts/ specs/_template specs/012-rebrand-lawgraph-ai .github/ AGENTS.md README.md PRD.md BACKLOG.md` exits non-zero (no matches).
- **AC-5**: `docs/adr/0002-rebrand-lawgraph-ai.md` exists and is linked from `docs/adr/README.md`.
- **AC-6**: `docs/operator-rebrand-runbook.md` exists and is linked from `docs/architecture.md` and ADR 0002.
- **AC-7**: `python scripts/spec_validator.py` exits 0.
- **AC-8**: `python scripts/backlog_lint.py` exits 0.
- **AC-9**: Frontend `npm run build` succeeds; metadata titles render "LawGraph AI".

## 11. LegalBench Impact

- Tasks affected: none.
- Expected delta: 0 pp.

## 12. Risks & Open Questions

- **R-1**: Anyone who pushed downstream branches off the half-rebranded state will see merge conflicts in every doc file. _Mitigation_: the operator runbook documents `git stash` + re-pull.
- **R-2**: Stale byte-code (`.pyc` files imported under the old `lexgraph` package name) survives on developer machines. _Mitigation_: runbook step 3 clears `__pycache__`.
- **R-3**: `LexGraph_AI_Proposal.md` filename remains — naive `grep` of the repo for "LexGraph" will hit it. _Accepted_: the filename is historical; ADR 0002 explains.

## 13. Out of Scope / Follow-ups

- Rename `LexGraph_AI_Proposal.md` → `LawGraph_AI_Proposal.md`. Would lose `git log --follow` history; deferred unless someone needs it.
- A CI check that fails the build if `LexGraph` reappears outside the historical proposal file. Tracked as a follow-up in [BACKLOG.md](../../BACKLOG.md).
- Eventually retire ADR 0002 once the brand drift fades from the working memory of contributors.

## Follow-ups Discovered

- **BL-20260505-01** — *infra, low* — Add a CI grep check that fails when `LexGraph` (case-sensitive) appears outside `LexGraph_AI_Proposal.md` and historical specs `001-*`…`011-*`. Catches future regressions of this rebrand.
- **BL-20260505-02** — *doc-gap, low* — Annotate `LexGraph_AI_Proposal.md` with a top-of-file banner pointing readers at ADR 0002 and clarifying that the canonical product name is LawGraph AI.
