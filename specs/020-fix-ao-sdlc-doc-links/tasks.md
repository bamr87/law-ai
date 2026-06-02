# Tasks: Fix AO-SDLC Doc-Link Case Mismatch + Restore Backlog Gate

> Each task references one or more `FR-*` / `NFR-*` / `AC-*` IDs from [spec.md](spec.md). CI's [spec_validator.py](../../scripts/spec_validator.py) enforces that every requirement is referenced by at least one task.

## Conventions

- Status: `[ ]` todo / `[~]` in-progress / `[x]` done.
- Owner: GitHub handle or `@copilot` / `@agent:<role>`.
- Each task lists exact files to touch and how to verify.

---

## T-001 — Correct the 7 case-mismatched AO-SDLC doc links + test data

- **Refs**: FR-1, FR-2, AC-2
- **Owner**: @bamr87
- **Status**: `[x]`
- **Files**:
  - `AGENTS.md` (href `docs/AO-SDLC.md` → `docs/ao-sdlc.md`)
  - `docs/constitution.md` (hrefs `AO-SDLC.md` → `ao-sdlc.md`, `AO-SDLC-guide.md` → `ao-sdlc-guide.md`; matching link text)
  - `docs/ao-sdlc.md` (href `AO-SDLC-guide.md` → `ao-sdlc-guide.md`)
  - `specs/README.md` (href `../docs/AO-SDLC.md` → `../docs/ao-sdlc.md`)
  - `specs/011-django-backend/spec.md`, `specs/011-django-backend/plan.md` (href `../../docs/AO-SDLC-guide.md` → lowercase)
  - `tests/test_docs.py` (`REQUIRED_DOCS`: `docs/AO-SDLC.md` → `docs/ao-sdlc.md`)
- **Steps**:
  1. Replace each uppercase href with its lowercase canonical form; fix visible link text where it shows the path.
  2. Update the `REQUIRED_DOCS` entry to the lowercase path.
- **Verify**:
  - Case-sensitive scan reports 0 case-only mismatches (AC-2).

## T-002 — Add the case-mismatch guard test

- **Refs**: FR-3, AC-3
- **Owner**: @bamr87
- **Status**: `[x]`
- **Files**:
  - `tests/test_docs.py` (add `test_no_case_mismatched_doc_links`)
- **Steps**:
  1. Walk every `*.md` (skip `.git`, `node_modules`, `.next`, `.venv`, caches), parse `[text](href)` links.
  2. Skip external/anchor hrefs; resolve relative hrefs against the file's dir.
  3. Flag a link only when the target does **not** exist case-exact **but** a case-insensitive variant does (right file, wrong case).
  4. Assert the flagged list is empty, listing offenders in the message.
- **Verify**:
  - The new test passes after T-001; fails if any uppercase AO-SDLC link is reintroduced.

## T-003 — Gate the root structural tier in CI

- **Refs**: FR-4, NFR-CI-1, AC-3, AC-5
- **Owner**: @bamr87
- **Status**: `[x]`
- **Files**:
  - `.github/workflows/ci.yml` (new `repo-structural` job)
- **Steps**:
  1. Add a job (`needs: spec-gate`) that checks out, sets up Python 3.12, `pip install pytest`, and runs `pytest tests/ -m "not backend and not frontend" -q`.
  2. Exclude the heavy subprocess suites (`backend`/`frontend` markers) so the job stays dependency-light (NFR-CI-1).
- **Verify**:
  - `pytest tests/ -m "not backend and not frontend"` green in the backend container (Linux, `/repo` mount) (AC-3).

## T-004 — Resolve the duplicate backlog id

- **Refs**: FR-5, AC-1, NFR-SAFETY-1
- **Owner**: @bamr87
- **Status**: `[x]`
- **Files**:
  - `BACKLOG.md`
- **Steps**:
  1. Renumber the orphaned `doc-gap` `BL-20260511-01` (the "missing `docs/AO-SDLC.md`" item) to `BL-20260511-32`.
  2. Move it to `## Done` with a `(resolved 2026-06-02)` note pointing at specs/020; leave the canonical spec-017 `BL-20260511-01` untouched.
  3. Mirror this spec's follow-ups (`BL-20260602-01`, `BL-20260602-02`) into `## Open`.
- **Verify**:
  - `python3 scripts/backlog_lint.py` exits 0 — unique ids, no removed entries (AC-1, NFR-SAFETY-1).

## T-005 — Verify all gates & constitution compliance

- **Refs**: AC-1, AC-3, AC-4, NFR-AUDIT-1, NFR-HITL-1
- **Owner**: @bamr87
- **Status**: `[x]`
- **Steps**:
  1. `python3 scripts/spec_validator.py` → `PASS specs/020-fix-ao-sdlc-doc-links` (AC-4).
  2. `python3 scripts/backlog_lint.py` → exit 0 (AC-1).
  3. Backend container: `pytest tests/ -m "not backend and not frontend"` green (AC-3).
  4. `make test-backend` green (no collateral on the Django suite).
  5. Confirm no agent/LLM (NFR-AUDIT-1) or ingestion/HITL (NFR-HITL-1) path was touched — docs/tests/CI only.
- **Verify**:
  - All commands above exit 0.

---

## Done-When (Definition of Done)

- All tasks `[x]`.
- All `AC-*` from `spec.md` covered by passing checks.
- `scripts/spec_validator.py` + `scripts/backlog_lint.py` exit 0; root structural tier green in a Linux container.
- LegalBench delta: 0 pp (no reasoning logic changed).
- `## Follow-ups Discovered` populated and mirrored into [BACKLOG.md](../../BACKLOG.md).

---

## Follow-ups Discovered

> Append-only. Mirror each item into [BACKLOG.md](../../BACKLOG.md) with a `BL-YYYYMMDD-NN` id.

- BL-20260602-01 — *doc-gap, low* — Fix non-case broken relative links in current governing docs: `docs/constitution.md` links to `AGENTS.md` (3×) but it lives at the repo root, so the href should be `../AGENTS.md` (404s on every platform). _Surfaced in:_ specs/020-fix-ao-sdlc-doc-links.
- BL-20260602-02 — *test-gap, med* — Update or historically-annotate the ~120 `backend/app/*` references in shipped specs 011 + `docs/adr/0001-adopt-django-backend.md` (pre-Django-rebrand layout), then promote `test_no_case_mismatched_doc_links` to a full relative-link existence check. _Surfaced in:_ specs/020-fix-ao-sdlc-doc-links.
