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
