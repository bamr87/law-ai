"""The author → gates → judge → revise loop (spec 054 FR-6)."""

from __future__ import annotations

from typing import Any

import pytest

from law_ai.lsat.factory.revise import (
    author_with_review,
    judge_blocks,
    judge_objections,
)

pytestmark = [pytest.mark.unit]


def _author(drafts: list[dict[str, Any] | None], *, degraded_at: int | None = None):
    calls: list[list[str]] = []

    async def run(critique: list[str]) -> tuple[dict[str, Any] | None, str, bool]:
        calls.append(list(critique))
        n = len(calls)
        if degraded_at is not None and n >= degraded_at:
            return None, "fallback/offline", True
        return drafts[min(n, len(drafts)) - 1], "test/model", False

    run.calls = calls  # type: ignore[attr-defined]
    return run


async def _async(value: dict[str, Any]) -> dict[str, Any]:
    return value


@pytest.mark.asyncio
async def test_accepts_first_clean_draft_without_a_judge() -> None:
    author = _author([{"v": 1}])
    out = await author_with_review(author, lambda d: [])
    assert out.accepted and out.draft == {"v": 1} and len(out.rounds) == 1


@pytest.mark.asyncio
async def test_gate_issues_are_the_next_rounds_critique() -> None:
    author = _author([{"v": 1}, {"v": 2}])
    out = await author_with_review(author, lambda d: ["bad"] if d["v"] == 1 else [])
    assert out.accepted and out.draft == {"v": 2}
    assert author.calls == [[], ["bad"]]
    assert out.rounds[0].gate_issues == ["bad"] and out.rounds[1].accepted


@pytest.mark.asyncio
async def test_judge_fail_and_key_disagreement_block_and_feed_back() -> None:
    verdicts = iter(
        [
            {
                "verdict": "fail",
                "issues": ["Choice (B) also works."],
                "key_agrees": False,
                "solved_key": "B",
            },
            {"verdict": "flag", "issues": ["minor"], "key_agrees": True},
            {"verdict": "pass", "issues": [], "key_agrees": True},
        ]
    )

    async def judge(d: dict[str, Any]) -> dict[str, Any]:
        return next(verdicts)

    author = _author([{"v": 1}, {"v": 2}, {"v": 3}])
    out = await author_with_review(author, lambda d: [], judge)
    # fail → revised; flag with an issue → revised again while rounds remain.
    assert out.accepted and out.draft == {"v": 3} and len(out.rounds) == 3
    critique = author.calls[1]
    assert critique[0].startswith("The judge solved the item blind and reached B")
    assert "Choice (B) also works." in critique
    assert author.calls[2] == ["minor"]
    assert out.judge is not None and out.judge["verdict"] == "pass"


@pytest.mark.asyncio
async def test_a_flag_is_accepted_on_the_final_round() -> None:
    async def judge(d: dict[str, Any]) -> dict[str, Any]:
        return {"verdict": "flag", "issues": ["still minor"], "key_agrees": True}

    author = _author([{"v": 1}, {"v": 2}])
    out = await author_with_review(author, lambda d: [], judge, max_rounds=2)
    assert out.accepted and out.draft == {"v": 2} and len(out.rounds) == 2
    # A flag with nothing concrete never costs a round.
    quiet = _author([{"v": 1}])
    out = await author_with_review(
        quiet,
        lambda d: [],
        lambda d: _async({"verdict": "flag", "issues": [], "key_agrees": True}),
    )
    assert out.accepted and len(out.rounds) == 1


@pytest.mark.asyncio
async def test_cap_returns_last_draft_unaccepted() -> None:
    author = _author([{"v": 1}])
    out = await author_with_review(author, lambda d: ["never"], max_rounds=2)
    assert not out.accepted and out.draft == {"v": 1} and len(out.rounds) == 2


@pytest.mark.asyncio
async def test_degraded_author_stops_the_loop() -> None:
    author = _author([{"v": 1}], degraded_at=2)
    out = await author_with_review(author, lambda d: ["fix"], max_rounds=3)
    assert out.degraded and not out.accepted and out.draft == {"v": 1}
    assert len(out.rounds) == 2


def test_blocking_rules() -> None:
    assert not judge_blocks({"verdict": "fail", "degraded": True})
    assert not judge_blocks(None)
    assert judge_blocks({"verdict": "flag", "key_agrees": False})
    assert judge_blocks({"verdict": "flag", "issues": ["x"]})
    assert not judge_blocks({"verdict": "flag", "issues": ["x"]}, final=True)
    assert judge_blocks({"verdict": "fail", "issues": []}, final=True)
    assert judge_objections({"degraded": True, "issues": ["[OFFLINE] x"]}) == []
    assert judge_objections(
        {"single_best_answer": False, "issues": ["[OFFLINE] x", "real"]}
    ) == [
        "A second choice is defensible; make exactly one choice survive.",
        "real",
    ]


@pytest.mark.asyncio
async def test_final_reviewer_runs_once_on_acceptance_and_can_unaccept() -> None:
    seen: list[dict[str, Any]] = []

    async def final_ok(d: dict[str, Any]) -> dict[str, Any]:
        seen.append(d)
        return {"verdict": "flag", "issues": ["for the human"], "key_agrees": True}

    out = await author_with_review(
        _author([{"v": 1}]), lambda d: [], final_reviewer=final_ok
    )
    # A flag from the final reviewer is a reservation, not a block, and it
    # never costs another round.
    assert out.accepted and len(out.rounds) == 1
    assert seen == [{"v": 1}]
    assert out.final_review == {
        "verdict": "flag",
        "issues": ["for the human"],
        "key_agrees": True,
    }

    async def final_fail(d: dict[str, Any]) -> dict[str, Any]:
        return {
            "verdict": "fail",
            "issues": ["wrong key"],
            "key_agrees": False,
            "solved_key": "C",
        }

    out = await author_with_review(
        _author([{"v": 1}]), lambda d: [], final_reviewer=final_fail
    )
    assert not out.accepted and out.draft == {"v": 1} and out.final_review is not None
    # Never runs on a draft that was not accepted in the first place.
    calls: list[int] = []

    async def counting(d: dict[str, Any]) -> dict[str, Any]:
        calls.append(1)
        return {"verdict": "pass"}

    out = await author_with_review(
        _author([{"v": 1}]), lambda d: ["never"], max_rounds=1, final_reviewer=counting
    )
    assert not out.accepted and calls == []
