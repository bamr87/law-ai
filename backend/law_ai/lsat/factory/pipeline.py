"""Pipeline facade — the factory lifecycle as five composable verbs.

Spec 024 FR-8 backing functions (the ``lsat_factory`` management command is a
thin argparse shell over these):

* :func:`plan`     — coverage census + gap analysis → ranked targets
* :func:`compile_plan` — targets → manifest artifact with compiled prompts
* :func:`execute_manifest` — fulfill jobs with an executor, ingest the
  results, and (with ``judge_enabled``) attach an advisory judge verdict
* :func:`ingest_drafts_file` — consume externally produced drafts
* :func:`export_bundle` — manifest → self-contained prompts-only bundle for an
  external generation farm (no repo checkout needed)
* :func:`status`   — bank census, coverage holes, pending-proposal summary

``plan``/``compile_plan``/``ingest``/``status`` never touch a network (AC-1);
only ``execute_manifest`` with a live executor does.
"""

from __future__ import annotations

import json
import logging
import shutil
from pathlib import Path
from typing import Any

from law_ai.agents_runtime.crews.lsat_content_author import DraftQuestion

from law_ai.lsat.factory.config import FactoryConfig
from law_ai.lsat.factory.coverage import (
    GenerationTarget,
    coverage_matrix,
    plan_targets,
)
from law_ai.lsat.factory.executors import (
    DraftFileExecutor,
    ExecutionError,
    Executor,
    RawBatch,
)
from law_ai.lsat.factory.intake import IngestResult, ingest_batch
from law_ai.lsat.factory.guides import draft_guides
from law_ai.lsat.factory.judge import judge_result
from law_ai.lsat.factory.manifest import (
    GenerationManifest,
    build_manifest,
    latest_manifest_path,
    read_manifest,
    write_manifest,
)
from law_ai.lsat.services.bank import load_bank
from law_ai.lsat.services.proposals import list_proposals
from law_ai.lsat.services.writing import load_writing_prompts

logger = logging.getLogger("law_ai.lsat.factory.pipeline")


def plan(config: FactoryConfig | None = None) -> list[GenerationTarget]:
    """Ranked generation targets for the current bank + audit state."""
    return plan_targets(config or FactoryConfig.from_settings())


def compile_plan(
    config: FactoryConfig | None = None,
    targets: list[GenerationTarget] | None = None,
) -> tuple[GenerationManifest, Path]:
    """Freeze a plan into a manifest artifact; returns (manifest, path)."""
    cfg = config or FactoryConfig.from_settings()
    manifest = build_manifest(targets if targets is not None else plan(cfg), cfg)
    path = write_manifest(manifest, cfg)
    logger.info(
        "factory manifest %s written (%d jobs) → %s",
        manifest.manifest_id,
        len(manifest.jobs),
        path,
    )
    return manifest, path


async def execute_manifest(
    manifest: GenerationManifest,
    executor: Executor,
    config: FactoryConfig | None = None,
    *,
    job_ids: list[str] | None = None,
) -> list[IngestResult]:
    """Fulfill (a subset of) a manifest's jobs and ingest every batch.

    Jobs run sequentially — generation latency dominates and sequential runs
    keep provenance ordering trivial; parallel fan-out belongs to external
    executors working from the manifest file. A failed job is recorded as an
    empty :class:`IngestResult` carrying the truncated executor error in
    ``error`` rather than aborting the batch run.
    """
    cfg = config or FactoryConfig.from_settings()
    wanted = set(job_ids) if job_ids else None
    results: list[IngestResult] = []
    for job in manifest.jobs:
        if wanted is not None and job.job_id not in wanted:
            continue
        try:
            batch: RawBatch = await executor.execute(job)
        except ExecutionError as exc:
            logger.warning("factory job failed: %s", exc)
            results.append(
                IngestResult(
                    job_id=job.job_id,
                    rejected=[],
                    error=str(exc)[:300],
                    model_label=f"{executor.name}/failed",
                )
            )
            continue
        result = ingest_batch(
            batch.payload,
            job=job,
            config=cfg,
            executor_name=executor.name,
            model_label=batch.model_label,
            latency_ms=batch.latency_ms,
        )
        if job.target.mode != "writing_prompt":
            # Both post-steps speak the MCQ contract: a drafted writing task
            # has no keyed answer to judge and no solve guide to write.
            #
            # Judge tier (BL-20260702-02): advisory verdicts attached to the
            # proposals' meta before a human opens the queue. Never fatal.
            result = await judge_result(
                result,
                config=cfg,
                tier_model_hint=cfg.claude_tier_models.get("judge"),
            )
            # Guide-at-authoring (BL-20260901-04): the walkthrough is drafted
            # with the item, not swept for later. Also never fatal.
            result = await draft_guides(result, config=cfg)
        results.append(result)
    return results


async def ingest_drafts_file(
    manifest: GenerationManifest,
    drafts_path: Path,
    config: FactoryConfig | None = None,
) -> list[IngestResult]:
    """Consume an externally produced drafts JSONL against a manifest (AC-2)."""
    executor = DraftFileExecutor(drafts_path)
    available = executor.fulfilled_job_ids()
    fulfilled = [j.job_id for j in manifest.jobs if j.job_id in available]
    return await execute_manifest(manifest, executor, config, job_ids=fulfilled or None)


_BUNDLE_README = """# LSAT factory generation bundle

Everything an external generation farm needs to fulfil this manifest. No repo
checkout, no network access to this project, and no knowledge of the factory
is required: read `manifest.json`, generate, write `drafts.jsonl`, send it back.

## What is here

| File | Contents |
|------|----------|
| `manifest.json` | `manifest_id`, `created_at`, and one entry per job: `job_id`, `tier`, `model_hint`, `template_version`, `drafts_per_job`, and the fully rendered `prompt`. |
| `draft.schema.json` | JSON Schema for a single draft object (the same contract the intake gates enforce). |
| `README.md` | This file. |

The prompts are rendered — send each job's `prompt` to a model as-is. The
`model_hint` is a suggestion, not a requirement; `tier` says how much
capability the job wants (`bulk` < `standard` < `premium`).

## What to send back

One JSON object per line (JSONL), one line per job:

```json
{"job_id": "mfst-20260101-000000-abc123-job01", "drafts": [ {draft}, ... ], "model": "your-provider/your-model"}
```

* `job_id` — copied verbatim from `manifest.json`. Unknown ids are ignored.
* `drafts` — `drafts_per_job` objects validating against `draft.schema.json`.
  Do **not** set `passage_id`: the platform owns passage linkage.
* `model` — optional label recorded as the batch's provenance model.
* A job whose target `mode` is `passage_set` may add a top-level `passage`
  object alongside `drafts`; it is parked for a reviewer, never auto-promoted.

## How it is ingested

```sh
manage.py lsat_factory ingest --manifest <path to the original manifest> --drafts drafts.jsonl
```

Every returned draft still passes the intake gates (schema, concept lint,
near-duplicate detection, answer-key balance) and lands as a *pending*
proposal for human review. Nothing in this bundle can write to the live bank.
"""


def export_bundle(
    manifest: GenerationManifest,
    out_dir: Path,
    config: FactoryConfig | None = None,
    *,
    archive: bool = False,
) -> Path:
    """Write a self-contained prompts-only bundle for an external farm (FR-8).

    BL-20260702-03. The manifest already carries each job's rendered prompt,
    so this is packaging, not a second pipeline: the bundle strips the config
    snapshot and the planning internals, ships the draft JSON Schema, and
    documents the JSONL return contract that ``lsat_factory ingest`` consumes.

    Returns the bundle directory, or the ``.zip`` beside it when *archive*.
    """
    del config  # accepted for call-site symmetry; nothing here reads settings
    bundle = out_dir / manifest.manifest_id
    bundle.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": manifest.schema_version,
        "manifest_id": manifest.manifest_id,
        "created_at": manifest.created_at,
        "jobs": [
            {
                "job_id": job.job_id,
                "tier": job.tier,
                "model_hint": job.model_hint,
                "template_version": job.template_version,
                "section": job.target.section,
                "difficulty": job.target.difficulty,
                "mode": job.target.mode,
                "drafts_per_job": job.target.count,
                "prompt": job.prompt,
            }
            for job in manifest.jobs
        ],
    }
    (bundle / "manifest.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    (bundle / "draft.schema.json").write_text(
        json.dumps(DraftQuestion.model_json_schema(), indent=2, ensure_ascii=False)
        + "\n",
        encoding="utf-8",
    )
    (bundle / "README.md").write_text(_BUNDLE_README, encoding="utf-8")
    if archive:
        archived = shutil.make_archive(str(bundle), "zip", root_dir=str(bundle))
        return Path(archived)
    return bundle


def status(config: FactoryConfig | None = None) -> dict[str, Any]:
    """Operator snapshot: bank census, worst coverage holes, queue depth."""
    cfg = config or FactoryConfig.from_settings()
    bank = list(load_bank().values())
    by_section: dict[str, int] = {}
    for q in bank:
        by_section[q.section] = by_section.get(q.section, 0) + 1

    cells = coverage_matrix(cfg)
    holes = sorted(
        (c for c in cells if c.deficit > 0),
        key=lambda c: (-c.deficit, c.archetype_id, c.difficulty),
    )
    pending = list_proposals(status="pending", limit=500)
    factory_pending = [
        p for p in pending if isinstance(p.get("meta"), dict) and "factory" in p["meta"]
    ]
    latest = latest_manifest_path(cfg)
    # BL-20260831-28: the writing library is content the factory now plans
    # for, so an operator snapshot has to show it.
    writing_prompts = load_writing_prompts()
    writing_by_difficulty: dict[str, int] = {}
    for prompt in writing_prompts.values():
        writing_by_difficulty[prompt.difficulty] = (
            writing_by_difficulty.get(prompt.difficulty, 0) + 1
        )

    return {
        "bank_total": len(bank),
        "bank_by_section": by_section,
        "writing_prompts": len(writing_prompts),
        "writing_by_difficulty": writing_by_difficulty,
        "coverage_cells": len(cells),
        "cells_with_deficit": len(holes),
        "top_deficits": [
            {
                "archetype_id": c.archetype_id,
                "difficulty": c.difficulty,
                "have": c.have,
                "want": c.want,
            }
            for c in holes[:10]
        ],
        "pending_proposals": len(pending),
        "pending_from_factory": len(factory_pending),
        "latest_manifest": str(latest) if latest else None,
    }


def load_manifest(
    path: Path | None = None, config: FactoryConfig | None = None
) -> GenerationManifest:
    """Read the given manifest, or the most recent one when path is omitted."""
    cfg = config or FactoryConfig.from_settings()
    target = path or latest_manifest_path(cfg)
    if target is None:
        raise FileNotFoundError(
            f"no manifests found under {cfg.resolved_output_dir()}/manifests"
        )
    return read_manifest(target)
