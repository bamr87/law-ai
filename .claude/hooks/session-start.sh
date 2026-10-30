#!/usr/bin/env bash
# SessionStart hook — orient any Claude Code session to Law AI's Docker-first
# workflow and the fleet's spec-driven loop. Injects a short operational
# reminder as additionalContext and reports tool availability. Never fails
# the session.
set +e

branch="$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo unknown)"
have() { command -v "$1" >/dev/null 2>&1 && echo yes || echo no; }
# `timeout` is GNU coreutils — absent on stock macOS, which made this check
# always report the daemon as down there. Use it only when available.
docker_up="no"
if command -v docker >/dev/null 2>&1; then
  if command -v timeout >/dev/null 2>&1; then
    timeout 8 docker info >/dev/null 2>&1 && docker_up="yes"
  else
    docker info >/dev/null 2>&1 && docker_up="yes"
  fi
fi
# The hub's spec-driven kit: a parent hub checkout when this repo sits inside
# bamr87/bamr87 as a submodule, else a cached sparse clone under .fleet/.
kit="$(tools/fleet-kit.sh 2>/dev/null || echo unresolved)"

read -r -d '' CTX <<EOT
Law AI operational reminder (branch: ${branch}).
- Docker-first: run every dev/test/lint/typecheck/eval command via 'make' (which wraps 'docker compose run --rm'). Never run pytest / ruff / mypy / black / pip install / npm install / python manage.py on the host.
- Sanctioned host commands: make, docker compose, git, gh, tools/fleet-kit.sh (resolves the hub's stdlib spec/backlog gates), 'python3 scripts/ux_audit.py'.
- Gates before any PR: 'make lint', 'make typecheck', 'make test', 'make lint-specs'. Close the constitution §11 loop: tasks.md '## Follow-ups Discovered' + mirror each into BACKLOG.md as BL-YYYYMMDD-NN + copy the new bullets into the PR body.
- Spec-driven chain: the fleet's spec-driven plugin (enabled in .claude/settings.json): /spec-driven:specify -> :clarify -> :plan -> :tasks -> :implement ; /spec-driven:evolve for an autonomous cycle. docs/spec-driven.md maps it onto this repo; AGENTS.md is canonical.
- Tool check: docker=$(have docker) (daemon ${docker_up}) make=$(have make) python3=$(have python3) gh=$(have gh) hub-kit=${kit}. If the docker daemon is down, host-only work is limited to git + the spec gate.
EOT

python3 - "$CTX" <<'PY' 2>/dev/null || printf '{}'
import json, sys
print(json.dumps({"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": sys.argv[1]}}))
PY
