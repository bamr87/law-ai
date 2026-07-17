# `.claude/` — Claude Code configuration for Law AI

Claude Code is a sanctioned dev-time surface for this repo (see [AGENTS.md](../AGENTS.md) § "Development Orchestration" and [CLAUDE.md](../CLAUDE.md)). This directory configures the Claude Code harness so every session inherits the repo's **Docker-first, spec-driven** guardrails. It does **not** change the product runtime — the deployed app's LLM stays Ollama (local-first) per constitution §1.

## Layout

| Path | What it does |
|------|--------------|
| [`settings.json`](settings.json) | Project settings. `permissions.deny` blocks host-level `pytest`/`ruff`/`mypy`/`black`/`pip install`/`npm install`/`python manage.py` (Docker-first enforcement). Wires the two hooks below. |
| [`hooks/session-start.sh`](hooks/session-start.sh) | `SessionStart` — injects a short operational reminder (Docker-first rules, sanctioned host commands, the pre-PR gates, the AO-SDLC chain) and reports tool availability. |
| [`hooks/gate-check.sh`](hooks/gate-check.sh) | `PostToolUse` on `Write`/`Edit` — after any edit to `BACKLOG.md` or `specs/`, runs `spec_validator.py` + `backlog_lint.py` and feeds failures back so the §11 gates stay green. |
| [`commands/`](commands) | The AO-SDLC chain as slash commands — `/specify`, `/clarify`, `/plan`, `/tasks`, `/implement`, `/evolve`, `/new-agent`. Each is a thin pointer to the canonical prompt under [`prompts/`](../prompts) (single source of truth, shared with GitHub Copilot). |
| [`agents/`](agents) | Repo-specific subagents: `constitution-reviewer` (audits a diff against the constitution gates) and `backlog-triager` (verifies BL-* items against the code). Both read-only. |
| [`skills/run-law-ai/`](skills/run-law-ai) | Skill to build/run/smoke-test the app via the committed `driver.sh` (daphne + SQLite, no heavy deps). |

## Notes

- **Permissions are restrictive only.** `settings.json` intentionally ships no `allow`
wildcards, so it never auto-approves command categories. If you want fewer prompts for `make`/`git`/`docker compose`, add your own `allow` rules via `/permissions` (they land in `.claude/settings.local.json`, which is gitignored).
- **Hooks apply to future sessions.** Claude Code loads `.claude/settings.json` at session
start; a session that begins before this file exists won't pick it up until reload (`/hooks`) or restart.
- **Canonical guide precedence:** [AGENTS.md](../AGENTS.md) is the source of truth; the
  commands here defer to [`prompts/`](../prompts); do not duplicate standards into this dir.
