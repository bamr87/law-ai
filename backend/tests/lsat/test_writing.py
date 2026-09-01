"""Argumentative Writing content model + loaders (spec 047 FR-1/FR-2, AC-1/AC-2)."""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from law_ai.lsat.services import bank as bank_mod
from law_ai.lsat.services import writing as writing_mod
from law_ai.lsat.services.bank import MCQ_SECTIONS, Question, load_sections
from law_ai.lsat.services.writing import (
    WritingRubric,
    load_writing_prompts,
    load_writing_rubrics,
    public_prompt_view,
    rubric_for,
)

pytestmark = pytest.mark.unit


@pytest.fixture()
def writing_sandbox(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    """Per-test copy of the writing data files, redirected through bank.DATA_DIR.

    ``writing.py`` resolves its directory through the bank module (the
    guides.py convention), so pointing ``bank.DATA_DIR`` at a sandbox
    redirects both loaders and lets a test corrupt a file without touching
    checked-in content.
    """
    real = bank_mod.DATA_DIR
    sandbox = tmp_path / "lsat_data"
    sandbox.mkdir()
    for name in (
        "concepts.json",
        "sections.json",
        "writing_rubrics.json",
        "writing_prompts.json",
    ):
        (sandbox / name).write_text(
            (real / name).read_text(encoding="utf-8"), encoding="utf-8"
        )
    monkeypatch.setattr(bank_mod, "DATA_DIR", sandbox)

    def _clear() -> None:
        bank_mod.load_concepts.cache_clear()
        writing_mod.reset_writing_caches()

    _clear()
    yield sandbox
    _clear()


def _write(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def _mutate_prompts(sandbox: Path, mutate: Any) -> None:
    path = sandbox / "writing_prompts.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    mutate(data["items"][0])
    _write(path, data)
    writing_mod.reset_writing_caches()


# ---------------------------------------------------------------------------
# AC-1 — the shipped library loads, and cross-reference drift fails loudly
# ---------------------------------------------------------------------------


class TestShippedContent:
    def test_rubrics_and_prompts_load(self) -> None:
        rubrics = load_writing_rubrics()
        prompts = load_writing_prompts()
        assert rubrics, "no writing rubric shipped"
        assert prompts, "no writing prompts shipped"

    def test_every_prompt_resolves_its_rubric(self) -> None:
        for prompt in load_writing_prompts().values():
            assert rubric_for(prompt).id == prompt.rubric_id

    def test_self_check_covers_every_rubric_criterion(self) -> None:
        # A self-check that skips a criterion leaves an offline learner with no
        # way to score that dimension at all — the whole point of FR-3.
        for prompt in load_writing_prompts().values():
            rubric = rubric_for(prompt)
            checked = {s.criterion_id for s in prompt.self_check}
            assert checked == set(
                rubric.criterion_ids
            ), f"{prompt.id} self-check misses {set(rubric.criterion_ids) - checked}"

    def test_model_response_annotates_every_criterion(self) -> None:
        for prompt in load_writing_prompts().values():
            rubric = rubric_for(prompt)
            annotated = {a.criterion_id for a in prompt.model_response.annotations}
            assert annotated == set(rubric.criterion_ids), (
                f"{prompt.id} model response leaves "
                f"{set(rubric.criterion_ids) - annotated} unexplained"
            )

    def test_ws_section_metadata_ships(self) -> None:
        sections = load_sections()
        assert "WS" in sections
        assert sections["WS"].concepts, "WS section lists no concepts"


class TestRubricValidation:
    def _base(self) -> dict[str, Any]:
        return {
            "id": "r1",
            "name": "R",
            "summary": "s",
            "bands": [
                {"level": 1, "label": "Low", "descriptor": "d"},
                {"level": 2, "label": "High", "descriptor": "d"},
            ],
            "criteria": [
                {"id": "a", "name": "A", "description": "d", "weight": 0.5},
                {"id": "b", "name": "B", "description": "d", "weight": 0.5},
            ],
        }

    def test_valid_rubric_accepted(self) -> None:
        assert WritingRubric.model_validate(self._base()).criterion_ids == ("a", "b")

    def test_weights_must_sum_to_one(self) -> None:
        payload = self._base()
        payload["criteria"][0]["weight"] = 0.9
        with pytest.raises(ValidationError, match="weights sum to"):
            WritingRubric.model_validate(payload)

    def test_duplicate_criterion_ids_rejected(self) -> None:
        payload = self._base()
        payload["criteria"][1]["id"] = "a"
        with pytest.raises(ValidationError, match="duplicate criterion ids"):
            WritingRubric.model_validate(payload)

    def test_bands_must_ascend(self) -> None:
        payload = self._base()
        payload["bands"] = list(reversed(payload["bands"]))
        with pytest.raises(ValidationError, match="ascend"):
            WritingRubric.model_validate(payload)

    def test_band_notes_must_name_declared_levels(self) -> None:
        payload = self._base()
        payload["criteria"][0]["band_notes"] = {"7": "nope"}
        with pytest.raises(ValidationError, match="unknown band level"):
            WritingRubric.model_validate(payload)


class TestLoaderCrossReferences:
    def test_unknown_rubric_fails_the_load(self, writing_sandbox: Path) -> None:
        _mutate_prompts(writing_sandbox, lambda p: p.update(rubric_id="nope"))
        with pytest.raises(ValueError, match="unknown rubric"):
            load_writing_prompts()

    def test_self_check_on_unknown_criterion_fails(self, writing_sandbox: Path) -> None:
        _mutate_prompts(
            writing_sandbox,
            lambda p: p["self_check"].append(
                {"criterion_id": "not-a-criterion", "prompt": "?"}
            ),
        )
        with pytest.raises(ValueError, match="self-check references criteria"):
            load_writing_prompts()

    def test_annotation_on_unknown_criterion_fails(self, writing_sandbox: Path) -> None:
        _mutate_prompts(
            writing_sandbox,
            lambda p: p["model_response"]["annotations"].append(
                {"criterion_id": "not-a-criterion", "note": "x"}
            ),
        )
        with pytest.raises(ValueError, match="annotates criteria"):
            load_writing_prompts()

    def test_unknown_concept_tag_fails(self, writing_sandbox: Path) -> None:
        _mutate_prompts(
            writing_sandbox, lambda p: p["concepts"].append("no-such-concept")
        )
        with pytest.raises(ValueError, match="unknown concept"):
            load_writing_prompts()

    def test_duplicate_prompt_id_fails(self, writing_sandbox: Path) -> None:
        path = writing_sandbox / "writing_prompts.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        data["items"].append(data["items"][0])
        _write(path, data)
        writing_mod.reset_writing_caches()
        with pytest.raises(ValueError, match="duplicate writing prompt id"):
            load_writing_prompts()

    def test_model_response_must_take_a_declared_position(
        self, writing_sandbox: Path
    ) -> None:
        _mutate_prompts(
            writing_sandbox,
            lambda p: p["model_response"].update(position_id="not-a-position"),
        )
        with pytest.raises(ValueError, match="unknown position"):
            load_writing_prompts()

    def test_missing_files_load_empty_rather_than_crash(
        self, writing_sandbox: Path
    ) -> None:
        (writing_sandbox / "writing_prompts.json").unlink()
        (writing_sandbox / "writing_rubrics.json").unlink()
        writing_mod.reset_writing_caches()
        assert load_writing_prompts() == {}
        assert load_writing_rubrics() == {}


# ---------------------------------------------------------------------------
# AC-2 — WS has no multiple-choice form
# ---------------------------------------------------------------------------


class TestWritingIsNotAQuestion:
    def _mcq(self, section: str) -> dict[str, Any]:
        return {
            "id": "x-001",
            "section": section,
            "type": section,
            "difficulty": "easy",
            "stem": "s",
            "choices": [{"label": ch, "text": "t"} for ch in "ABCDE"],
            "correct": "A",
            "explanation": "e",
            "source": "original (CC0)",
        }

    @pytest.mark.parametrize("section", MCQ_SECTIONS)
    def test_mcq_sections_still_validate(self, section: str) -> None:
        assert Question.model_validate(self._mcq(section)).section == section

    def test_ws_question_is_rejected(self) -> None:
        with pytest.raises(ValidationError, match="no multiple-choice"):
            Question.model_validate(self._mcq("WS"))

    def test_ws_rejected_via_the_type_alias_alone(self) -> None:
        payload = self._mcq("LR")
        payload["type"] = "WS"
        with pytest.raises(ValidationError, match="no multiple-choice"):
            Question.model_validate(payload)

    def test_no_writing_item_reaches_the_bank(self) -> None:
        assert all(q.section in MCQ_SECTIONS for q in bank_mod.load_bank().values())


# ---------------------------------------------------------------------------
# Public view — the model response is withheld pre-draft
# ---------------------------------------------------------------------------


class TestPublicView:
    def test_public_view_carries_no_model_response(self) -> None:
        prompt = next(iter(load_writing_prompts().values()))
        payload = public_prompt_view(prompt).model_dump()
        assert "model_response" not in payload
        assert payload["has_model_response"] is True
        # The essay text must not leak through any other field.
        assert prompt.model_response.essay[:80] not in json.dumps(payload)

    def test_public_view_keeps_the_self_check(self) -> None:
        # Self-check questions are not spoilers — they are the offline
        # feedback loop and must be readable before drafting.
        prompt = next(iter(load_writing_prompts().values()))
        assert public_prompt_view(prompt).self_check == prompt.self_check
