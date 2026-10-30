# Tasks: AO-SDLC Framework Hardening (gitorio backport)

> Each task must reference one or more `FR-*` / `NFR-*` / `AC-*` IDs from `spec.md`. CI's `spec_validator.py` enforces that every requirement in `spec.md` is referenced by at least one task.

## Conventions

- Status: `[ ]` todo / `[~]` in-progress / `[x]` done.

---

## T-001 — Harden spec_validator.py

- **Refs**: FR-1, NFR-AUDIT-1, AC-1
- **Owner**: @bamr87
- **Status**: `[x]`
- **Files**: `scripts/spec_validator.py`
- **Verify**: template copy validates at `draft` and `clarified`; `specs/999-nope` target exits 1 with a `FAIL … not a valid spec directory` line; all 37 specs PASS.

## T-002 — CI-effective append-only backlog lint

- **Refs**: FR-2, NFR-SEC-1, AC-2
- **Owner**: @bamr87
- **Status**: `[x]`
- **Files**: `scripts/backlog_lint.py`, `.github/workflows/ci.yml`
- **Verify**: scratch-repo reproduction — committed deletion passes with default base, fails with `BACKLOG_LINT_BASE=HEAD^1` (run during the gitorio review; base-ref plumbing identical here).

## T-003 — evolve_audit dedup / insert / provenance

- **Refs**: FR-3, AC-3
- **Owner**: @bamr87
- **Status**: `[x]`
- **Files**: `scripts/evolve_audit.py`
- **Verify**: harness asserts render includes `_Surfaced in:_`, dedup key retains `.ts`, and insertion lands after the real `## Open` heading despite an earlier prose mention.

## T-004 — evolve.yml pipefail + real audit output

- **Refs**: FR-4
- **Owner**: @bamr87
- **Status**: `[x]`
- **Files**: `.github/workflows/evolve.yml`
- **Verify**: YAML parses; the `audit` heredoc writes to `$GITHUB_OUTPUT` before the `changed` flag.

## T-005 — cwd-safe gate hook

- **Refs**: FR-5
- **Owner**: @bamr87
- **Status**: `[x]`
- **Files**: `.claude/hooks/gate-check.sh`
- **Verify**: a sibling-repo `specs/` path exits 0 silently under `CLAUDE_PROJECT_DIR=/Users/bamr87/github/law-ai`.

## T-006 — Promote picker + id-minter + test to main

- **Refs**: FR-6, AC-4
- **Owner**: @bamr87
- **Status**: `[x]`
- **Files**: `scripts/next_backlog_id.py`, `scripts/pick_backlog_item.py`, `tests/test_backlog_picker.py`
- **Verify**: both scripts run (`BL-20260818-01` minted; picker returns the top open item as JSON); `py_compile` clean; pytest runs in CI (Docker-first — not run on host).

---

## Done-When (Definition of Done)

- All tasks `[x]`.
- All `AC-*` from `spec.md` verified.
- `make lint && make test` green on the PR (CI; gate mechanics only).
- LegalBench delta: n/a (spec §11).
- **`## Follow-ups Discovered` section below populated.**

---

## Follow-ups Discovered

> Append-only. Mirror each item into [BACKLOG.md](../../BACKLOG.md) with a `BL-YYYYMMDD-NN` id. CI (`scripts/spec_validator.py`) checks this section exists. CI (`scripts/backlog_lint.py`) checks the BACKLOG mirror.

- BL-20260818-02 — infra, low — Maintainer decision: default-OFF kill-switch gate on evolve.yml (gitorio's `*_ENABLED` convention) — deliberately NOT backported because it would silently idle live weekly automation.
- BL-20260818-03 — tech-debt, low — Retire the stale `.claude/worktrees/cranky-burnell-fd2782/` worktree now that its scripts/tests/skills are promoted or superseded (the asdlc-* SKILL.md variants remain unique to it).
