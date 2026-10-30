# Spec: Commit the first real LegalBench baseline

- **ID**: 056-legalbench-baseline
- **Status**: draft
- **Owner**: @bamr87
- **Created**: 2026-10-18
- **Roadmap Epic**: constitution §3 / §10 — a LegalBench baseline "established and tracked in CI" that the 1 pp regression gate can actually compare against
- **Constitution Compliance**: confirmed against [docs/constitution.md](../../docs/constitution.md). §1: the harness stays pinned to one local Ollama model and does **not** route through `LLM_PROVIDER_CHAIN` ("Evals stay pinned"); no hosted model, no Anthropic or xAI call, no prompt text leaves the runner. §3: the ≤ 1 pp per-subset regression rule is kept exactly as written. §4: per-item and per-run events go through `law_ai.core.audit_jsonl` (JSONL-first). §8: no new dependency, no secret. §12 I1: the only automated output is an artifact; the baseline reaches `main` through a human-reviewed PR. §13: answered in §2.

## 1. Problem & Motivation

Every reasoning change in this repo is supposed to be held to "no listed LegalBench subset drops more than 1 pp" (constitution §3), and constitution §10 marks "LegalBench baseline established and tracked in CI" as **Met**. Neither is true in practice: `backend/var/legalbench/baseline.json` has never been committed, both rows of the `docs/legalbench.md` "Baseline scores" table read `_TBD_`, and with no baseline `--check-regression` prints "no baseline.json to compare against" and exits 0. The gate therefore passes every change by construction.

The machinery around the number is in place. The real dataset fetcher (BL-20260811-09), deterministic decoding (`temperature=0, seed=0`), the exit-2 "could not run" path, `--fail-on-synthetic` (BL-20260811-10) and model/scorer comparability (BL-20260906-29) all shipped through spec 031 and spec 052. Spec 052 claimed the baseline itself and recorded it as blocked: the gate model could not load on the sweep host for lack of free RAM (BL-20260906-28).

Two newer facts change what is possible. The repository is now **public**, so GitHub-hosted standard runners cost $0 and the harness needs no secret (Ollama is local, the dataset is public). And the most recent nightly run (run `38212032910`, started 2026-10-17 20:53 MDT) shows the "Pull the LegalBench gate model" step **succeeding** on a hosted runner — the LegalBench steps were then *skipped* only because the unrelated "Run test coverage" step failed (4 failing integration tests) earlier in the same job. The blocker is no longer hardware; it is workflow ordering and a missing, reviewed procedure for producing and committing the number.

A first baseline is also only useful if later runs can prove they are comparable to it. Today `baseline.json` would record the model tag and scorers but not the model digest, the Ollama version, the dataset revisions or manifest hash, the per-task cap, the decoding options, or how many items errored. Several of those can change silently (an Ollama tag can be re-pushed; a CPU-bound item can time out and drop out of the denominator), and each one would turn the 1 pp gate into a comparison of two different measurements.

## 2. Origin & Background

- Backlog items claimed: **BL-20260906-28** (record and commit the first real LegalBench baseline, high) moves from `## Open` to `## Claimed`, `claimed-by:specs/056-legalbench-baseline`. **BL-20260906-34** (prove the LegalBench scored gate green once, med) is claimed alongside it because the hosted-runner path in this spec is that proof. **BL-20260811-10** and **BL-20260810-04** stay in `## Claimed` but are re-pointed `claimed-by:specs/056-legalbench-baseline (was specs/052-backlog-zero)`: spec 052 shipped everything in them except the baseline number, and recorded the remainder as blocked; this spec owns that remainder. No entry is deleted.
- Related, not claimed: **BL-20260511-06** (LegalAnalyst/PrecedentHunter backfill) lists "once the LegalBench baseline lands" as its one undemonstrated precondition; this spec produces that precondition but does not close the item. **BL-20260906-29** (comparability check) is the shipped mechanism FR-6 extends.
- Prior art: spec 018 (harness, `LICENSES.md`), spec 031 (truthful measurement: paths, exit codes, history, scorers), spec 052 package P09b_eval (fetcher at pinned revisions, `--fail-on-synthetic`, nightly model-pull step), [docs/legalbench.md](../../docs/legalbench.md), [backend/var/legalbench/LICENSES.md](../../backend/var/legalbench/LICENSES.md).
- **Review question (constitution §13)** — *who is the stronger here, and what does this feature do for them?* This feature scores a **model** against a benchmark; it does not rank, score, or summarise legal authority for a user. One subset deserves the question anyway: `precedent_retrieval` (`citation_prediction_classification`, `citation_prediction_open`) rewards a model for reproducing the citation an opinion's authoring court chose. The stronger party there is the authoring court and the litigants whose briefing shaped that opinion — the record of what the winning side got a court to cite. A high `precedent_retrieval` score measures agreement with that record, not legal correctness, and `docs/legalbench.md` must say so in the baseline table (FR-11). Nothing in this spec feeds benchmark accuracy into retrieval ranking or presents it to end users.

## 3. Goals

- G1: A real, reviewed `backend/var/legalbench/baseline.json` is on `main`, and the `docs/legalbench.md` baseline table carries its numbers and commit SHA.
- G2: The baseline records everything that defines the measurement, so any later run either is provably comparable or fails loudly as incomparable.
- G3: The baseline can be produced, and the gate run, on a GitHub-hosted runner at $0 with no secrets, on demand (`workflow_dispatch`).
- G4: The scored gate in nightly is no longer skipped because an unrelated step failed.

## 4. Non-Goals

- NG1: New subsets. `contract_nli`, `definitions` and `causation` are fetchable today but are not part of the gate; adding them is follow-up BL-20261018-01.
- NG2: A hosted-model (Anthropic or xAI) baseline. Constitution §1 says LegalBench does not route through the chain and gains no hosted mode; a reference lane on `claude-sonnet-5-5` would need an ADR amending §1 first (follow-up BL-20261018-02, OQ-3).
- NG3: Running the scored eval on pull requests. PR CI keeps the `reasoning-change`-labelled harness self-check only; a 7B CPU run does not fit a PR feedback loop.
- NG4: Changing the 1 pp tolerance or the scorers. Both are constitution-level or baseline-reset decisions (OQ-2).
- NG5: Fixing the four failing nightly coverage tests. FR-9 stops them from hiding the LegalBench result; the fix itself is follow-up BL-20261018-03.

## 5. User Stories

- As Amr, I want one button (`gh workflow run legalbench-baseline.yml`) that produces a baseline file I can review and commit, so the regression gate stops passing by default.
- As a contributor changing a prompt or retriever, I want `make test-legalbench-gate` to tell me "you regressed", "the eval could not run", or "this run is not comparable to the baseline" — never a silent pass.
- As a reviewer, I want the baseline PR to show exactly which model digest, dataset revision, decoding options and item counts produced the numbers, with the LegalBench licence and citation alongside.

## 6. Functional Requirements

- **FR-1 (task subset)**: The baseline covers exactly the two gated subsets, `core_reasoning` (`hearsay`, `personal_jurisdiction`, `ucc_v_common_law`, `abercrombie`) and `precedent_retrieval` (`citation_prediction_classification`, `citation_prediction_open`), as mapped in `SUBSET_TASKS` (`backend/law_ai/eval/fetch.py`), each task capped at `DEFAULT_MAX_ITEMS_PER_TASK` = 50 and round-robined — at most 300 items. The actual per-task and per-subset `n` is recorded, not assumed.
- **FR-2 (dataset sourcing)**: Items come only from `make legalbench-cache` at the pinned revisions — Hugging Face `nguha/legalbench` at `DATA_REVISION` `daec8237410aa23e3faf4bc41ad8b3a7e1696826` and GitHub `HazyResearch/legalbench` at `PROMPT_REVISION` `b46bf4ffae90524b2b72aaa30e7745fe9db64481` — with the manifest sha256 check enforced and the per-task licence check (`ALLOWED_LICENCES`) passing. `items.jsonl` stays git-ignored and is never committed.
- **FR-3 (pinned run config)**: One gate model, declared once as a Make variable `LEGALBENCH_MODEL ?= mistral:7b-instruct-q4_K_M` and passed explicitly as `--model` by `test-legalbench`, `test-legalbench-gate` and `legalbench-baseline` (today `legalbench-baseline` inherits `OLLAMA_DEFAULT_MODEL`, which the GPU overlay sets to a 70B model). The nightly pull step and the new workflow read the same value. The Ollama server is the compose-pinned `ollama/ollama:0.12.6`. Decoding stays `temperature=0.0, seed=0` and additionally pins `num_ctx` and `num_predict` in the request `options` so a server-default change cannot truncate a few-shot prompt or an answer.
- **FR-4 (provider pin)**: The harness keeps calling Ollama directly via `_call_ollama()` and never `law_ai.core.llm`; `LLM_PROVIDER_CHAIN` is not consulted, and no Anthropic, xAI or other hosted model is reachable from a baseline or gate run. This is the constitution §1 "Evals stay pinned" carve-out from the §4 choke-point rule, and the spec records it rather than working around it.
- **FR-5 (baseline schema v2)**: `--update-baseline` writes `baseline.json` with `schema_version: 2` and, additively to today's `model`/`timestamp`/`run_id`/`accuracies`/`scorers`: `model_digest` (from Ollama `/api/show` or `/api/tags`), `ollama_version` (`/api/version`), `options` (the exact decoding options sent), `data_revision`, `prompt_revision`, `manifest_sha256`, `max_items_per_task`, `git_sha`, `runner` (`github-hosted` or `workstation`, plus OS/arch), and per subset `n`, `scored`, `errored`, `correct`, `tasks` (per-task `n`/`correct`). It also writes `item_outcomes` — `{subset: {item_index: 0|1}}` — and its sha256 as `item_outcomes_sha256`. `item_outcomes` holds item indices and booleans only, no task text, prompts, answers or model output, so committing it redistributes no LegalBench content.
- **FR-6 (comparability)**: `baseline_comparability()` treats a run as not comparable when any of `model_digest`, `ollama_version`, `options`, `data_revision`, `prompt_revision`, `manifest_sha256`, `max_items_per_task` or a subset's `scorer` differs from a v2 baseline (a v1 baseline keeps today's model+scorer check).
- **FR-7 (regression gate)**: `--check-regression` exits `1` when any tracked subset's accuracy is more than `REGRESSION_TOLERANCE_PP` (1.0 pp) below the baseline (constitution §3, unchanged). It exits with a new distinct code `3` when a baseline file is present but the run is not comparable (FR-6), and when `--require-baseline` is passed and no baseline exists; `test-legalbench-gate` passes `--require-baseline` once T-008 lands. Exit `2` keeps meaning "could not run". The silent exit-0 skip is removed from the gated path.
- **FR-8 (baseline refusals)**: `--update-baseline` refuses (exit 1, no file written) a run that used synthetic stubs (today), any `--limit` (the cap is part of the measurement), or any item with `errored > 0`. A read timeout from Ollama (`TimeoutError`/`socket.timeout`, which `urllib` does not wrap in `URLError` on a read) is caught and counted as an errored item rather than crashing the run, and the per-item timeout is a setting `LEGALBENCH_ITEM_TIMEOUT_S` (default 300 on CPU) instead of the hard-coded 120.
- **FR-9 (CI vs manual)**: A new `.github/workflows/legalbench-baseline.yml`, `workflow_dispatch` only, on `ubuntu-latest`, with `permissions: contents: read` and no secrets: it frees disk, builds the backend image, starts only the services the harness needs, pulls `LEGALBENCH_MODEL`, runs `make legalbench-cache`, runs the eval twice with `--update-baseline` written to two separate paths, fails if the two `item_outcomes_sha256` values differ, and uploads `baseline.json`, both reports and `history.jsonl` as a 90-day artifact. It never pushes, never opens a PR and holds no permission that could merge one (I1). In `nightly-tests.yml` the four LegalBench steps run when not `dry_run` and not `cancelled()`, so a failing coverage step no longer skips the scored gate. The manual workstation path (`make legalbench-cache && make legalbench-baseline`) stays documented, but the **committed** baseline comes from the hosted runner, because that is the hardware the nightly gate compares on.
- **FR-10 (versioning)**: `baseline.json` changes only in a PR that also updates the `docs/legalbench.md` baseline table (scores, run id, baseline commit SHA, runner) and states which FR-6 field changed and why. A change to the model, Ollama version, dataset revision, manifest, cap, decoding options or a scorer is a baseline reset and must be re-recorded in the same PR. Git history of the file is the version history; the old values are never edited in place.
- **FR-11 (attribution)**: `docs/legalbench.md` and `backend/var/legalbench/LICENSES.md` carry, next to the baseline table: the LegalBench citation (Guha et al., "LegalBench: A Collaboratively Built Benchmark for Measuring Legal Reasoning in Large Language Models", NeurIPS 2023 Datasets and Benchmarks Track, arXiv:2308.11462), the dataset licence per task as read by the fetcher (CC BY 4.0 for all six gated tasks at the pinned revision), the code licence (MIT), both pinned revisions, and each task's own source line copied from its README at `PROMPT_REVISION`. The `precedent_retrieval` row states that it measures agreement with the citing court's choice, not correctness (§13).
- **FR-12 (provenance)**: Each `legalbench.item` event additionally carries `prompt_sha256`, `response_sha256`, `model_digest` and `data_revision`; a successful `--update-baseline` writes one `legalbench.baseline_recorded` event with the baseline's sha256 and the FR-5 header fields. Events go through `law_ai.core.audit_jsonl` (JSONL-first, Postgres mirror best-effort). The stale module docstring in `legalbench.py` that claims per-item OpenTelemetry spans is corrected to match `docs/legalbench.md`.

## 7. Non-Functional Requirements

- **NFR-COST-1**: $0 hosted-model spend (no hosted model is called) and $0 Actions spend (standard GitHub-hosted runner on a public repository). If the repository goes private again, `legalbench-baseline.yml` stays manual-only and the docs say the run then bills Actions minutes.
- **NFR-PERF-1**: One full run (≤ 300 items, CPU, 4 vCPU / 16 GB hosted runner) must finish inside the 360-minute job limit; the workflow sets `timeout-minutes: 330` and records the measured wall-clock per subset in the report so the budget is visible.
- **NFR-DET-1**: Two back-to-back runs on the same runner with the same FR-5 header produce identical `item_outcomes_sha256`; if they do not, the run is reported as non-deterministic and no baseline is accepted.
- **NFR-SEC-1**: No secret, token or credential is read or required; the dataset fetch uses the existing stdlib `fetch.py` (outbound HTTPS to Hugging Face and GitHub raw only).
- **NFR-AUDIT-1**: Every item and every baseline write is logged via `law_ai.core.audit_jsonl` per FR-12, with `source="legalbench"`, `agent_version`, and `confidence`.
- **NFR-HITL-1**: `human_approval_required` does not apply (no ingestion, no new agent, no schema migration); the human gate is the baseline PR itself, reviewed by Amr, as constitution §10 / I1 require.
- **NFR-DOCKER-1**: Every eval command runs through `make` inside the backend container; nothing runs on the host except `make`, `docker compose`, the stdlib validators, `git` and `gh`.

## 8. Data Model Impact

No Neo4j node, edge or Postgres table changes. `baseline.json` gains the FR-5 fields (schema v2, additive; v1 files stay readable). `history.jsonl` rows gain `model_digest`, `data_revision` and `errored` per subset where missing. Audit events gain the FR-12 fields; `AuditEvent` stores payloads as JSON, so no migration.

## 9. API Surface

None. The change is to a CLI (`python -m law_ai.eval.legalbench`: new `--require-baseline` flag, new exit code 3), three Make targets, two workflows and docs.

## 10. Agent / Crew Impact

No agent is added or modified. The baseline is the precondition BL-20260511-06 names for demonstrating `LegalAnalyst` / `PrecedentHunter` parity on `LegalWorkflow`, and every later spec that changes prompts, retrievers or workflow graphs is measured against it.

## 11. Acceptance Criteria

- **AC-1**: Given a cached dataset at the pinned revisions, when `legalbench-baseline.yml` is dispatched on `main`, then the job completes within NFR-PERF-1, both runs report `errored = 0`, their `item_outcomes_sha256` match, and the artifact contains a schema-v2 `baseline.json` with every FR-5 field populated.
- **AC-2**: Given that artifact, when it is committed in a PR with the filled `docs/legalbench.md` table and that PR merges, then `make test-legalbench-gate` on the same runner class against the same header exits 0 and prints per-subset deltas of 0.00 pp.
- **AC-3**: Given a committed baseline, when a run differs from it in any FR-6 field (unit-tested with a fabricated report per field), then `--check-regression` exits 3 and names the field.
- **AC-4**: Given a committed baseline, when a fabricated report drops one subset by 1.01 pp, then `--check-regression` exits 1; at exactly 1.00 pp it exits 0.
- **AC-5**: Given `--update-baseline`, when the run used stubs, `--limit`, or had any errored item, then no file is written and the process exits 1 with the reason.
- **AC-6**: Given an Ollama stub that sleeps past `LEGALBENCH_ITEM_TIMEOUT_S` on a read, when the harness runs, then the item is counted as errored and the run does not crash with a traceback.
- **AC-7**: Given `make -n test-legalbench test-legalbench-gate legalbench-baseline`, then each expands with `--model mistral:7b-instruct-q4_K_M` (or the overridden `LEGALBENCH_MODEL`), and the nightly pull step and the new workflow use the same variable.
- **AC-8**: Given a nightly run whose "Run test coverage" step fails, then "Run LegalBench eval (regression gate)" still executes (asserted by a repo-level test that parses `nightly-tests.yml` for the step's `if:` expression).
- **AC-9**: Given `legalbench-baseline.yml`, then a repo-level test asserts it is `workflow_dispatch`-only, declares `permissions: contents: read`, references no `secrets.` expression, and contains no `git push`, `gh pr` or merge step.
- **AC-10**: Given a run, then every `legalbench.item` event carries the FR-12 fields, and `--update-baseline` emits exactly one `legalbench.baseline_recorded` event.
- **AC-11**: Given `docs/legalbench.md` after the baseline PR, then the table has no `_TBD_`, names the run id, baseline commit SHA and runner, carries the FR-11 citation and licences, and the `precedent_retrieval` row carries the §13 label.

## 12. LegalBench Impact

- Tasks affected: `core_reasoning` (hearsay, personal_jurisdiction, ucc_v_common_law, abercrombie) and `precedent_retrieval` (citation_prediction_classification, citation_prediction_open).
- Expected delta: none defined — this spec establishes the first baseline those deltas are measured against. Implementation tasks T-001 to T-006 change harness plumbing only (options, timeouts, metadata, exit codes); no prompt, scorer or retriever changes, and the decoding pin of `num_ctx`/`num_predict` lands **before** the baseline is recorded so it is part of the measured configuration.

## 13. Risks & Open Questions

- **R-1**: CPU inference on a 4-vCPU hosted runner may be slow; ~300 items with LegalBench few-shot prompts could take hours. Mitigation: NFR-PERF-1 budget, per-subset wall-clock in the report, FR-8 timeout setting; if the budget is blown, OQ-4 decides.
- **R-2**: llama.cpp output can differ across CPU microarchitectures even at temperature 0, so a hosted runner on a different CPU generation could flip items. Mitigation: NFR-DET-1 double run; `runner` recorded; a gate failure that traces to hardware is reported as such in the PR, not "fixed" by widening the tolerance.
- **R-3**: With ≤ 100 `precedent_retrieval` items, 1 pp is one item: a single flip fails the gate. This is what constitution §3 says; OQ-2 asks whether Amr wants that.
- **R-4**: The hosted-runner disk budget (model ~4.4 GB plus images) has failed nightly before. Mitigation: the new workflow starts only `ollama` and its backend dependencies, and reuses the nightly disk-cleanup step.
- **R-5**: Constitution §10 already marks "LegalBench baseline established and tracked in CI" as **Met** although no baseline exists. This spec makes the claim true rather than editing the constitution, which would need an ADR and maintainer review.

> [OPEN QUESTION OQ-1]: Which host produces the committed baseline — the GitHub-hosted `ubuntu-latest` runner via `legalbench-baseline.yml` (recommended: it is the hardware nightly compares on, $0 on a public repo, no secrets), or Amr's workstation via `make legalbench-baseline` (faster, but Apple-silicon/GPU output may not match the hosted CPU gate)?

> [OPEN QUESTION OQ-2]: Keep the 1 pp tolerance literally per subset (constitution §3; on `precedent_retrieval` that is a single item), or open an ADR to express it as max(1 pp, N items) or a confidence interval? Recommended: keep 1 pp for this spec, report item counts next to every delta, and revisit after the first few gated runs (follow-up BL-20261018-04).

> [OPEN QUESTION OQ-3]: Do you want a non-gating *reference* lane on an Anthropic model (`claude-sonnet-5-5`, pinned `LLM_PROVIDER_CHAIN=anthropic_api`, through `law_ai.core.llm` with `llm_call` provenance)? Constitution §1 currently forbids LegalBench routing through the chain, so this needs an ADR first, and it would cost real API money per run (≤ 300 items) and need the `ANTHROPIC_API_KEY` secret. Recommended: not in this spec (BL-20261018-02).

> [OPEN QUESTION OQ-4]: If a full hosted CPU run does not fit the 330-minute budget, which do you prefer — split the two subsets into two jobs, run the baseline on a workstation (see OQ-1), or lower `DEFAULT_MAX_ITEMS_PER_TASK` (a baseline reset that changes what "accuracy" means)?

> [OPEN QUESTION OQ-5]: The `nightly-tests.yml` schedule is commented out because Actions in the then-private repo were refused by the billing block (bamr87/bamr87#268). Now that the repo is public, should the weekly Monday 06:00 UTC schedule be restored as part of this spec, or stay `workflow_dispatch`-only until the coverage failures (BL-20261018-03) are fixed?

## 14. Out of Scope / Follow-ups

- New subsets in the gate (BL-20261018-01), a hosted reference lane (BL-20261018-02), the four failing nightly coverage tests (BL-20261018-03), an item-count-aware tolerance (BL-20261018-04), CODEOWNERS/label protection for `baseline.json` (BL-20261018-05), and per-item flip reporting from `item_outcomes` (BL-20261018-06). See `tasks.md` § Follow-ups Discovered.
