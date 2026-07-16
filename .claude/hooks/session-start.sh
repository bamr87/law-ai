#!/usr/bin/env bash
# SessionStart hook — orient any Claude Code session to LawGraph AI's
# Docker-first, spec-driven workflow. Injects a short operational reminder as
# additionalContext and reports tool availability. Never fails the session.
set +e

branch="$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo unknown)"
have() { command -v "$1" >/dev/null 2>&1 && echo yes || echo no; }
docker_up="no"
if command -v docker >/dev/null 2>&1 && timeout 8 docker info >/dev/null 2>&1; then
  docker_up="yes"
fi

read -r -d '' CTX <<EOF
LawGraph AI operational reminder (branch: ${branch}).
- Docker-first: run every dev/test/lint/typecheck/eval command via 'make' (which wraps 'docker compose run --rm'). Never run pytest / ruff / mypy / black / pip install / npm install / python manage.py on the host.
- Sanctioned host commands: make, docker compose, git, gh, 'python3 scripts/spec_validator.py', 'python3 scripts/backlog_lint.py'.
- Gates before any PR: 'make lint', 'make typecheck', 'make test', 'make lint-specs'. Close the constitution §11 loop: tasks.md '## Follow-ups Discovered' + mirror each into BACKLOG.md as BL-YYYYMMDD-NN + copy the new bullets into the PR body.
- AO-SDLC chain (as slash commands): /specify -> /clarify -> /plan -> /tasks -> /implement ; /evolve for autonomous runs. Canonical prompts live in prompts/.
- Tool check: docker=$(have docker) (daemon ${docker_up}) make=$(have make) python3=$(have python3) gh=$(have gh). If the docker daemon is down, host-only work is limited to git + the two stdlib validators.
EOF

python3 - "$CTX" <<'PY' 2>/dev/null || printf '{}'
import json, sys
print(json.dumps({"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": sys.argv[1]}}))
PY
