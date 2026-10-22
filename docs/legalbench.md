# LegalBench Evaluation Harness

> How the LegalBench harness runs and scores the tracked subsets, how the real data is cached, and how the baseline and regression gate decide a pass.

> Living evaluation manual for Law AI. The harness lives in [backend/law_ai/eval/](../backend/law_ai/eval/) and is invoked through the `Docker: LegalBench Eval` VS Code task (or `make test-legalbench`).

## Purpose

[LegalBench](https://github.com/HazyResearch/legalbench) is the 162-task collaborative benchmark for legal reasoning in LLMs (Stanford / HazyResearch / contributors). Law AI uses it as the **mandatory regression suite** for any change that touches reasoning — agent prompts, retrieval strategy, model defaults, or workflow graphs. Per [docs/constitution.md](constitution.md) §3 and §6, a regression of more than **1 pp** on a listed task blocks the PR.

**The harness is pinned to a fixed local Ollama model — it does not route through `LLM_PROVIDER_CHAIN`** (constitution §1; see `_call_ollama()` in [legalbench.py](../backend/law_ai/eval/legalbench.py)). This is deliberate even though Claude is now the default provider for the product runtime (spec 034): the harness measures one named model against a fixed benchmark, and a silent fallback to a different provider would silently change what is being measured, making the 1 pp regression policy meaningless. Point the harness at a different model with `--model`, never by letting the provider chain choose.

## Task subsets we track

The harness defaults to two named subsets:

| Subset                | What it covers                                                                 | Why it matters for Law AI |
|-----------------------|--------------------------------------------------------------------------------|-----------------------------|
| `core_reasoning`      | Rule-application, issue spotting, conclusion derivation across mixed domains   | Baseline for the `LegalAnalyst` crew (IRAC quality) |
| `precedent_retrieval` | Identification + ranking of relevant prior cases given a fact pattern          | Baseline for the `PrecedentHunter` crew + GraphRAG  |

Additional subsets (e.g. `contract_nli`, `definitions`, `causation`) can be enabled per-spec; record the chosen list in the spec's `## Evaluation` section, and add the name to the `ALLOWED_SUBSETS` allow-list in `legalbench.py` (constitution §3 permits only tracked subsets without a spec amendment).

## Running the harness

**One-liner (VS Code):** run the `Docker: LegalBench Eval` task, or `make test-legalbench` from a shell.

**CLI equivalent** (Docker-first — see [AGENTS.md](../AGENTS.md) § Docker-First Workflow; never run this bare on the host):

```bash
docker compose run --rm backend python -m law_ai.eval.legalbench \
  --subset core_reasoning,precedent_retrieval
```

Common options:

- `--subset <names>` — comma-separated list of LegalBench task groups (default: `core_reasoning,precedent_retrieval`).
- `--model <ollama-tag>` — override `OLLAMA_DEFAULT_MODEL` for the run.
- `--limit <N>` — cap items per task during local development; CI runs unlimited.
- `--report <path>` — write a JSON report (default `backend/var/legalbench/<UTC>.json`).
- `--check-regression` — exit non-zero when any subset drops more than 1 pp against `baseline.json` (constitution §3). This is the flag that actually implements the "Regression policy" below; use it in CI (`make test-legalbench-gate`).
- `--update-baseline` — write this run's accuracies to `baseline.json`. Refuses to run against synthetic-stub data (`make legalbench-baseline`).
- `--fail-on-synthetic` — exit non-zero if any subset fell back to synthetic stub fixtures, guarding CI against "measuring" fixtures instead of the real dataset.

Corresponding Make targets: `make test-legalbench` (plain run), `make test-legalbench-gate` (adds `--check-regression --fail-on-synthetic`), `make legalbench-cache` (fetch the real dataset), `make legalbench-baseline` (adds `--update-baseline`).

**Where the scores show up** (BL-20260811-12): every run appends to `history.jsonl`, emits one `autonomy_legalbench_delta` audit event per subset — which is what fills the autonomy digest's "LegalBench Delta" section — and nightly renders the last ten runs into the workflow run summary via `python3 scripts/legalbench_summary.py`. The JSON artifact is now the least of the four.

Every item emits a per-item audit event via `law_ai.core.audit_jsonl` (`_emit_item_event()`), visible through [`GET /api/agents/runs`](api-examples.md) — the harness does **not** emit OpenTelemetry spans, so runs are not inspectable in Phoenix ([docs/local-ai.md](local-ai.md) covers what Phoenix does trace: LangGraph/CrewAI agent calls).

### Infrastructure failures vs. model regressions

An item that never reaches the model (Ollama unreachable, model not pulled) is **not** scored as incorrect — it is excluded from the accuracy denominator, and the CLI exits with code `2` (`EvalInfrastructureError`) rather than reporting a misleading `accuracy=0.0`. Exit code `1` means an actual tracked-subset regression; code `2` means the eval infrastructure itself was unavailable. Decoding is pinned to `temperature=0, seed=0` so the 1 pp regression tolerance is meaningful against deterministic output.

### Synthetic-stub fixtures

Until the real LegalBench dataset is cached locally (`make legalbench-cache` — see "Caching the real dataset" below), the harness falls back to small synthetic-stub fixtures per subset (`is_synthetic()` in [loaders.py](../backend/law_ai/eval/loaders.py)). A run that used stubs prints a `SYNTHETIC-STUBS` warning banner and is refused as a baseline by `--update-baseline`. Every run appends a compact row to `backend/var/legalbench/history.jsonl` regardless of stub status, so score drift over time is visible even before a real baseline exists. Since `BL-20260811-10` the CI gate also passes `--fail-on-synthetic`, so a stub-backed run can no longer satisfy it: cache the dataset first.

## Caching the real dataset

```bash
make legalbench-cache                                  # core_reasoning,precedent_retrieval
LEGALBENCH_SUBSETS=contract_nli,definitions make legalbench-cache
python3 scripts/fetch_legalbench.py --subset causation # host wrapper, same thing
```

[`law_ai/eval/fetch.py`](../backend/law_ai/eval/fetch.py) downloads the real task data and writes `backend/var/legalbench/<subset>/items.jsonl` in the loader's JSONL contract (`index`, `text`, `answer`, `metadata`). Three decisions are frozen in that module rather than in prose (BL-20260811-09):

1. **Pinned revisions, never `main`.** Task data comes from the Hugging Face dataset `nguha/legalbench` at `DATA_REVISION`; prompt templates (`base_prompt.txt`) and the per-task licence READMEs come from GitHub `HazyResearch/legalbench` at `PROMPT_REVISION`. A benchmark that changes under the harness makes the 1 pp policy meaningless.
2. **Per-task licence review, enforced in code.** Each task's README `**License**:` line is parsed and checked against `ALLOWED_LICENCES` (`cc-by-4.0`, `cc-by-sa-4.0`) *before* any item is written; an unrecognised or missing licence aborts the fetch. The reviewed licence is stamped into every item's `metadata.licence`. The reviewed table lives in [backend/var/legalbench/LICENSES.md](../backend/var/legalbench/LICENSES.md).
3. **CI downloads; we never vendor.** `items.jsonl` stays git-ignored. Reproducibility comes from the pinned revisions plus `manifest.json` (tracked), which records the sha256 of every downloaded source file — a fetch that sees a different digest fails loudly instead of quietly re-benchmarking. Re-run with `MANIFEST=update make legalbench-cache` only after deciding the upstream change is intended, and re-baseline afterwards.

Each subset is several LegalBench tasks (`SUBSET_TASKS` in `fetch.py`; the mapping table is in `LICENSES.md`), capped at 50 items per task and round-robined so `--limit` samples across tasks instead of draining the first one. The fetcher is stdlib-only, so it runs in the plain backend image without the heavy `legalbench` extras.

Nightly runs the cache step before the gate ([nightly-tests.yml](../.github/workflows/nightly-tests.yml)), keyed on the pinned revisions via `actions/cache`.

### CI status of the scored gate

Where the scored run actually happens, and where it does not:

| Workflow | What it runs | State |
|---|---|---|
| [ci.yml](../.github/workflows/ci.yml) `legalbench` job | `pytest tests/eval` — a *harness* self-check on PRs labelled `reasoning-change` | Active. Never produces a score; PR runners cannot host the multi-GB Ollama model. |
| [integration-tests.yml](../.github/workflows/integration-tests.yml) | `pytest -m integration` against real Neo4j/Postgres/Redis | Active, green on every backend PR. |
| [nightly-tests.yml](../.github/workflows/nightly-tests.yml) | `make test-legalbench-gate` — the scored regression gate | Weekly (Mon 06:00 UTC) + `workflow_dispatch`. |

The nightly workflow spent 2026-07-03 → 2026-09-05 `disabled_manually` after 37/37 scheduled runs died on hosted-runner disk exhaustion, so the scored gate had **never** completed a run in CI. Re-enabling it (`gh workflow enable nightly-tests.yml`) was only half the fix: the workflow started the Ollama container but never pulled a model into its empty volume, so `make test-legalbench-gate` could only ever exit 2 ("could not run"). A "Pull the LegalBench gate model" step now fetches `mistral:7b-instruct-q4_K_M` (~4.4 GB, the one model the eval uses) between service start-up and the gate (`BL-20260511-26`).

Record the first genuinely green scored run here — run id and date — before treating this gate as proven. Until then the disk-space fix (commit 613ab69) and the pull step remain untested end to end on a hosted runner.


## How answers are scored

Scoring dispatches on the subset ([scoring.py](../backend/law_ai/eval/scoring.py) `SCORERS`), and the rule that produced a number is recorded on the report row, in `history.jsonl`, and in `baseline.json` — two numbers are only comparable when their scorers match.

| Subset | Scorer | Rule |
|--------|--------|------|
| `precedent_retrieval` | `bm25_recall@1` | Exact/prefix first; otherwise rank every candidate answer in the subset against the model's response with Okapi BM25 (stdlib, no new dependency) and require the true case to come **first**. With no candidate pool, fall back to token recall of the expected case name at `RECALL_THRESHOLD` (0.6), after dropping `v.`/`vs` and corporate suffixes. Yes/No answers (`citation_prediction_classification`) keep the default rule. |
| `contract_nli` | `entailment_class` | Map `yes`/`true`/`entailment` and `no`/`false`/`contradiction` onto entailment classes before comparing, so a model that answers "Entailment" to a "Yes" key scores correct. |
| everything else | `default_match` | Exact match after normalisation, prefix match, first-word match, and closed-vocabulary label extraction ("The answer is True." → `true`). |

**A scorer change is a baseline reset.** These rules move accuracy numbers by construction, so `baseline.json` records `scorers` alongside `accuracies`; re-record the baseline in the same commit that changes a rule, or the 1 pp gate is comparing two different measurements.

## Baseline scores

Baselines are captured in the JSON report and surfaced in PR descriptions. The dataset blocker is gone (`make legalbench-cache`, above), and the gate now refuses stub data — `make test-legalbench-gate` passes `--check-regression --fail-on-synthetic`, so a run with no cached dataset exits non-zero instead of "passing" against five smoke fixtures (`BL-20260811-10`). What is still missing is the recorded numbers: `baseline.json` must be produced by a machine that can actually load the gate model.

**Recording the first baseline** (a runner or workstation with `mistral:7b-instruct-q4_K_M` pulled and ~5 GB of free RAM for it):

```bash
make legalbench-cache      # real items at the pinned revision
make legalbench-baseline   # runs the eval, writes backend/var/legalbench/baseline.json
```

Then commit `baseline.json` (it is whitelisted in `.gitignore`) and fill the table below with its accuracies and the commit SHA. `--update-baseline` refuses a synthetic run, so the file cannot be created from fixtures by accident. The numbers are specific to the model, the pinned dataset revision, the 50-items-per-task cap, **and** the scorers recorded in the file — change any of them and re-baseline.

Both rows are still `_TBD_`, and that is the one open dependency of the LegalWorkflow backfill (BL-20260511-06). The backfill itself shipped — `PrecedentHunter` runs the workflow's own `build_default_retriever()`, and the analyze node now returns the IRAC split `LegalAnalyst` used to stub — but "once the LegalBench baseline lands" cannot be *demonstrated* until someone runs the two commands above on a host that can load the gate model ([BL-20260811-10](../BACKLOG.md)). Until then the parity evidence for the backfill is unit-level (`backend/tests/agents/test_legal_analyst.py::TestLangGraphBackfill`, `backend/tests/agents/test_precedent_hunter.py`), not eval-level, and this note is the record of that gap rather than a claim it is closed.

| Task subset           | Baseline score | Recorded in commit | Notes |
|-----------------------|----------------|--------------------|-------|
| `core_reasoning`      | _TBD_          | _TBD_              | Dataset cached ([BL-20260811-09](../BACKLOG.md)); numbers await a run on a host that can load the gate model ([BL-20260811-10](../BACKLOG.md)). TopicFrontier prompt uses this subset. |
| `precedent_retrieval` | _TBD_          | _TBD_              | Same ([BL-20260811-10](../BACKLOG.md)) — `PrecedentHunter` now runs real GraphRAG retrieval (BL-20260511-06) and the subset is scored by `bm25_recall@1`, so this row measures retrieval quality rather than a stub. TopicFrontier prompt uses this subset. |

## Licenses policy

The LegalBench **code and harness** (github.com/HazyResearch/legalbench) is released under the [MIT License](https://opensource.org/licenses/MIT) by the HazyResearch contributors.

The LegalBench **dataset** is released under [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). Usage is permitted for research and product evaluation provided attribution is included. Note that individual task subsets may carry additional sub-licenses (e.g. ContractNLI data is CC BY 4.0 separately from the LegalBench MIT wrapper). A `LICENSES.md` file must be committed alongside any checked-in LegalBench data fixture; see [backend/var/legalbench/LICENSES.md](../backend/var/legalbench/LICENSES.md), which now carries the pinned revisions and the per-task review table. Do **not** redistribute raw task data without attribution — the fetcher's answer to this is that we never redistribute it at all (decision 3 above). The policy is enforced mechanically: `fetch_task()` refuses any task whose README licence is not in `ALLOWED_LICENCES`, so an unreviewed task cannot reach the cache.

## Regression policy

1. Any spec that changes prompts, retrievers, model defaults, or workflow graphs **must** declare the LegalBench subset(s) it touches in `spec.md` § Evaluation.
2. The PR description **must** include a before/after table for those subsets and the resulting delta.
3. **Block-on-regression:** the gated run (`make test-legalbench-gate`, i.e. `--check-regression`) fails if any tracked subset regresses by more than 1 pp against `baseline.json`.
4. Improvements ≥ 1 pp on any subset must be accompanied by an updated baseline entry in this file.

**When this actually runs:** the scored, gated run above does not fire on every PR — it runs weekly via the `legalbench` step in [nightly-tests.yml](../.github/workflows/nightly-tests.yml) (cadence was cut from daily after runner disk exhaustion). The `legalbench` job in [ci.yml](../.github/workflows/ci.yml) only runs on PRs labelled `reasoning-change`, and only verifies the harness itself (`pytest tests/eval` — paths, scoring, regression-gate logic), not a live scored run; PR runners cannot host the multi-GB Ollama model the harness requires. See [docs/ao-sdlc.md](ao-sdlc.md) for the full CI/nightly gate sequencing — that doc is canonical for *when* this gate fires, this section is canonical for *what* it checks and how to run it yourself.

## Adding a new subset

1. Add it to the `--subset` allow-list (`ALLOWED_SUBSETS`) in [backend/law_ai/eval/legalbench.py](../backend/law_ai/eval/legalbench.py).
2. Document it in the table above with a one-sentence rationale.
3. Run a baseline pass and record the score.
4. Reference the new subset in the touching spec's `## Evaluation` section.

## LSAT per-item regression (the sibling harness)

LegalBench answers "did the *agent* get worse on the benchmark". The LSAT bank has a sibling question — "did the chain's blind solve of *this particular item* change" — and it is deliberately **not** part of the LegalBench harness, which stays pinned to one local Ollama model so its numbers stay comparable.

The LSAT loop is built on the spec 045 FR-14 cross-check (`cross_check()` in [backend/law_ai/lsat/services/crosscheck.py](../backend/law_ai/lsat/services/crosscheck.py)), which solves a bank question blind through `LLM_PROVIDER_CHAIN` and compares the answer to the stored key:

1. **A baseline is recorded at approval.** `ProposalApproveView` calls `proposals.cross_check_on_approval()` after a draft is promoted, so every new bank item carries a fresh "tutor-grade" prediction from day one. Set `LSAT_CROSS_CHECK_ON_APPROVE=false` to skip the extra provider call; a provider outage never undoes an approval.
2. **Every fresh verdict is an audit event.** `cross_check()` writes an `lsat_cross_check` event through `core.provenance`, so `AuditEvent` (and the JSONL tail) hold the per-question time series — the response cache only keeps the latest verdict and cannot see a flip.
3. **Flips are reported.** `regression_report()` in [backend/law_ai/lsat/services/regression.py](../backend/law_ai/lsat/services/regression.py) groups those events per question id and flags items whose earliest verdict agreed with the key and whose latest one does not (`regressed`) or the reverse (`recovered`). Cached re-reads and degraded no-provider verdicts are ignored. The report is surfaced as `regressions` on `GET /api/lsat/validation`.

Unlike the LegalBench gate, this one does not block a PR: model choice varies per environment, so it is a reviewer signal, not a threshold.

### Why not `LegalAnalyst`? (deliberate substitution, BL-20260527-06)

The backlog item that asked for this loop named `LegalAnalyst` as the predictor. It is not used here, and that is on purpose, not an oversight. `LegalAnalyst` ([backend/law_ai/agents_runtime/crews/legal_analyst.py](../backend/law_ai/agents_runtime/crews/legal_analyst.py), see [docs/agent-roles.md](agent-roles.md)) is an IRAC document-analysis agent: it reads a legal document and emits issue/rule/application/conclusion prose. It never produces an A–E choice, so it cannot be scored against a bank answer key, and a "tutor-grade prediction" derived from it would have to be re-graded by a second model to become comparable over time — which is exactly the drift the regression bundle exists to detect.

`cross_check()` is the tutor-grade predictor instead: it is a blind solve of the same item through the same provider chain, it returns a single labelled choice plus a rationale, and it already writes an audited per-item verdict. Any future change that routes the approval-time prediction elsewhere should keep those three properties.


## Related docs

- [docs/agent-roles.md](agent-roles.md) — which agents the subsets exercise.
- [docs/local-ai.md](local-ai.md) — the local Ollama + Phoenix substrate; Phoenix traces LangGraph/CrewAI agent calls, not LegalBench runs (see above).
- [docs/ao-sdlc.md](ao-sdlc.md) — when the LegalBench gate fires in CI vs. nightly.
- [docs/constitution.md](constitution.md) §1 (Ollama pinning for the harness), §3, §6 (quality and testing gates).
