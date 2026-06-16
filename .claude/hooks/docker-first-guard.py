#!/usr/bin/env python3
"""Docker-first guard (PreToolUse hook on the Bash tool).

Enforces CLAUDE.md "Docker-first" + AGENTS.md: dev/test/lint/typecheck/eval
commands run INSIDE Docker via ``make`` / ``docker compose run``, never on the
host. Blocks bare host ``pytest|ruff|black|mypy|isort``, ``npm|pnpm|yarn
install|run|test|…``, ``pip install``, and ``python manage.py`` — but only when
they are the actual command of a segment (so ``grep -rn pytest`` is fine), and
never when the segment goes through ``docker``/``make``. Sanctioned host
commands (``python3 scripts/*.py``, ``git``, ``gh``) pass.

Exit 0 = allow; exit 2 = block (stderr reason is shown to the agent).
Fail-open: any parse error allows the command.
"""

from __future__ import annotations

import json
import re
import sys

_BARE = {"pytest", "ruff", "black", "mypy", "isort"}
_NPM = {"npm", "pnpm", "yarn"}
_NPM_VERBS = {"install", "ci", "run", "test", "exec", "add"}
_ASSIGN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
_WRAPPERS = {"env", "sudo", "time", "nice", "xargs", "command"}
_DOCKER_OR_MAKE = re.compile(r"(^|\s)(docker\b|make\b)")


def _violation(segment: str) -> str | None:
    # A segment going through docker/make is allowed.
    if _DOCKER_OR_MAKE.search(segment):
        return None
    toks = segment.strip().split()
    i = 0
    while i < len(toks) and (_ASSIGN.match(toks[i]) or toks[i] in _WRAPPERS):
        i += 1
    if i >= len(toks):
        return None
    head = toks[i].split("/")[-1]
    rest = toks[i + 1 :]
    if head in _BARE:
        return f"bare host '{head}'"
    if head in _NPM and rest and rest[0] in _NPM_VERBS:
        return "host node package manager"
    if re.fullmatch(r"pip[0-9.]*", head) and rest and rest[0] == "install":
        return "host pip install"
    if re.fullmatch(r"python[0-9.]*", head) and rest and rest[0] == "manage.py":
        return "host 'python manage.py'"
    return None


def main() -> int:
    try:
        cmd = json.load(sys.stdin).get("tool_input", {}).get("command", "")
    except Exception:
        return 0
    if not cmd:
        return 0
    # Split into command segments on shell operators, then check each head.
    segments = re.split(r"&&|\|\||[;&|()\n]", cmd)
    reason = next((r for r in (_violation(s) for s in segments) if r), None)
    if reason:
        sys.stderr.write(
            f"Docker-first violation ({reason}). Run it inside Docker instead:\n"
            "  make test | make lint | make typecheck\n"
            "  docker compose run --rm backend pytest tests/...   (single test)\n"
            "  make manage CMD='migrate'                          (manage.py)\n"
            "See CLAUDE.md 'Docker-first' / AGENTS.md. "
            "(python3 scripts/*.py, git, gh are fine on the host.)\n"
        )
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
