# Tasks: Revert abortive LexGraph rebrand

- **Spec**: [spec.md](spec.md)
- **Plan**: [plan.md](plan.md)
- **Status**: shipped (2026-05-05)

## T-001 — Rename package directory

- [x] `git mv backend/lexgraph backend/lawgraph`
- [x] `find backend -type d -name __pycache__ -exec rm -rf {} +`
- **Closes**: FR-1, AC-1

## T-002 — Mass brand sweep across non-historical docs/prompts/specs

- [x] sed `LexGraph AI` → `LawGraph AI`
- [x] sed `LexGraph` → `LawGraph`
- [x] sed `backend/lexgraph/` → `backend/lawgraph/`
- [x] sed `lexgraph\.` → `lawgraph.`
- [x] sed `"lexgraph"` / `'lexgraph'` → `"lawgraph"` / `'lawgraph'`
- **Files**: `docs/`, `prompts/`, `.github/`, `AGENTS.md`, `README.md`, `PRD.md`, `BACKLOG.md`, `backend/README.md`, `tests/README.md`, `local-ai-plan.md`, `specs/_template/`, `specs/README.md`
- **Closes**: FR-2, FR-3, FR-4, AC-4

## T-003 — Author ADR 0002

- [x] Create [docs/adr/0002-rebrand-lawgraph-ai.md](../../docs/adr/0002-rebrand-lawgraph-ai.md)
- [x] Add ADR-0002 row to [docs/adr/README.md](../../docs/adr/README.md)
- **Closes**: FR-5, AC-5

## T-004 — Author operator runbook

- [x] Create [docs/operator-rebrand-runbook.md](../../docs/operator-rebrand-runbook.md)
- [x] Sections: Greenfield, Upgrade-from-broken-state, "What did NOT change", Rollback, Verification checklist
- **Closes**: FR-6, AC-6

## T-005 — Rewrite spec/plan/tasks

- [x] Replace `specs/012-rebrand-lawgraph-ai/{spec,plan,tasks}.md` with revert-shaped contents
- **Closes**: FR-7

## T-006 — BACKLOG hygiene

- [x] Correct `lexgraph/...` path references inside open BACKLOG entries (e.g. BL-20260503-23) to `lawgraph/...`
- [x] Append `BL-20260505-01` (CI grep guard) and `BL-20260505-02` (proposal-file banner) to `## Open`
- [x] Add a `Done` entry summarising spec 012 with shipped date
- **Closes**: FR-8

## T-007 — Verification gate

- [x] `grep -rn "LexGraph\|backend/lexgraph" docs/ prompts/ specs/_template specs/012-rebrand-lawgraph-ai .github/ AGENTS.md README.md PRD.md BACKLOG.md backend/README.md tests/README.md local-ai-plan.md` returns no matches outside the explanatory references inside ADR 0002 and the operator runbook (NFR-CONSISTENCY-1).
- [x] `grep -rn "LexGraph" backend/lawgraph/ frontend/app frontend/components frontend/lib` returns no matches (NFR-CONSISTENCY-2).
- [x] `cd backend && python -c "import lawgraph"` succeeds (with deps installed).
- [x] Specs `001-*` … `011-*` left unmodified (NFR-HISTORY-1) — verified via `git status`.
- [x] Operators following the runbook lose no data (NFR-OPS-1) — Postgres role/db/password unchanged, no `docker compose down -v` required.
- [x] ADR 0002 lists alternatives considered including "complete the rebrand", "third name", "leave broken" (NFR-AUDIT-1).
- [x] Frontend `npm run build` renders metadata titles "LawGraph AI" (AC-9).
- [ ] `python scripts/spec_validator.py` exits 0
- [ ] `python scripts/backlog_lint.py` exits 0
- [ ] `pytest -q` collects without `ModuleNotFoundError`
- **Closes**: AC-2, AC-3, AC-4, AC-7, AC-8, AC-9, NFR-CONSISTENCY-1, NFR-CONSISTENCY-2, NFR-AUDIT-1, NFR-HISTORY-1, NFR-OPS-1

## Follow-ups Discovered

- **BL-20260505-01** — *infra, low* — CI grep check that fails when `LexGraph` (case-sensitive) appears outside `LexGraph_AI_Proposal.md` and historical specs `001-*`…`011-*`.
- **BL-20260505-02** — *doc-gap, low* — Add a top-of-file banner to `LexGraph_AI_Proposal.md` pointing readers at ADR 0002 and the canonical name.
