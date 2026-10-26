# Changelog

All notable changes to this project are documented in this file. The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## Unreleased

### Added

- `CHANGELOG.md`, in Keep a Changelog format.
- `LICENSE` file (MIT).
- `.github/sdlc.yml`: the repo's SDLC declaration (`modules.spec_driven: true`, `backlog.mode: file`), `tools/fleet-kit.sh` (resolves the fleet hub's spec-driven kit), `specs/_review_questions.json` (the constitution §13 review question as data), `docs/spec-driven.md`, `docs/history/`.

### Changed

- **The spec-driven SDLC loop is the fleet's, consumed by reference** (2026-10-25). The `/specify → /clarify → /plan → /tasks → /implement` chain and `/evolve` are the hub's `spec-driven` Claude Code plugin (`/spec-driven:*`, enabled in `.claude/settings.json`); CI's `Spec Drift Gate` is one `uses:` of the hub's reusable `spec-gate.yml@v2` (check context `Spec Drift Gate / Spec gate`; the ruleset was updated to match); the nightly's stale-backlog issue is the same gate's `backlog-triage` job; `make lint-specs` runs the hub's `spec_validator.py --strict` and `backlog_lint.py` through `tools/fleet-kit.sh`. See `docs/spec-driven.md`.
- `AGENTS.md` is the canonical agent file in the fleet's six-heading shape (decision D4) and absorbs what `CLAUDE.md` used to carry; `CLAUDE.md` is a pointer (`@AGENTS.md`). `README.md` leads with the three audiences the platform serves.
- Root documents moved under `docs/`: `PRD.md` → `docs/prd.md`, `Law_AI_Proposal.md` → `docs/history/2026-04-proposal.md`, `local-ai-plan.md` → `docs/history/2026-04-local-ai-plan.md`, `nextjs-scoped-app-shell-architecture.md` → `docs/app-shell-architecture.md`; `AO-SDLC_Outline_Guide.md`, `docs/ao-sdlc.md` and `docs/ao-sdlc-guide.md` are replaced by `docs/spec-driven.md` (the generic half lives in the hub's `docs/SPEC-DRIVEN.md`). Links in `specs/` were rewritten.
- `ci.yml`: the UI shell audit (`scripts/ux_audit.py`) runs as its own `UI/UX Shell Contract` job; every job transitively needs the spec gate.

### Removed

- `prompts/`, `scripts/spec_validator.py`, `scripts/backlog_lint.py`, `scripts/next_backlog_id.py`, `scripts/pick_backlog_item.py`, `scripts/evolve_audit.py`, `.claude/commands/{specify,clarify,plan,tasks,implement,evolve}.md`, `.claude/hooks/gate-check.sh`, `.claude/agents/backlog-triager.md`: all now in the hub kit.
- `.github/workflows/evolve.yml` (superseded by the hub's `repo-evolution.yml`, opt-in via the registry), the three GitFactory lines `factory--{backlog-triage,evolve-pilot,issue-concierge}.yml` with `.factory/`, and the Copilot prompt files `advance-open-work` and `ship-open-changes`.
- **The test pillar** ([ADR 0008](docs/adr/0008-retire-test-pillar.md), 2026-10-26): the `TestSynthesizer` crew and prompt, the `test_pillar` autonomy kind, the `autonomy-nightly-tests` beat entry, `law_ai.eval.coverage_audit`, `GET /api/agents/proposed-tests`, `GET /api/agents/autonomy/lowest-coverage`, `backend/tests/autonomy/proposed/`, the `ProposedTestReview` component and the lowest-coverage panel, and the nightly's synthesis step. Constitution §12 I5 is retired; `run_autonomy` defaults to `digest`.
- The `governance-triage` Celery beat job (`law_ai.core.governance`, `law_ai.core.tasks.governance_triage`, the `GOVERNANCE_TRIAGE_GITHUB_*` settings and `.env.example` keys): product code that shelled out to the repo's dev scripts from a bind-mounted checkout. Its tests and the root tests of the removed scripts went with it.

## History

No versions have been tagged yet. The project started on 2026-05-03 and has 177 commits on `main`. The most recent changes:

- 2026-10-16: test(lsat): make the tutor no-trace test set telemetry off instead of assuming it ([#164](https://github.com/bamr87/law-ai/pull/164))
- 2026-10-16: fix(neo4j): give each event loop its own driver instead of sharing one across loops ([#166](https://github.com/bamr87/law-ai/pull/166))
- 2026-10-14: ci: pause schedules while Actions billing is blocked (bamr87/bamr87#268) ([#163](https://github.com/bamr87/law-ai/pull/163))
- 2026-10-07: chore(deps): bump the frontend-npm group across 1 directory with 23 updates ([#158](https://github.com/bamr87/law-ai/pull/158))
- 2026-10-07: chore(deps): bump next from 16.3.6 to 16.3.8 in /frontend ([#156](https://github.com/bamr87/law-ai/pull/156))
- 2026-10-07: chore(deps): bump next from 16.3.6 to 16.3.8 in /lsat-static ([#154](https://github.com/bamr87/law-ai/pull/154))
- 2026-10-07: feat(lsat-static): export Spec 053 playbooks + wire SolveAssist (#126) ([#127](https://github.com/bamr87/law-ai/pull/127))
- 2026-10-07: chore(deps): hold eslint at 9.x until eslint-plugin-react supports ESLint 10 ([#157](https://github.com/bamr87/law-ai/pull/157))
- 2026-10-07: chore(deps): bump brace-expansion in /lsat-static ([#141](https://github.com/bamr87/law-ai/pull/141))
- 2026-10-07: chore(deps): bump source-map-js from 1.2.1 to 1.2.2 in /frontend ([#150](https://github.com/bamr87/law-ai/pull/150))
- 2026-10-07: chore(deps): bump sharp from 0.35.4 to 0.35.5 in /frontend ([#151](https://github.com/bamr87/law-ai/pull/151))
- 2026-10-07: chore(deps): bump sharp from 0.35.4 to 0.35.5 in /lsat-static ([#152](https://github.com/bamr87/law-ai/pull/152))
- …and 93 earlier changes.

The full record is in the [commit history](https://github.com/bamr87/law-ai/commits/main) and the [merged pull requests](https://github.com/bamr87/law-ai/pulls?q=is%3Apr+is%3Amerged).
