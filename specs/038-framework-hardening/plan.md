# Plan: AO-SDLC Framework Hardening (gitorio backport)

> Companion to `spec.md`. Describes **how** we will satisfy the requirements.

## 1. Architecture Overview

Straight backport of the reviewed-and-regression-proven gitorio fixes onto the originals here, file by file, preserving law-ai-specific behavior (the extra coverage/LegalBench scanners in `evolve_audit.py` are kept and gain provenance tails; the Docker-first docstrings stay).

## 2. Component Changes

| Layer | File / Module | Change |
|-------|---------------|--------|
| Gates | `scripts/spec_validator.py` | FR-1: template-identical exemption, `PRE_TASKS_STATUSES`, loud bad-target failures, module-level `_rel` |
| Gates | `scripts/backlog_lint.py` + `.github/workflows/ci.yml` spec-gate | FR-2: `BACKLOG_LINT_BASE` env, CI passes `HEAD^1`, honest comments |
| Discovery | `scripts/evolve_audit.py` | FR-3: `'. '` dedup split, heading-line insert anchor + EOF guard, `surfaced` field on all four scanners |
| Automation | `.github/workflows/evolve.yml` | FR-4: `set -o pipefail`, heredoc capture of the `audit` output |
| Hooks | `.claude/hooks/gate-check.sh` | FR-5: `CLAUDE_PROJECT_DIR` root anchor, in-repo-only path filter |
| Tooling | `scripts/next_backlog_id.py`, `scripts/pick_backlog_item.py`, `tests/test_backlog_picker.py` | FR-6: promoted from `.claude/worktrees/cranky-burnell-fd2782/` |

## 3. Data & Schema Migrations

None.

## 4. Tech Choices & Alternatives

| Decision | Chosen | Alternatives Considered | Why |
|----------|--------|-------------------------|-----|
| Backport form | Port gitorio's exact fixes | Re-derive independently | The fixes carry an adversarial review + scratch-repo reproductions; re-deriving re-risks them |
| CI base ref | `HEAD^1` via env | `github.event.pull_request.base.sha \|\| github.event.before` | `HEAD^1` covers push and PR merge commits with `fetch-depth: 2` and no zero-SHA edge cases |
| evolve.yml kill switch | NOT backported | Match gitorio's default-OFF gate | Would silently idle live weekly automation; explicitly a maintainer decision (spec §14) |

No constitution deviation; no ADR needed.

## 5. Provenance & Audit Hook-up

No LLM/tool-call paths change. The audit's generated bullets now carry `_Surfaced in:_` tails, *improving* backlog provenance.

## 6. HITL Gates

Unchanged, and strengthened where it counts: the append-only guarantee (constitution §11's audit-trail promise) is now actually enforced in CI, not only in local hooks.

## 7. Test Strategy

Function-level harness checks (dedup key, render, insert anchoring against a synthetic backlog with a prose `## Open` mention), lifecycle checks (template copy validates at `draft`/`clarified`; modified-with-placeholder fails), a scratch-repo committed-deletion reproduction for the base-ref fix, `py_compile` over all touched scripts, and the promoted `tests/test_backlog_picker.py` running under CI's pytest (Docker-first: not run on host).

## 8. Rollout

Pure gate mechanics — no runtime behavior change to any workflow except that failures now surface (pipefail) and the weekly PR body gains its intended log. `make lint-specs` CLI unchanged.

## 9. Risks & Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Stage-aware gating hides missing coverage pre-/tasks | low | low | drift check still forces `shipped` truth; `/tasks` bumps status into the enforced zone |
| `HEAD^1` absent on first commit / shallow clones | low | low | existing `CalledProcessError → None` fallback skips the diff gracefully |

## 10. Estimated Effort

One backport session (done).
