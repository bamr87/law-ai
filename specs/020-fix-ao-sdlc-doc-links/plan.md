# Plan: Fix AO-SDLC Doc-Link Case Mismatch + Restore Backlog Gate

> Companion to [spec.md](spec.md). Docs + tests + CI only — no runtime code.

## 1. Architecture Overview

Three small, independent changes plus one backlog correction:

1. Correct 7 case-mismatched Markdown link hrefs to the canonical lowercase AO-SDLC doc paths.
2. Add a case-only link guard to the root structural suite and fix the latent uppercase entry in its `REQUIRED_DOCS`.
3. Wire the dependency-light root structural tier into CI so the guard (and the existing docs/specs/configs checks) actually run.
4. Renumber the duplicate backlog id so `backlog_lint` is green again.

No Mermaid diagram warranted.

## 2. Component Changes

| Layer | File / Module | Change |
|-------|---------------|--------|
| Docs | `AGENTS.md`, `docs/constitution.md`, `docs/ao-sdlc.md`, `specs/README.md`, `specs/011-django-backend/{spec,plan}.md` | uppercase `AO-SDLC[-guide].md` link hrefs → lowercase (7 occurrences) |
| Tests | `tests/test_docs.py` | `REQUIRED_DOCS`: `docs/AO-SDLC.md` → `docs/ao-sdlc.md`; add `test_no_case_mismatched_doc_links` |
| CI | `.github/workflows/ci.yml` | new `repo-structural` job: `pytest tests/ -m "not backend and not frontend"` |
| Backlog | `BACKLOG.md` | renumber orphan `BL-20260511-01` → `BL-20260511-32`, move to `## Done`; add `BL-20260602-01/02` follow-ups |

## 3. Data & Schema Migrations

None.

## 4. Tech Choices & Alternatives

| Decision | Chosen | Alternatives Considered | Why |
|----------|--------|-------------------------|-----|
| Fix direction | Lowercase the references | Rename files to uppercase | `docs/` is uniformly lowercase; minimal blast radius |
| Guard scope | Case-only mismatch detector | Full relative-link existence check | A full checker fails on ~120 historical `backend/app/*` refs; case-only isolates this bug class cleanly |
| Guard home | Root `tests/test_docs.py` | `backend/tests/` | Repo-wide docs concern belongs in the root structural suite; CI wiring (FR-4) gives it teeth |

No constitution §2 deviation; no ADR required.

## 5. Provenance & Audit Hook-up

Not applicable — no LLM/tool/DB write paths are introduced.

## 6. HITL Gates

Spec gate (this review) and PR gate per constitution §10. No ingestion/deploy gate touched.

## 7. Test Strategy

- Unit: `test_no_case_mismatched_doc_links` (new) + corrected `test_doc_exists_and_nontrivial` parametrization.
- Integration: none (no services).
- Linux verification: run `pytest tests/ -m "not backend and not frontend"` inside the backend container (case-sensitive fs, `/repo` mount) to reproduce CI behavior.
- LegalBench: n/a.

## 8. Rollout

- No flag. Effective on merge. The new CI job runs on the next push/PR.

## 9. Risks & Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Guard trips on historical moved links | med | med | case-only detection (verified 7→0) |
| New CI job flaky | low | low | dependency-light tier (pytest only), designed CI-able by conftest |

## 10. Estimated Effort

~1 agent-hour. No human pairing required beyond the spec/PR gate.
