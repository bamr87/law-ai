# LegalBench Evaluation Harness

> Living evaluation manual for Law AI. Closes [BL-20260430-06](../BACKLOG.md). The harness lives in [backend/law_ai/eval/](../backend/law_ai/eval/) and is invoked through the `Run LegalBench Eval` VS Code task.

## Purpose

[LegalBench](https://github.com/HazyResearch/legalbench) is the 162-task collaborative benchmark for legal reasoning in LLMs (Stanford / HazyResearch / contributors). Law AI uses it as the **mandatory regression suite** for any change that touches reasoning — agent prompts, retrieval strategy, model defaults, or workflow graphs. Per [docs/constitution.md](constitution.md) §3 and §6, a regression of more than **1 pp** on a listed task blocks the PR.

## Task subsets we track

The harness defaults to two named subsets:

| Subset                | What it covers                                                                 | Why it matters for Law AI |
|-----------------------|--------------------------------------------------------------------------------|-----------------------------|
| `core_reasoning`      | Rule-application, issue spotting, conclusion derivation across mixed domains   | Baseline for the `LegalAnalyst` crew (IRAC quality) |
| `precedent_retrieval` | Identification + ranking of relevant prior cases given a fact pattern          | Baseline for the `PrecedentHunter` crew + GraphRAG  |

Additional subsets (e.g. `contract_nli`, `definitions`, `causation`) can be enabled per-spec; record the chosen list in the spec's `## Evaluation` section.

## Running the harness

**One-liner (VS Code):** run the `Run LegalBench Eval` task.

**CLI equivalent:**

```bash
cd backend
python -m law_ai.eval.legalbench --subset core_reasoning,precedent_retrieval
```

Common options:

- `--subset <names>` — comma-separated list of LegalBench task groups.
- `--model <ollama-tag>` — override `OLLAMA_DEFAULT_MODEL` for the run.
- `--limit <N>` — cap items per task during local development; CI runs unlimited.
- `--report <path>` — write a JSON report (default `backend/var/legalbench/<UTC>.json`).

Every run emits an OpenTelemetry trace per item via `law_ai.core.provenance`, so individual prompt + response pairs are inspectable in Phoenix (see [docs/local-ai.md](local-ai.md)).

## Baseline scores

Baselines are captured in the JSON report and surfaced in PR descriptions. There is no static baseline checked in yet — record the first stable result as `backend/var/legalbench/baseline.json` and reference its commit SHA in [docs/architecture.md](architecture.md). Track follow-up [BL-20260430-06](../BACKLOG.md) for committing the first published baseline.

| Task subset           | Baseline score | Recorded in commit | Notes |
|-----------------------|----------------|--------------------|-------|
| `core_reasoning`      | _TBD_          | _TBD_              | Establish on the next reasoning-touching spec. TopicFrontier prompt uses this subset. |
| `precedent_retrieval` | _TBD_          | _TBD_              | Establish after GraphRAG hookup ([BL-20260502-04](../BACKLOG.md)). TopicFrontier prompt uses this subset. |

## Licenses policy

The LegalBench **code and harness** (github.com/HazyResearch/legalbench) is released under the [MIT License](https://opensource.org/licenses/MIT) by the HazyResearch contributors.

The LegalBench **dataset** is released under [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). Usage is permitted for research and product evaluation provided attribution is included. Note that individual task subsets may carry additional sub-licenses (e.g. ContractNLI data is CC BY 4.0 separately from the LegalBench MIT wrapper). A `LICENSES.md` file must be committed alongside any checked-in LegalBench data fixture; see [BL-20260430-06](../BACKLOG.md) for the tracking item. Do **not** redistribute raw task data without attribution.

## Regression policy

1. Any spec that changes prompts, retrievers, model defaults, or workflow graphs **must** declare the LegalBench subset(s) it touches in `spec.md` § Evaluation.
2. The PR description **must** include a before/after table for those subsets and the resulting delta.
3. **Block-on-regression:** PRs are not merged if any tracked subset regresses by more than 1 pp.
4. Improvements ≥ 1 pp on any subset must be accompanied by an updated baseline entry in this file.

## Adding a new subset

1. Add it to the `--subset` allow-list in [backend/law_ai/eval/legalbench.py](../backend/law_ai/eval/legalbench.py).
2. Document it in the table above with a one-sentence rationale.
3. Run a baseline pass and record the score.
4. Reference the new subset in the touching spec's `## Evaluation` section.

## Related docs

- [docs/agent-roles.md](agent-roles.md) — which agents the subsets exercise.
- [docs/local-ai.md](local-ai.md) — the local Ollama + Phoenix substrate the harness runs against by default.
- [docs/constitution.md](constitution.md) §3, §6 — quality and testing gates.
