# Spec: Fix AO-SDLC Doc-Link Case Mismatch + Restore Backlog Gate

- **ID**: 021-fix-ao-sdlc-doc-links
- **Status**: shipped
- **Owner**: @bamr87
- **Created**: 2026-06-02
- **Backlog Origin**: BL-20260511-01 (the mis-numbered `doc-gap` duplicate — renumbered to BL-20260511-32 and resolved here)
- **Constitution Compliance**: confirmed against [docs/constitution.md](../../docs/constitution.md) — §1 mission unaffected (docs/tests only), §3 quality gates strengthened, §9 documentation, §11 continuous evolution (gate restored, follow-ups recorded).

## 1. Problem & Motivation

Two coupled defects were found while running `/evolve`:

1. **The evolution gate is RED.** `scripts/backlog_lint.py` fails with `duplicate id BL-20260511-01`: the id is used twice in [BACKLOG.md](../../BACKLOG.md) — once for the canonical spec-017 follow-up (line 109, *infra*, Cypher migration runner) and once for an orphaned auto-discovered *doc-gap* (line 27). Because [/evolve](../../prompts/evolve.md) step 5 requires `backlog_lint` to exit 0, **no evolution cycle can pass its gates until this is fixed.**

2. **The orphan flags a real cross-platform bug.** That doc-gap reads "Author missing doc `docs/AO-SDLC.md`. Referenced by AGENTS.md but file does not exist." The file *does* exist — as lowercase `docs/ao-sdlc.md` — so the item is a false "missing doc". The true defect is **case-mismatched links**: governing docs link to `docs/AO-SDLC.md` / `docs/AO-SDLC-guide.md` (uppercase) while the files are lowercase. These resolve on case-insensitive filesystems (macOS dev) but **404 on case-sensitive ones (Linux / CI / Docker / GitHub's rendered Markdown)**. A repo-wide scan finds exactly **7** such case-only mismatches, all AO-SDLC.

3. **The same bug is latent in the test suite.** `tests/test_docs.py` lists `docs/AO-SDLC.md` (uppercase) in `REQUIRED_DOCS`; `test_doc_exists_and_nontrivial` therefore passes on macOS but would **fail on Linux**. It has not fired because **the root `tests/` structural suite is not run by any CI workflow** (`ci.yml` only runs the backend suite with `working-directory: backend`). So the docs/specs/configs guardrails currently have no teeth.

## 2. Origin & Background

- **BL-20260511-01** (the *doc-gap* duplicate) — surfaced by an `evolve_audit` discovery scan; collided with the spec-017 id of the same date.
- Scans: `7` case-only link mismatches; `0` after fix. `120` other broken relative links exist but are genuinely-moved historical references (`backend/app/*` pre-Django-rebrand) with no case-variant on disk — out of scope (see §13).

## 3. Goals

- G1: Restore `backlog_lint` to exit 0 by making every `BL-*` id unique, without deleting any historical entry.
- G2: Make every Markdown link to the AO-SDLC docs resolve on a case-sensitive filesystem.
- G3: Add a regression guard that fails when any Markdown link points at a file that exists only under a different case.
- G4: Give the root structural suite (and the new guard) real CI teeth.

## 4. Non-Goals

- NG1: Renaming the doc files to uppercase. The `docs/` convention is lowercase (`architecture.md`, `constitution.md`, …); references are corrected to match, not the reverse.
- NG2: Fixing the ~120 historical `backend/app/*` links in shipped specs / ADR 0001 (they document the pre-rebrand layout). Tracked as a follow-up.
- NG3: Fixing non-case broken links (e.g. `docs/constitution.md` → `AGENTS.md` should be `../AGENTS.md`). Tracked as a follow-up.
- NG4: Any backend/runtime/agent change.

## 5. User Stories

- As a contributor on Linux/CI, I want doc links to resolve so navigation and rendered Markdown are not broken.
- As the Evolution Pilot, I want `backlog_lint` green so `/evolve` cycles can pass their gates.
- As a maintainer, I want CI to fail when someone re-introduces a case-mismatched doc link.

## 6. Functional Requirements

- **FR-1**: Every Markdown link whose href targets the AO-SDLC docs uses the canonical lowercase path (`docs/ao-sdlc.md`, `docs/ao-sdlc-guide.md`, or the correct relative form). All 7 known occurrences are corrected.
- **FR-2**: `tests/test_docs.py` `REQUIRED_DOCS` references `docs/ao-sdlc.md` (lowercase) so the existence check is correct on case-sensitive filesystems.
- **FR-3**: A new test `test_no_case_mismatched_doc_links` scans every tracked `*.md` file and fails if any relative link target exists only under a different case (right file, wrong case). It must ignore genuinely-missing targets so it does not trip on historical references.
- **FR-4**: A CI job runs the root structural tier (`pytest tests/ -m "not backend and not frontend"`) so the structural guardrails — including FR-3 — are enforced on every push/PR.
- **FR-5**: `BACKLOG.md` contains no duplicate ids: the orphaned `doc-gap` entry is renumbered to `BL-20260511-32` and moved to `## Done` with a resolution note; the canonical `BL-20260511-01` (spec-017) is left untouched.

## 7. Non-Functional Requirements

- **NFR-AUDIT-1**: Not applicable — no agent/LLM path is touched.
- **NFR-HITL-1**: Not applicable — no ingestion or high-stakes path is touched.
- **NFR-SAFETY-1**: No `BACKLOG.md` history is deleted — entries are moved/renumbered, never removed (`backlog_lint`'s subset check stays green).
- **NFR-CI-1**: The new CI job is dependency-light (`pip install pytest` only — no Docker, Neo4j, or node_modules), consistent with the `tests/conftest.py` smoke+specs contract.

## 8. API Surface

None.

## 9. Agent / Crew Impact

None.

## 10. Acceptance Criteria

- **AC-1**: `python3 scripts/backlog_lint.py` exits 0 (no duplicate ids; no removed entries).
- **AC-2**: A case-sensitive scan of all `*.md` reports 0 case-only link mismatches (the 7 AO-SDLC links resolve).
- **AC-3**: `pytest tests/ -m "not backend and not frontend"` is green when run in a Linux/case-sensitive environment (verified in the backend container via the `/repo` mount), including the new `test_no_case_mismatched_doc_links`.
- **AC-4**: `python3 scripts/spec_validator.py` reports `PASS specs/021-fix-ao-sdlc-doc-links`.
- **AC-5**: `.github/workflows/ci.yml` defines a job that runs the root structural tier, so FR-3/FR-4 are gated in CI.

## 11. LegalBench Impact

- Tasks affected: none.
- Expected delta: 0 pp (no reasoning logic changed).

## 12. Risks & Open Questions

- **R-1**: A broad link checker could fail on the ~120 historical `backend/app/*` references. *Mitigation*: FR-3 flags **case-only** mismatches (target exists under a different case); genuinely-moved files have no case variant and are ignored. Verified: 7 before, 0 after.
- **R-2**: Editing two shipped spec-011 files. *Mitigation*: changes are mechanical link-case repairs only — no decision/content is altered.

## 13. Out of Scope / Follow-ups

- BL-20260602-01 — fix non-case broken links in current docs (e.g. `docs/constitution.md` → `AGENTS.md` should be `../AGENTS.md`).
- BL-20260602-02 — update or historically-annotate the ~120 `backend/app/*` references in specs 011 / ADR 0001, then promote FR-3 to a full relative-link existence check.
