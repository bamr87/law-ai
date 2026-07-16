"""Exporter tests (spec 025 T-001: FR-1, FR-2, AC-1)."""

from __future__ import annotations

import json
from io import StringIO
from pathlib import Path

from django.core.management import call_command

from law_ai.lsat.management.commands.lsat_export import build_content
from law_ai.lsat.services.bank import Question, load_bank


class TestBuildContent:
    def test_questions_are_full_model_dumps_with_keys(self) -> None:
        content = build_content()
        assert content["schema_version"] == 1
        assert content["counts"]["total"] == len(load_bank())
        for raw in content["questions"]:
            # Round-trips through the canonical model — and keeps the key.
            q = Question.model_validate(raw)
            assert raw["correct"] in {c["label"] for c in raw["choices"]}
            assert raw["explanation"]
            assert q.id == raw["id"]

    def test_ordering_is_stable(self) -> None:
        a = build_content()
        b = build_content()
        a.pop("generated_at")
        b.pop("generated_at")
        assert a == b
        # Sections grouped LR → RC → LG, ids sorted within each section.
        sections = [q["section"] for q in a["questions"]]
        assert sections == sorted(sections, key=("LR", "RC", "LG").index)
        for sec in ("LR", "RC", "LG"):
            sec_ids = [q["id"] for q in a["questions"] if q["section"] == sec]
            assert sec_ids == sorted(sec_ids)

    def test_passages_and_concepts_included(self) -> None:
        content = build_content()
        passage_ids = {p["id"] for p in content["passages"]}
        for q in content["questions"]:
            if q.get("passage_id"):
                assert q["passage_id"] in passage_ids
        assert {c["id"] for c in content["concepts"]} >= {
            "weaken",
            "grouping-game",
            "rc-inference",
        }


class TestCommand:
    def test_writes_artifact(self, tmp_path: Path) -> None:
        out = StringIO()
        call_command("lsat_export", "--out", str(tmp_path), stdout=out)
        artifact = tmp_path / "content.json"
        assert artifact.is_file()
        blob = json.loads(artifact.read_text(encoding="utf-8"))
        assert blob["counts"]["total"] == len(load_bank())
        assert "exported" in out.getvalue()

    def test_deterministic_apart_from_timestamp(self, tmp_path: Path) -> None:
        # AC-1: two runs differ only in generated_at.
        call_command("lsat_export", "--out", str(tmp_path / "a"), stdout=StringIO())
        call_command("lsat_export", "--out", str(tmp_path / "b"), stdout=StringIO())
        a = json.loads((tmp_path / "a" / "content.json").read_text())
        b = json.loads((tmp_path / "b" / "content.json").read_text())
        a.pop("generated_at")
        b.pop("generated_at")
        assert a == b
