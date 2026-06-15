---
name: asdlc-tasks
description: AO-SDLC step 4 — break a plan into an ordered, testable tasks.md (ending with a Follow-ups Discovered section). Use when asked to write tasks, break down a plan, or continue the AO-SDLC chain after plan.
---

Runs the AO-SDLC **tasks** step. Full instructions: [prompts/tasks.md](prompts/tasks.md) — read it and execute it. Paths are relative to the repo root.

## Preconditions
- `specs/NNN-*/plan.md` exists.

## Run
1. Read and follow [prompts/tasks.md](prompts/tasks.md) to fill `tasks.md` with ordered, individually-testable tasks (`T-001`, …), each naming the files it touches and the test it adds/extends (constitution §6).
2. **`tasks.md` MUST end with a populated `## Follow-ups Discovered` section** — `scripts/spec_validator.py` enforces this. "No follow-ups" is allowed only with `_none — justified: <reason>_`.

## Next
→ `asdlc-implement` (per task), then mirror the follow-ups into `BACKLOG.md` (`python3 scripts/next_backlog_id.py`).
