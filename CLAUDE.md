<!-- kit: sdlc v0.1.0 · pointer only (decision D4, UPS-AGENT-08). The rules live in AGENTS.md. -->
# Law AI

The canonical agent instructions for this repo are in [AGENTS.md](AGENTS.md). Claude Code loads them through the import below; add nothing else here.

The spec-driven chain (`/spec-driven:specify` → `:clarify` → `:plan` → `:tasks` → `:implement`, `/spec-driven:evolve`) is the fleet hub's plugin, enabled in `.claude/settings.json`; [docs/spec-driven.md](docs/spec-driven.md) maps it onto this repo.

@AGENTS.md
