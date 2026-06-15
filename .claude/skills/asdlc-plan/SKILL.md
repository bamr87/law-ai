---
name: asdlc-plan
description: AO-SDLC step 3 — produce the implementation plan (plan.md) for a clarified spec. Use when asked to plan a spec, write plan.md, or continue the AO-SDLC chain after clarify.
---

Runs the AO-SDLC **plan** step. Full instructions: [prompts/plan.md](prompts/plan.md) — read it and execute it. Paths are relative to the repo root.

## Preconditions (enforce — refuse if unmet)
- `specs/NNN-*/spec.md` exists **and has no unresolved `OPEN QUESTION OQ-N`**. If any remain, stop and tell the user to run `asdlc-clarify` first; list the unresolved markers.

## Run
1. Read and follow [prompts/plan.md](prompts/plan.md) to fill `plan.md`: architecture, file-by-file changes, the quality gates the PR must pass (constitution §3), and the test plan (§6).
2. Keep the plan inside the locked tech stack (constitution §2); any new top-level dependency needs an ADR note.

## Next
→ `asdlc-tasks`.
