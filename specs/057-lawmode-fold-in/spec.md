# Spec: Fold lawmode into law-ai

- **ID**: 057-lawmode-fold-in
- **Status**: draft
- **Owner**: @bamr87
- **Created**: 2026-11-12
- **Roadmap Epic**: [#226](https://github.com/bamr87/law-ai/issues/226) (decision relayed from Amr via Grok Bot, 2026-11-12: fold lawmode into law-ai; not revived standalone, not retired) · PRD [§5.8](../../docs/prd.md) · catalog `LAWAI-022`
- **Constitution Compliance**: confirmed against [docs/constitution.md](../../docs/constitution.md). §1: every lawmode LLM call moves onto `law_ai.core.llm` (`LLM_PROVIDER_CHAIN`, default `claude_code,anthropic_api,xai,ollama`), so `ollama` stays reachable and no further vendor is added; lawmode's OpenAI backend (`langchain-openai`, default `gpt-4o`) and its raw-`requests` Grok client are **not** carried over, and lawmode gets no model default of its own. §2: every call is recorded through `law_ai.core.provenance`. §5/§7: high and critical findings become HITL items, and nothing is posted to a pull request or blocks a merge without a human. §8: `httpx` + `tenacity`, no `requests`; this spec adds **no** new runtime dependency. §11: the migration code is written by Claude Code from the handoff issues, not by the planning bot (hub constitution §26).

## 1. Problem & Motivation

`lawmode/` is the imported [bamr87/lawmode](https://github.com/bamr87/lawmode) "legal reviewer for developers": a CLI, a LangGraph pipeline of eight legal-risk chains (jurisdiction, domain, privacy, licence, security, accessibility, copyright, regulatory), a GitHub PR reviewer and a VS Code extension. It sits in the law-ai tree but outside every law-ai rule. Deep dive issue #226 found that:

- it defaults to OpenAI (`LLMConfig.provider="openai"`, `model="gpt-4o"`), a vendor constitution §1 rejects, and calls `llm.invoke` directly with no provider chain, no provenance and no HITL;
- its prompts are inline f-strings (AGENTS.md forbids inline prompts), and its Grok client and tools use raw `requests`;
- its research "tools" (CourtListener, EUR-Lex, Google Scholar, SPDX) are stubs that never make a request;
- its CLI is a single `click` command, but the VS Code extension runs `lawmode scan <file> --json`, a subcommand that does not exist, so the extension cannot work;
- the extension builds its shell command by string interpolation (`child_process.exec`), and its build output (`out/*.js`, `*.js.map`) is committed (hub UPS-REPO-07);
- its workflow is nested at `lawmode/.github/workflows/lawmode.yml`, so GitHub never runs it, and no law-ai Make target or CI job lints, type-checks or tests a line of it.

Amr has decided the code is **folded into law-ai**: the useful parts become a first-class law-ai feature that obeys the constitution and runs under law-ai CI.

## 2. Origin & Background

- Origin: law-ai deep dive cycle 1 day 14 (2026-11-12), issue [#226](https://github.com/bamr87/law-ai/issues/226) ("lawmode/: decide fold-in, revive or retire"), decision relayed from Amr via Grok Bot on 2026-11-12: **fold in**.
- Backlog items: this spec files BL-20261112-09 … BL-20261112-12 (see `## Follow-ups Discovered` in [tasks.md](tasks.md)); it claims none.
- Prior art reused, not rebuilt: `law_ai.core.llm` (spec 034, ADR 0005, ADR 0007), `law_ai.core.provenance`, the `PendingReview` HITL queue (spec 015; `ingestionapp/quarantine_kinds.py`), versioned prompts under `backend/law_ai/agents_runtime/prompts/`, the CourtListener source in `backend/law_ai/ingestionapp/sources/courtlistener.py`.
- The migration plan, with the full file-by-file inventory and destination of every lawmode piece, is [docs/lawmode-migration.md](../../docs/lawmode-migration.md).
- **Review question (constitution §13)** — *who is the stronger here, and what does this feature do for them?* lawmode **scores** legal risk in source code (critical / high / medium / low) against jurisdictions and regulations, and a score can gate a merge. The stronger party is whoever owns the repository being scanned, or a platform that could use an automated "legally fine" verdict to ship over the objections of the people its code affects (data subjects, users who need accessibility, upstream licensors). The fold-in therefore makes the score *advisory*: every finding cites the authority or licence it relies on with provenance, a high or critical finding goes to a human through the HITL queue rather than auto-blocking or auto-passing, a clean scan is reported as "no findings from these checks", never as "compliant", and every output carries the lawmode disclaimer (not legal advice).

## 3. Goals

- G1: lawmode's legal-risk review runs inside the law-ai backend as `law_ai.lawmode`, with every LLM call on `LLM_PROVIDER_CHAIN`, every call recorded through provenance, and high/critical findings routed to HITL.
- G2: The moved code is under law-ai CI: `make lint`, `make typecheck`, `make test` and the coverage gate cover it, and the VS Code extension has its own lint/typecheck/test in the same `make` targets.
- G3: The CLI and the VS Code extension agree on one JSON contract, and the extension can actually run a scan.
- G4: Retiring the old `lawmode/` tree is a separate, explicit later step that only happens with Amr's OK.

## 4. Non-Goals

- Reviving lawmode as a standalone product, package or repository.
- Archiving, deleting or retiring any part of `lawmode/` or the `bamr87/lawmode` repository in this spec's implementation phases (Phase 6 only proposes it; see FR-10).
- A GitHub Actions workflow that comments on, or sets status checks on, law-ai pull requests (deferred: BL-20261112-11).
- Publishing the VS Code extension to the Marketplace (deferred: BL-20261112-12).
- Adding OpenAI, Gemini or any provider outside constitution §1.
- Changing LegalBench scope or the eval pins.

## 5. User Stories

- **US1:** As a developer on a repository, I run one command (`make lawmode-scan TARGET=…`, or `lawmode scan <path> --json`) and get a list of legal-risk findings, each with a severity, a jurisdiction, the authority or licence it cites and a mitigation, so that I can fix issues before review.
- **US2:** As the law-ai operator (Amr), I know every lawmode model call went through the provider chain and is recorded in the provenance log, so that a scan of private source code never leaves for an unapproved vendor and can be audited later.
- **US3:** As a reviewer, I see high and critical lawmode findings in the HITL queue and decide on them myself, so that no automated legal verdict blocks or passes a change without a human.
- **US4:** As a VS Code user, I run "LawMode: Scan" and see findings as diagnostics in the editor, so that I get the same results as the CLI where I write code.
- **US5:** As a maintainer, I see lawmode code fail `make lint`, `make typecheck` or `make test` like any other law-ai code, so that it does not rot again.
- **US6:** As Amr, I decide when the old `lawmode/` tree is archived or removed, after the folded feature has shipped, so that nothing is lost before its replacement is proven.

## 6. Functional Requirements

- **FR-1**: A Django app `law_ai.lawmode` holds lawmode's domain: the finding/report schemas (Pydantic v2, ported from `lawmode/lawmode/models.py`), the policy (jurisdictions, severity gating, domains; ported from `lawmode/.lawmode/policy.yaml` to Python defaults in `law_ai/lawmode/policy.py`, overridable through settings) and the review service (ported from `lawmode/lawmode/core.py`).
- **FR-2**: Every lawmode LLM call goes through `law_ai.core.llm` (`LLMRequest` → the provider chain). lawmode has no provider client, no `langchain-openai` / `langchain-anthropic` import and no model name in code. With no override it uses the chain's configured models; any lawmode-specific override is read from settings, and an Anthropic override is rejected at startup unless it is `claude-opus-5-5`, `claude-sonnet-5-5` or `claude-haiku-5-5`.
- **FR-3**: The eight review chains run as a LangGraph graph in `backend/law_ai/agents_runtime/graphs/` built on the chain adapter in `law_ai.core.llm.langchain`, each chain's prompt a versioned Markdown file under `backend/law_ai/agents_runtime/prompts/lawmode/` passed with `prompt_id` / `prompt_version`.
- **FR-4**: Each LLM call and each tool call records a provenance event through `law_ai.core.provenance` (scan id, chain, prompt id/version, provider, model, input hash, findings count).
- **FR-5**: Findings at a severity the policy marks `block` or `require_approval` (default: critical, high) create a `PendingReview` item of a new kind `lawmode_finding`; the scan result reports them as "awaiting human review", never as pass/fail.
- **FR-6**: Research tools that lawmode needs are real or absent: CourtListener lookups reuse `ingestionapp/sources/courtlistener.py`; an SPDX licence lookup and an EUR-Lex lookup, if kept, use `httpx` + `tenacity` with timeouts; the Google Scholar stub is dropped (no scraping).
- **FR-7**: A management command `lawmode_scan` (`make lawmode-scan TARGET=… [DIFF=1] [JURISDICTION=…]`) scans a path or a `git diff`, prints a human summary or `--json`, and writes the report artifacts that lawmode wrote under `.lawmode/`. The JSON schema is versioned and documented in `docs/lawmode.md`.
- **FR-8**: The VS Code extension lives under law-ai's tree outside `lawmode/`, runs the scan with `execFile`/`spawn` and an argument array (no shell string), consumes the FR-7 JSON contract, and has no committed build output.
- **FR-9**: law-ai CI covers the moved code: backend code under `make lint` (ruff), `make typecheck` (the mypy ratchet, `scripts/mypy_ratchet.py`) and `make test` with the coverage gate; the extension under `make lint` / `make typecheck` / `make test` via its npm scripts in a `node:20-alpine` container, the same pattern as `make test-lsat-static`. No new paid CI and no new secrets.
- **FR-10**: Retiring the old tree (removing or archiving `lawmode/`, its nested workflow, `lawmode/CLAUDE.md`, and the `bamr87/lawmode` repository) is a separate PR that is opened **only after Amr approves it in his own words** on #226 or the Phase 6 issue.

## 7. Non-Functional Requirements

- **NFR-SEC-1**: All external HTTP via `httpx` with `tenacity` retry and an explicit timeout; no `requests`. The extension never builds a shell command string.
- **NFR-SEC-2**: Scanned source code is sent only to providers in `LLM_PROVIDER_CHAIN`; the docs explain `LLM_PROVIDER_CHAIN=ollama` for code that must not leave the machine.
- **NFR-AUDIT-1**: Every agent/LLM/tool call logged via `law_ai.core.provenance` (FR-4).
- **NFR-HITL-1**: `human_approval_required` is declared for the high/critical path (FR-5); `ENABLE_HUMAN_APPROVAL_GATES=false` is not a lawmode bypass — the scan then reports those findings as unreviewed.
- **NFR-QUAL-1**: New backend code meets the repo coverage gate and mypy settings; no new `# type: ignore` without a reason.
- **NFR-DEP-1**: No new runtime dependency (LangGraph, LangChain core, httpx, tenacity and Pydantic are already in `backend/pyproject.toml`; PyYAML is not a direct dependency, so reading a per-repository `.lawmode/policy.yaml` is deferred to BL-20261112-10). Dropping `click`, `rich`, `gitpython`, `requests`, `langchain-openai` and `langchain-anthropic` is deliberate; if an implementer needs one, the spec is amended first with a licence and security note (constitution §8).

## 8. Data Model Impact

- New `PendingReview.kind` constant `lawmode_finding` (code-only per spec 015 FR-6, no migration).
- Optional `LawmodeScan` model (scan id, target, policy hash, started/finished, findings JSON) — Phase 2 decides; if added, it ships with a migration and admin.

## 9. API Surface

- Management command `lawmode_scan` and Make target `lawmode-scan`.
- A console entry `lawmode` (`scan` subcommand) for the extension, implemented as a thin wrapper over the management command (Phase 4 decides wrapper vs. `docker compose exec`).
- No new HTTP endpoint in this spec.

## 10. Agent / Crew Impact

New graph `code_legal_review` (eight chain nodes plus aggregate and HITL gate) registered with the agents runtime; no change to existing crews.

## 11. Acceptance Criteria

- **AC-1**: Given a repository fixture with a GPL dependency and a hard-coded personal-data field, when `make lawmode-scan TARGET=<fixture> JSON=1` runs with a stubbed provider, then the JSON lists a licence finding and a privacy finding, each with severity, jurisdiction, citation and mitigation.
- **AC-2**: Given the scan above, then every LLM call in it appears in the provenance log with provider, model and prompt id/version, and `git grep -n "openai\|gpt-4o\|requests\." backend/law_ai/lawmode backend/law_ai/agents_runtime/graphs/code_legal_review.py` is empty.
- **AC-3**: Given a critical finding, when the scan finishes, then a `PendingReview` of kind `lawmode_finding` exists, the scan exit code does not signal "blocked" by itself, and the JSON marks the finding `awaiting_review`.
- **AC-4**: Given the extension, when its tests run, then the scan is invoked with an argument array (no shell string) and parses the FR-7 JSON fixture into diagnostics.
- **AC-5**: Given a PR that breaks lawmode Python or TypeScript, then `make lint`, `make typecheck` or `make test` fails in CI.
- **AC-6**: Given an Anthropic model override other than the three allowed ids, then settings validation fails at startup.
- **AC-7**: Until Amr approves Phase 6 in his own words, `lawmode/` is unchanged on `main` by this spec's PRs.

## 12. LegalBench Impact

None: no reasoning path that LegalBench gates changes; evals stay pinned (constitution §1).

## 13. Risks & Open Questions

- **R-1**: Source code sent to hosted tiers may be confidential. Mitigation: NFR-SEC-2 and a docs section on pinning `ollama`.
- **R-2**: An automated legal-risk score can be read as legal advice. Mitigation: disclaimer on every output, advisory wording (§2 review question), HITL for high/critical.
- **R-3**: Two copies (old `lawmode/` and the folded app) drift during migration. Mitigation: the old tree is frozen (no new features) from Phase 1; Phase 6 retires it with Amr's OK.
- **OQ-1**: Does the extension call the CLI in the backend container, a local virtualenv, or a backend HTTP endpoint? Phase 5 resolves; default: the CLI via an argument array, with the command configurable.
- **OQ-2**: Keep EUR-Lex and SPDX lookups or drop them with the other stubs? Phase 3 resolves on evidence (do the chains use them?).
- **OQ-3**: Where does the extension live: `extensions/vscode-lawmode/` (proposed) or under `frontend/`? Phase 5 resolves.

## 14. Out of Scope / Follow-ups

BL-20261112-09 … BL-20261112-12 (see [tasks.md](tasks.md) `## Follow-ups Discovered` and [BACKLOG.md](../../BACKLOG.md)).
