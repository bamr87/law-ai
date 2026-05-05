# Tasks: Rebrand from LawGraph AI to LawGraph AI

> **Status: BLOCKED on `/clarify`.** This file is a placeholder so CI's
> [scripts/spec_validator.py](../../scripts/spec_validator.py) is satisfied
> while [spec.md § 13](spec.md#13-open-decisions-block-plan-and-beyond-until-resolved)
> open decisions await human answers. The task list below is the **planned**
> breakdown from [plan.md § 11](plan.md#11-estimated-effort); none should be
> started until OQ-1 → OQ-5 are resolved and the spec is re-marked
> `clarified`.

## Conventions

- Status: `[ ]` todo / `[~]` in-progress / `[x]` done / `[!]` blocked.
- Owner: GitHub handle or `@copilot` / `@agent:<role>`.

---

## T-001 — ADR + constitution amendment

- **Refs**: FR-6, NFR-DOC-1
- **Owner**: @copilot (HUMAN-PAIRED for Level-2 sign-off)
- **Status**: `[!]` blocked-on-clarify (OQ-2)
- **Files**:
  - `docs/adr/0002-rebrand-lawgraph-ai.md` (new)
  - `docs/constitution.md` (footnote + brand sweep)
  - `docs/adr/README.md` (index entry)

## T-002 — Rebrand helper script + dry-run audit

- **Refs**: FR-1
- **Owner**: @copilot
- **Status**: `[!]` blocked-on-clarify
- **Files**:
  - `scripts/rebrand.sh` (new — temporary, deleted at T-011)
  - emit `rebrand-dryrun.txt` artifact

## T-003 — Python package rename + import sweep

- **Refs**: FR-2, FR-7, NFR-PARITY-1, NFR-COV-1, AC-2
- **Owner**: @copilot
- **Status**: `[!]` blocked-on-clarify (OQ-4)
- **Files**:
  - `git mv backend/lawgraph backend/lawgraph`
  - all `from lawgraph...` → `from lawgraph...` across `backend/` and `tests/`

## T-004 — Settings / ASGI / Celery / pytest config

- **Refs**: FR-3, AC-7
- **Owner**: @copilot
- **Status**: `[!]` blocked-on-clarify
- **Files**:
  - `backend/lawgraph/{asgi,wsgi,celery,__init__,manage}.py`
  - `backend/lawgraph/settings/{base,dev,test,prod}.py`
  - `pytest.ini`

## T-005 — Docker, compose, env, Makefile, CI workflows

- **Refs**: FR-4, FR-8, AC-6
- **Owner**: @copilot
- **Status**: `[!]` blocked-on-clarify (OQ-5)
- **Files**:
  - `docker-compose.yml`, `backend/Dockerfile`, `frontend/Dockerfile`
  - `.env.example`, `Makefile`, `.github/workflows/*.yml`

## T-006 — Frontend brand sweep + tests

- **Refs**: FR-1, AC-3, AC-8
- **Owner**: @copilot
- **Status**: `[!]` blocked-on-clarify (OQ-3)
- **Files**:
  - `frontend/app/{layout.tsx,page.tsx}`, `frontend/components/NavBar.tsx`
  - `frontend/__tests__/**` for any brand-string assertions
  - `frontend/package.json` `name` field

## T-007 — Docs, specs, BACKLOG, copilot-instructions sweep

- **Refs**: FR-7, NFR-DOC-1, AC-1
- **Owner**: @copilot
- **Status**: `[!]` blocked-on-clarify
- **Files**:
  - `docs/**/*.md` (excluding `docs/adr/0001-adopt-django-backend.md` and
    `docs/adr/0002-rebrand-lawgraph-ai.md`)
  - `specs/**/*.md` (preserve direct quotations of historical state)
  - `BACKLOG.md`, `.github/copilot-instructions.md`, `AGENTS.md`,
    `README.md`, `PRD.md`, `AOS-DLC_Outline_Guide.md`

## T-008 — Ops scripts + launchd plist rename

- **Refs**: FR-4
- **Owner**: @copilot
- **Status**: `[!]` blocked-on-clarify
- **Files**:
  - `scripts/launchd/com.lawgraph.evolve.plist` → `com.lawgraph.evolve.plist`
  - `backend/scripts/{init-db.sh,ingest_sample.py,ollama-bootstrap.sh}`
  - `scripts/{backlog_lint.py,evolve_audit.py,spec_validator.py}` (docstring sweep)

## T-009 — Author operator rebrand runbook

- **Refs**: FR-9, NFR-MIGRATION-SAFETY-1, AC-9
- **Owner**: @copilot
- **Status**: `[!]` blocked-on-clarify (OQ-5)
- **Files**:
  - `docs/operator-rebrand-runbook.md` (new)

## T-010 — CI grep gate + final preserve-historical-quote test

- **Refs**: AC-1, AC-4, AC-5
- **Owner**: @copilot
- **Status**: `[!]` blocked-on-clarify
- **Files**:
  - `.github/workflows/ci.yml` (new step running the AC-1 grep)
  - `tests/test_repo_structure.py` (extend to assert the carve-outs)

## T-011 — Memory updates + cutover commit

- **Refs**: FR-5, FR-10, NFR-LICENSE-1, NFR-AUDIT-1, NFR-SEC-1, AC-10
- **Owner**: @copilot (HUMAN-PAIRED — final review gate)
- **Status**: `[!]` blocked-on-clarify
- **Files**:
  - `LawGraph_AI_Proposal.md` → `LawGraph_AI_Proposal.md` (rename + banner)
  - `/memories/repo/*.md` (this workspace) — sweep for new package paths
  - `git rm scripts/rebrand.sh`

---

## Done-When (Definition of Done)

- All `T-*` tasks `[x]`.
- All `AC-*` from [spec.md](spec.md) verified.
- `make lint && make test && cd frontend && npm test -- --run` green.
- `python scripts/spec_validator.py && python scripts/backlog_lint.py` exit 0.
- LegalBench delta = 0.0 pp (parity check, NFR-PARITY-1).
- Maintainer signs off on the cutover commit (HITL Level-2 per
  [docs/constitution.md](../../docs/constitution.md) §10).
- `## Follow-ups Discovered` populated and mirrored to
  [BACKLOG.md](../../BACKLOG.md).

---

## Follow-ups Discovered

_none yet — task list will be filled in after `/clarify` resolves OQ-1
through OQ-5 and `/implement` runs._
