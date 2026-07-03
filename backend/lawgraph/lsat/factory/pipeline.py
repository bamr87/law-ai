"""Pipeline facade — the factory lifecycle as five composable verbs.

Spec 024 FR-8 backing functions (the ``lsat_factory`` management command is a
thin argparse shell over these):

* :func:`plan`     — coverage census + gap analysis → ranked targets
* :func:`compile_plan` — targets → manifest artifact with compiled prompts
* :func:`execute_manifest` — fulfill jobs with an executor and ingest results
* :func:`ingest_drafts_file` — consume externally produced drafts
* :func:`status`   — bank census, coverage holes, pending-proposal summary

``plan``/``compile_plan``/``ingest``/``status`` never touch a network (AC-1);
only ``execute_manifest`` with a live executor does.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from lawgraph.lsat.factory.config import FactoryConfig
from lawgraph.lsat.factory.coverage import (
    GenerationTarget,
    coverage_matrix,
    plan_targets,
)
from lawgraph.lsat.factory.executors import (
    DraftFileExecutor,
    ExecutionError,
    Executor,
    RawBatch,
)
from lawgraph.lsat.factory.intake import IngestResult, ingest_batch
from lawgraph.lsat.factory.manifest import (
    GenerationManifest,
    build_manifest,
    latest_manifest_path,
    read_manifest,
    write_manifest,
)
from lawgraph.lsat.services.bank import load_bank
from lawgraph.lsat.services.proposals import list_proposals

logger = logging.getLogger("lawgraph.lsat.factory.pipeline")


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
    empty :class:`IngestResult` with the error in ``balance_flag``-adjacent
    metadata rather than aborting the batch run.
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
                    model_label=f"{executor.name}/failed",
                )
            )
            continue
        results.append(
            ingest_batch(
                batch.payload,
                job=job,
                config=cfg,
                executor_name=executor.name,
                model_label=batch.model_label,
                latency_ms=batch.latency_ms,
            )
        )
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
    return {
        "bank_total": len(bank),
        "bank_by_section": by_section,
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
