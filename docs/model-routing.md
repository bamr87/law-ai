# Model Routing for AO-SDLC

> Which model runs which step. This is the **canonical policy**; the per-step
> recommendation is mirrored as machine-readable frontmatter in each
> [prompts/](../prompts/) file and in the `.github/prompts/*.prompt.md`
> wrappers so the right model is selected automatically when a step runs.

This policy applies to the **development-orchestration layer only** (GitHub
Copilot + Claude Code writing/refactoring this repo). It does **not** touch the
**product runtime LLM**, which stays Ollama / local-first per
[docs/constitution.md](constitution.md) §1 and [AGENTS.md](../AGENTS.md)
§ "Development Orchestration". The two layers are independent.

## Why route by step

Not every AO-SDLC step needs the same model. Routing makes the workflow:

- **More accurate** — the highest-reasoning model handles the upstream steps
  (`/specify`, `/clarify`, `/plan`) where a mistake is most expensive because it
  propagates into every downstream task.
- **More efficient** — faster, cheaper models handle the mechanical downstream
  steps (`/tasks`, `/implement`) where the spec already constrains the work, so
  premium reasoning tokens are spent only where they pay off.
- **More versatile** — every step lists an explicit fallback plus an escalation
  rule, so a run can degrade gracefully when the preferred model is unavailable
  and step up to a stronger model when a step proves harder than expected.

## Tiers

| Tier | Model | Use for |
|------|-------|---------|
| **Reasoning** | `Claude Opus 4.8` | Deep requirements analysis, ambiguity resolution, architecture, constitution-compliance judgement. The upstream "think hard" steps. |
| **Execution** | `Claude Sonnet 4.6` | Decomposition and code generation against an already-clarified spec/plan. The downstream "do the work" steps. |
| **Review / alt** | `GPT-5` | Cross-model review, fallback when a Claude tier is unavailable, second opinion on high-stakes specs. |

Model names follow the Copilot frontmatter convention used in
`.github/prompts/*.prompt.md` (e.g. `Claude Opus 4.8 (copilot)`); Claude Code
maps the same display names to its CLI/SDK model ids.

## Routing table

| Step / Prompt | Phase | Task type | Recommended | Fallback |
|---|---|---|---|---|
| [/specify](../prompts/specify.md) | 1 — Requirements | Author traceable, testable spec; check all constitution rules | **Claude Opus 4.8** | GPT-5 |
| [/clarify](../prompts/clarify.md) | 1 — Requirements | Resolve ambiguity; must not guess on legal-accuracy / HITL | **Claude Opus 4.8** | GPT-5 |
| [/plan](../prompts/plan.md) | 2 — Architecture | Map every FR/NFR to concrete modules; ADR judgement | **Claude Opus 4.8** | GPT-5 |
| [/tasks](../prompts/tasks.md) | 3 — Implementation | Decompose plan into small, independently verifiable tasks | **Claude Sonnet 4.6** | Claude Opus 4.8 |
| [/implement](../prompts/implement.md) | 3 — Implementation | Smallest code change for one task + tests | **Claude Sonnet 4.6** | Claude Opus 4.8 |
| [/implement-feature](../prompts/implement-feature.md) | 3 — Implementation | Multi-layer feature build (API → agent → UI → tests) | **Claude Sonnet 4.6** | Claude Opus 4.8 |
| [/new-agent](../prompts/new-agent.md) | 3 — Implementation | Scaffold a new agent role + LegalBench test | **Claude Sonnet 4.6** | Claude Opus 4.8 |
| [/evolve](../prompts/evolve.md) | Autopilot (1→4) | Pick work + drive the whole chain | **Claude Opus 4.8** (driver) | GPT-5 |

The `/evolve` driver runs each sub-step under that sub-step's own recommended
tier: it keeps Opus 4.8 for the `/specify` → `/clarify` → `/plan` legs and hands
the `/tasks` → `/implement` legs to Sonnet 4.6. That keeps a full autopilot
cycle accurate where it matters and cheap where it doesn't.

## Escalation & fallback rules

1. **Escalate on difficulty.** If an Execution-tier step (`/tasks`,
   `/implement`, `/implement-feature`, `/new-agent`) fails its `Verify:` block or
   quality gates **twice**, or the task touches a schema migration, a HITL gate,
   or legal-reasoning logic, re-run it on the step's **fallback** (Reasoning tier)
   before asking a human.
2. **Never downgrade the upstream steps.** `/specify`, `/clarify`, and `/plan`
   must run on a Reasoning-tier model (Opus 4.8, or GPT-5 only if Opus is
   unavailable). Do not run them on an Execution-tier model to save cost — an
   error here is the most expensive kind.
3. **Cross-model review for high-stakes specs.** When a spec sets
   `human_approval_required: true` (constitution §5) or is rated `high_stakes`,
   get a second-opinion pass from the **Review / alt** tier (`GPT-5`) before the
   human gate.
4. **Honour the stop conditions.** Model escalation never overrides the
   [/evolve](../prompts/evolve.md) "Stop Conditions" — licensing, new data
   source, product-runtime model swap, destructive migration, or HITL-gate
   removal still stop for a human regardless of which model is driving.

## How a step picks its model

- **GitHub Copilot / Claude Code (interactive or coding agent):** the `model:`
  array in the prompt's frontmatter is the recommendation order — the first
  entry is the recommended tier, later entries are fallbacks. The
  `.github/prompts/*.prompt.md` wrappers carry the same ordering for Copilot's
  prompt picker.
- **Plain `prompts/*.md` slash commands:** each file's YAML frontmatter
  (`model`, `phase`, `step`) records the same recommendation so the routing
  travels with the prompt even when it is invoked outside the Copilot picker.

Keep this table, the prompt frontmatter, and the
[ao-sdlc-guide.md](ao-sdlc-guide.md) "Model Routing by Phase" section in sync —
if you change a recommendation in one place, change it in all three.
