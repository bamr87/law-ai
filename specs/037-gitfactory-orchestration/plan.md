# Plan: GitFactory-Managed Agentic Orchestration

> Companion to `spec.md`. Describes **how** we will satisfy the requirements.

## 1. Architecture Overview

GitFactory (sibling repo `gitorio`) is the compiler: each line is a standalone blueprint under `.factory/`, compiled by `gitorio/app/scripts/gen-aosdlc-factory.ts` into `.github/workflows/factory--*.yml`. law-ai owns the blueprints, the operating prompts, and the kill-switch variables; gitorio owns the compiler and template. Regeneration after a blueprint change: `cd ../gitorio/app && npx vite-node scripts/gen-aosdlc-factory.ts ../../law-ai`.

## 2. Component Changes

| Layer | File / Module | Change |
|-------|---------------|--------|
| Orchestration | `.factory/{evolve-pilot,backlog-triage,issue-concierge}.blueprint.json` | new — source of truth per line |
| Orchestration | `.factory/prompts/{evolve-pilot,backlog-triage,issue-concierge}.md` | new — hand-authored operating prompts |
| CI/CD | `.github/workflows/factory--*.yml` | new — GENERATED, never hand-edited |
| Governance | `BACKLOG.md`, this spec | BL-20260817-06 claimed |

## 3. Data & Schema Migrations

None.

## 4. Tech Choices & Alternatives

| Decision | Chosen | Alternatives Considered | Why |
|----------|--------|-------------------------|-----|
| Agent runtime | `anthropics/claude-code-action@v1` (compiled) | Bare `@anthropic-ai/claude-code` runner | Sanctioned surface; matches `claude.yml` auth; grants computed, not hand-rolled |
| Line ownership | Blueprints live here, compiler lives in gitorio | Hand-authored YAML | Drift detection via header hash; least privilege for free; constitution-friendly HITL defaults |
| Gate posture | Default-OFF repo variables per line | Enabled-on-merge | A merged workflow must be inert until a human arms it |

No constitution §2 deviation — no new runtime dependency enters the product; no ADR needed.

## 5. Provenance & Audit Hook-up

No product LLM paths change (`core.provenance` untouched). Operational provenance: Actions run logs + the `GENERATED` header hash + the concierge comment marker.

## 6. HITL Gates

Three explicit gates: (1) each line's `*_ENABLED` variable is unset ⇒ the gate job idles the line; (2) pilot/triage output is a PR a human merges; (3) prompts embed the constitution stop conditions, converting hard questions into reports instead of actions.

## 7. Test Strategy

- Compiler side (gitorio): catalog invariant test compiles the template with zero error diagnostics; generator run verified by fragment greps (gate/guard/grants).
- law-ai side: `make lint-specs` equivalents — `scripts/spec_validator.py` + `scripts/backlog_lint.py` — plus `markdown-oneline` CI on the new prose.

## 8. Rollout

Ships default-OFF (no behavior change on merge). Arming order: `ISSUE_CONCIERGE_ENABLED` first (lowest blast radius), then `BACKLOG_TRIAGE_ENABLED`, then `EVOLVE_PILOT_ENABLED`; observe first runs before widening. Disarm = flip the variable back; no redeploy.

## 9. Risks & Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Pilot guesses on a needs-human item | med | med | Stop conditions in prompt; PR-only; rate limit 1/day; default-OFF |
| Concierge mislabels / double-comments | med | low | Existing-labels-only rule; `<!-- factory-concierge -->` dedup marker; bot guard prevents self-retrigger |
| Hand-edits to generated YAML | low | med | `GENERATED` header + hash; gitorio drift banner; this plan documents the regen command |

## 10. Estimated Effort

Done in one cross-repo session (gitorio specs/002 + this package).
