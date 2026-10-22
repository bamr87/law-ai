# Law AI — Constitution

> The rules every spec, plan and PR must satisfy to be valid — mission, locked stack, quality gates, provenance, HITL, testing, security, autonomy invariants and jurisprudential honesty.

> Org-wide, non-negotiable standards for every spec, plan, and implementation produced by humans or AI agents in this repo. This is the **first** document any agent reads when running [/specify](../prompts/specify.md), [/plan](../prompts/plan.md), or [/implement](../prompts/implement.md).
>
> Higher-level principles, mission, and tech-stack rationale live in [AGENTS.md](../AGENTS.md). This file encodes only the **rules a spec or PR must satisfy to be valid**.

## 1. Mission Alignment

Every feature must trace to the mission in [AGENTS.md](../AGENTS.md): privacy-aware, auditable, graph-native legal intelligence with HITL on high-stakes paths.

**Product-runtime LLM policy (amended 2026-08-11, spec 034; amended 2026-09-04, [ADR 0007](adr/0007-xai-runtime-provider.md)).** The runtime is a single **ordered provider chain**, configured in `LLM_PROVIDER_CHAIN` and implemented in `law_ai.core.llm`:

1. `claude_code` — Anthropic Claude over a subscription OAuth token.
2. `anthropic_api` — Anthropic Claude over `ANTHROPIC_API_KEY`.
3. `xai` — xAI Grok over a subscription OAuth token (sanctioned 2026-09-04, implemented in spec 050).
4. `ollama` — the local open-weights model.

Claude is the **default product runtime**. This repeals the prior rule that rejected any spec wiring a closed-source model into the runtime; that rule is superseded, not merely unenforced. The trade is deliberate and its costs are named here so no spec can pretend otherwise:

- **Legal text leaves the machine.** Prompts on the Claude tiers are sent to a third party. Any matter under a confidentiality obligation that forbids third-party processing MUST pin the chain to `ollama` (`LLM_PROVIDER_CHAIN=ollama`). Deployments handling privileged client data SHOULD default to that pin.
- **Reproducibility is provider-dependent.** Benchmarks and evals MUST pin a single provider so results stay comparable; the LegalBench harness is pinned to Ollama for exactly this reason.

**xAI amendment (2026-09-04, [ADR 0007](adr/0007-xai-runtime-provider.md)).** xAI is a sanctioned product-runtime vendor. `xai` is the **third default tier** — below both Anthropic tiers, above `ollama` — so once implemented, a deployment that has not pinned `LLM_PROVIDER_CHAIN` tries xAI before falling to the local model. The terms of the amendment:

- **Auth is OAuth-first, and there is no API-key tier.** The `xai` tier authenticates with a SuperGrok / X Premium+ subscription OAuth token, mirroring `claude_code`. xAI publishes no such flow — its documented API takes a bearer `XAI_API_KEY` — so spec 050 implements the OAuth 2.0 grant against `auth.x.ai` that Kilo Code ships in the open, reusing the public Grok-CLI desktop client. A spec adding an `XAI_API_KEY` tier is **not** covered by this amendment. The shipped default is `claude_code,anthropic_api,xai,ollama`; the tier is inert until an operator runs `make xai-login`, so an unauthorised deployment behaves exactly as it did before.
- **A second egress path, not a second privacy story.** Two third parties now sit in the default chain. `LLM_PROVIDER_CHAIN=ollama` remains the **only** configuration that keeps prompt text on the host, and it is still required for any matter under a confidentiality obligation forbidding third-party processing.
- **No transport exemption.** `xai` is a provider class behind `law_ai.core.llm` like every other tier. It routes through the §4 choke point and writes the same `llm_call` provenance event, naming the provider and model that actually served the call.
- **Evals stay pinned.** LegalBench does not route through the chain and does not gain an xAI mode; adding a tier changes nothing about §6.

What this amendment does **not** relax — a spec violating any of these is still rejected:

- **Local-first must remain reachable.** `ollama` stays a first-class provider and the chain's last tier. A change that makes the product unable to run wholly locally **must be rejected**.
- **Provenance is unchanged.** Every model call is logged through `core.provenance` with the provider and model that actually served it, including which tiers were skipped or failed (§4).
- **No silent fabrication.** When every provider fails, the caller degrades to an honest refusal — never a fabricated answer (§13).
- **No further vendor.** Anthropic, xAI, and Ollama are the sanctioned runtime providers. A spec adding OpenAI, Gemini, or any other vendor to the chain **must be rejected** without a further amendment to this section.

**Development orchestration remains a separate layer.** GitHub Copilot and Claude Code are the sanctioned AI dev surfaces (Copilot Chat in VS Code + the GitHub Copilot coding agent in the cloud; the Claude Code CLI / IDE extensions + the Claude Agent SDK). The dev surface and the runtime provider are configured independently: which model edits this code is not the same decision as which model serves users. Specs proposing other coding agents (Cursor, Continue.dev, Aider, Codex, Gemini CLI, etc.) or their config files **must be rejected**. See [AGENTS.md](../AGENTS.md) § "Development Orchestration".

## 2. Tech Stack (Locked)

- Backend: Python 3.12+, Django 5 (ASGI via daphne), Django REST Framework, Channels, Celery (Redis broker), Pydantic v2 (domain layer), CrewAI + LangGraph, Neo4j, Postgres (Django ORM async + raw asyncpg where required), Chroma; runtime LLM providers are Anthropic Claude (default), xAI Grok (sanctioned 2026-09-04, spec 050), and Ollama (local fallback) — see §1.
- Frontend: Next.js 15 App Router, TypeScript strict, Tailwind, shadcn/ui, Cytoscape.js, TanStack Query.
- Infra: Docker Compose for local; GitHub Actions for CI.

No new top-level frameworks (e.g. Vue, LlamaIndex as primary) without an ADR in `docs/adr/` and explicit approval. The Django adoption itself is recorded in [docs/adr/0001-adopt-django-backend.md](adr/0001-adopt-django-backend.md), which supersedes the previous FastAPI lock established in earlier revisions of this section.

## 3. Code Quality Gates

A spec **must** declare and a PR **must** pass:

- `ruff check` + `black --check` clean (line length 88).
- `mypy law_ai --strict` clean for any touched module, and never worse anywhere. `make typecheck` runs the strict check through the ratchet in [scripts/mypy_ratchet.py](../scripts/mypy_ratchet.py), which compares per-file strict-error counts against `backend/mypy-baseline.txt` and fails when a count grows or a file the baseline calls clean stops being clean. A file with no baseline entry — every new module — must be strict-clean. Burning a file down is a diff to that baseline (`make mypy-baseline`); the baseline may only shrink, and when it reaches zero it is deleted so plain `mypy law_ai --strict` becomes the gate (BL-20260429-04).
- Frontend: `npm run lint` + `npx tsc --noEmit` clean.
- Pytest + Vitest green; combined coverage **≥ 75%** on changed files.
- LegalBench regression run (`Run LegalBench Eval` task) when reasoning logic changes — score must not regress more than 1 pp on listed tasks.

## 4. Provenance & Audit (Non-Negotiable)

- Every agent LLM call, tool call, and retrieval must go through `law_ai.core.provenance`.
- **`law_ai.core.llm` is the sole sanctioned choke point for model calls.** Every provider request in the §1 chain is issued through it, and it alone writes the `llm_call` provenance event (provider, model, and which tiers were skipped or failed). No feature module may call a provider transport (the Claude Code SDK, the Anthropic API, an Ollama client) directly — doing so bypasses the audit layer and is rejected at review regardless of which provider is involved.
- **Durability is dual-write, JSONL-first.** Every provenance event is appended to an append-only JSONL log and mirrored into a queryable Postgres `AuditEvent` row (written synchronously outside async/ASGI contexts, deferred to Celery inside them). The JSONL write happens first and unconditionally, specifically so an event is never silently lost if the Postgres leg fails or is delayed.
- Every Neo4j node/edge created or updated must carry `source`, `source_url` (when applicable), `ingest_timestamp`, `agent_version`, and `confidence` (0–1).
- Nodes are **never** hard-deleted. Use `archived_at` soft-delete.

## 5. Human-in-the-Loop (HITL) Requirements

Spec **must** declare `human_approval_required: true` for any of:

- Ingestion of a new public data source.
- Schema migration (Neo4j or Postgres).
- A new agent output path that has no existing confidence or verification gate (see the runtime mechanisms below) — new paths inherit the requirement until the spec earns an explicit exemption.
- Production deployment of a new agent role.

At runtime, HITL is enforced by confidence and verification thresholds, not by a subject-matter classifier — no `high_stakes` topic list (criminal, immigration, life-safety, regulatory filings, or similar) exists anywhere in `backend/law_ai`, and none may gate approval until a spec actually builds one:

- **Ingestion.** `IngestionScout` (`backend/law_ai/ingestionapp/services/scout.py`) routes any extraction below `CONFIDENCE_THRESHOLD = 0.7` to `pending_review` instead of committing it to the graph, gated by `ENABLE_HUMAN_APPROVAL_GATES` (default `True`, `backend/law_ai/settings/base.py`).
- **Analysis.** `LegalWorkflow` and `LegalAnalyst` (`backend/law_ai/agents_runtime/graphs/legal_workflow.py`, `crews/legal_analyst.py`) set structured `human_approval_required` / `requires_review` booleans whenever citations are unverified, retrieval returns zero results, or the output is a `degraded` fallback (e.g. the LangGraph/Ollama engine unavailable) — never by asserting the topic is inherently sensitive.
- A spec that needs subject-matter gating (e.g. a real `high_stakes` classifier) must build and name the mechanism explicitly; until then, do not describe one as already enforced.

## 6. Testing Standards

Every new feature ships with:

- ≥ 1 unit test (mocked external deps).
- ≥ 1 integration test (real Neo4j/Postgres via `docker compose`).
- For new agents: ≥ 1 test in `backend/tests/agents/` covering `run(input: dict) -> dict` and its Pydantic output (the agent contract in [AGENTS.md](../AGENTS.md)).
- For new frontend components: ≥ 1 Vitest + RTL test in `frontend/__tests__/`.

LegalBench scoring itself is **not** a per-agent, per-PR obligation: it runs centralized, pinned to Ollama for comparability (§1), via `make test-legalbench` and the nightly workflow, and is required on a PR only when it changes reasoning logic (gated by the `reasoning-change` label; see §3). The `legalbench` pytest marker exists in `backend/pyproject.toml` for this centralized run — do not add it to individual agent test files.

## 7. Spec-Driven Workflow (AO-SDLC Phase 1)

Every change larger than a typo follows the spec workflow:

1. Author creates `specs/NNN-feature-slug/` from [specs/_template](../specs/_template).
2. Run [/specify](../prompts/specify.md) → fills `spec.md`.
3. Run [/clarify](../prompts/clarify.md) → resolves open questions in-place.
4. Run [/plan](../prompts/plan.md) → fills `plan.md`.
5. Run [/tasks](../prompts/tasks.md) → fills `tasks.md`.
6. Open PR with all four files. CI runs [scripts/spec_validator.py](../scripts/spec_validator.py) drift gate.
7. Run [/implement](../prompts/implement.md) per task; PRs reference `specs/NNN-...` in description.

[/evolve](../prompts/evolve.md) runs this same seven-step chain autonomously end-to-end (BACKLOG scan through implementation), still bound by every gate in this document — most directly §10 Autonomy Level and §11 Continuous Evolution. It runs on a weekly schedule via [.github/workflows/evolve.yml](../.github/workflows/evolve.yml) and on demand from either sanctioned dev surface (§1).

See [docs/ao-sdlc.md](ao-sdlc.md) for how phases map onto Law AI and [ao-sdlc-guide.md](ao-sdlc-guide.md) for the full framework reference.

## 8. Security Baselines

- No secrets in repo. `.env.example` only.
- All external HTTP via `httpx` + `tenacity` retries; no raw `requests`.
- Input validation with Pydantic at every API boundary.
- LLM tool calls run through provenance — never give an agent shell or unsandboxed `eval`.
- Dependency additions require a brief license + security note in the spec.

## 9. Documentation

- Architecture changes update [docs/architecture.md](architecture.md).
- New agent roles update [docs/agent-roles.md](agent-roles.md).
- New external data sources update `docs/data-sources.md` (create if missing).
- Graph schema changes update `docs/data-model.md` (create if missing).

## 10. Autonomy Level

This repo currently operates at **AO-SDLC Level 2 (Collaborative)**: agents draft, humans approve at the spec gate and the PR gate. Promotion to Level 3 requires:

- LegalBench baseline established and tracked in CI. **Met** — `backend/law_ai/eval/legalbench.py` writes and reads `baseline.json`; `.github/workflows/nightly-tests.yml` gates on `--check-regression`.
- Langfuse (or equivalent) traces wired up. **Met** — self-hosted Arize Phoenix is a compose service, instrumented via `backend/law_ai/core/telemetry.py` (OTEL → Phoenix) and started in the nightly workflow.
- ADR documenting which classes of change may auto-merge. **Not met** — no such ADR exists; [docs/adr/0003-autonomy-orchestrator.md](adr/0003-autonomy-orchestrator.md) affirms Level 2, and I1 below still forbids all auto-merge.

Two of three prerequisites already exist in the codebase. This is not a promotion, and does not change the Level-2 determination: the remaining ADR is a human-authored governance decision, not a scan of what's already built, and the repo does not self-promote by inference.

## 11. Continuous Evolution (Self-Improving Repo)

The repo must always grow forward. Every implementation cycle MUST end with explicit follow-ups so future agents and humans inherit a richer task graph than they started with.

- **Every `tasks.md`** ends with a `## Follow-ups Discovered` section. CI ([scripts/spec_validator.py](../scripts/spec_validator.py)) enforces this.
- **Every follow-up** is mirrored into [BACKLOG.md](../BACKLOG.md) with a `BL-YYYYMMDD-NN` id. CI ([scripts/backlog_lint.py](../scripts/backlog_lint.py)) enforces format and forbids deletion of historical entries (move to `## Done` instead).
- **Every `/specify`** must first scan `BACKLOG.md` and reference any matching `BL-*` items in spec §2; matched items move from `## Open` to `## Claimed`.
- **"No follow-ups"** is allowed only with an explicit justification line (`_none — justified: <reason>_`) preserved in the PR description.
- **Mission drift guard.** Follow-ups MUST be consistent with §1 Mission Alignment, §2 Tech Stack, and §4 Provenance. Items proposing a third LLM vendor beyond Anthropic and Ollama (§1), frameworks not listed in §2, or removal of provenance must be rejected at triage.
- **Refactor budget.** At least one `refactor` or `tech-debt` BACKLOG item should be promoted into `specs/` for every three feature specs shipped, to prevent rot.
- **Tests stay aligned.** When a `BL-*` item is promoted into a spec, the new `tasks.md` must add or extend tests covering the BACKLOG'd concern — self-evolution never lowers coverage.

## 12. Autonomy Loop Invariants

Recorded by [docs/adr/0003-autonomy-orchestrator.md](adr/0003-autonomy-orchestrator.md). "AutonomyOrchestrator" here names the role, not a class — the implementation is the functional entry point `law_ai.core.autonomy.run_cycle()` and the `manage.py run_autonomy` management command, invoked via `make autonomy-run KIND=… SOURCE=…`, driving the two cooperating loops named in the ADR (`TestPilot` / `test_synthesizer.py` and `CorpusGrowth` / `topic_frontier.py`). This entry point and any future autonomous loop in this repo MUST satisfy all of the following — CI and code-review reject violations:

- **I1 — No auto-merge.** Every loop ends in either a draft PR (code) or a `PendingReview` row (data). No GitHub Actions workflow may be granted permissions sufficient to merge a PR; no Celery task may write to a `:Case`/`:Statute` node outside `IngestionScout.run_and_commit`.
- **I2 — Closed source registry.** Recursion expands within `law_ai.ingestionapp.sources.SOURCE_REGISTRY` whose member name appears in `AUTONOMY_ALLOWED_SOURCES`. Adding a new adapter is its own `/specify` cycle (preserves §5).
- **I3 — Kill-switch.** A single settings flag (`AUTONOMY_ENABLED`, default `False`) short-circuits every loop with one provenance event (`event_type='autonomy_disabled'`). Operators must explicitly opt-in per environment.
- **I4 — One audited entry point.** Every cycle is invoked through `law_ai.core.autonomy.run_cycle()` and emits paired `autonomy_cycle.start` + `autonomy_cycle.end` provenance events, and is additionally projected into the queryable `audit.AutonomyRun` row that the digest and the ops surfaces read ([docs/data-model.md](data-model.md)). Passing `--cycle-id` makes the entry point idempotent: a cycle whose id has already ended is *replayed* — the recorded result is returned with `replayed: true` and one `autonomy_cycle.replayed` event, and the runner is not invoked a second time ([docs/local-ai.md](local-ai.md)). The daily digest under `AUTONOMY_DIGEST_DIR` is the canonical human-review surface.
- **I5 — Propose-only test synthesis.** Autonomy-generated tests land as `*.proposed.py` decorated with `@pytest.mark.skip("autonomy-proposed")`. Reviewers must explicitly un-skip.
- **I6 — Provenance preserved.** Every adapter dispatch records `{adapter_name, query, items_returned, items_quarantined}`; every LLM call goes through `law_ai.core.provenance` (preserves §4).

Promotion to Level 3 — even for narrow change classes — requires a separate ADR amending §10 and these invariants.

## 13. Jurisprudential Honesty (Power-Aware Outputs)

Recorded by [docs/adr/0004-jurisprudential-stance.md](adr/0004-jurisprudential-stance.md); the full argument lives in [docs/philosophy.md](philosophy.md), which is the philosophical source of record for this repo.

The project's operating premise is Thrasymachean **as a description of our data, not as a goal for our system**: the legal record is the record of what the stronger parties have gotten courts to say (victor-authored opinions, non-random settlement selection, repeat-player advantage, uneven coverage). The system's job is to make that visible and contestable — never to launder it as neutral truth, never to exploit it. The craft serves its subject, not its operator.

Every spec and PR must satisfy:

- **Authority ≠ correctness.** A spec **must be rejected** if it presents a citation count, centrality score, or "leading case" ranking as a measure of legal correctness. Such signals may be computed and shown, labelled as what they measure. No agent may assert a holding on citation volume alone.
- **Attribution.** A spec **must be rejected** if it states a legal proposition without its issuing authority (court, jurisdiction, date, binding/persuasive, majority/dissent). Unattributed statements of "the law" are the laundering this section exists to prevent.
- **Absence is reported.** Retrieval surfaces must distinguish "no results in our corpus" from "no such law." Thin or jurisdictionally lopsided result sets say so.
- **Consensus stays a corpus fact.** Agreement across retrieved sources is reported with its count and its sources named — never as verification. This raises the §4 grounding bar; it never relaxes it.
- **Review question.** Spec review asks: *who is the stronger here, and what does this feature do for them?* An answer is required in spec §2 for any feature that ranks, scores, or summarizes legal authority.

Limits, so this clause is not misread: it authorizes labelling, not filtering. Down-ranking sources by ideology or party identity, assigning moral scores to judges or litigants, or curating the corpus toward a preferred outcome are **prohibited** — they merely install a different stronger party. See [docs/philosophy.md](philosophy.md) §6.

---

**Amendments to this constitution require an ADR in `docs/adr/` and review by a human maintainer.**
