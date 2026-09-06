"""Difficulty, measured — a structural proxy plus the graded fold-back.

BL-20260903-14. Until now every synthesized item inherited its schema's
*declared* band: ``lr-necessary-assumption`` said ``hard`` and every item it
ever produced was hard, in every domain, at every seed, for every learner.
Two things are wrong with that.

**It is not comparable across families.** "Hard" on a quantifier schema and
"hard" on an assumption schema were two authors' opinions expressed in the same
word. Nothing put them on one scale, so a census that counts hard items counted
two different things.

**It is not per item.** Arrangements are drawn now (BL-20260903-15): the same
schema emits a two-link chain with one side conditional and a four-link chain
with two, and calling both ``easy`` throws away the difference the draw just
created.

So this module scores each *item* on features that mean the same thing in every
family, and bands the score against the engine's own distribution:

``premises``
    Statements that must be held at once — including rendered preamble.
``depth``
    Nesting of the deepest premise. A conditional whose antecedent is itself a
    conjunction is not one fact.
``slots``
    Distinct properties, entities and groups in play.
``rules``
    Constraints the drawn arrangement imposed (0 for a fixed arrangement).
``closeness``
    The share of premise-satisfying models in which the *best distractor* is
    true. This is the feature that makes families comparable: it is measured in
    the same unit — a fraction of the item's own admissible cases — whether the
    trap is a quantifier scope error or a not-quite-necessary assumption, and a
    trap true in 95% of cases is a hard trap by any definition.
``space``
    ``log10`` of the model space: how many cases the item ranges over.
``obligations``
    How many entailment relations the family's rule demands, read off the
    family rules :mod:`law_ai.lsat.synth.verify` documents. A must-be-true item
    asks one question of the models; a sufficient-assumption item asks three
    (the conclusion does *not* follow, it does follow once the credited choice
    is added, and it still does not follow for any distractor). That is a
    property of the family, not an opinion about it, and it is the other half
    of what makes bands comparable across families.

Two deliberate limits.

**Structural items get no proxy.** ``lr-causal-weaken`` and
``lr-percent-vs-number`` have no model space, so every model-based feature is
zero and the proxy cannot tell them apart. Rather than pretend, :func:`measure`
returns ``None`` for a structural proof kind and the declared band stands —
the same honesty the verifier already applies to a structural guarantee.

**The proxy never moves a band more than one step.** The declared band is a
prior worth keeping: a proxy is a proxy, and an ``easy`` schema that suddenly
emits ``elite`` items on one unlucky draw would be a worse error than the one
this module fixes. :func:`blend` clamps.

Where real evidence exists it outranks both: :mod:`law_ai.lsat.synth.calibrate`
folds ``lsat_grade`` accuracy back onto the schema that produced the item, and
a schema with enough attempts is banded by what learners actually did.
"""

from __future__ import annotations

import math
from typing import Any

from pydantic import BaseModel

from law_ai.lsat.services.bank import DIFFICULTY_ORDER, Difficulty
from law_ai.lsat.synth.logic import (
    And,
    Atom,
    Iff,
    Implies,
    Not,
    Or,
    Statement,
)
from law_ai.lsat.synth.schemas import Blueprint
from law_ai.lsat.synth.verify import VerificationReport

#: Feature weights. Chosen to put the six features on a comparable scale rather
#: than fitted to an outcome: one point per premise, and a distractor true in
#: every admissible case is worth four premises of work.
WEIGHTS: dict[str, float] = {
    "premises": 1.0,
    "depth": 1.5,
    "slots": 0.6,
    "rules": 0.8,
    "closeness": 4.0,
    "space": 1.2,
    "obligations": 1.0,
}

#: Entailment relations each family's verification rule demands, counted from
#: the family rules in :mod:`law_ai.lsat.synth.verify`. Not a difficulty
#: judgement: it is how many model-theoretic questions the item's own proof had
#: to answer.
FAMILY_OBLIGATIONS: dict[str, int] = {
    "must_be_true": 1,
    "cannot_be_true": 1,
    "acceptability": 2,
    "sufficient_assumption": 3,
    "necessary_assumption": 2,
}

#: Score cut points, in the engine's own units: the 40th and 75th percentiles
#: of the sweep over every proved (schema, domain, seed) triple — 200 items,
#: five seeds against every domain a schema supports. Constants rather than a
#: live quantile, so one item's band never depends on which other items
#: happened to be generated alongside it. Re-derive them with
#: ``lsat_synth_calibrate --structural`` after adding schemas, and expect the
#: bands of existing items to move when you do.
SCORE_CUTS: tuple[float, float] = (14.7, 16.0)

#: The three bands the proxy assigns, easiest first. The scale has five
#: (spec 047) but the proved registry declares only these, and a proxy that
#: could emit a band no schema ever declares would be asserting more than it
#: measures.
PROXY_BANDS: tuple[Difficulty, Difficulty, Difficulty] = ("easy", "med", "hard")


class ItemComplexity(BaseModel):
    """The structural proxy for one item, with the features behind it."""

    premises: int = 0
    depth: int = 1
    slots: int = 0
    rules: int = 0
    closeness: float = 0.0
    space: float = 0.0
    obligations: int = 0
    score: float = 0.0
    band: Difficulty = "med"

    def explain(self) -> str:
        """One line naming the features, for a preview or a review queue."""
        return (
            f"{self.score:.1f} → {self.band} (premises {self.premises}, "
            f"depth {self.depth}, slots {self.slots}, rules {self.rules}, "
            f"closeness {self.closeness:.2f}, space 10^{self.space:.1f}, "
            f"obligations {self.obligations})"
        )

    def dump(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


def statement_depth(statement: Statement) -> int:
    """Nesting depth. Atoms are 1; a quantified or relational leaf is 2.

    A quantified statement is not an atom: "most reviewed applications were
    approved" already relates two predicates, and treating it as a fact would
    make a quantifier item look simpler than a conditional one.
    """
    if isinstance(statement, Not):
        return 1 + statement_depth(statement.inner)
    if isinstance(statement, Implies):
        return 1 + max(
            statement_depth(statement.antecedent),
            statement_depth(statement.consequent),
        )
    if isinstance(statement, Iff):
        return 1 + max(
            statement_depth(statement.left), statement_depth(statement.right)
        )
    if isinstance(statement, And | Or):
        return 1 + max((statement_depth(p) for p in statement.parts), default=0)
    if isinstance(statement, Atom):
        return 1
    return 2


def band_for(score: float) -> Difficulty:
    """Band one score against :data:`SCORE_CUTS`."""
    low, high = SCORE_CUTS
    if score < low:
        return PROXY_BANDS[0]
    if score < high:
        return PROXY_BANDS[1]
    return PROXY_BANDS[2]


def _closeness(report: VerificationReport) -> float:
    """How nearly-true the best distractor is, as a share of admissible cases."""
    if report.premise_models <= 0:
        return 0.0
    shares = [
        c.supporting_models / report.premise_models
        for c in report.choices
        if not c.role.startswith("credited")
    ]
    return max(shares) if shares else 0.0


def measure(blueprint: Blueprint, report: VerificationReport) -> ItemComplexity | None:
    """Score one item, or ``None`` when there is nothing to measure.

    ``None`` means the proof kind is structural: no model space, so every
    model-derived feature would be zero and the score would say only that the
    item is structural. The declared band stands in that case.
    """
    if blueprint.proof_kind != "logical" or blueprint.space is None:
        return None
    statements: list[Statement] = list(blueprint.premises)
    if blueprint.conclusion is not None:
        statements.append(blueprint.conclusion)
    spec = blueprint.binding_spec
    rules = blueprint.arrangement.get("rule_count", 0)
    features = ItemComplexity(
        premises=len(blueprint.premises) + len(blueprint.preamble),
        depth=max((statement_depth(s) for s in statements), default=1),
        slots=len(spec.property_slots) + len(spec.entity_slots) + len(spec.group_slots),
        rules=rules if isinstance(rules, int) else 0,
        closeness=round(_closeness(report), 4),
        space=round(math.log10(report.space_models), 4) if report.space_models else 0.0,
        obligations=FAMILY_OBLIGATIONS.get(blueprint.family, 1),
    )
    features.score = round(
        WEIGHTS["premises"] * features.premises
        + WEIGHTS["depth"] * (features.depth - 1)
        + WEIGHTS["slots"] * features.slots
        + WEIGHTS["rules"] * features.rules
        + WEIGHTS["closeness"] * features.closeness
        + WEIGHTS["space"] * features.space
        + WEIGHTS["obligations"] * features.obligations,
        4,
    )
    features.band = band_for(features.score)
    return features


def blend(declared: Difficulty, measured: ItemComplexity | None) -> Difficulty:
    """The band an item ships with: the proxy, clamped to one step of declared.

    The clamp is the whole reason this is safe to turn on. The proxy sees
    structure, not prose, and one unlucky draw should not be able to move a
    schema's item two bands away from the judgement of whoever wrote it.
    """
    if measured is None:
        return declared
    order = list(DIFFICULTY_ORDER)
    if declared not in order:  # pragma: no cover - Difficulty is closed
        return measured.band
    lo = max(0, order.index(declared) - 1)
    hi = min(len(order) - 1, order.index(declared) + 1)
    return order[min(hi, max(lo, order.index(measured.band)))]
