# The spec-driven loop in Law AI

Law AI runs the fleet's spec-driven SDLC loop (AO-SDLC) **by reference**. The machinery — the `/specify → /clarify → /plan → /tasks → /implement` chain, the `/evolve` autopilot, the spec and backlog gates, the discovery audit — lives in the bamr87 fleet hub as the `spec-driven` kit ([bamr87/bamr87 templates/spec-driven](https://github.com/bamr87/bamr87/tree/main/templates/spec-driven); operating guide: [bamr87/bamr87 docs/SPEC-DRIVEN.md](https://github.com/bamr87/bamr87/blob/main/docs/SPEC-DRIVEN.md)). This repo carries only what is Law AI's: the specs, the backlog, the constitution, the review question, and the product gates around them. This page is the map from the fleet loop onto this repo.

It replaces the former `AO-SDLC_Outline_Guide.md` (v2.0, 2026-08-11, whose generic half is now the hub doc and whose runtime half lives in [architecture.md](architecture.md) and [llm-provider-chain.md](llm-provider-chain.md)) and `docs/ao-sdlc.md`. Law AI operates at **Autonomy Level 2 (Collaborative)** per [constitution.md](constitution.md) §10: agents draft, humans approve at the spec gate and the PR gate.

## What this repo keeps

| Artifact | Role | Enforced by |
|---|---|---|
| [constitution.md](constitution.md) | The non-negotiable rules a spec or PR must satisfy: mission alignment and the runtime chain (§1), the locked stack (§2), quality gates (§3), provenance (§4), HITL (§5), testing (§6), the spec workflow (§7), autonomy invariants (§10–12), jurisprudential honesty (§13) | the spec gate, the `constitution-reviewer` agent, review |
| [AGENTS.md](../AGENTS.md) | The canonical engineering guide: standards, structure, the Docker-first workflow, the dev-surface policy | convention + review; `CLAUDE.md` and `copilot-instructions.md` defer to it |
| [BACKLOG.md](../BACKLOG.md) | The append-only work register (`BL-YYYYMMDD-NN — kind, severity — text`; `## Open` / `## Claimed` / `## Done`) and the backlog of record declared in [.github/sdlc.yml](../.github/sdlc.yml) | `backlog_lint.py` (format, unique ids, append-only against the previous commit) |
| [specs/](../specs/) `NNN-slug/{spec,plan,tasks}.md` | One package per non-trivial change: the persistent memory CI validates and agents re-derive context from | `spec_validator.py` (every `FR`/`NFR`/`AC` covered by a task, no unresolved `OQ-N`, `shipped` means every task `[x]`, a populated `## Follow-ups Discovered`) |
| [specs/_template/](../specs/_template/) | Law AI's own spec/plan/tasks template: §2 Origin & Background with the §13 review question, a LegalBench-impact section | repo-owned since it was seeded; never overwritten by the kit |
| [specs/_review_questions.json](../specs/_review_questions.json) | Constitution §13 as data: a spec that ranks, scores or summarises legal authority must answer *who is the stronger here, and what does this feature do for them?* in §2 | the validator warns; `--strict` (which `make lint-specs` and CI pass) fails |

## How the loop runs here

| Surface | How |
|---|---|
| **Claude Code** | The `spec-driven@bamr87` plugin, enabled in [.claude/settings.json](../.claude/settings.json) from the hub's marketplace. Commands: `/spec-driven:specify <BL-id or intent>` → `:clarify <slug>` → `:plan` → `:tasks` → `:implement T-NNN`; `/spec-driven:evolve` for one autonomous cycle (user-invoked only; halts on licensing, a new data source, a model swap, a data-dropping migration, an HITL-gate change, or a constitution amendment). `@agent-spec-driven:backlog-triager` reconciles `BACKLOG.md` against the code. The plugin's PostToolUse hook runs both gates after every edit to `BACKLOG.md` or `specs/`. Repo-specific commands stay in [.claude/commands/](../.claude/commands/): `/new-agent`, `/implement-feature`, `/ux-review`. |
| **Local gate** | `make lint-specs`: [tools/fleet-kit.sh](../tools/fleet-kit.sh) resolves the kit (the parent hub checkout at `../..` when this repo is checked out inside the hub as a submodule, else a cached sparse clone under `.fleet/`, gitignored; `make fleet-kit` refreshes it), then runs `spec_validator.py --root . --strict`, `backlog_lint.py --root .` and this repo's own `scripts/ux_audit.py`. Mint a backlog id with `python3 "$(tools/fleet-kit.sh)/tools/next_backlog_id.py" --root .`. |
| **CI** | The `Spec Drift Gate` job in [ci.yml](../.github/workflows/ci.yml) is one `uses:` of the hub's reusable `spec-gate.yml@v2`; every other job `needs:` it. The `UI/UX Shell Contract` job runs `scripts/ux_audit.py` beside it. |
| **Nightly** | [nightly-tests.yml](../.github/workflows/nightly-tests.yml) runs the kit's validators through the resolver, the discovery audit (`evolve_audit.py`: TODO/FIXME scan, docs `AGENTS.md` names that are missing, a coverage shortfall from `backend/coverage.xml`) whose new `BL-*` items ride the nightly draft PR, and — on the schedule only — the `backlog-triage` job: the same reusable gate with `stale-report` + `file-issue`, keeping one idempotent `backlog-triage` issue for `## Open` items older than 60 days or an inconsistent spec. |
| **GitHub Copilot** | Sanctioned for completions, chat, code review and the cloud coding agent. It cannot load a Claude Code plugin: when driving a spec by hand, follow this page and the hub's skill text ([templates/spec-driven/skills/](https://github.com/bamr87/bamr87/tree/main/templates/spec-driven/skills)); `make lint-specs` and CI enforce the same gates whichever surface wrote the files. |

## Law AI's own gates around the loop

Every `/spec-driven:implement` cycle ends green on, in Docker via `make`: `make lint` (ruff, black, eslint), `make typecheck` (mypy `--strict` behind the ratchet in `scripts/mypy_ratchet.py`, tsc), `make test` (backend pytest with its coverage floor, frontend vitest), plus `make lint-specs`. Reasoning changes add `make test-legalbench` (the scored, gated run is weekly in the nightly; a PR labelled `reasoning-change` verifies the harness itself); anything a user could see ships screenshots (the **Visual Evidence Gate**, [ui-ux-review.md](ui-ux-review.md)); frontend changes run the axe-core smoke. The constitution §11 loop closes the cycle: `tasks.md` ends with a populated `## Follow-ups Discovered`, each item is mirrored into `BACKLOG.md`, and the PR body copies the new bullets so a reviewer sees what the next cycle inherits.

## Which checks block a merge

Running a gate and *enforcing* it are different things. `markdown-oneline` went red on `main` when #73 merged and stayed red across four stacked PRs before anyone noticed, because nothing blocked a merge on a failing check (`BL-20260815-01`). The enforcement lives in a **repository ruleset**, versioned at [.github/rulesets/main-required-checks.json](../.github/rulesets/main-required-checks.json) so it is reviewable in a diff. It targets the default branch and requires four contexts:

| Required context | Produced by |
|---|---|
| `Spec Drift Gate / Spec gate` | [ci.yml](../.github/workflows/ci.yml) job `spec-gate` — a reusable-workflow call, so GitHub names the context `<caller job name> / <called job name>` |
| `Backend Lint + Type-check` | ci.yml job `backend-lint` |
| `Backend Tests + Coverage` | ci.yml job `backend-test` |
| `oneline` | [markdown-oneline.yml](../.github/workflows/markdown-oneline.yml) job `oneline` (no `name:`, so the job id is the context) |

Two things to know: **a skipped job satisfies a required check** (the `changes` job path-filters the backend jobs, so a docs-only PR reports `skipped` and merges), and **a check context is the job's `name:`, falling back to its job id** — renaming a job, here or in the hub's reusable workflow, silently orphans the protection, which is why `tests/test_configs.py::test_required_status_checks_match_real_jobs` pins the two together.

Applying or updating the ruleset is a repo-settings write a maintainer does deliberately:

```bash
gh api -X POST repos/{owner}/{repo}/rulesets --input .github/rulesets/main-required-checks.json
# already applied? update in place with the ruleset id:
gh api repos/{owner}/{repo}/rulesets --jq '.[] | "\(.id) \(.name)"'
gh api -X PUT repos/{owner}/{repo}/rulesets/<id> --input .github/rulesets/main-required-checks.json
```

The repo-admin role keeps an `always` bypass so bot PRs can still be merged by the owner when a path-filtered check never reports.

## Smoke-testing the nightly locally

Scheduled workflows are awkward to iterate on. [nightly-tests.yml](../.github/workflows/nightly-tests.yml) takes a `dry_run` input that skips every Docker-heavy step (coverage, LegalBench, e2e, the live-model slice) while still running the spec/backlog gates and the discovery audit:

```bash
gh workflow run nightly-tests.yml -f dry_run=true    # on the real runner
make nightly-dry-run                                 # locally, via nektos/act
```

`make nightly-dry-run` needs [act](https://github.com/nektos/act) on the host (`brew install act`) — the one sanctioned exception to the Docker-first `make` rule, because act *is* the Docker runner. Defaults live in [.actrc](../.actrc). act sets `ACT=true` and the "Open draft PR" step is guarded by `!env.ACT`, so a local run never pushes a branch; the `backlog-triage` job is schedule-only and never files an issue from a dispatch (`BL-20260511-18`). Inside the act container the resolver has no parent hub, so it sparse-clones the kit — the run needs network for that one step.

## What was retired on 2026-10-25

Moved into the hub and deleted here: `prompts/` (the chain, now the plugin's skills), `scripts/spec_validator.py`, `backlog_lint.py`, `next_backlog_id.py`, `pick_backlog_item.py` and `evolve_audit.py` (the kit's `tools/`), `.claude/commands/{specify,…,evolve}.md`, `.claude/hooks/gate-check.sh` and `.claude/agents/backlog-triager.md` (the plugin), `.github/workflows/evolve.yml` (the weekly audit — superseded by the hub's `repo-evolution.yml`, which a repo opts into with `auto_evolve: true` in the hub registry, and by `repo-scout.yml` + the issue pipeline for issues), the three GitFactory lines `factory--{backlog-triage,evolve-pilot,issue-concierge}.yml` with their `.factory/` blueprints (their jobs are the hub's loops: the issue pipeline's intake, the scout, repo-evolution), the Copilot prompt files `advance-open-work` and `ship-open-changes`, and the backend's `governance-triage` Celery beat job (`law_ai.core.governance`), which shelled out to the repo's scripts from a bind-mounted checkout — product code running the dev harness. The repo's own tests of those copies (`tests/test_specs_and_backlog.py`, `test_backlog_picker.py`, `test_evolve_audit.py`) went with them; the kit tests itself. Spec 037 (GitFactory orchestration) and 038 (framework hardening) remain the historical record of the lines as they ran here.

On 2026-10-26 the **test pillar** followed ([ADR 0008](adr/0008-retire-test-pillar.md)): the `TestSynthesizer` crew that proposed pytest files for this repo's own thinnest modules, its `proposed-tests` and `lowest-coverage` API views, the `ProposedTestReview` queue and the coverage panel in the frontend, the `autonomy-nightly-tests` beat entry, and the nightly's synthesis step. Proposing changes to the codebase is the hub's evolution loop's job; the product's autonomy loop keeps corpus growth, the digest and the LSAT content pillars.

## What is intentionally not built

- A roadmap-agent crew (phase 0 automation); the PRD is [prd.md](prd.md).
- An SRE feedback loop (production incident → auto-issue → coding agent). `law_ai.core.provenance` and the Phoenix/OpenTelemetry tracing (the `local-ai` extra) are the substrate.
- Multi-agent debate via AutoGen.
- An AI-augmented review job in CI. Nothing in the constitution blocks it since the 2026-08-11 runtime amendment (spec 034).

Each lands via its own spec under `specs/`, and promotion to Autonomy Level 3 is a constitution amendment (§10), not a flag.
