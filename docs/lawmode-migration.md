# lawmode fold-in: migration plan

> The plan for folding the imported `lawmode/` legal reviewer into law-ai: every piece mapped to its destination, the phases Claude Code implements, and the retirement step that waits for Amr's OK.

This plan moves the imported `lawmode/` legal reviewer for developers into law-ai as a first-class feature. Amr decided on 2026-11-12, relayed via Grok Bot on [#226](https://github.com/bamr87/law-ai/issues/226), that lawmode is **folded into law-ai**. It is not revived as a standalone product and it is not retired.

- **Requirement**: [PRD §5.8](prd.md) · catalog `LAWAI-022` (status `planned`)
- **Spec**: [specs/057-lawmode-fold-in](../specs/057-lawmode-fold-in/spec.md), with its [plan](../specs/057-lawmode-fold-in/plan.md) and [tasks](../specs/057-lawmode-fold-in/tasks.md)
- **Who implements**: Claude Code, from one handoff issue per phase (hub constitution §26/§28). This plan contains no migration code.
- **What is not done now**: nothing in `lawmode/` is archived, deleted or retired by this plan or by phases 1–5. Phase 6 only *proposes* retirement, and it needs Amr's OK in his own words.

## 1. Rules the folded code must follow

| Rule | Source | What it means for lawmode |
|---|---|---|
| One provider path | constitution §1, [llm-provider-chain.md](llm-provider-chain.md) | Every model call goes through `law_ai.core.llm` and `LLM_PROVIDER_CHAIN` (`claude_code,anthropic_api,xai,ollama`). lawmode's own `llm/` package is not carried over. |
| No further vendor | constitution §1 | The OpenAI backend (`langchain-openai`, default `gpt-4o`) is dropped. No OpenAI or Gemini default is kept or added. |
| Model defaults | constitution §1, `.env.example` | lawmode gets no model default of its own and inherits the chain's defaults (today `CLAUDE_CODE_MODEL=claude-opus-5-5`). An optional `LAWMODE_MODELS` override accepts only `claude-opus-5-5`, `claude-sonnet-5-5` or `claude-haiku-5-5` for the Anthropic tiers. The old `grok-2-1212` default is dropped, and xAI is reached only through the chain's `xai` tier. |
| Provenance | constitution §2 | Every LLM call and tool call is recorded through `law_ai.core.provenance`, with a prompt id and version. |
| HITL | constitution §5/§7 | Critical and high findings become `PendingReview(kind="lawmode_finding")` items. No automated verdict blocks or passes a change. |
| HTTP | constitution §8 | Use `httpx` + `tenacity` with timeouts. Do not use `requests`. |
| No inline prompts | AGENTS.md | Prompts move to `backend/law_ai/agents_runtime/prompts/lawmode/<chain>.v1.md`. |
| CI | constitution §3, hub UPS-REPO-07 | The code is covered by `make lint`, `make typecheck` and `make test` (coverage ≥ 75 %). No build output is committed. Actions spend stays $0. |

## 2. Inventory and destinations

Every tracked file under `lawmode/` (excluding `node_modules`) is listed below, in groups. Python LOC are from `main` @ `6570be8`.

### 2.1 Python package `lawmode/lawmode/` (1,833 LOC across the package)

| Piece | What it is today | Destination | Phase |
|---|---|---|---|
| `cli.py` (275) | A single `click` command `main(target, --diff, -j, -c, -o, -v, --json)`. It has **no `scan` subcommand**, even though the extension calls one. | `backend/law_ai/lawmode/management/commands/lawmode_scan.py` plus `make lawmode-scan`. A `lawmode scan … --json` entry wraps it for the extension. `click`/`rich` are dropped. | P4 |
| `core.py` (282) | `LawModeAgent.review_code`, `generate_artifacts` (writes `.lawmode/`) | `backend/law_ai/lawmode/services/review.py` and `services/artifacts.py` | P1 |
| `models.py` (68) | Pydantic finding and report models | `backend/law_ai/lawmode/schemas.py`, plus a versioned JSON schema `schema/report.v1.json` (P4) | P1 |
| `config.py` (96) | `LLMConfig` (provider `openai`, model `gpt-4o`) and `PolicyConfig` (severity gating) | `PolicyConfig` becomes `backend/law_ai/lawmode/policy.py` plus settings. `LLMConfig` is **dropped**, and model choice belongs to the chain. | P1 |
| `chains/chain_builder.py` (369) | LangGraph pipeline of 8 chains (jurisdiction, domain, privacy, licence, security, accessibility, copyright, regulatory). It uses inline f-string prompts, calls `llm.invoke` directly, and has no provenance. | `backend/law_ai/agents_runtime/graphs/code_legal_review.py` on `law_ai.core.llm.langchain.ChatProviderChain`. Prompts move to `agents_runtime/prompts/lawmode/*.v1.md`. A HITL node is added. | P2 |
| `llm/base.py`, `llm/factory.py` (68), `llm/grok.py` (111) | Its own provider layer: OpenAI via `ChatOpenAI`, and Grok via raw `requests.post` | **Not ported.** It is replaced by `law_ai.core.llm`. | P1 |
| `tools/courtlistener.py` | A CourtListener v3 search **stub** with no HTTP call | Reuse `backend/law_ai/ingestionapp/sources/courtlistener.py` | P3 |
| `tools/eurlex.py`, `tools/spdx.py` | Stubs with no HTTP call | `backend/law_ai/agents_runtime/tools/{eurlex,spdx}.py` on `httpx` + `tenacity`, **or dropped** if the chains do not need them (spec OQ-2) | P3 |
| `tools/scholar.py` | A stub that builds a Google Scholar URL | **Dropped**. No scraping. | P3 |
| `tools/base.py` | `LegalTool` wrapper | Replaced by the agents-runtime tool convention | P3 |
| `github/app.py` (44), `github/pr_reviewer.py` (140) | A PR event handler that posts comments and status checks | Not ported in phases 1–5. Posting to PRs is deferred to BL-20261112-11, behind HITL and Amr's OK. | — |
| `__init__.py` files | Package markers | Recreated in the new app | P1 |

### 2.2 Tests and examples

| Piece | Destination | Phase |
|---|---|---|
| `tests/test_config.py`, `tests/test_models.py`, `tests/test_tools.py` | Rewritten against the new modules in `backend/tests/lawmode/`, with mocked providers and HTTP | P1–P3 |
| `tests/integration/test_grok*.py` (4), `test_local.py`, `README.md` | **Not ported.** They call live APIs. An optional `@pytest.mark.integration` test against a local Ollama may replace them. | P2 |
| `examples/debug_agent.py`, `debug_chains.py`, `debug_llm.py`, `example_scan.py` | Folded into `docs/lawmode.md` usage examples. The debug scripts are not ported. | P4 |
| `vscode-extension/test_files/test_{clean,gdpr,gpl}.py` | `backend/tests/lawmode/fixtures/repo/`, shared by the CLI (AC-1) and extension tests | P4 |

### 2.3 VS Code extension `lawmode/vscode-extension/`

| Piece | Destination | Phase |
|---|---|---|
| `src/extension.ts`, `src/client.ts`, `src/diagnostics.ts`, `src/types.ts` | `extensions/vscode-lawmode/src/` (location is spec OQ-3). `client.ts` moves from `child_process.exec` with an interpolated string to `execFile` with an argument array. `types.ts` follows JSON schema v1. | P5 |
| `package.json` (commands `lawmode.scan`, `lawmode.scanWorkspace`, `lawmode.showRisks`), `package-lock.json`, `tsconfig.json`, `.vscodeignore` | Same folder. Add `lint`, `typecheck` and `test` npm scripts, run by root `make lint` / `make typecheck` / `make test` in `node:20-alpine` (as `make test-lsat-static` does). | P5 |
| `out/*.js`, `out/*.js.map` (8 committed build files) | **Not copied.** `out/` goes in `.gitignore` in the new location. The old copies are removed only in P6. | P5 / P6 |
| `test-mock.js`, `test-extension.md`, `.vscode/` (2), `README.md` | Replaced by real unit tests and `docs/lawmode.md` | P5 |

### 2.4 Configuration, packaging and docs

| Piece | Destination | Phase |
|---|---|---|
| `.lawmode/policy.yaml` | Defaults in `backend/law_ai/lawmode/policy.py`. Per-repo YAML is deferred (BL-20261112-10, which needs PyYAML). | P1 |
| `.lawmode/risks.yaml`, `review.json`, `mitigations.md` | Sample outputs, which become test fixtures and doc examples | P4 |
| `.lawmode/DISCLAIMER.md`, `LAWYER_MODE_IS_ALWAYS_ON.md`, `DISCLAIMER.md` | One disclaimer in `backend/law_ai/lawmode/disclaimer.md`, printed with every report | P1 |
| `.github/workflows/lawmode.yml` | Nested, so GitHub never runs it. It is replaced by the root CI coverage in P5. A PR-review workflow is deferred (BL-20261112-11). | P5 |
| `pyproject.toml`, `requirements.txt`, `setup.py` | Not ported. The code uses `backend/pyproject.toml`, and **no new dependency** is added (spec NFR-DEP-1). | P1 |
| `Dockerfile`, `docker-compose.yml`, `.dockerignore`, `Makefile` | Not ported. The code runs in the backend image via `make lawmode-scan`. | P4 |
| `.env.example` | Settings documented in root `.env.example` (`LAWMODE_MODELS`, `LAWMODE_JURISDICTIONS`). There are no OpenAI keys. | P1 |
| `README.md`, `INSTALL.md`, `QUICKSTART.md`, `IMPLEMENTATION.md`, `PRD.md` | Consolidated into `docs/lawmode.md` and PRD §5.8 | P4 |
| `CHANGELOG.md`, `LICENSE` (MIT) | Kept with the old tree until P6. The MIT notice is preserved in `docs/lawmode.md` credits when code is ported. | P4 / P6 |
| `.editorconfig`, `.gitignore`, `.vscode/` (3), `tools/unwrap-prose.py` | Duplicates of root tooling. They go when the old tree goes (P6). | P6 |
| `CLAUDE.md` | An agent-config file for the old repo. **It is not edited by any phase.** It is removed only with the old tree in P6, with Amr's OK. | P6 |

## 3. Phases

Each phase gets one handoff issue for Claude Code and one draft PR. Each PR carries `Governed by: PRD §5.8 / LAWAI-022 / spec 057`. The handoff issues stay `agent:blocked` until Amr merges this plan, which ratifies PRD §5.8 (hub constitution §28.1).

| Phase | Scope | Acceptance |
|---|---|---|
| **P1** | Port the core (`law_ai.lawmode` app, schemas, policy, review service) to `law_ai.core.llm`, with settings validation | spec AC-6. `make lint && make typecheck && make test` green |
| **P2** | `code_legal_review` graph with 8 versioned prompts, provenance, and the `lawmode_finding` HITL kind | spec AC-2, AC-3 |
| **P3** | Research tools on `httpx` + `tenacity`. Reuse CourtListener and drop Scholar. | No `requests` imports, tools tests green |
| **P4** | `lawmode_scan` command, `make lawmode-scan`, JSON v1, `docs/lawmode.md` | spec AC-1 |
| **P5** | VS Code extension under law-ai CI | spec AC-4, AC-5 |
| **P6** | **Proposal only. Needs Amr's OK in his own words.** Remove or archive `lawmode/`, including the nested workflow, committed `out/` and `lawmode/CLAUDE.md`. Archive `bamr87/lawmode`. Update README and AGENTS layout. | spec AC-7 holds until approval |

From P1 on, the old `lawmode/` tree is frozen: no features and no fixes. Fixes land in the folded code.

## 4. Proposed later step: retiring the old pieces (needs Amr's OK)

After P1–P5 ship and `LAWAI-022` is `shipped`, the old `lawmode/` tree is dead weight. This plan **proposes** these steps, and none of them happens without Amr approving it in his own words on #226 or on the Phase 6 issue:

1. Delete `lawmode/` from law-ai, or move it to `docs/history/`. This includes `lawmode/CLAUDE.md`, the inert nested workflow and the committed `vscode-extension/out/`.
2. Archive the upstream `bamr87/lawmode` repository. This is a repository settings change, so Amr does it or explicitly approves it.
3. Remove the `lawmode/` rows from `README.md` and `AGENTS.md`.

An agent saying that Amr agreed is not approval.

## 5. Open questions

The spec carries OQ-1 (how the extension reaches the CLI), OQ-2 (whether to keep the EUR-Lex and SPDX lookups) and OQ-3 (where the extension lives). Each is resolved in the phase that needs it, and the answer is recorded in the spec before code lands.
