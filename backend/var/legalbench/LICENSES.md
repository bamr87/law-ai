# LegalBench Dataset Licenses

> **Required reading before committing `baseline.json`.** Per spec 018 T-002,
> this file must enumerate the license for every LegalBench task subset we
> cache locally. Do **not** commit `baseline.json` or any `items.jsonl` files
> until the corresponding license entry is present here.

## Pinned revisions, per-task review, and the vendoring decision (BL-20260811-09)

The fetcher is [law_ai/eval/fetch.py](../../law_ai/eval/fetch.py) (`make legalbench-cache`). It downloads from two pinned commits, never from `main`:

| What | Source | Pinned revision |
|------|--------|-----------------|
| Task data (`test.tsv`) | Hugging Face dataset `nguha/legalbench` | `daec8237410aa23e3faf4bc41ad8b3a7e1696826` |
| Prompt templates + task READMEs | GitHub `HazyResearch/legalbench` | `b46bf4ffae90524b2b72aaa30e7745fe9db64481` |

**Vendoring decision: CI downloads, we never vendor.** `backend/var/legalbench/*/items.jsonl` stays git-ignored. Reproducibility comes from the two pinned revisions plus `manifest.json` (tracked), which records the sha256 of every downloaded source file; a later fetch that sees a different digest fails loudly rather than quietly re-benchmarking. This keeps CC BY-SA obligations moot — we do not redistribute the data — and keeps the repo small.

**Per-task licence review is mechanical, not a promise.** `fetch_task()` parses the `**License**:` line out of each task's README and refuses any task whose licence is not in `ALLOWED_LICENCES` (`cc-by-4.0`, `cc-by-sa-4.0`), before a single item is written. The licence it read is stamped into every cached item's `metadata.licence`.

### Task-to-subset mapping (as fetched)

| Law AI subset | LegalBench tasks | Licence |
|---------------|------------------|---------|
| `core_reasoning` | `hearsay`, `personal_jurisdiction`, `ucc_v_common_law`, `abercrombie` | CC BY 4.0 |
| `precedent_retrieval` | `citation_prediction_classification`, `citation_prediction_open` | CC BY 4.0 |
| `contract_nli` | `contract_nli_explicit_identification`, `contract_nli_confidentiality_of_agreement`, `contract_nli_sharing_with_third-parties` | CC BY 4.0 |
| `definitions` | `definition_classification`, `definition_extraction` | CC BY-SA 4.0 |
| `causation` | `legal_reasoning_causality` | CC BY 4.0 |

Each subset takes the head of each task's test split, capped at `DEFAULT_MAX_ITEMS_PER_TASK` (50) and round-robined across tasks so `--limit` samples every task rather than only the first. Changing the mapping or the cap changes what "accuracy" means — re-record `baseline.json` when either moves.

## Tracked Subsets

### core_reasoning

- **Source**: LegalBench benchmark (HazyResearch / Stanford Law / contributors)
- **Repository**: https://github.com/HazyResearch/legalbench
- **Code license**: MIT License (covers the LegalBench harness and task wrapper code)
- **Dataset license**: CC BY 4.0 (covers the task data/items used for evaluation)
- **Citation**: Guha et al. (2023) "LegalBench: A Collaboratively Built Benchmark for
  Measuring Legal Reasoning in Large Language Models."
- **Notes**: Tasks in this subset are drawn from publicly available legal
reasoning exercises. Individual tasks may have their own sub-licenses documented in the LegalBench task registry at `legalbench/tasks/`. Verify per task before distributing cached data.

### precedent_retrieval

- **Source**: LegalBench benchmark (HazyResearch / Stanford Law / contributors)
- **Repository**: https://github.com/HazyResearch/legalbench
- **Code license**: MIT License (covers the LegalBench harness and task wrapper code)
- **Dataset license**: CC BY 4.0 (covers the task data/items used for evaluation)
- **Citation**: Same as `core_reasoning` above.
- **Notes**: Fact patterns are synthetic or drawn from public-domain judicial opinions.
  Court opinions in the United States are not protected by copyright (17 U.S.C. § 105).

### contract_nli

- **Source**: LegalBench benchmark; original NLI data from ContractNLI (Koreeda & Manning 2021)
- **Repository**: https://github.com/HazyResearch/legalbench
- **License**: MIT License (LegalBench wrapper); ContractNLI data CC BY 4.0
- **Notes**: Do not redistribute the raw contract text outside of the LegalBench
  framework without verifying the CC BY 4.0 attribution requirements.

### definitions

- **Source**: LegalBench benchmark (HazyResearch / Stanford Law / contributors)
- **Repository**: https://github.com/HazyResearch/legalbench
- **Code license**: MIT License (covers the LegalBench harness and task wrapper code)
- **Dataset license**: CC BY-SA 4.0 — both mapped tasks (`definition_classification`, `definition_extraction`) declare share-alike in their task READMEs, unlike the rest of the tracked subsets. Verified 2026-09-05 against the pinned revision; admissible only because we never redistribute the cached items.
- **Notes**: Legal definitions are derived from public-domain legal dictionaries
  and statutory text.

### causation

- **Source**: LegalBench benchmark (HazyResearch / Stanford Law / contributors)
- **Repository**: https://github.com/HazyResearch/legalbench
- **Code license**: MIT License (covers the LegalBench harness and task wrapper code)
- **Dataset license**: CC BY 4.0 (covers the task data/items used for evaluation)
- **Notes**: Causation scenarios are synthetic; no copyrightable underlying material.

---

## Policy

1. Only commit `items.jsonl` caches after confirming the corresponding entry above.
2. If a new subset is added to `legalbench.ALLOWED_SUBSETS`, add its entry here
   **first**, before populating the cache or recording a baseline.
3. This file is checked by `make lint-specs` via `spec_validator.py` (the spec
   references this path in T-002).

4. The per-task licence check in `law_ai/eval/fetch.py` enforces rule 1 mechanically. Widening `ALLOWED_LICENCES` requires a licence review recorded above, not just a code change.

_Last updated: 2026-09-05 (BL-20260811-09 — pinned revisions, per-task review, vendoring decision). Originally written 2026-05-11 (spec 018 T-002)._
