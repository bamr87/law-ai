"""Verification — the report that makes a generated item trustworthy.

Spec 049 FR-9/FR-10/FR-11. Every item carries one of these, and an item whose
report is not clean is never emitted. The report is deliberately verbose about
*what was checked over how many models*, because "the key is proved" is only
worth anything if the claim is inspectable.

The family rules:

``must_be_true``
    Exactly one choice entailed, and it is the credited one.
``cannot_be_true``
    Exactly one choice contradicted, and it is the credited one.
``acceptability``
    The credited choice is consistent with the rules; every other is ruled out.
``sufficient_assumption``
    ``premises ⊭ conclusion``; ``premises ∧ credited ⊨ conclusion``; and for each
    distractor ``premises ∧ D ⊭ conclusion``.
``necessary_assumption``
    ``premises ∧ conclusion ⊨ credited``, and not so for any distractor. This is
    the negation test stated model-theoretically: if the argument is sound, a
    necessary assumption must hold.
``structural``
    No model check. The credited answer came from the attack pool, every
    distractor from the disjoint inert pool, and the report says the guarantee is
    structural so nothing downstream mistakes it for a proof.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass

from pydantic import BaseModel, Field

from law_ai.lsat.services.bank import ChoiceLabel
from law_ai.lsat.synth.logic import (
    Evaluation,
    InconsistentPremises,
    Statement,
    evaluate,
)
from law_ai.lsat.synth.schemas import Blueprint, ProofKind

#: A choice far longer than its neighbours is a tell before it is a distractor.
#: Authored prose (the structural families) varies more than templated
#: statements, so the ratio alone is a blunt gate; the check that actually
#: matters is that the *credited* answer is not the outlier, since "pick the
#: longest one" is the heuristic this guards against.
MAX_CHOICE_LENGTH_RATIO = 3.2
MIN_CHOICE_CHARS = 8
#: How much longer than the typical choice the credited answer may be before
#: "pick the longest" starts to work.
CREDITED_LENGTH_TELL_RATIO = 1.6


class Check(BaseModel):
    name: str
    passed: bool
    detail: str = ""


class ChoiceStatus(BaseModel):
    label: str
    role: str
    status: str = Field(
        description="entailed / contingent / contradicted, or 'not-checked' on a "
        "structural item."
    )
    supporting_models: int = 0


class VerificationReport(BaseModel):
    """What was proved about one item, and how."""

    schema_id: str
    family: str
    proof_kind: ProofKind
    space: str = "n/a"
    space_models: int = 0
    premise_models: int = 0
    credited_label: str
    choices: list[ChoiceStatus] = Field(default_factory=list)
    checks: list[Check] = Field(default_factory=list)

    @property
    def ok(self) -> bool:
        return all(c.passed for c in self.checks)

    @property
    def failures(self) -> list[Check]:
        return [c for c in self.checks if not c.passed]

    def summary(self) -> str:
        verdict = "verified" if self.ok else "FAILED"
        if self.proof_kind == "structural":
            return f"{verdict} ({self.proof_kind}; {len(self.checks)} checks)"
        return (
            f"{verdict} ({self.proof_kind}; {self.premise_models} of "
            f"{self.space_models} models satisfy the premises; "
            f"{len(self.checks)} checks)"
        )


@dataclass(frozen=True)
class LabelledChoice:
    label: ChoiceLabel
    role: str
    text: str
    statement: Statement | None


def _surface_checks(choices: list[LabelledChoice]) -> list[Check]:
    texts = [c.text for c in choices]
    credited = next(c for c in choices if c.role.startswith("credited"))
    checks = [
        Check(
            name="choices_distinct",
            passed=len(set(texts)) == len(texts),
            detail=(
                "two choices render identically"
                if len(set(texts)) != len(texts)
                else ""
            ),
        ),
        Check(
            name="choices_non_trivial",
            passed=all(len(t) >= MIN_CHOICE_CHARS for t in texts),
            # Detail only on failure — a passing check that prints a complaint
            # reads like a warning in the report.
            detail=(
                ""
                if all(len(t) >= MIN_CHOICE_CHARS for t in texts)
                else "a choice is too short to be a real option"
            ),
        ),
    ]
    lengths = [len(t) for t in texts]
    ratio = max(lengths) / max(1, min(lengths))
    checks.append(
        Check(
            name="choice_length_band",
            passed=ratio <= MAX_CHOICE_LENGTH_RATIO,
            detail=(
                f"longest/shortest = {ratio:.1f}, over {MAX_CHOICE_LENGTH_RATIO}"
                if ratio > MAX_CHOICE_LENGTH_RATIO
                else ""
            ),
        )
    )
    # Measured against the *median*, not the extremes: one terse distractor
    # should not condemn an otherwise even set, and what a test taker actually
    # notices is a credited answer that stands apart from the typical choice.
    #
    # Both directions count. Guarding only against a long credited answer moves
    # the tell rather than removing it: balancing distractors upward against a
    # long key leaves the *short* key conspicuous instead, which is just as
    # solvable without reading.
    credited_length = len(credited.text)
    typical = statistics.median(lengths)
    is_unique_extreme = (
        credited_length == max(lengths) and lengths.count(credited_length) == 1
    ) or (credited_length == min(lengths) and lengths.count(credited_length) == 1)
    off_band = (
        credited_length > typical * CREDITED_LENGTH_TELL_RATIO
        or credited_length * CREDITED_LENGTH_TELL_RATIO < typical
    )
    checks.append(
        Check(
            name="credited_length_is_unremarkable",
            passed=not (is_unique_extreme and off_band),
            detail=(
                (
                    f"credited choice is {credited_length} chars against a median of "
                    f"{typical:.0f} — it stands out without being read"
                )
                if is_unique_extreme and off_band
                else ""
            ),
        )
    )
    return checks


def _family_checks(
    blueprint: Blueprint,
    choices: list[LabelledChoice],
    result: Evaluation,
    credited_index: int,
) -> list[Check]:
    """The rule that defines what "correct" means for this item's family."""
    out: list[Check] = []
    credited_status = result.status_of(credited_index)
    others = [(i, c) for i, c in enumerate(choices) if i != credited_index]
    if blueprint.family == "must_be_true":
        out.append(
            Check(
                name="credited_is_entailed",
                passed=credited_status == "entailed",
                detail=f"credited choice is {credited_status}",
            )
        )
        offenders = [c.label for i, c in others if result.status_of(i) == "entailed"]
        out.append(
            Check(
                name="no_other_choice_entailed",
                passed=not offenders,
                detail=f"also entailed: {', '.join(offenders)}" if offenders else "",
            )
        )
    elif blueprint.family == "cannot_be_true":
        out.append(
            Check(
                name="credited_is_contradicted",
                passed=credited_status == "contradicted",
                detail=f"credited choice is {credited_status}",
            )
        )
        offenders = [
            c.label for i, c in others if result.status_of(i) == "contradicted"
        ]
        out.append(
            Check(
                name="no_other_choice_contradicted",
                passed=not offenders,
                detail=f"also impossible: {', '.join(offenders)}" if offenders else "",
            )
        )
    elif blueprint.family == "acceptability":
        out.append(
            Check(
                name="credited_is_consistent",
                passed=credited_status != "contradicted",
                detail=f"credited arrangement is {credited_status}",
            )
        )
        offenders = [
            c.label for i, c in others if result.status_of(i) != "contradicted"
        ]
        out.append(
            Check(
                name="every_distractor_violates_a_rule",
                passed=not offenders,
                detail=f"also permitted: {', '.join(offenders)}" if offenders else "",
            )
        )
    elif blueprint.family in ("sufficient_assumption", "necessary_assumption"):
        out.extend(_assumption_checks(blueprint, choices, result, credited_index))
    else:  # pragma: no cover - registry is closed
        out.append(Check(name="known_family", passed=False, detail=blueprint.family))

    return out


def verify(
    blueprint: Blueprint, choices: list[LabelledChoice], *, schema_id: str
) -> VerificationReport:
    """Classify every choice and run the family's rule plus the surface gates."""
    credited = next(c for c in choices if c.role.startswith("credited"))
    report = VerificationReport(
        schema_id=schema_id,
        family=blueprint.family,
        proof_kind=blueprint.proof_kind,
        credited_label=credited.label,
    )

    if blueprint.proof_kind == "structural" or blueprint.space is None:
        report.choices = [
            ChoiceStatus(label=c.label, role=c.role, status="not-checked")
            for c in choices
        ]
        roles = [c.role for c in choices]
        report.checks = [
            Check(
                name="single_credited_choice",
                passed=sum(1 for r in roles if r.startswith("credited")) == 1,
                detail="a structural item must have exactly one credited choice",
            ),
            Check(
                name="distractors_from_inert_pool",
                passed=all(r == "inert" for r in roles if not r.startswith("credited")),
                detail="a distractor was not drawn from the inert pool",
            ),
            *_surface_checks(choices),
        ]
        return report

    space = blueprint.space
    report.space = space.describe()
    report.space_models = space.size()

    statements = [c.statement for c in choices]
    if any(s is None for s in statements):
        report.checks = [
            Check(
                name="statements_present",
                passed=False,
                detail="a logical item has a choice with no statement to check",
            )
        ]
        return report
    checked: list[Statement] = [s for s in statements if s is not None]

    # One enumeration for everything: per-choice status, equivalence, and both
    # assumption criteria all read off the same truth masks.
    extra = [blueprint.conclusion] if blueprint.conclusion is not None else []
    try:
        result = evaluate(space, blueprint.premises, [*checked, *extra])
    except InconsistentPremises as exc:
        report.checks = [
            Check(name="premises_satisfiable", passed=False, detail=str(exc))
        ]
        return report

    report.premise_models = result.premise_models
    report.choices = [
        ChoiceStatus(
            label=c.label,
            role=c.role,
            status=result.status_of(i),
            supporting_models=result.supporting(i),
        )
        for i, c in enumerate(choices)
    ]
    checks: list[Check] = [
        Check(
            name="premises_satisfiable",
            passed=report.premise_models > 0,
            detail=f"{report.premise_models} models satisfy the premises",
        )
    ]

    credited_index = next(
        i for i, c in enumerate(choices) if c.role.startswith("credited")
    )
    checks.extend(_family_checks(blueprint, choices, result, credited_index))

    # Equivalence is meaningful wherever the distractors are supposed to differ
    # in *what they claim*. On an acceptability item they are not: every
    # distractor is an impossible arrangement, so they all share the empty mask
    # by design, and the check that matters there is that the arrangements read
    # differently — which `choices_distinct` already makes.
    if blueprint.family != "acceptability":
        seen: dict[int, str] = {}
        equivalents: list[str] = []
        for i, choice in enumerate(choices):
            mask = result.masks[i]
            if mask in seen:
                equivalents.append(f"{seen[mask]}={choice.label}")
            else:
                seen[mask] = choice.label
        checks.append(
            Check(
                name="no_equivalent_choices",
                passed=not equivalents,
                detail=", ".join(equivalents),
            )
        )

    checks.extend(_surface_checks(choices))
    report.checks = checks
    return report


def _assumption_checks(
    blueprint: Blueprint,
    choices: list[LabelledChoice],
    result: Evaluation,
    credited_index: int,
) -> list[Check]:
    """The exact model-theoretic criteria, read off the shared truth masks.

    Over the premise-satisfying models, with ``mask_c`` for the conclusion:

    * sufficient — ``mask_choice ⊆ mask_c``: every case in which the assumption
      holds is a case in which the conclusion holds, so adding it forces the
      conclusion.
    * necessary — ``mask_c ⊆ mask_choice``: every case in which the argument
      succeeds is a case in which the assumption holds. That is the negation
      test written as a set inclusion — negate the assumption and no successful
      case survives.
    """
    if blueprint.conclusion is None:
        return [
            Check(
                name="conclusion_present",
                passed=False,
                detail="an assumption item needs a conclusion to test against",
            )
        ]
    # The conclusion was appended after the choices in `evaluate`.
    conclusion_mask = result.masks[len(choices)]
    full = (1 << result.premise_models) - 1
    credited_mask = result.masks[credited_index]
    checks: list[Check] = [
        Check(
            name="premises_alone_do_not_suffice",
            passed=conclusion_mask != full,
            detail="the conclusion already follows without any assumption",
        )
    ]

    if blueprint.family == "sufficient_assumption":
        checks.append(
            Check(
                name="credited_closes_the_gap",
                passed=credited_mask != 0 and (credited_mask & ~conclusion_mask) == 0,
                detail=(
                    "the credited answer does not force the conclusion"
                    if (credited_mask & ~conclusion_mask) != 0
                    else ""
                ),
            )
        )
        offenders = [
            c.label
            for i, c in enumerate(choices)
            if i != credited_index
            and result.masks[i] != 0
            and (result.masks[i] & ~conclusion_mask) == 0
        ]
        checks.append(
            Check(
                name="no_distractor_closes_the_gap",
                passed=not offenders,
                detail=f"also sufficient: {', '.join(offenders)}" if offenders else "",
            )
        )
        return checks

    checks.append(
        Check(
            name="credited_is_required_by_a_sound_argument",
            passed=(conclusion_mask & ~credited_mask) == 0,
            detail=(
                "the argument can succeed without the credited answer"
                if (conclusion_mask & ~credited_mask) != 0
                else ""
            ),
        )
    )
    offenders = [
        c.label
        for i, c in enumerate(choices)
        if i != credited_index and (conclusion_mask & ~result.masks[i]) == 0
    ]
    checks.append(
        Check(
            name="no_distractor_is_required",
            passed=not offenders,
            detail=f"also required: {', '.join(offenders)}" if offenders else "",
        )
    )
    return checks
