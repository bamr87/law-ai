---
name: asdlc-specify
description: AO-SDLC step 1 — create or fill a spec package (specs/NNN-slug/spec.md) from an intent or BACKLOG item. Use when asked to write a spec, specify a feature, start a spec-driven change, or begin the AO-SDLC chain.
---

Runs the AO-SDLC **specify** step. Full instructions: [prompts/specify.md](prompts/specify.md) — read it and execute it. Paths are relative to the repo root.

## Preconditions
- A one-line intent and/or a `BL-*` id to claim. **Scan [BACKLOG.md](BACKLOG.md) first** (constitution §11): if an Open `BL-*` matches, reference it in spec §2 and move it `## Open` → `## Claimed`.
- Read [docs/constitution.md](docs/constitution.md) §1/§2/§4 — reject intents needing a closed-source product-runtime LLM, an unlisted framework, or removal of provenance.

## Run
1. Pick the next free `NNN`, create `specs/NNN-feature-slug/` from [specs/_template](specs/_template).
2. Read and follow [prompts/specify.md](prompts/specify.md) to fill `spec.md`, leaving any unknowns as `OPEN QUESTION OQ-N` markers.
3. Declare `human_approval_required: true` where constitution §5 requires it.

## Next
→ `asdlc-clarify` to resolve the `OQ-N` markers.
