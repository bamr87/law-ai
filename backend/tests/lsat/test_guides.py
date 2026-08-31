"""Tests for the solve-guide store (spec 041 T-001/T-002, AC-1)."""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path

import pytest
from pydantic import ValidationError

from law_ai.lsat.services import bank as bank_mod
from law_ai.lsat.services.guides import (
    SolveGuide,
    SolveStep,
    load_guides,
    public_guide_view,
    reset_guide_cache,
)


@pytest.fixture(autouse=True)
def _fresh_cache() -> Iterator[None]:
    reset_guide_cache()
    yield
    reset_guide_cache()


@pytest.fixture()
def sandbox_data_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Copy the real data dir so tests can write a custom guides.json."""
    real = bank_mod.DATA_DIR
    sandbox = tmp_path / "lsat_data"
    sandbox.mkdir()
    for name in ("lr_bank.json", "rc_bank.json", "lg_bank.json"):
        src = real / name
        if src.is_file():
            (sandbox / name).write_text(src.read_text(encoding="utf-8"))
    monkeypatch.setattr(bank_mod, "DATA_DIR", sandbox)
    bank_mod.load_bank.cache_clear()
    yield sandbox
    bank_mod.load_bank.cache_clear()


def _minimal_guide(question_id: str, **overrides: object) -> dict[str, object]:
    # The FR-11 quality gate requires the answer step to name the question's
    # real correct choice, so look it up when the question exists.
    bank = bank_mod.load_bank()
    correct = bank[question_id].correct if question_id in bank else "B"
    guide: dict[str, object] = {
        "question_id": question_id,
        "method": "test method",
        "steps": [
            {"kind": "orient", "title": "Read", "text": "Read it."},
            {
                "kind": "answer",
                "title": "Answer",
                "text": f"It is {correct}.",
                "spoiler": True,
            },
        ],
    }
    guide.update(overrides)
    return guide


def _write_guides(data_dir: Path, items: list[dict[str, object]]) -> None:
    (data_dir / "guides.json").write_text(json.dumps({"items": items}))
    reset_guide_cache()


# ---------------------------------------------------------------------------
# Seed content (FR-3)
# ---------------------------------------------------------------------------


def test_seed_guides_load_and_cover_all_sections() -> None:
    guides = load_guides()
    assert len(guides) >= 9
    bank = bank_mod.load_bank()
    by_section: dict[str, int] = {}
    rep_types: set[str] = set()
    for g in guides.values():
        assert g.question_id in bank
        assert len(g.steps) >= 4
        # Every guide ends with a spoiler answer step.
        assert g.steps[-1].kind == "answer"
        assert g.steps[-1].spoiler is True
        section = bank[g.question_id].section
        by_section[section] = by_section.get(section, 0) + 1
        for step in g.steps:
            if step.representation is not None:
                rep_types.add(step.representation.rep_type)
    assert by_section.get("LG", 0) >= 3
    assert by_section.get("LR", 0) >= 3
    assert by_section.get("RC", 0) >= 3
    # All five representation kinds are exercised by the seed content.
    assert rep_types == {"sequence", "grid", "notation", "argument_map", "passage_map"}


# ---------------------------------------------------------------------------
# Validation failures (AC-1)
# ---------------------------------------------------------------------------


def test_guide_for_unknown_question_fails_loudly(sandbox_data_dir: Path) -> None:
    _write_guides(sandbox_data_dir, [_minimal_guide("no-such-question")])
    with pytest.raises(ValueError, match="unknown question"):
        load_guides()


def test_duplicate_guides_rejected(sandbox_data_dir: Path) -> None:
    qid = next(iter(bank_mod.load_bank()))
    _write_guides(sandbox_data_dir, [_minimal_guide(qid), _minimal_guide(qid)])
    with pytest.raises(ValueError, match="duplicate guide"):
        load_guides()


def test_empty_steps_rejected(sandbox_data_dir: Path) -> None:
    qid = next(iter(bank_mod.load_bank()))
    _write_guides(sandbox_data_dir, [_minimal_guide(qid, steps=[])])
    with pytest.raises(ValidationError):
        load_guides()


def test_unknown_rep_type_rejected(sandbox_data_dir: Path) -> None:
    qid = next(iter(bank_mod.load_bank()))
    guide = _minimal_guide(qid)
    steps = guide["steps"]
    assert isinstance(steps, list)
    steps[0]["representation"] = {"rep_type": "hologram", "stuff": []}
    _write_guides(sandbox_data_dir, [guide])
    with pytest.raises(ValidationError):
        load_guides()


def test_argument_map_edge_must_reference_nodes() -> None:
    with pytest.raises(ValueError, match="unknown node id"):
        SolveStep.model_validate(
            {
                "kind": "diagram",
                "title": "Map",
                "text": "…",
                "representation": {
                    "rep_type": "argument_map",
                    "nodes": [{"id": "p1", "role": "premise", "text": "P."}],
                    "edges": [{"from": "p1", "to": "ghost", "relation": "supports"}],
                },
            }
        )


def test_answer_step_forced_to_spoiler() -> None:
    step = SolveStep(kind="answer", title="A", text="It is C.", spoiler=False)
    assert step.spoiler is True


def test_missing_file_returns_empty(sandbox_data_dir: Path) -> None:
    reset_guide_cache()
    assert load_guides() == {}


# ---------------------------------------------------------------------------
# Quality validation (FR-11)
# ---------------------------------------------------------------------------


def _question_with_correct(label: str) -> object:
    bank = bank_mod.load_bank()
    return next(q for q in bank.values() if q.correct == label)


def test_quality_rejects_answer_leak_before_answer_step() -> None:
    from law_ai.lsat.services.guides import validate_guide_quality

    q = _question_with_correct("D")
    guide = SolveGuide.model_validate(
        {
            "question_id": q.id,  # type: ignore[attr-defined]
            "method": "m",
            "steps": [
                {
                    "kind": "infer",
                    "title": "Leaky",
                    "text": "Clearly the answer is D here.",
                },
                {"kind": "answer", "title": "A", "text": "D is correct."},
            ],
        }
    )
    problems = validate_guide_quality(guide, q)
    assert any("names the correct choice" in p for p in problems)


def test_quality_rejects_complete_elimination_without_spoiler() -> None:
    from law_ai.lsat.services.guides import validate_guide_quality

    q = _question_with_correct("D")
    guide = SolveGuide.model_validate(
        {
            "question_id": q.id,  # type: ignore[attr-defined]
            "method": "m",
            "steps": [
                {
                    "kind": "eliminate",
                    "title": "Sweep",
                    "text": "A fails, B fails, C fails, and E fails too.",
                },
                {"kind": "answer", "title": "A", "text": "So D remains."},
            ],
        }
    )
    problems = validate_guide_quality(guide, q)
    assert any("complete elimination" in p for p in problems)


def test_quality_rejects_board_inconsistency() -> None:
    from law_ai.lsat.services.guides import validate_guide_quality

    q = _question_with_correct("D")
    guide = SolveGuide.model_validate(
        {
            "question_id": q.id,  # type: ignore[attr-defined]
            "method": "m",
            "steps": [
                {
                    "kind": "diagram",
                    "title": "Board",
                    "text": "Sketch it.",
                    "representation": {
                        "rep_type": "sequence",
                        "slots": ["1", "2"],
                        "entities": ["F", "G"],
                        "placements": {"3": "Z"},
                        "exclusions": {},
                    },
                },
                {"kind": "answer", "title": "A", "text": "D is correct."},
            ],
        }
    )
    problems = validate_guide_quality(guide, q)
    assert any("unknown slot" in p for p in problems)
    assert any("unknown entity" in p for p in problems)


def test_quality_requires_answer_step_to_name_the_choice() -> None:
    from law_ai.lsat.services.guides import validate_guide_quality

    q = _question_with_correct("D")
    guide = SolveGuide.model_validate(
        {
            "question_id": q.id,  # type: ignore[attr-defined]
            "method": "m",
            "steps": [
                {"kind": "orient", "title": "Read", "text": "Read it."},
                {"kind": "answer", "title": "A", "text": "You know it now."},
            ],
        }
    )
    problems = validate_guide_quality(guide, q)
    assert any("never names the correct choice" in p for p in problems)


def test_quality_clean_seed_guides_pass() -> None:
    from law_ai.lsat.services.guides import validate_guide_quality

    bank = bank_mod.load_bank()
    for guide in load_guides().values():
        assert validate_guide_quality(guide, bank[guide.question_id]) == []


# ---------------------------------------------------------------------------
# Public view / spoiler stripping (FR-4)
# ---------------------------------------------------------------------------


def test_public_view_withholds_spoiler_content() -> None:
    guide = SolveGuide.model_validate(_minimal_guide("q-x"))
    view = public_guide_view(guide)
    assert view["step_count"] == 2
    first, last = view["steps"]
    assert first["locked"] is False
    assert first["text"] == "Read it."
    assert last == {
        "kind": "answer",
        "title": "Answer",
        "spoiler": True,
        "locked": True,
    }


def test_public_view_include_spoilers_returns_full_steps() -> None:
    guide = SolveGuide.model_validate(_minimal_guide("q-x"))
    view = public_guide_view(guide, include_spoilers=True)
    last = view["steps"][-1]
    assert last["locked"] is False
    assert last["text"] == "It is B."


def test_public_view_serializes_edges_with_from_alias() -> None:
    seed = load_guides()
    guide = seed["lr-001"]
    view = public_guide_view(guide, include_spoilers=True)
    maps = [
        s["representation"]
        for s in view["steps"]
        if s.get("representation") and s["representation"]["rep_type"] == "argument_map"
    ]
    assert maps, "lr-001 seed guide should carry an argument_map"
    edge = maps[0]["edges"][0]
    assert "from" in edge and "from_" not in edge
