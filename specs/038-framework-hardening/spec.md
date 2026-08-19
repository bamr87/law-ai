# Spec: AO-SDLC Framework Hardening (gitorio backport)

- **ID**: 038-framework-hardening
- **Status**: shipped
- **Owner**: @bamr87
- **Created**: 2026-08-18
- **Roadmap Epic**: constitution §11 — keep the self-evolution gates trustworthy
- **Constitution Compliance**: confirmed against [docs/constitution.md](../../docs/constitution.md)

## 1. Problem & Motivation

When gitorio adopted this repo's AO-SDLC framework (its ADR-022), a five-lens adversarial review of the port confirmed defects that exist verbatim in the originals here: the template-placeholder gate makes the documented `/specify` → `/clarify` → `/plan` lifecycle unable to validate (fresh template copies always fail, and the PostToolUse hook blocks on it); the append-only backlog check is a self-comparison no-op in CI (the checked-out worktree IS `HEAD` — the ci.yml comment even claims a `HEAD~1` comparison that never happens); `evolve_audit`'s dedup key truncates at the first `.` inside every file-extension, so the weekly audit re-appends the same findings with fresh ids forever; `evolve.yml` interpolates a step output (`steps.audit.outputs.audit`) that is never set and its `tee` masks audit crashes; the gate hook derives the repo root from the shell cwd (breaks cross-repo sessions); and the deterministic picker/id-minter scripts the skills reference live only in a stale worktree, not on main.

## 2. Origin & Background

- Backlog items claimed: BL-20260818-01 (moved to `## Claimed`, annotated `claimed-by:specs/038-framework-hardening`).
- Upstream provenance: gitorio ADR-022's adversarial verification (16 confirmed findings; the subset that applies here) and gitorio ADR-024's cross-repo hook incident.

## 3. Goals

- G1: Every gate enforces what its documentation claims, in CI and locally.
- G2: The `/evolve` tooling referenced by skills exists on main.

## 4. Non-Goals

- NG1: A default-OFF kill switch on `evolve.yml` (gitorio's convention) — that would silently idle live weekly automation; left as an explicit maintainer decision (follow-up below).
- NG2: Any product-code change.

## 5. User Stories

- As a maintainer, I want a committed deletion of a BACKLOG entry to fail CI, so the append-only audit trail is machine-guaranteed, not aspirational.
- As an agent running `/specify`, I want the validator to pass at every documented intermediate stage, so the hook teaches instead of deadlocks.

## 6. Functional Requirements

- **FR-1**: `spec_validator.py` exempts files byte-identical to their `_template/` counterpart from the placeholder check and skips requirement-coverage at statuses `draft`/`clarified`/`planned`; typo'd explicit targets and misnamed `specs/` dirs fail loudly; out-of-repo targets don't crash.
- **FR-2**: `backlog_lint.py` reads `BACKLOG_LINT_BASE` (default `HEAD`); ci.yml's spec-gate sets `HEAD^1` so the append-only check bites in CI.
- **FR-3**: `evolve_audit.py` dedups on `'. '` (extension-safe), anchors insertion on the `## Open` heading line (EOF-safe), and renders `_Surfaced in:_` provenance tails.
- **FR-4**: `evolve.yml` sets pipefail and captures `audit.out` into the `audit` step output it already interpolates.
- **FR-5**: `gate-check.sh` anchors on `CLAUDE_PROJECT_DIR` and gates only files inside this repo.
- **FR-6**: `next_backlog_id.py`, `pick_backlog_item.py`, and `tests/test_backlog_picker.py` are promoted from the worktree to main.

## 7. Non-Functional Requirements

- **NFR-AUDIT-1**: No historical BACKLOG entry is touched; all changes are gate-mechanics only.
- **NFR-SEC-1**: No new dependencies, no widened permissions; scripts stay stdlib-only host-sanctioned.

## 8. Data Model Impact

None.

## 9. API Surface

None.

## 10. Agent / Crew Impact

None to `agents_runtime`. The `/specify`–`/evolve` chain and the asdlc skills gain working preconditions (validator passes at documented stages; the picker they reference exists).

## 11. LegalBench Impact

- Tasks affected: none.
- Expected delta: 0 pp.

## 12. Acceptance Criteria

- **AC-1**: A fresh `cp -r specs/_template specs/NNN-x` with only spec.md's title/status filled validates at `draft` and `clarified`; a *modified* file retaining a placeholder still fails.
- **AC-2**: In a scratch repo, a committed BACKLOG deletion passes lint with the default base and fails with `BACKLOG_LINT_BASE=HEAD^1`.
- **AC-3**: `Candidate.render` emits the `_Surfaced in:_` tail and `_existing_titles` keeps the full path-bearing title (dedup key includes the extension).
- **AC-4**: `python3 scripts/spec_validator.py` (all 37 specs) and `python3 scripts/backlog_lint.py` exit 0.

## 13. Risks & Open Questions

- **R-1**: Stage-aware coverage could let a spec linger at `planned` with untasked requirements — mitigated: the status↔task drift check still forces `shipped` accuracy, and `/tasks` bumps to `in-progress` where coverage is enforced.

## 14. Out of Scope / Follow-ups

- Maintainer decision: adopt gitorio's default-OFF `EVOLVE_AUDIT_ENABLED`-style kill switch on `evolve.yml` (mirrored to BACKLOG below).
