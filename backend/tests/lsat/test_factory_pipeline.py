"""Pipeline e2e tests (spec 024 T-007: FR-8 backing functions, AC-1, AC-2)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from law_ai.lsat.factory.config import FactoryConfig
from law_ai.lsat.factory.executors import ExecutionError, RawBatch
from law_ai.lsat.factory.manifest import GenerationJob
from law_ai.lsat.factory.pipeline import (
    compile_plan,
    execute_manifest,
    ingest_drafts_file,
    load_manifest,
    plan,
    status,
)
from law_ai.lsat.services import proposals

_STEM_BANK = (
    "Museum attendance doubled after free-admission Fridays began; the "
    "director credits the policy. Which finding most weakens that claim?",
    "A firm's revenue grew each quarter it advertised on podcasts; the CMO "
    "concludes the ads caused the growth. What most undermines this?",
    "Students using flashcards outscored peers; the tutor infers flashcards "
    "work. Which alternative most challenges the inference?",
)


def _draft_for(job: GenerationJob, i: int) -> dict[str, Any]:
    return {
        "section": job.target.section,
        "difficulty": job.target.difficulty,
        "stem": f"{_STEM_BANK[i % len(_STEM_BANK)]} (variant {job.job_id}-{i})",
        "choices": [
            {"label": label, "text": f"option {label} #{i}"}
            for label in ("A", "B", "C", "D", "E")
        ],
        "correct": ("A", "B", "C", "D", "E")[i % 5],
        "explanation": "Key holds; each other choice fails distinctly.",
        "concepts": list(job.target.concepts[:2]),
        "confidence": 0.7,
    }


class TestOfflineLifecycle:
    def test_plan_compile_status(self, factory_env: FactoryConfig) -> None:
        # AC-1: fully offline plan → compile → status.
        targets = plan(factory_env)
        assert targets
        _manifest, path = compile_plan(factory_env, targets)
        assert path.is_file()
        snapshot = status(factory_env)
        assert snapshot["bank_total"] > 0
        assert snapshot["latest_manifest"] == str(path)
        assert snapshot["cells_with_deficit"] > 0

    @pytest.mark.asyncio
    async def test_external_drafts_roundtrip(
        self, factory_env: FactoryConfig, tmp_path: Path
    ) -> None:
        # AC-2: compile → external drafts JSONL → ingest → pending proposals.
        manifest, _ = compile_plan(factory_env)
        jobs = [j for j in manifest.jobs if j.target.mode == "items"][:2]
        assert jobs, "expected at least one items-mode job"
        drafts_path = tmp_path / "external_drafts.jsonl"
        with drafts_path.open("w", encoding="utf-8") as fh:
            for j, job in enumerate(jobs):
                record = {
                    "job_id": job.job_id,
                    "model": f"external/test-{job.tier}",
                    "drafts": [
                        _draft_for(job, j * 3 + i) for i in range(job.target.count)
                    ],
                }
                fh.write(json.dumps(record) + "\n")

        results = await ingest_drafts_file(manifest, drafts_path, factory_env)
        assert len(results) == len(jobs)
        accepted = [pid for r in results for pid in r.accepted]
        assert accepted
        rows = proposals.list_proposals(status="pending")
        assert len(rows) == len(accepted)
        metas = {r["meta"]["factory"]["manifest_id"] for r in rows}
        assert metas == {manifest.manifest_id}
        snapshot = status(factory_env)
        assert snapshot["pending_from_factory"] == len(accepted)

    @pytest.mark.asyncio
    async def test_failed_job_reported_not_fatal(
        self, factory_env: FactoryConfig
    ) -> None:
        manifest, _ = compile_plan(factory_env)

        class _Boom:
            name = "boom"

            async def execute(self, job: GenerationJob) -> RawBatch:
                raise ExecutionError(f"job {job.job_id}: nope")

        results = await execute_manifest(
            manifest, _Boom(), factory_env, job_ids=[manifest.jobs[0].job_id]
        )
        assert len(results) == 1
        assert results[0].accepted == []
        assert results[0].model_label == "boom/failed"
        # Operators must see WHY the job failed, not just that it did.
        assert results[0].error is not None and "nope" in results[0].error

    def test_load_manifest_requires_artifacts(self, factory_env: FactoryConfig) -> None:
        with pytest.raises(FileNotFoundError):
            load_manifest(None, factory_env)
