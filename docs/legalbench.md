# LegalBench Evaluation Harness

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

**CLI equivalent** (Docker-first — see [CLAUDE.md](../CLAUDE.md); never run this bare on the host):

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

Corresponding Make targets: `make test-legalbench` (plain run), `make test-legalbench-gate` (adds `--check-regression`), `make legalbench-baseline` (adds `--update-baseline`).

Every item emits a per-item audit event via `law_ai.core.audit_jsonl` (`_emit_item_event()`), visible through [`GET /api/agents/runs`](api-examples.md) — the harness does **not** emit OpenTelemetry spans, so runs are not inspectable in Phoenix ([docs/local-ai.md](local-ai.md) covers what Phoenix does trace: LangGraph/CrewAI agent calls).

### Infrastructure failures vs. model regressions

An item that never reaches the model (Ollama unreachable, model not pulled) is **not** scored as incorrect — it is excluded from the accuracy denominator, and the CLI exits with code `2` (`EvalInfrastructureError`) rather than reporting a misleading `accuracy=0.0`. Exit code `1` means an actual tracked-subset regression; code `2` means the eval infrastructure itself was unavailable. Decoding is pinned to `temperature=0, seed=0` so the 1 pp regression tolerance is meaningful against deterministic output.

### Synthetic-stub fixtures

Until the real LegalBench dataset is cached locally, the harness falls back to small synthetic-stub fixtures per subset (`is_synthetic()` in [loaders.py](../backend/law_ai/eval/loaders.py)). A run that used stubs prints a `SYNTHETIC-STUBS` warning banner and is refused as a baseline by `--update-baseline`. Every run appends a compact row to `backend/var/legalbench/history.jsonl` regardless of stub status, so score drift over time is visible even before a real baseline exists. See `BL-20260811-09`/`BL-20260811-10` below — caching the real dataset is the blocker for a first honest baseline.

## Baseline scores

Baselines are captured in the JSON report and surfaced in PR descriptions. There is no static baseline checked in yet — every run today is stub-backed (see above). Once `BL-20260811-09` caches the real dataset, record the first stable result as `backend/var/legalbench/baseline.json` and reference its commit SHA here; that follow-up is tracked as `BL-20260811-10` and `BL-20260511-24`.

| Task subset           | Baseline score | Recorded in commit | Notes |
|-----------------------|----------------|--------------------|-------|
| `core_reasoning`      | _TBD_          | _TBD_              | Blocked on real-dataset caching ([BL-20260811-09](../BACKLOG.md)); establish once `BL-20260811-10` lands. TopicFrontier prompt uses this subset. |
| `precedent_retrieval` | _TBD_          | _TBD_              | Same blocker ([BL-20260811-09](../BACKLOG.md)/[BL-20260811-10](../BACKLOG.md)) — the GraphRAG hookup this row previously waited on has already shipped (`BL-20260511-06`, specs/018). TopicFrontier prompt uses this subset. |

## Licenses policy

The LegalBench **code and harness** (github.com/HazyResearch/legalbench) is released under the [MIT License](https://opensource.org/licenses/MIT) by the HazyResearch contributors.

The LegalBench **dataset** is released under [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). Usage is permitted for research and product evaluation provided attribution is included. Note that individual task subsets may carry additional sub-licenses (e.g. ContractNLI data is CC BY 4.0 separately from the LegalBench MIT wrapper). A `LICENSES.md` file must be committed alongside any checked-in LegalBench data fixture; see [BL-20260511-25](../BACKLOG.md) for the tracking item. Do **not** redistribute raw task data without attribution.

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

## Related docs

- [docs/agent-roles.md](agent-roles.md) — which agents the subsets exercise.
- [docs/local-ai.md](local-ai.md) — the local Ollama + Phoenix substrate; Phoenix traces LangGraph/CrewAI agent calls, not LegalBench runs (see above).
- [docs/ao-sdlc.md](ao-sdlc.md) — when the LegalBench gate fires in CI vs. nightly.
- [docs/constitution.md](constitution.md) §1 (Ollama pinning for the harness), §3, §6 (quality and testing gates).
