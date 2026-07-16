---
description: "AO-SDLC /implement — implement one task from tasks.md, with gates + follow-ups"
argument-hint: "<task id, e.g. T-003, inside specs/NNN-*/tasks.md>"
---

Execute the canonical Law AI AO-SDLC **implement** step for a single task.

Read [prompts/implement.md](../../prompts/implement.md) now and follow it exactly. Stop after one task — do not chain into the next.

Task: $ARGUMENTS

Before finishing: run gates in Docker (`make test-backend`, `make lint`, `make typecheck` where wired) plus `python3 scripts/spec_validator.py` and `python3 scripts/backlog_lint.py`; append `## Follow-ups Discovered` and mirror each into [BACKLOG.md](../../BACKLOG.md) as `BL-YYYYMMDD-NN`. Never run pytest/ruff/mypy/black on the host.
