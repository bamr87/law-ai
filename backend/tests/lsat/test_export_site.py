"""Exporter tests (spec 025 T-001: FR-1, FR-2, AC-1; spec 047 FR-6, AC-5)."""

from __future__ import annotations

import json
from io import StringIO
from pathlib import Path

from django.core.management import call_command

from law_ai.lsat.management.commands.lsat_export import SCHEMA_VERSION, build_content
from law_ai.lsat.services.bank import Question, load_bank
from law_ai.lsat.services.writing import (
    WritingPrompt,
    WritingRubric,
    load_writing_prompts,
    load_writing_rubrics,
)


class TestBuildContent:
    def test_questions_are_full_model_dumps_with_keys(self) -> None:
        content = build_content()
        assert content["schema_version"] == SCHEMA_VERSION
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


class TestWritingPayload:
    """Spec 047 FR-6: the writing section ships in the static artifact."""

    def test_prompts_and_rubrics_round_trip(self) -> None:
        content = build_content()
        prompts = load_writing_prompts()
        rubrics = load_writing_rubrics()
        assert content["counts"]["writing_prompts"] == len(prompts)
        assert len(content["writing_prompts"]) == len(prompts)
        assert len(content["writing_rubrics"]) == len(rubrics)
        for raw in content["writing_prompts"]:
            assert WritingPrompt.model_validate(raw).id == raw["id"]
        for raw in content["writing_rubrics"]:
            assert WritingRubric.model_validate(raw).id == raw["id"]

    def test_model_responses_ship_in_full(self) -> None:
        # The published site has no backend, so the annotated worked example
        # IS the offline feedback loop (FR-3 / NFR-OFFLINE-1). The client
        # locks it until submit; the bundle must still carry it.
        content = build_content()
        for raw in content["writing_prompts"]:
            assert raw["model_response"]["essay"]
            assert raw["model_response"]["annotations"]
            assert raw["self_check"]

    def test_every_prompt_rubric_resolves_inside_the_artifact(self) -> None:
        content = build_content()
        rubric_ids = {r["id"] for r in content["writing_rubrics"]}
        for raw in content["writing_prompts"]:
            assert raw["rubric_id"] in rubric_ids

    def test_writing_ordering_is_stable(self) -> None:
        content = build_content()
        ids = [p["id"] for p in content["writing_prompts"]]
        assert ids == sorted(ids)

    def test_ws_section_ships_with_zero_questions(self) -> None:
        content = build_content()
        codes = {s["code"] for s in content["sections"]}
        assert "WS" in codes
        assert content["counts"]["WS"] == 0
        assert not [q for q in content["questions"] if q["section"] == "WS"]


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


# ---------------------------------------------------------------------------
# Knowledge library (spec 048 T-021: FR-13, NFR-DETERMINISM-1, AC-5)
# ---------------------------------------------------------------------------


class TestLibraryExport:
    def test_library_and_tracks_ship_whole(self) -> None:
        from law_ai.lsat.services.library import load_library, load_tracks

        content = build_content()
        assert content["counts"]["library_articles"] == len(load_library())
        assert content["counts"]["library_tracks"] == len(load_tracks())
        assert len(content["library"]) == len(load_library())

    def test_articles_carry_compiled_blocks_not_markdown(self) -> None:
        """Both clients render typed blocks; neither parses anything."""
        content = build_content()
        for article in content["library"]:
            assert article["blocks"], article["id"]
            assert "markdown" not in article
            assert {b["block_type"] for b in article["blocks"]} <= {
                "heading",
                "paragraph",
                "list",
                "callout",
                "table",
                "notation",
            }

    def test_articles_carry_their_outline(self) -> None:
        for article in build_content()["library"]:
            assert article["outline"], article["id"]
            anchors = {e["anchor"] for e in article["outline"]}
            assert "key-takeaways" in anchors, article["id"]

    def test_tracks_carry_computed_durations(self) -> None:
        for track in build_content()["library_tracks"]:
            assert track["article_count"] == len(track["article_ids"])
            assert track["estimated_minutes"] > 0

    def test_library_ordering_is_stable(self) -> None:
        ids = [a["id"] for a in build_content()["library"]]
        assert ids == sorted(ids)

    def test_tracks_ship_in_curriculum_order_not_id_order(self) -> None:
        """The authored order is the syllabus; both readers land on its head."""
        from law_ai.lsat.services.library import load_tracks

        shipped = [t["id"] for t in build_content()["library_tracks"]]
        assert shipped == list(load_tracks())
        assert shipped != sorted(shipped), (
            "id order and file order coincide — this test no longer proves "
            "the exporter preserves curriculum order"
        )

    def test_reexport_is_byte_identical_apart_from_the_timestamp(self) -> None:
        first, second = build_content(), build_content()
        first.pop("generated_at")
        second.pop("generated_at")
        assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)
