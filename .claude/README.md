# `.claude/` — Claude Code configuration for Law AI

Claude Code is a sanctioned dev-time surface for this repo ([AGENTS.md](../AGENTS.md) § "Development orchestration"). This directory configures the harness so every session inherits the repo's **Docker-first** guardrails and the fleet's **spec-driven** loop. It does **not** change the product-runtime LLM policy: that is the ordered provider chain in `LLM_PROVIDER_CHAIN` ([docs/constitution.md](../docs/constitution.md) §1). Which AI edits this repo's code is independent of which LLM serves end users.

## The spec-driven loop is a plugin, not a copy

Since 2026-10-25 the AO-SDLC chain lives in the fleet hub as the `spec-driven` Claude Code plugin ([bamr87/bamr87 templates/spec-driven](https://github.com/bamr87/bamr87/tree/main/templates/spec-driven); operating guide [bamr87/bamr87 docs/SPEC-DRIVEN.md](https://github.com/bamr87/bamr87/blob/main/docs/SPEC-DRIVEN.md); how it maps onto this repo: [docs/spec-driven.md](../docs/spec-driven.md)). [`settings.json`](settings.json) enables it (`extraKnownMarketplaces.bamr87` + `enabledPlugins["spec-driven@bamr87"]`), and Claude Code loads it once you trust the workspace. It provides:

| From the plugin | What it does |
|---|---|
| `/spec-driven:specify`, `:clarify`, `:plan`, `:tasks`, `:implement` | the chain, one step per command |
| `/spec-driven:evolve` | the autopilot (user-invoked only; halts on every stop condition that needs a human) |
| `@agent-spec-driven:backlog-triager` | verifies open `BL-*` items against the code and proposes a reconciliation; read-only |
| PostToolUse hook on `Write`/`Edit` | after any edit to `BACKLOG.md` or `specs/`, runs the spec validator and backlog lint from the plugin's own tools and blocks on failure, so the §11 gates stay green |

Nothing from the plugin is vendored here. Outside Claude Code, `tools/fleet-kit.sh` resolves the same tools for `make lint-specs`, and CI runs them by reference through the hub's reusable `spec-gate.yml`.

## Layout (what stays repo-specific)

| Path | What it does |
|------|--------------|
| [`settings.json`](settings.json) | Enables the plugin. `permissions.deny` blocks host-level `pytest`/`ruff`/`mypy`/`black`/`pip install`/`npm install`/`python manage.py` and the obvious bypass spellings (`python -m pytest`, `poetry run`, `npm run test`, `npx`) — Docker-first enforcement. Wires the SessionStart hook. |
| [`hooks/session-start.sh`](hooks/session-start.sh) | `SessionStart` — injects a short operational reminder (Docker-first rules, sanctioned host commands, the pre-PR gates, the plugin commands) and reports tool availability, including whether the hub kit resolves. |
| [`commands/`](commands) | Repo-specific commands: `/new-agent` (scaffold a Law AI agent with the `run()` contract, Pydantic output, provenance and a test), `/implement-feature` (the feature checklist across backend, agent, graph, frontend and eval), `/ux-review` (one UI/UX review pass). |
| [`agents/constitution-reviewer.md`](agents/constitution-reviewer.md) | Read-only subagent that audits a diff against the constitution gates (provenance, grounding, HITL, graph invariants, Docker-first, the §11 loop). |
| [`skills/run-law-ai/`](skills/run-law-ai) | Build/run/smoke-test the app via the committed `driver.sh` (daphne + SQLite, no heavy deps). |
| [`skills/ux-review/`](skills/ux-review) | The UI/UX review loop: score the rubric, fix the worst finding, promote the fix into the gate. |

## Notes

- **Permissions are restrictive only.** `settings.json` intentionally ships no `allow` wildcards, so it never auto-approves command categories. If you want fewer prompts for `make`/`git`/`docker compose`, add your own `allow` rules via `/permissions` (they land in `.claude/settings.local.json`, which is gitignored).
- **Hooks and plugins apply to future sessions.** Claude Code loads `.claude/settings.json` at session start; a session that begins before a change won't pick it up until reload (`/hooks`, `/plugin`) or restart. A repo-declared marketplace is only honoured after you accept the workspace trust dialog.
- **Canonical guide precedence:** [AGENTS.md](../AGENTS.md) is the source of truth; nothing here duplicates its standards.
