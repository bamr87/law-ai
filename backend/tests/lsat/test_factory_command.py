"""Management-command smoke tests (spec 024 T-007: FR-8, AC-1, AC-5)."""

from __future__ import annotations

import json
from io import StringIO
from pathlib import Path
from typing import Any

import pytest

from django.core.management import call_command
from django.core.management.base import CommandError

from law_ai.lsat.factory.config import FactoryConfig
from law_ai.lsat.factory.pipeline import compile_plan


def _run(*args: str) -> str:
    out = StringIO()
    call_command("lsat_factory", *args, stdout=out)
    return out.getvalue()


class TestCommand:
    def test_plan_json(self, factory_env: FactoryConfig) -> None:
        payload: Any = json.loads(_run("plan", "--json"))
        assert isinstance(payload, list) and payload
        assert {"archetype_id", "difficulty", "tier", "count"} <= set(payload[0])

    def test_compile_then_status(self, factory_env: FactoryConfig) -> None:
        compiled: Any = json.loads(_run("compile", "--json"))
        assert compiled["jobs"]
        text = _run("status")
        assert "LSAT factory status" in text
        assert compiled["manifest_id"] in text

    def test_run_with_drafts_executor(
        self, factory_env: FactoryConfig, tmp_path: Path
    ) -> None:
        manifest, _ = compile_plan(factory_env)
        job = next(j for j in manifest.jobs if j.target.mode == "items")
        drafts = tmp_path / "d.jsonl"
        drafts.write_text(
            json.dumps(
                {
                    "job_id": job.job_id,
                    "drafts": [
                        {
                            "section": job.target.section,
                            "difficulty": job.target.difficulty,
                            "stem": "Ferry ridership fell after tolls rose; "
                            "the council blames tolls. What most weakens this?",
                            "choices": [
                                {"label": label, "text": f"opt {label}"}
                                for label in ("A", "B", "C", "D", "E")
                            ],
                            "correct": "D",
                            "explanation": "D introduces the confound; others fail.",
                            "concepts": list(job.target.concepts[:1]),
                            "confidence": 0.7,
                        }
                    ],
                }
            )
            + "\n",
            encoding="utf-8",
        )
        text = _run(
            "run", "--executor", "drafts", "--drafts", str(drafts), "--jobs", job.job_id
        )
        assert "Ingest complete" in text
        assert "+1 proposal(s)" in text

    def test_run_claude_code_gate(self, factory_env: FactoryConfig) -> None:
        # AC-5: outside the dev OAuth opt-in the executor must refuse.
        with pytest.raises(CommandError, match="executor unavailable"):
            _run("run", "--executor", "claude_code")

    def test_ingest_requires_existing_drafts_file(
        self, factory_env: FactoryConfig
    ) -> None:
        compile_plan(factory_env)
        with pytest.raises(CommandError, match="not found"):
            _run("ingest", "--drafts", "/nonexistent/drafts.jsonl")


# --------------------------------------------------------------------------
# BL-20260702-03 — export-manifest: a prompts-only bundle an external farm can
# run with no checkout of this repo.
# --------------------------------------------------------------------------


class TestExportManifest:
    def test_bundle_is_self_contained(
        self, factory_env: FactoryConfig, tmp_path: Path
    ) -> None:
        manifest, _ = compile_plan(factory_env)
        out = tmp_path / "bundles"
        payload: Any = json.loads(_run("export-manifest", "--out", str(out), "--json"))

        bundle = Path(payload["path"])
        assert bundle.is_dir()
        assert payload["manifest_id"] == manifest.manifest_id
        assert payload["jobs"] == len(manifest.jobs)
        assert {p.name for p in bundle.iterdir()} == {
            "manifest.json",
            "draft.schema.json",
            "README.md",
        }

        exported = json.loads((bundle / "manifest.json").read_text(encoding="utf-8"))
        assert exported["manifest_id"] == manifest.manifest_id
        assert len(exported["jobs"]) == len(manifest.jobs)
        # Prompts travel rendered; nothing needs the repo to fulfil a job.
        for job, exported_job in zip(manifest.jobs, exported["jobs"], strict=True):
            assert exported_job["job_id"] == job.job_id
            assert exported_job["prompt"] == job.prompt
            assert exported_job["tier"] == job.tier
            assert exported_job["drafts_per_job"] == job.target.count
        # The config snapshot (thresholds, tier map, output paths) stays home.
        assert "config" not in exported

        schema = json.loads((bundle / "draft.schema.json").read_text(encoding="utf-8"))
        assert "stem" in schema["properties"] and "choices" in schema["properties"]

        readme = (bundle / "README.md").read_text(encoding="utf-8")
        assert "drafts.jsonl" in readme
        assert "lsat_factory ingest" in readme

    def test_bundle_round_trips_into_ingest(
        self, factory_env: FactoryConfig, tmp_path: Path
    ) -> None:
        """A farm reading only the bundle can produce an ingestible JSONL."""
        compile_plan(factory_env)
        out = tmp_path / "bundles"
        payload: Any = json.loads(_run("export-manifest", "--out", str(out), "--json"))
        exported = json.loads(
            (Path(payload["path"]) / "manifest.json").read_text(encoding="utf-8")
        )
        job = next(j for j in exported["jobs"] if j["mode"] == "items")

        drafts = tmp_path / "farm.jsonl"
        drafts.write_text(
            json.dumps(
                {
                    "job_id": job["job_id"],
                    "model": "farm/gpu-box",
                    "drafts": [
                        {
                            "section": job["section"],
                            "difficulty": job["difficulty"],
                            "stem": "Ridership climbed after the fare cut; the "
                            "planner credits price. What most weakens that?",
                            "choices": [
                                {"label": label, "text": f"opt {label}"}
                                for label in ("A", "B", "C", "D", "E")
                            ],
                            "correct": "C",
                            "explanation": "C names the confound; others fail.",
                            "concepts": [],
                            "confidence": 0.6,
                        }
                    ],
                }
            )
            + "\n",
            encoding="utf-8",
        )
        text = _run("ingest", "--drafts", str(drafts))
        assert "Ingest complete" in text

    def test_zip_archive_is_written(
        self, factory_env: FactoryConfig, tmp_path: Path
    ) -> None:
        compile_plan(factory_env)
        payload: Any = json.loads(
            _run("export-manifest", "--out", str(tmp_path / "b"), "--zip", "--json")
        )
        archive = Path(payload["path"])
        assert archive.suffix == ".zip" and archive.is_file()

    def test_export_requires_a_manifest(self, factory_env: FactoryConfig) -> None:
        with pytest.raises(CommandError):
            _run("export-manifest")
