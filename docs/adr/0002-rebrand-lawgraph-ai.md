# ADR 0002 — Revert abortive LexGraph rebrand; canonical name remains LawGraph AI

- **Status**: accepted
- **Date**: 2026-05-05
- **Spec**: [specs/012-rebrand-lawgraph-ai](../../specs/012-rebrand-lawgraph-ai/spec.md)
- **Constitution clauses amended**: [§1 Mission Alignment](../constitution.md#1-mission-alignment) (clarifies brand text), [§2 Tech Stack](../constitution.md#2-tech-stack-locked) (canonical Python package name).
- **Operator runbook**: [docs/operator-rebrand-runbook.md](../operator-rebrand-runbook.md)

## Context

The repo was bootstrapped under two competing names. The original Git commit (`Initial commit: LexGraph AI scaffolding`) labelled the proposal `LexGraph_AI_Proposal.md`, while every Python module, Django app config, settings module, ASGI/WSGI entrypoint, Celery app name, env var, Postgres role, and docker-compose service used `lawgraph` / "LawGraph AI". A subsequent half-finished pass renamed only the on-disk Python package directory from `backend/lawgraph/` to `backend/lexgraph/` while leaving every `from lawgraph...` import, `apps.py` `name="lawgraph.<app>"`, `Celery("lawgraph")`, `DJANGO_SETTINGS_MODULE=lawgraph.settings.*`, and `daphne ... lawgraph.asgi:application` reference untouched. The backend therefore would not boot in that intermediate state.

Spec 012 was originally drafted to *complete* the LexGraph rebrand. Re-evaluation prior to landing showed:

1. The actual codebase is overwhelmingly LawGraph (every import, every settings value, the docker-compose service env vars, the Postgres role/db).
2. The user-facing brand the team wants is LawGraph AI.
3. The "LexGraph" strings were a stray scaffolding artefact, not an intentional rebrand.

This ADR records the decision to **revert** the abortive LexGraph rename rather than complete it.

## Decision

Adopt **"LawGraph AI"** (PascalCase: `LawGraph`; lowercase identifier: `lawgraph`; uppercase env prefix: `LAWGRAPH`) as the canonical product and Python-package name. Apply the revert mechanically:

1. **Brand text** — every user-facing string in code, docs, prompts, CI workflows, frontend metadata reads "LawGraph AI" or `LawGraph`.
2. **Python package** — `backend/lexgraph/` was renamed back to `backend/lawgraph/` via `git mv` (preserves history). No source-file edits were required because every `from lawgraph...` import was already correct.
3. **Settings module** — `DJANGO_SETTINGS_MODULE` defaults to `lawgraph.settings.<env>` (already the case in [backend/manage.py](../../backend/manage.py), [backend/lawgraph/asgi.py](../../backend/lawgraph/asgi.py), [backend/lawgraph/wsgi.py](../../backend/lawgraph/wsgi.py), and [backend/lawgraph/celery.py](../../backend/lawgraph/celery.py)).
4. **Celery app** — `Celery("lawgraph")` (unchanged).
5. **Phoenix project** — default `PHOENIX_PROJECT_NAME=lawgraph` (unchanged).
6. **Postgres identifiers** — role, database, password (`lawgraph` / `lawgraph` / `lawgraph-dev`) unchanged.
7. **GitHub repo slug stays `law-ai`** ([specs/012 NG-1](../../specs/012-rebrand-lawgraph-ai/spec.md)).
8. **Historical artefacts**:
   - [ADR 0001](0001-adopt-django-backend.md) and active specs `specs/001-*` … `specs/011-*` are append-only history per [docs/constitution.md](../constitution.md) §11. References to `backend/app/` (pre-Django-cutover) inside those specs are not touched.
   - The proposal file remains at `LexGraph_AI_Proposal.md` for blame/history. New writing must reference it as the historical proposal; the current product name is LawGraph AI.

The revert is a **single audited cutover**: a `git mv backend/lexgraph backend/lawgraph` plus a sed sweep over `docs/`, `prompts/`, `.github/`, top-level files (`README.md`, `AGENTS.md`, `PRD.md`, `BACKLOG.md`, `local-ai-plan.md`), the rebrand spec itself, and the `_template/` spec scaffold.

## Consequences

**Positive**

- Backend boots again. Imports, settings module, Celery `-A` flag, and ASGI dotted path all resolve.
- Single, consistent brand across the repo.
- Zero data-layer impact: Postgres role/db/password are unchanged, Neo4j password is unchanged, Phoenix project name is unchanged.
- The audit trail (`audit.AuditEvent`, Phoenix traces) is unchanged.

**Negative / Risks**

- Anyone who pulled the half-rebranded intermediate state and pushed downstream branches will see merge conflicts in every doc file. Mitigation: this ADR + [docs/operator-rebrand-runbook.md](../operator-rebrand-runbook.md) document the revert path.
- Historical commits and spec 012's pre-revert revision still mention "LexGraph". Intentional (append-only history) but a naive `grep` in the git log will turn them up.
- The proposal file's filename (`LexGraph_AI_Proposal.md`) remains in tree as historical; renaming would lose `git log --follow` history for low payoff.

**Neutral**

- LegalBench scores: zero delta — no reasoning logic changed.
- No env var deltas for any operator who was running on the original LawGraph stack.

## Alternatives Considered

| Alternative | Why rejected |
|-------------|--------------|
| **Complete the LexGraph rebrand** (rename every `from lawgraph` → `from lexgraph`, settings module, Celery app, env vars, Postgres role) | Hundreds of source-file edits across ~50 files plus docker-compose, .env.example, Makefile. Would also force every operator to recreate Postgres volumes. Zero user-visible benefit; the team prefers "LawGraph". |
| **Coin a third name** | Burns goodwill, doubles migration cost, no compelling differentiator. |
| **Leave the half-rebranded state** | Backend doesn't boot. Not viable. |
| **Rebrand specs 001–011 retroactively** | Violates [docs/constitution.md](../constitution.md) §11 (append-only history). |

## Supersedes / Superseded by

- **Supersedes**: the implicit "LexGraph" naming in the bootstrap commit and the abortive rename pass. Any in-flight PR that still uses "LexGraph" wording must rebase on this commit.
- **Superseded by**: none.

## References

- [specs/012-rebrand-lawgraph-ai/spec.md](../../specs/012-rebrand-lawgraph-ai/spec.md) — functional + non-functional requirements, acceptance criteria.
- [specs/012-rebrand-lawgraph-ai/plan.md](../../specs/012-rebrand-lawgraph-ai/plan.md) — replacement-map architecture and component change list.
- [specs/012-rebrand-lawgraph-ai/tasks.md](../../specs/012-rebrand-lawgraph-ai/tasks.md) — implementation sequence.
- [docs/operator-rebrand-runbook.md](../operator-rebrand-runbook.md) — operator-facing migration manual.
- [ADR 0001](0001-adopt-django-backend.md) — the Django cutover whose tail end inadvertently introduced the `lexgraph/` directory.
