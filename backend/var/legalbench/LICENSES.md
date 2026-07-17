# LegalBench Dataset Licenses

> **Required reading before committing `baseline.json`.** Per spec 018 T-002,
> this file must enumerate the license for every LegalBench task subset we
> cache locally. Do **not** commit `baseline.json` or any `items.jsonl` files
> until the corresponding license entry is present here.

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
- **Dataset license**: CC BY 4.0 (covers the task data/items used for evaluation)
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

_Last updated: 2026-05-11 (spec 018 T-002 implementation)._
