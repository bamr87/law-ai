---
name: asdlc-clarify
description: AO-SDLC step 2 — resolve the OPEN QUESTION (OQ-N) markers in a spec.md in place. Use when asked to clarify a spec, resolve open questions, or continue the AO-SDLC chain after specify.
---

Runs the AO-SDLC **clarify** step. Full instructions: [prompts/clarify.md](prompts/clarify.md) — read it and execute it. Paths are relative to the repo root.

## Preconditions
- A `specs/NNN-*/spec.md` exists with one or more `OPEN QUESTION OQ-N` markers.

## Run
1. Read and follow [prompts/clarify.md](prompts/clarify.md); resolve every `OQ-N` **in place** in `spec.md`.
2. **Stop and surface to a human** — do not invent an answer — if a question touches: a new external data source, licensing, a model swap, a destructive schema migration, or a HITL gate (constitution §5).

## Next
→ `asdlc-plan` once **all** `OQ-N` are resolved (it will refuse otherwise).
