# Tasks: {Feature Name}

> Each task must reference one or more `FR-*` / `NFR-*` / `AC-*` IDs from `spec.md`. CI's [spec_validator.py](../../scripts/spec_validator.py) enforces that every requirement in `spec.md` is referenced by at least one task.

## Conventions

- Status: `[ ]` todo / `[~]` in-progress / `[x]` done.
- Owner: GitHub handle or `@copilot` / `@agent:<role>`.
- Each task lists exact files to touch and how to verify.

---

## T-001 — {Short imperative title}

- **Refs**: FR-1, AC-1
- **Owner**: @copilot
- **Status**: `[ ]`
- **Files**:
  - `backend/lawgraph/{agentsapi,analysis,graph,lsat}/...py` (new — pick the matching router)
  - `backend/tests/api/test_....py` (new)
- **Steps**:
  1. …
  2. …
- **Verify**:
  - `cd backend && pytest tests/api/test_....py -q` passes.
  - `mypy app/ --strict` clean.

## T-002 — …

- **Refs**: FR-2, NFR-AUDIT-1
- **Owner**: …
- **Status**: `[ ]`
- **Files**: …
- **Steps**: …
- **Verify**: …

---

## Done-When (Definition of Done)

- All tasks `[x]`.
- All `AC-*` from `spec.md` covered by passing tests.
- `make lint && make test` green.
- LegalBench delta recorded in PR description (if §11 of spec applies).
- Provenance logging verified manually for new agent paths.
- **`## Follow-ups Discovered` section below populated** — at minimum, every implementer must record one of: a new BACKLOG entry, a refactor candidate, a missing test, or `_none_` (must be justified in the PR).

---

## Follow-ups Discovered

> Append-only. Mirror each item into [BACKLOG.md](../../BACKLOG.md) with a `BL-YYYYMMDD-NN` id. CI ([scripts/spec_validator.py](../../scripts/spec_validator.py)) checks this section exists. CI ([scripts/backlog_lint.py](../../scripts/backlog_lint.py)) checks the BACKLOG mirror.

- _none_  <!-- replace with bullets like: "BL-YYYYMMDD-NN — feature, med — short description." -->
