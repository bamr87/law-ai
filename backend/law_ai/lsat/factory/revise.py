"""Author → gates → judge → revise: the improvement loop (spec 054 FR-6).

The factory's judge tier was advisory only: a ``fail`` verdict rode on the
proposal and changed nothing, so a draft the judge had already torn apart
still reached the reviewer exactly as written. This loop closes that gap for
authors that can take a critique. Each round the author drafts, the
deterministic gates run, and the judge attacks the draft; every objection is
handed back to the author for the next round, up to a bound. The outcome
carries the whole history so a reviewer sees what was objected to and what
changed, and it lands in the HITL queue like anything else — the loop improves
what a human is shown, never who decides (constitution §5).

Written against callables rather than crews so it is testable with fakes and
reusable by any author that accepts a ``critique``.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Any

from pydantic import BaseModel, Field

logger = logging.getLogger("law_ai.lsat.factory.revise")

#: Default cap on drafting rounds. Three is one draft plus two revisions; every
#: round bills at least one provider call, so callers may lower it.
DEFAULT_MAX_ROUNDS = 3

#: ``author(critique) -> (draft | None, model_label, degraded)``. A ``None``
#: draft with ``degraded=True`` means no provider answered; the loop stops.
AuthorFn = Callable[[list[str]], Awaitable[tuple[dict[str, Any] | None, str, bool]]]
#: ``gates(draft) -> issues``; an empty list is a pass.
GateFn = Callable[[dict[str, Any]], list[str]]
#: ``judge(draft) -> verdict dict`` with at least ``verdict`` (pass|flag|fail),
#: ``issues``, ``key_agrees`` and ``degraded``.
JudgeFn = Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]


class ReviseRound(BaseModel):
    """What one round produced and what was objected to."""

    round: int = Field(ge=1)
    model: str
    gate_issues: list[str] = Field(default_factory=list)
    judge: dict[str, Any] | None = None
    #: The critique handed to the *next* round (gate issues + judge issues).
    critique: list[str] = Field(default_factory=list)
    accepted: bool = False


class ReviseOutcome(BaseModel):
    draft: dict[str, Any] | None
    rounds: list[ReviseRound] = Field(default_factory=list)
    #: True when the final draft cleared the gates, the judge did not fail it,
    #: and the final reviewer (when one runs) did not fail it either.
    accepted: bool = False
    #: The final reviewer's verdict (spec 054: Fable), when one ran.
    final_review: dict[str, Any] | None = None
    #: True when the author could not draft at all (no provider).
    degraded: bool = False
    #: The last judge verdict, for the proposal's ``meta.factory.judge``.
    judge: dict[str, Any] | None = None
    model: str = "fallback/offline"


def judge_objections(verdict: dict[str, Any]) -> list[str]:
    """The judge's actionable complaints, as critique lines.

    A degraded verdict decides nothing and contributes nothing; a ``fail`` or a
    disagreeing blind key is stated first because it is the thing to fix.
    """
    if verdict.get("degraded"):
        return []
    out: list[str] = []
    if verdict.get("key_agrees") is False and verdict.get("solved_key"):
        out.append(
            "The judge solved the item blind and reached "
            f"{verdict['solved_key']}, not the stated key; either the key or the "
            "distractors are wrong."
        )
    if verdict.get("single_best_answer") is False:
        out.append("A second choice is defensible; make exactly one choice survive.")
    for issue in verdict.get("issues") or []:
        text = str(issue).strip()
        if text and not text.startswith("[OFFLINE]"):
            out.append(text)
    return out


def judge_blocks(verdict: dict[str, Any] | None, *, final: bool = False) -> bool:
    """Whether a verdict is a reason to redraft.

    ``fail`` blocks; so does a blind key that disagrees with the stated one
    even under ``flag``, because a wrong key is the one defect no reviewer
    should have to catch. A ``flag`` that names concrete issues blocks too
    while rounds remain — that is the loop improving what the reviewer sees —
    but on the ``final`` round it is accepted as what it is: a draft with a
    named reservation for a human. A degraded verdict never blocks: an outage
    is not an objection.
    """
    if verdict is None or verdict.get("degraded"):
        return False
    if verdict.get("verdict") == "fail":
        return True
    if verdict.get("key_agrees") is False:
        return True
    return (
        not final
        and verdict.get("verdict") == "flag"
        and bool(judge_objections(verdict))
    )


async def _finalize(
    outcome: ReviseOutcome, final_reviewer: JudgeFn | None
) -> ReviseOutcome:
    """Run the final reviewer over an accepted draft; a block un-accepts it.

    The final reviewer is a second, independent judge (a different model by
    design). It never triggers another round — its objections are for the
    human — so a `fail` or a disagreeing key simply files the draft flagged.
    """
    if final_reviewer is None or outcome.draft is None or not outcome.accepted:
        return outcome
    verdict = await final_reviewer(outcome.draft)
    blocked = judge_blocks(verdict, final=True)
    return outcome.model_copy(update={"final_review": verdict, "accepted": not blocked})


async def author_with_review(
    author: AuthorFn,
    gates: GateFn,
    judge: JudgeFn | None = None,
    *,
    max_rounds: int = DEFAULT_MAX_ROUNDS,
    final_reviewer: JudgeFn | None = None,
) -> ReviseOutcome:
    """Draft, check, attack, revise — up to ``max_rounds`` — and report it all.

    Stops early on the first draft that passes the gates and is not blocked
    by the judge. When the cap is hit, the *last* draft is returned with
    ``accepted=False`` so it can still be filed for a human with its history,
    rather than thrown away after paying for it. An accepted draft then goes
    to ``final_reviewer`` when one is given (spec 054: Fable); its verdict is
    recorded on the outcome and a block un-accepts the draft without another
    round.

    >>> import asyncio
    >>> async def ok(critique): return ({"stem": "x"}, "test/model", False)
    >>> asyncio.run(author_with_review(ok, lambda d: [])).accepted
    True
    """
    rounds: list[ReviseRound] = []
    critique: list[str] = []
    last_draft: dict[str, Any] | None = None
    last_verdict: dict[str, Any] | None = None
    model = "fallback/offline"
    for n in range(1, max(1, max_rounds) + 1):
        draft, model, degraded = await author(critique)
        if draft is None or degraded:
            rounds.append(ReviseRound(round=n, model=model, critique=critique))
            return ReviseOutcome(
                draft=last_draft,
                rounds=rounds,
                accepted=False,
                degraded=True,
                judge=last_verdict,
                model=model,
            )
        last_draft = draft
        gate_issues = list(gates(draft))
        verdict: dict[str, Any] | None = None
        if not gate_issues and judge is not None:
            verdict = await judge(draft)
            last_verdict = verdict
        accepted = not gate_issues and not judge_blocks(
            verdict, final=n >= max(1, max_rounds)
        )
        next_critique = gate_issues + (judge_objections(verdict) if verdict else [])
        rounds.append(
            ReviseRound(
                round=n,
                model=model,
                gate_issues=gate_issues,
                judge=verdict,
                critique=next_critique,
                accepted=accepted,
            )
        )
        if accepted:
            return await _finalize(
                ReviseOutcome(
                    draft=draft,
                    rounds=rounds,
                    accepted=True,
                    judge=verdict,
                    model=model,
                ),
                final_reviewer,
            )
        critique = next_critique
        logger.info("revise round %d: %d objection(s)", n, len(critique))
    return ReviseOutcome(
        draft=last_draft,
        rounds=rounds,
        accepted=False,
        judge=last_verdict,
        model=model,
    )


__all__ = [
    "DEFAULT_MAX_ROUNDS",
    "AuthorFn",
    "GateFn",
    "JudgeFn",
    "ReviseOutcome",
    "ReviseRound",
    "author_with_review",
    "judge_blocks",
    "judge_objections",
]
