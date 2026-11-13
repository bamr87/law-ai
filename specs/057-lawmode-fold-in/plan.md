# Plan: Fold lawmode into law-ai

Spec: [spec.md](spec.md) · Migration inventory: [docs/lawmode-migration.md](../../docs/lawmode-migration.md) · Decision: [#226](https://github.com/bamr87/law-ai/issues/226)

## 1. Architecture Overview

```
make lawmode-scan / lawmode scan --json        VS Code extension (extensions/vscode-lawmode)
        │                                               │ execFile(argv), parses JSON v1
        ▼                                               ▼
manage.py lawmode_scan ──► law_ai.lawmode.services.review.run_scan(target, policy)
                                    │
                                    ▼
             agents_runtime/graphs/code_legal_review.py (LangGraph)
     jurisdiction ─ domain ─ privacy ─ licence ─ security ─ accessibility ─ copyright ─ regulatory
                                    │  each node: prompts/lawmode/<chain>.v1.md
                                    ▼
             law_ai.core.llm.langchain.ChatProviderChain ─► LLM_PROVIDER_CHAIN
                 (claude_code → anthropic_api → xai → ollama)   + law_ai.core.provenance
                                    │
                                    ▼
                    aggregate ─► HITL gate: critical/high → PendingReview(kind="lawmode_finding")
                                    │
                                    ▼
                    report (JSON v1, Markdown) + .lawmode/ artifacts + disclaimer
```

## 2. Component Changes

| Area | Change | Phase |
|---|---|---|
| `backend/law_ai/lawmode/` (new app) | `apps.py`, `schemas.py` (from `lawmode/lawmode/models.py`), `policy.py` (from `config.py` `PolicyConfig` + `.lawmode/policy.yaml`), `services/review.py` (from `core.py`), `services/artifacts.py` (from `generate_artifacts`), `disclaimer.md` | P1 |
| `backend/law_ai/settings/base.py` | `INSTALLED_APPS += law_ai.lawmode`; `LAWMODE_MODELS` (optional per-provider override, Anthropic values validated against the three allowed ids), `LAWMODE_JURISDICTIONS` | P1 |
| `backend/law_ai/agents_runtime/graphs/code_legal_review.py` | Eight chain nodes + aggregate + HITL gate, from `lawmode/lawmode/chains/chain_builder.py` | P2 |
| `backend/law_ai/agents_runtime/prompts/lawmode/*.v1.md` | One prompt per chain, extracted from the inline f-strings | P2 |
| `backend/law_ai/ingestionapp/quarantine_kinds.py` | `LAWMODE_FINDING = "lawmode_finding"` | P2 |
| `backend/law_ai/agents_runtime/tools/` | `spdx.py`, `eurlex.py` on `httpx` + `tenacity` (if OQ-2 keeps them); CourtListener via `ingestionapp/sources/courtlistener.py`; Scholar dropped | P3 |
| `backend/law_ai/lawmode/management/commands/lawmode_scan.py`, root `Makefile` | CLI (from `lawmode/lawmode/cli.py`), `make lawmode-scan`, JSON schema v1, `scan` subcommand wrapper | P4 |
| `extensions/vscode-lawmode/` (proposed), root `Makefile`, `.github/workflows/ci.yml` path filters | Extension ported from `lawmode/vscode-extension/src/*.ts`, `execFile`, no `out/` in git, npm lint/tsc/test in `node:20-alpine` | P5 |
| `docs/lawmode.md`, `README.md`, `AGENTS.md` layout table | User docs; layout rows point to the folded locations | P4–P5 |
| `lawmode/` (old tree) | **Unchanged** in P1–P5 (frozen). Removal/archive only in P6, only with Amr's OK | P6 |

## 3. Data & Schema Migrations

None required for the `PendingReview` kind (code-only). If P2 adds a `LawmodeScan` model, it ships its own migration; no data backfill.

## 4. Tech Choices & Alternatives

- **Provider access**: `ChatProviderChain` (existing LangChain adapter over `law_ai.core.llm`) so the LangGraph port keeps its shape. Alternative rejected: keep lawmode's `llm/factory.py` and add an Anthropic backend — that is a second provider path and breaks §1/§2.
- **Model defaults**: none in lawmode. The chain's defaults apply (`CLAUDE_CODE_MODEL=claude-opus-5-5` today). Implementers may suggest `claude-sonnet-5-5` for the eight per-chain calls through `LAWMODE_MODELS` as an operator setting, never as a hard-coded default for a non-Anthropic vendor. OpenAI (`gpt-4o`) and `grok-2-1212` defaults are removed.
- **CLI**: Django management command instead of `click` (no new dependency; same pattern as the rest of the backend).
- **Policy file**: Python defaults + settings now; per-repository YAML later (BL-20261112-10) because PyYAML is not a direct dependency.
- **Dependencies**: none added (spec NFR-DEP-1). Dropped: `langchain-openai`, `langchain-anthropic`, `requests`, `click`, `rich`, `gitpython` (diff via `git` subprocess with an argument list in the management command — a CLI process, not an agent tool).

## 5. Provenance & Audit Hook-up

`run_scan` opens a provenance scope (scan id, target hash, policy hash); every chain node passes `prompt_id="lawmode.<chain>"`, `prompt_version="v1"` on its `LLMRequest`, so `law_ai.core.llm` records provider, model, attempts, usage and cost. Tool calls record a provenance event with URL host and status. The final report carries the scan id so a finding can be traced to its calls.

## 6. HITL Gates

`human_approval_required=True` for the critical/high path. The graph's HITL node creates one `PendingReview(kind="lawmode_finding")` per gated finding with the finding, citation and provenance id. The CLI reports `awaiting_review` and exits 0 unless the scan itself failed (exit 2), so no automated verdict blocks or passes a change. Posting to a GitHub PR is out of scope (BL-20261112-11).

## 7. Test Strategy

- Unit: schemas, policy, severity gating, artifact writer, JSON v1 contract, settings validation (AC-6) — `backend/tests/lawmode/`.
- Graph: each node with a stubbed `LLMProvider` returning fixture JSON; provenance assertions (AC-2); HITL creation (AC-3).
- Tools: `respx`/`httpx.MockTransport`, no live network in `make test`.
- CLI: management command against `backend/tests/lawmode/fixtures/repo/` (AC-1).
- Extension: unit tests for argument-array invocation and JSON → diagnostics (AC-4) in `node:20-alpine`.
- lawmode's live-API tests (`lawmode/tests/integration/test_grok*.py`, `test_local.py`) are not ported; an optional `@pytest.mark.integration` test against a local Ollama may be added.
- Coverage: the repo's `--cov-fail-under=75` applies to `law_ai.lawmode`.

## 8. Rollout

Phases ship as separate PRs from Claude Code, one handoff issue each, in order P1 → P5; P6 waits for Amr. Each PR carries `Governed by: PRD §5.8 / LAWAI-022 / spec 057`. `LAWAI-022` moves `planned → in-progress` with P1 and `→ shipped` after P5. The old `lawmode/` tree is frozen (no features) from P1.

| Phase | Scope | Exit check |
|---|---|---|
| P1 | `law_ai.lawmode` app: schemas, policy, review service skeleton on `law_ai.core.llm`, settings validation | AC-2 (partial), AC-6; lint/typecheck/test green |
| P2 | `code_legal_review` graph, eight versioned prompts, provenance, HITL kind | AC-2, AC-3 |
| P3 | Research tools on httpx + tenacity; CourtListener reuse; Scholar dropped | tools tests green, no `requests` |
| P4 | `lawmode_scan` command, `make lawmode-scan`, JSON v1, `docs/lawmode.md` | AC-1 |
| P5 | VS Code extension under law-ai CI | AC-4, AC-5 |
| P6 | **Proposal only — needs Amr's OK in his own words.** Remove or archive `lawmode/` (incl. nested workflow, committed `out/`, `lawmode/CLAUDE.md`), archive `bamr87/lawmode`, update README/AGENTS layout | AC-7 until approved |

## 9. Risks & Mitigations

| Risk | Mitigation |
|---|---|
| Confidential code sent to hosted providers | NFR-SEC-2; docs show `LLM_PROVIDER_CHAIN=ollama` |
| Output mistaken for legal advice | Disclaimer on every output; advisory wording; HITL |
| Old/new copies drift | Old tree frozen from P1; P6 retirement |
| Extension contract breaks again | JSON v1 schema fixture shared by backend and extension tests |
| Cost of eight calls per scan | Per-call usage/cost already recorded by the router; operator can set `LAWMODE_MODELS` to `claude-haiku-5-5`/`claude-sonnet-5-5` or pin `ollama` |

### Design for Failure

| Failure | Detection | Behaviour |
|---|---|---|
| Every provider tier unavailable | `LLMUnavailableError` from the chain | Scan exits 2 "could not run", no partial "clean" report |
| One chain node fails | Node exception | Report lists the chain as `not_run`; never counted as "no findings" |
| HITL gates disabled | `ENABLE_HUMAN_APPROVAL_GATES=false` | Gated findings reported `unreviewed`, never auto-approved |
| Tool HTTP error | tenacity exhausted | Finding keeps "citation unavailable"; provenance records the failure |
| Extension cannot find the CLI | spawn error | Clear error diagnostic; no shell fallback |

## 10. Estimated Effort

P1 M · P2 L · P3 S · P4 M · P5 M · P6 S (after approval).
