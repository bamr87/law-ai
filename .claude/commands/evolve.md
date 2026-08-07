---
description: "AO-SDLC /evolve — autonomously advance the repo by one full AO-SDLC cycle"
argument-hint: "(optional) BL-id to target; blank = auto-pick highest priority"
---

> Note: this is **law-ai's** AO-SDLC autopilot loop — distinct from the bamr87 hub monorepo's `/evolve`, which runs the fleet self-evolution loop.

Execute the canonical Law AI **evolve** autopilot.

Read [prompts/evolve.md](../../prompts/evolve.md) now and follow it exactly, including its Stop Conditions and the `/specify → /clarify → /plan → /tasks → /implement` chain.

Target (optional): $ARGUMENTS

Honor every Stop Condition (licensing, new data source, model swap, data-dropping migration, HITL-gate removal, or a required constitution amendment) — surface to a human and halt rather than proceeding. All gates run in Docker via `make`.
