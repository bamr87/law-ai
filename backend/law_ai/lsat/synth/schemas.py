"""The schema registry — item skeletons, with no words in them.

Spec 049 FR-4/FR-6/FR-10. A schema knows one LSAT pattern's *logic*: which
model space it lives in, how its premises are built, what the credited answer
is, and where its distractors come from. It knows nothing about English; that
is :mod:`law_ai.lsat.synth.realize`'s job, and the separation is what lets one
schema produce items in any domain without touching an entailment.

**Distractors are selected by proof, not by assertion.** A schema supplies a
generous *pool* of candidate statements and :func:`select_distractors`
classifies the whole pool against the premises, then draws from the ones that
provably have the required status. So a schema author cannot accidentally ship a
"wrong" answer that is in fact entailed — the commonest and most damaging defect
in hand-authored formal items, and the one spec 045's cross-check exists to
catch after the fact. Here it cannot happen in the first place.

Two proof kinds live side by side and are never conflated:

``logical``
    The credited answer's status is *decided* by the model checker, and every
    distractor is decided not to have it.
``structural``
    The item is *built* to commit exactly one enumerated defect and its
    distractors are drawn from a disjoint pool of facts the construction does
    not touch. That is a real guarantee, but it is not a proof, so these items
    are never eligible for the direct-write path in
    :mod:`law_ai.lsat.synth.generate`.
"""

from __future__ import annotations

import random
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal, Protocol

from law_ai.lsat.services.bank import Difficulty, Section
from law_ai.lsat.synth.lexicon import DomainPack
from law_ai.lsat.synth.logic import (
    Adjacent,
    All,
    And,
    AtSlot,
    Atom,
    AssignModel,
    AssignSpace,
    Before,
    DiffGroup,
    Implies,
    InGroup,
    ModelSpace,
    Most,
    No,
    Not,
    NotAll,
    NotAtSlot,
    Or,
    OrderSpace,
    PropSpace,
    RegionSpace,
    SameGroup,
    Some,
    Statement,
    classify_all,
    evaluate,
)
from law_ai.lsat.synth.realize import Binding

Family = Literal[
    "must_be_true",
    "cannot_be_true",
    "sufficient_assumption",
    "necessary_assumption",
    "acceptability",
    "structural",
]
ProofKind = Literal["logical", "structural"]

#: How many answer choices an LSAT item has. Not configurable — the bank model
#: requires exactly A–E.
CHOICE_COUNT = 5


class SchemaError(ValueError):
    """A schema cannot produce a valid item from the material it was given."""


@dataclass(frozen=True)
class BindingSpec:
    """What vocabulary a schema needs bound before it can be rendered."""

    property_slots: tuple[str, ...] = ()
    entity_slots: tuple[str, ...] = ()
    group_slots: tuple[str, ...] = ()
    needs_ordering: bool = False
    needs_causal: bool = False
    needs_ratio: bool = False


@dataclass(frozen=True)
class FormalChoice:
    """One answer choice.

    ``statement`` is what the checker evaluates; ``surface`` overrides rendering
    for choices that are not statements about the subject (a full game
    arrangement, or a prose observation in a structural item).
    """

    role: str
    statement: Statement | None = None
    surface: str | None = None


@dataclass(frozen=True)
class Blueprint:
    """One item's word-free content."""

    family: Family
    proof_kind: ProofKind
    binding_spec: BindingSpec
    premises: tuple[Statement, ...] = ()
    conclusion: Statement | None = None
    choices: tuple[FormalChoice, ...] = ()
    space: ModelSpace | None = None
    #: Extra prose the stimulus needs that is not a premise statement (game
    #: setups, study observations). Rendered verbatim.
    preamble: tuple[str, ...] = ()


@dataclass(frozen=True)
class SchemaMeta:
    id: str
    section: Section
    archetype_id: str
    family: Family
    proof_kind: ProofKind
    difficulty: Difficulty
    concepts: tuple[str, ...]
    capability: str
    version: int = 1
    summary: str = ""


class Schema(Protocol):
    # Read-only, like ModelSpace.kind: every schema is a frozen dataclass, and a
    # settable protocol member would exclude all of them.
    @property
    def meta(self) -> SchemaMeta: ...

    def build(self, rng: random.Random, domain: DomainPack) -> Blueprint: ...

    def stem(self, rng: random.Random) -> str: ...

    def explain(self, blueprint: Blueprint, binding: Binding, credited: str) -> str: ...

    def method(self) -> str: ...


# ---------------------------------------------------------------------------
# Proof-driven distractor selection
# ---------------------------------------------------------------------------


def _shape(statement: Statement) -> tuple[str, ...]:
    """A statement's surface *form*, ignoring which slots it mentions.

    Used to keep the five choices parallel. A credited conditional sitting among
    four bare facts is longer than all of them, and "pick the longest" then
    solves the item without reading it — a tell real item writers work to avoid
    and a generator will reproduce every time unless told not to.
    """
    if isinstance(statement, Not):
        return ("not", *_shape(statement.inner))
    if isinstance(statement, Implies):
        return ("implies", *_shape(statement.antecedent), *_shape(statement.consequent))
    if isinstance(statement, And | Or):
        return (type(statement).__name__.lower(), str(len(statement.parts)))
    return (type(statement).__name__.lower(),)


def _distinct_picks(
    pairs: list[tuple[int, Statement]],
    count: int,
    rng: random.Random,
    *,
    used: set[int],
    like: Statement | None = None,
) -> list[Statement]:
    """Draw statements with pairwise-distinct truth masks.

    Premises usually pin most of what they mention, so a candidate pool is full
    of statements that are false in exactly the same models. Four of those is
    one wrong answer written four ways.

    ``like`` asks for choices parallel in form to the credited answer, so the
    five options are the same *kind* of sentence and the item cannot be solved
    by shape alone.
    """
    rng.shuffle(pairs)
    if like is not None:
        target = _shape(like)
        pairs.sort(key=lambda pair: _shape(pair[1]) != target)
    chosen: list[Statement] = []
    for mask, statement in pairs:
        if len(chosen) >= count:
            break
        if mask in used:
            continue
        used.add(mask)
        chosen.append(statement)
    return chosen


def select_distractors(
    space: ModelSpace,
    premises: Sequence[Statement],
    pool: Sequence[Statement],
    rng: random.Random,
    *,
    exclude: Statement,
    count: int = CHOICE_COUNT - 1,
    prefer_contingent: int = 2,
) -> list[Statement]:
    """Draw ``count`` statements the checker proves are **not** entailed.

    Two properties are built in rather than checked afterwards:

    *Not entailed* — a distractor that in fact follows from the premises is a
    second correct answer, the single most damaging defect a formal item can
    have.

    *Pairwise non-equivalent* — two choices that hold in exactly the same cases
    are the same choice written twice. Premises often pin most of their atoms,
    which leaves a pool full of statements that are all false in the same
    single model; picking four of those produces an item with four
    indistinguishable wrong answers. Comparing truth masks catches that for
    free, since the enumeration is already done.

    ``prefer_contingent`` asks for merely-possible distractors over outright
    contradictions: both are wrong, but a contradicted choice is eliminable at a
    glance, and the difficulty of a real must-be-true item lives in the choices
    that *could* be true and simply do not follow.
    """
    candidates = [p for p in pool if p != exclude]
    if not candidates:
        raise SchemaError("distractor pool is empty")
    result = evaluate(space, premises, [exclude, *candidates])
    credited_mask = result.masks[0]
    full = (1 << result.premise_models) - 1

    contingent: list[tuple[int, Statement]] = []
    contradicted: list[tuple[int, Statement]] = []
    for i, candidate in enumerate(candidates, start=1):
        mask = result.masks[i]
        if mask in (full, credited_mask):
            continue
        (contradicted if mask == 0 else contingent).append((mask, candidate))
    target_shape = _shape(exclude)
    for bucket in (contingent, contradicted):
        rng.shuffle(bucket)
        bucket.sort(key=lambda pair: _shape(pair[1]) != target_shape)

    chosen: list[Statement] = []
    used_masks: set[int] = {credited_mask}

    def _take(source: list[tuple[int, Statement]], limit: int) -> None:
        for mask, candidate in source:
            if len(chosen) >= limit:
                return
            if mask in used_masks:
                continue
            used_masks.add(mask)
            chosen.append(candidate)

    _take(contingent, min(count, max(prefer_contingent, count - len(contradicted))))
    _take(contradicted, count)
    _take(contingent, count)
    if len(chosen) < count:
        raise SchemaError(
            f"pool yielded only {len(chosen)} distinct non-entailed distractors, "
            f"needed {count} (premises leave {result.premise_models} models, which "
            "usually means they pin too much)"
        )
    return chosen[:count]


def _entailed_from(
    space: ModelSpace,
    premises: Sequence[Statement],
    pool: Sequence[Statement],
    rng: random.Random,
) -> Statement:
    """Pick a credited answer the checker proves is entailed."""
    results = classify_all(space, premises, pool)
    entailed = [c for c, r in zip(pool, results, strict=True) if r.status == "entailed"]
    if not entailed:
        raise SchemaError("no candidate in the pool is entailed by the premises")
    return rng.choice(entailed)


# ---------------------------------------------------------------------------
# Logical schemas — Logical Reasoning
# ---------------------------------------------------------------------------

#: Slot letters deliberately avoid A–E. Those are the answer *labels*, and a
#: stimulus symbolized "A → B" beside choices labelled (A)–(E) is confusing for
#: a reader and indistinguishable from answer-elimination notation to the spec
#: 045 guide linter, which counts label mentions to catch a step that gives the
#: answer away.
_PROP_SLOTS = ("P", "Q", "R", "S", "T")


def _prop_pool(atoms: Sequence[str]) -> list[Statement]:
    """Every literal and simple conditional over ``atoms``.

    Deliberately generous and deliberately unfiltered: the checker decides which
    of these are entailed, contingent or contradicted, so the pool's job is
    variety rather than correctness.
    """
    pool: list[Statement] = []
    for a in atoms:
        pool.append(Atom(a))
        pool.append(Not(Atom(a)))
    for a in atoms:
        for b in atoms:
            if a == b:
                continue
            pool.append(Implies(Atom(a), Atom(b)))
            pool.append(Implies(Atom(a), Not(Atom(b))))
            pool.append(Implies(Not(Atom(a)), Atom(b)))
    return pool


@dataclass(frozen=True)
class ConditionalChain:
    """A → B → C plus a triggering fact; what must follow.

    ``forward`` runs modus ponens from the antecedent end; otherwise the chain is
    triggered at the far end and the credited answer is a contrapositive.
    """

    forward: bool
    meta: SchemaMeta

    def build(self, rng: random.Random, domain: DomainPack) -> Blueprint:
        space = PropSpace(atoms=_PROP_SLOTS)
        chain: list[Statement] = [
            Implies(Atom("P"), Atom("Q")),
            Implies(Atom("Q"), Atom("R")),
            # Two further conditionals hung off the chain in the direction
            # that stays *unresolved* once the trigger fires, so the premises
            # leave models in which D and E vary. Without them the premises pin
            # every atom, one model survives, and every true statement becomes
            # entailed — an item with five correct answers. The direction
            # matters: pointing into a chain that the trigger falsifies pins the
            # new atoms too.
            (
                Implies(Atom("S"), Atom("P"))
                if self.forward
                else Implies(Atom("P"), Atom("S"))
            ),
            (
                Implies(Atom("T"), Atom("P"))
                if self.forward
                else Implies(Atom("P"), Atom("T"))
            ),
        ]
        trigger: Statement = Atom("P") if self.forward else Not(Atom("R"))
        premises = tuple([*chain, trigger])
        pool = _prop_pool(_PROP_SLOTS)
        credited = _entailed_from(
            space,
            premises,
            [Atom("R")] if self.forward else [Not(Atom("P")), Not(Atom("Q"))],
            rng,
        )
        distractors = select_distractors(space, premises, pool, rng, exclude=credited)
        return Blueprint(
            family="must_be_true",
            proof_kind="logical",
            binding_spec=BindingSpec(property_slots=_PROP_SLOTS),
            premises=premises,
            choices=(
                FormalChoice(role="credited", statement=credited),
                *(FormalChoice(role="distractor", statement=d) for d in distractors),
            ),
            space=space,
        )

    def stem(self, rng: random.Random) -> str:
        return rng.choice(
            [
                "If the statements above are true, which one of the following must also be true?",
                "The statements above, if true, most support which one of the following?",
                "Which one of the following can be properly inferred from the statements above?",
            ]
        )

    def explain(self, blueprint: Blueprint, binding: Binding, credited: str) -> str:
        direction = (
            "Chaining the conditionals forward from the stated fact"
            if self.forward
            else "The stated fact denies the far end of the chain, so the contrapositive runs backward"
        )
        return (
            f"{direction} yields exactly one choice that holds in every case "
            f"consistent with the premises: {credited} Each other choice is "
            "consistent with the premises without following from them, or is "
            "ruled out by them outright."
        )

    def method(self) -> str:
        return (
            "Symbolize the conditionals, chain them through their shared terms, "
            "then apply the stated fact — forward for modus ponens, backward "
            "through the contrapositive when the fact is a denial."
        )


@dataclass(frozen=True)
class ConditionalCannotBeTrue:
    """A → B plus ¬B; which choice is impossible."""

    meta: SchemaMeta

    def build(self, rng: random.Random, domain: DomainPack) -> Blueprint:
        space = PropSpace(atoms=_PROP_SLOTS)
        # Two of the conditionals point *out* of the falsified atoms, so S and
        # T stay free and four models survive. A premise pointing in (S → Q)
        # would pin S as well, collapsing the space to two models — and with two
        # models there are only two possible truth patterns to choose four
        # distinct distractors from.
        premises: tuple[Statement, ...] = (
            Implies(Atom("P"), Atom("Q")),
            Implies(Atom("R"), Atom("P")),
            Implies(Atom("P"), Atom("S")),
            Implies(Atom("Q"), Atom("T")),
            Not(Atom("Q")),
        )
        pool = _prop_pool(_PROP_SLOTS)
        result = evaluate(space, premises, pool)
        full = (1 << result.premise_models) - 1
        contradicted = [
            (result.masks[i], c) for i, c in enumerate(pool) if result.masks[i] == 0
        ]
        possible = [
            (result.masks[i], c)
            for i, c in enumerate(pool)
            if result.masks[i] != 0 and result.masks[i] != full
        ]
        if not contradicted:
            raise SchemaError("cannot-be-true schema found no impossible candidate")
        rng.shuffle(contradicted)
        credited = contradicted[0][1]
        # Every distractor must be *possible*, and no two may be possible in
        # exactly the same cases — otherwise the item has one wrong answer
        # written several ways.
        distractors = _distinct_picks(
            possible, CHOICE_COUNT - 1, rng, used={0}, like=credited
        )
        if len(distractors) < CHOICE_COUNT - 1:
            raise SchemaError(
                "cannot-be-true schema found too few distinct possible distractors"
            )
        return Blueprint(
            family="cannot_be_true",
            proof_kind="logical",
            binding_spec=BindingSpec(property_slots=_PROP_SLOTS),
            premises=premises,
            choices=(
                FormalChoice(role="credited", statement=credited),
                *(FormalChoice(role="distractor", statement=d) for d in distractors),
            ),
            space=space,
        )

    def stem(self, rng: random.Random) -> str:
        return rng.choice(
            [
                "If the statements above are true, which one of the following CANNOT be true?",
                "Which one of the following is incompatible with the statements above?",
            ]
        )

    def explain(self, blueprint: Blueprint, binding: Binding, credited: str) -> str:
        return (
            "Four of the choices hold in at least one case consistent with the "
            f"premises. The credited answer holds in none: {credited} Note that "
            "the task is the reverse of a must-be-true item — you are looking "
            "for the impossibility, not the necessity."
        )

    def method(self) -> str:
        return (
            "Symbolize, take the contrapositive of each conditional, and test "
            "each choice for consistency rather than for necessity."
        )


_REGION_SLOTS = ("P", "Q", "R")


def _region_pool() -> list[Statement]:
    pool: list[Statement] = []
    for a in _REGION_SLOTS:
        for b in _REGION_SLOTS:
            if a == b:
                continue
            pool.extend([All(a, b), No(a, b), Some(a, b), NotAll(a, b), Most(a, b)])
    return pool


@dataclass(frozen=True)
class QuantifierCombination:
    """Two quantified premises sharing a term; what combines.

    ``most_most`` is the exam's favourite overlap inference — two majorities of
    the same set must intersect — and its characteristic trap is that the
    overlap is only ``some``, never ``most``. The checker settles both.
    """

    most_most: bool
    meta: SchemaMeta

    def build(self, rng: random.Random, domain: DomainPack) -> Blueprint:
        space = RegionSpace(predicates=_REGION_SLOTS)
        premises: tuple[Statement, ...] = (
            (Most("P", "Q"), Most("P", "R"))
            if self.most_most
            else (All("P", "Q"), Some("P", "R"))
        )
        pool = _region_pool()
        credited = _entailed_from(
            space, premises, [Some("Q", "R"), Some("R", "Q")], rng
        )
        distractors = select_distractors(space, premises, pool, rng, exclude=credited)
        return Blueprint(
            family="must_be_true",
            proof_kind="logical",
            binding_spec=BindingSpec(property_slots=_REGION_SLOTS),
            premises=premises,
            choices=(
                FormalChoice(role="credited", statement=credited),
                *(FormalChoice(role="distractor", statement=d) for d in distractors),
            ),
            space=space,
        )

    def stem(self, rng: random.Random) -> str:
        return rng.choice(
            [
                "If the statements above are true, which one of the following must also be true?",
                "Which one of the following is most strongly supported by the statements above?",
            ]
        )

    def explain(self, blueprint: Blueprint, binding: Binding, credited: str) -> str:
        core = (
            "Two majorities of the same set must share at least one member, so "
            "the overlap follows — but only as 'at least one'. A choice claiming "
            "most of one group falls in the other overreaches."
            if self.most_most
            else "A universal premise licenses substitution into the existential "
            "one, so the overlap follows."
        )
        return f"{core} The credited answer is the one that holds in every consistent case: {credited}"

    def method(self) -> str:
        return (
            "Write each premise as a relation between two groups, look for the "
            "shared term, and combine only as far as the weaker quantifier allows."
        )


@dataclass(frozen=True)
class AssumptionSchema:
    """A gapped argument: what bridges it (sufficient) or what it needs (necessary).

    Both criteria are exact and model-theoretic, which is why these two families
    sit on the ``logical`` side of the line:

    * **sufficient** — ``premises ∧ C ⊨ conclusion`` and, for every distractor,
      ``premises ∧ D ⊭ conclusion``.
    * **necessary**  — ``premises ∧ conclusion ⊨ C`` and, for every distractor,
      ``premises ∧ conclusion ⊭ D``. (If the argument is sound, a necessary
      assumption has to hold; that is exactly what the negation test checks by
      hand.)
    """

    necessary: bool
    meta: SchemaMeta

    def build(self, rng: random.Random, domain: DomainPack) -> Blueprint:
        space = PropSpace(atoms=_PROP_SLOTS)
        premises: tuple[Statement, ...] = (
            Implies(Atom("P"), Atom("Q")),
            Atom("P"),
        )
        conclusion: Statement = Atom("R")
        pool = _prop_pool(_PROP_SLOTS)

        # One enumeration answers both families. Over the models satisfying the
        # premises, a candidate's mask says where it holds and the conclusion's
        # mask says where the argument's conclusion holds:
        #
        #   sufficient : mask_C ⊆ mask_conclusion   (adding C forces it)
        #   necessary  : mask_conclusion ⊆ mask_C   (a sound argument requires it)
        #
        # Doing it with masks rather than a re-check per candidate also removes
        # the case that used to crash the schema — a candidate contradicting the
        # premises makes the premise set unsatisfiable, and re-checking against
        # it raises. Here that candidate simply has an empty mask.
        result = evaluate(space, premises, [conclusion, *pool])
        concl_mask = result.masks[0]
        candidate_masks = result.masks[1:]
        full = (1 << result.premise_models) - 1

        stated = {*premises, conclusion}
        credited_pool: list[tuple[int, Statement]] = []
        distractor_pool: list[tuple[int, Statement]] = []
        for mask, candidate in zip(candidate_masks, pool, strict=True):
            if self.necessary:
                qualifies = (concl_mask & ~mask) == 0
            else:
                # An empty mask is vacuously sufficient and a useless answer:
                # "assume something impossible" closes every gap.
                qualifies = mask != 0 and (mask & ~concl_mask) == 0
            if qualifies and candidate not in stated:
                credited_pool.append((mask, candidate))
            elif not qualifies:
                distractor_pool.append((mask, candidate))

        if not credited_pool:
            raise SchemaError(
                f"{'necessary' if self.necessary else 'sufficient'}-assumption "
                "schema found no qualifying candidate"
            )
        if self.necessary and concl_mask == full:
            raise SchemaError("the conclusion already follows; nothing is assumed")
        if not self.necessary and concl_mask == full:
            raise SchemaError("the premises already entail the conclusion")

        rng.shuffle(credited_pool)
        credited_mask, credited = credited_pool[0]
        distractors = _distinct_picks(
            distractor_pool,
            CHOICE_COUNT - 1,
            rng,
            used={credited_mask},
            like=credited,
        )
        if len(distractors) < CHOICE_COUNT - 1:
            raise SchemaError(
                "assumption schema found too few distinct non-qualifying distractors"
            )

        return Blueprint(
            family=(
                "necessary_assumption" if self.necessary else "sufficient_assumption"
            ),
            proof_kind="logical",
            binding_spec=BindingSpec(property_slots=_PROP_SLOTS),
            premises=premises,
            conclusion=conclusion,
            choices=(
                FormalChoice(role="credited", statement=credited),
                *(FormalChoice(role="distractor", statement=d) for d in distractors),
            ),
            space=space,
        )

    def stem(self, rng: random.Random) -> str:
        if self.necessary:
            return rng.choice(
                [
                    "The argument above depends on assuming which one of the following?",
                    "Which one of the following is an assumption required by the argument?",
                ]
            )
        return rng.choice(
            [
                "Which one of the following, if assumed, allows the conclusion to be properly drawn?",
                "The conclusion follows logically if which one of the following is assumed?",
            ]
        )

    def explain(self, blueprint: Blueprint, binding: Binding, credited: str) -> str:
        if self.necessary:
            return (
                "Hold the argument sound and ask what must then be true. Only one "
                f"choice is forced: {credited} Negate it and the argument no longer "
                "reaches its conclusion; negate any other choice and the argument "
                "survives, which is precisely the negation test."
            )
        return (
            "The premises leave a gap the conclusion cannot cross unaided. Adding "
            f"the credited answer closes it and the conclusion follows: {credited} "
            "Each other choice leaves at least one case where the premises hold "
            "and the conclusion fails."
        )

    def method(self) -> str:
        if self.necessary:
            return (
                "Find the gap between the premise terms and the conclusion terms, "
                "then negate each candidate: the one whose negation destroys the "
                "argument is the necessary assumption."
            )
        return (
            "Symbolize premises and conclusion, find the missing link in the "
            "chain, and choose the arrow that completes it in the right direction."
        )


# ---------------------------------------------------------------------------
# Logical schemas — Logic Games
# ---------------------------------------------------------------------------

_GAME_ENTITIES = ("e1", "e2", "e3", "e4", "e5")


def _order_rules(rng: random.Random) -> tuple[Statement, ...]:
    """A rule set that constrains without over-determining.

    Re-drawn until it leaves between two and thirty valid arrangements: one
    arrangement makes every true statement entailed, and too many makes the
    must-be-true variants have no answer.
    """
    return (
        Before("e1", "e2"),
        Adjacent("e3", "e4"),
        NotAtSlot("e5", 1),
    )


@dataclass(frozen=True)
class SequencingGame:
    """An ordering game: acceptability, or what must be true of every arrangement."""

    acceptability: bool
    meta: SchemaMeta

    def build(self, rng: random.Random, domain: DomainPack) -> Blueprint:
        space = OrderSpace(entities=_GAME_ENTITIES)
        premises = _order_rules(rng)
        valid = [m for m in space.models() if all(r.holds(m) for r in premises)]
        if len(valid) < CHOICE_COUNT:
            raise SchemaError("sequencing rules leave too few valid arrangements")

        if self.acceptability:
            # The credited answer is one valid arrangement; each distractor
            # breaks at least one rule. Rendered as a list, not a sentence.
            good = rng.choice(valid)
            invalid = [
                m for m in space.models() if not all(r.holds(m) for r in premises)
            ]
            rng.shuffle(invalid)
            picks = invalid[: CHOICE_COUNT - 1]
            choices = [
                FormalChoice(
                    role="credited",
                    statement=And(
                        tuple(AtSlot(e, i + 1) for i, e in enumerate(good.sequence))
                    ),
                )
            ]
            choices += [
                FormalChoice(
                    role="distractor",
                    statement=And(
                        tuple(AtSlot(e, i + 1) for i, e in enumerate(bad.sequence))
                    ),
                )
                for bad in picks
            ]
            return Blueprint(
                family="acceptability",
                proof_kind="logical",
                binding_spec=BindingSpec(
                    entity_slots=_GAME_ENTITIES, needs_ordering=True
                ),
                premises=premises,
                choices=tuple(choices),
                space=space,
            )

        pool: list[Statement] = []
        for a in _GAME_ENTITIES:
            for b in _GAME_ENTITIES:
                if a != b:
                    pool.append(Before(a, b))
            for slot in range(1, len(_GAME_ENTITIES) + 1):
                pool.extend([AtSlot(a, slot), NotAtSlot(a, slot)])
        credited = _entailed_from(space, premises, pool, rng)
        distractors = select_distractors(space, premises, pool, rng, exclude=credited)
        return Blueprint(
            family="must_be_true",
            proof_kind="logical",
            binding_spec=BindingSpec(entity_slots=_GAME_ENTITIES, needs_ordering=True),
            premises=premises,
            choices=(
                FormalChoice(role="credited", statement=credited),
                *(FormalChoice(role="distractor", statement=d) for d in distractors),
            ),
            space=space,
        )

    def stem(self, rng: random.Random) -> str:
        if self.acceptability:
            return "Which one of the following could be an accurate ordering?"
        return "Which one of the following must be true?"

    def explain(self, blueprint: Blueprint, binding: Binding, credited: str) -> str:
        if self.acceptability:
            return (
                "Four of the orderings break at least one stated rule; the "
                "credited answer breaks none. Work rule by rule across the "
                "choices rather than choice by choice against the rules — one "
                "rule usually eliminates two orderings in a single pass."
            )
        return (
            "Enumerating every arrangement the rules permit leaves exactly one "
            f"choice true in all of them: {credited} Each other choice is true "
            "in some arrangements and false in others, which makes it a could-be, "
            "not a must-be."
        )

    def method(self) -> str:
        if self.acceptability:
            return "Scan the choices rule by rule and eliminate any ordering that violates one."
        return (
            "Draw the board, combine the rules into what they jointly force, and "
            "test each choice against every arrangement that survives."
        )


_GROUP_ENTITIES = ("e1", "e2", "e3", "e4")
_GROUP_SLOTS = ("g1", "g2")


@dataclass(frozen=True)
class GroupingGame:
    """A distribution game: which assignment could be accurate."""

    meta: SchemaMeta

    def build(self, rng: random.Random, domain: DomainPack) -> Blueprint:
        space = AssignSpace(entities=_GROUP_ENTITIES, groups=_GROUP_SLOTS)
        premises: tuple[Statement, ...] = (
            DiffGroup("e1", "e2"),
            SameGroup("e3", "e4"),
            InGroup("e1", "g1"),
        )
        valid = [m for m in space.models() if all(r.holds(m) for r in premises)]
        invalid = [m for m in space.models() if not all(r.holds(m) for r in premises)]
        if not valid or len(invalid) < CHOICE_COUNT - 1:
            raise SchemaError("grouping rules leave no usable split")
        good = rng.choice(valid)
        rng.shuffle(invalid)

        def _as_statement(model: object) -> Statement:
            assert isinstance(model, AssignModel)
            return And(tuple(InGroup(e, g) for e, g in model.placement))

        return Blueprint(
            family="acceptability",
            proof_kind="logical",
            binding_spec=BindingSpec(
                entity_slots=_GROUP_ENTITIES, group_slots=_GROUP_SLOTS
            ),
            premises=premises,
            choices=(
                FormalChoice(role="credited", statement=_as_statement(good)),
                *(
                    FormalChoice(role="distractor", statement=_as_statement(bad))
                    for bad in invalid[: CHOICE_COUNT - 1]
                ),
            ),
            space=space,
        )

    def stem(self, rng: random.Random) -> str:
        return "Which one of the following could be an accurate assignment?"

    def explain(self, blueprint: Blueprint, binding: Binding, credited: str) -> str:
        return (
            "Four of the assignments break at least one stated rule; the credited "
            "answer breaks none. Take the rules one at a time across all five "
            "choices — the fixed placement usually eliminates two on its own."
        )

    def method(self) -> str:
        return "Test each choice against each rule in turn, eliminating on the first violation."


# ---------------------------------------------------------------------------
# Structural schemas — guaranteed by construction, not by the checker
# ---------------------------------------------------------------------------
#
# These families have no model-theoretic criterion: "which one most weakens the
# argument" is a claim about evidential support, not entailment, and no finite
# model settles it. What the engine *can* guarantee is construction: the
# stimulus is assembled from an authored scenario whose attacks and inert facts
# are disjoint pools, the credited answer is drawn from the attack pool, and
# every distractor from the inert pool. That is a real guarantee about where the
# text came from — and it is not a proof, so `proof_kind` says `structural` and
# the promotion gate refuses it.


@dataclass(frozen=True)
class CausalSchema:
    """Correlation reported as cause; what undermines or supports it."""

    weaken: bool
    meta: SchemaMeta

    def build(self, rng: random.Random, domain: DomainPack) -> Blueprint:
        if not domain.causal_scenarios:
            raise SchemaError(f"{domain.id} has no causal scenarios")
        scenario = rng.choice(domain.causal_scenarios)
        preamble = (
            f"A recent study of {scenario.population} found that those that "
            f"{scenario.cause_vp} {scenario.effect_vp} far more often than those "
            f"that did not.",
            f"The study concludes that {scenario.cause_np} produced "
            f"{scenario.effect_np}.",
        )
        if self.weaken:
            attacks = [
                ("alternative_cause", scenario.alternative_cause),
                ("reverse_causation", scenario.reverse_causation),
                ("sampling_flaw", scenario.sampling_flaw),
            ]
            role, credited_text = rng.choice(attacks)
        else:
            role, credited_text = "control_comparison", scenario.control_comparison

        inert = list(scenario.inert_facts)
        rng.shuffle(inert)
        # Closest in length to the credited answer, so the item cannot be solved
        # by picking the longest option. Authored prose varies far more than a
        # templated statement does, so this matters most here.
        inert.sort(key=lambda text: abs(len(text) - len(credited_text)))
        # Disjointness is the structural guarantee: an inert fact that happened
        # to restate an attack would give the item two credited answers.
        attack_texts = {
            scenario.alternative_cause,
            scenario.reverse_causation,
            scenario.sampling_flaw,
            scenario.control_comparison,
        }
        inert = [f for f in inert if f not in attack_texts]
        if len(inert) < CHOICE_COUNT - 1:
            raise SchemaError(
                f"scenario {scenario.id!r} has too few inert facts for a full choice set"
            )
        return Blueprint(
            family="structural",
            proof_kind="structural",
            binding_spec=BindingSpec(needs_causal=True),
            preamble=preamble,
            choices=(
                FormalChoice(role=f"credited:{role}", surface=credited_text),
                *(
                    FormalChoice(role="inert", surface=text)
                    for text in inert[: CHOICE_COUNT - 1]
                ),
            ),
        )

    def stem(self, rng: random.Random) -> str:
        if self.weaken:
            return rng.choice(
                [
                    "Which one of the following, if true, most seriously weakens the argument?",
                    "Which one of the following, if true, most calls the conclusion into question?",
                ]
            )
        return rng.choice(
            [
                "Which one of the following, if true, most strengthens the argument?",
                "Which one of the following, if true, provides the most support for the conclusion?",
            ]
        )

    def explain(self, blueprint: Blueprint, binding: Binding, credited: str) -> str:
        if self.weaken:
            return (
                "The argument moves from a correlation to a causal claim, so it is "
                "vulnerable wherever that leap can fail: another factor could "
                "explain the effect, the causation could run the other way, or the "
                "group observed could be unrepresentative. The credited answer "
                f"instantiates one of those: {credited} The other four are on-topic "
                "facts that bear on neither direction — the standard trap in this "
                "family is a choice that is interesting rather than damaging."
            )
        return (
            "To strengthen a causal claim drawn from a correlation, rule out the "
            f"competing explanations. The credited answer supplies the controlled "
            f"comparison that does exactly that: {credited} The other four leave "
            "every alternative explanation exactly where it was."
        )

    def method(self) -> str:
        return (
            "Name the causal claim, then generate the four standard attacks — "
            "alternative cause, reversed direction, unrepresentative sample, "
            "cause without effect — before reading the choices."
        )


@dataclass(frozen=True)
class RatioSchema:
    """A rate moved and a count is concluded; the base is what settles it."""

    meta: SchemaMeta

    def build(self, rng: random.Random, domain: DomainPack) -> Blueprint:
        if not domain.ratio_scenarios:
            raise SchemaError(f"{domain.id} has no ratio scenarios")
        scenario = rng.choice(domain.ratio_scenarios)
        preamble = (
            f"The share of {scenario.population} responsible for "
            f"{scenario.measure_np} was lower {scenario.late_period} than it was "
            f"in {scenario.early_period}.",
            f"It follows that fewer {scenario.measure_np} occurred "
            f"{scenario.late_period} than in {scenario.early_period}.",
        )
        inert = [f for f in scenario.inert_facts if f != scenario.base_change]
        rng.shuffle(inert)
        inert.sort(key=lambda text: abs(len(text) - len(scenario.base_change)))
        if len(inert) < CHOICE_COUNT - 1:
            raise SchemaError(
                f"scenario {scenario.id!r} has too few inert facts for a full choice set"
            )
        return Blueprint(
            family="structural",
            proof_kind="structural",
            binding_spec=BindingSpec(needs_ratio=True),
            preamble=preamble,
            choices=(
                FormalChoice(role="credited:base_change", surface=scenario.base_change),
                *(
                    FormalChoice(role="inert", surface=text)
                    for text in inert[: CHOICE_COUNT - 1]
                ),
            ),
        )

    def stem(self, rng: random.Random) -> str:
        return rng.choice(
            [
                # Every stem here has to take a standalone-sentence choice.
                # "…overlooks the possibility that" needs lowercase sentence
                # fragments, and mixing the two produces a choice list where one
                # option is visibly punctuated differently from the rest.
                "Which one of the following, if true, most seriously weakens the argument?",
                "Which one of the following, if true, most undermines the reasoning above?",
            ]
        )

    def explain(self, blueprint: Blueprint, binding: Binding, credited: str) -> str:
        return (
            "The premise is a proportion and the conclusion is a count, and the two "
            "move together only when the base holds steady. The credited answer "
            f"shows it did not: {credited} A falling share of a rapidly growing "
            "population is entirely compatible with a rising number. The other "
            "choices leave the denominator untouched."
        )

    def method(self) -> str:
        return (
            "Ask what the denominator did. A rate and a count imply each other "
            "only when the base population is stable."
        )


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


def _meta(
    schema_id: str,
    *,
    section: Section,
    archetype: str,
    family: Family,
    proof: ProofKind,
    difficulty: Difficulty,
    concepts: tuple[str, ...],
    capability: str,
    summary: str,
) -> SchemaMeta:
    return SchemaMeta(
        id=schema_id,
        section=section,
        archetype_id=archetype,
        family=family,
        proof_kind=proof,
        difficulty=difficulty,
        concepts=concepts,
        capability=capability,
        summary=summary,
    )


_REGISTRY: tuple[Schema, ...] = (
    ConditionalChain(
        forward=True,
        meta=_meta(
            "lr-conditional-chain-forward",
            section="LR",
            archetype="lr-conditional-inference",
            family="must_be_true",
            proof="logical",
            difficulty="easy",
            concepts=("modus-ponens", "conditional-reasoning", "must-be-true"),
            capability="prop",
            summary="Chain two conditionals forward from a stated fact.",
        ),
    ),
    ConditionalChain(
        forward=False,
        meta=_meta(
            "lr-conditional-chain-contrapositive",
            section="LR",
            archetype="lr-contrapositive-inference",
            family="must_be_true",
            proof="logical",
            difficulty="med",
            concepts=("modus-tollens", "contrapositive", "conditional-reasoning"),
            capability="prop",
            summary="Deny the far end of a chain and run it backward.",
        ),
    ),
    ConditionalCannotBeTrue(
        meta=_meta(
            "lr-conditional-cannot-be-true",
            section="LR",
            archetype="lr-cannot-be-true",
            family="cannot_be_true",
            proof="logical",
            difficulty="med",
            concepts=("cannot-be-true", "conditional-reasoning", "contrapositive"),
            capability="prop",
            summary="Find the choice no consistent case admits.",
        ),
    ),
    QuantifierCombination(
        most_most=True,
        meta=_meta(
            "lr-quantifier-most-overlap",
            section="LR",
            archetype="lr-must-be-true",
            family="must_be_true",
            proof="logical",
            difficulty="hard",
            concepts=("must-be-true", "universal-instantiation"),
            capability="region",
            summary="Two majorities of one set must overlap — but only as 'some'.",
        ),
    ),
    QuantifierCombination(
        most_most=False,
        meta=_meta(
            "lr-quantifier-all-some",
            section="LR",
            archetype="lr-must-be-true",
            family="must_be_true",
            proof="logical",
            difficulty="med",
            concepts=("must-be-true", "universal-instantiation"),
            capability="region",
            summary="A universal plus an existential over a shared term.",
        ),
    ),
    AssumptionSchema(
        necessary=False,
        meta=_meta(
            "lr-sufficient-assumption",
            section="LR",
            archetype="lr-sufficient-assumption",
            family="sufficient_assumption",
            proof="logical",
            difficulty="med",
            concepts=("sufficient-assumption", "conditional-reasoning"),
            capability="prop",
            summary="Supply the arrow that completes the chain.",
        ),
    ),
    AssumptionSchema(
        necessary=True,
        meta=_meta(
            "lr-necessary-assumption",
            section="LR",
            archetype="lr-necessary-assumption",
            family="necessary_assumption",
            proof="logical",
            difficulty="hard",
            concepts=("necessary-assumption", "conditional-reasoning"),
            capability="prop",
            summary="What the argument cannot do without.",
        ),
    ),
    SequencingGame(
        acceptability=True,
        meta=_meta(
            "lg-sequencing-acceptability",
            section="LG",
            archetype="lg-acceptability",
            family="acceptability",
            proof="logical",
            difficulty="easy",
            concepts=("sequencing", "elimination-grid"),
            capability="order",
            summary="Which ordering breaks no rule.",
        ),
    ),
    SequencingGame(
        acceptability=False,
        meta=_meta(
            "lg-sequencing-must-be-true",
            section="LG",
            archetype="lg-must-be-true",
            family="must_be_true",
            proof="logical",
            difficulty="med",
            concepts=("sequencing", "must-be-true"),
            capability="order",
            summary="What holds in every arrangement the rules permit.",
        ),
    ),
    GroupingGame(
        meta=_meta(
            "lg-grouping-acceptability",
            section="LG",
            archetype="lg-grouping",
            family="acceptability",
            proof="logical",
            difficulty="easy",
            concepts=("grouping-game", "elimination-grid"),
            capability="assign",
            summary="Which assignment breaks no rule.",
        ),
    ),
    CausalSchema(
        weaken=True,
        meta=_meta(
            "lr-causal-weaken",
            section="LR",
            archetype="lr-weaken",
            family="structural",
            proof="structural",
            difficulty="med",
            concepts=("weaken", "causation-vs-correlation", "alternative-cause"),
            capability="causal",
            summary="Undermine a causal claim drawn from a correlation.",
        ),
    ),
    CausalSchema(
        weaken=False,
        meta=_meta(
            "lr-causal-strengthen",
            section="LR",
            archetype="lr-strengthen",
            family="structural",
            proof="structural",
            difficulty="med",
            concepts=("strengthen", "causation-vs-correlation", "alternative-cause"),
            capability="causal",
            summary="Support a causal claim by ruling the alternatives out.",
        ),
    ),
    RatioSchema(
        meta=_meta(
            "lr-percent-vs-number",
            section="LR",
            archetype="lr-percent-vs-number",
            family="structural",
            proof="structural",
            difficulty="hard",
            concepts=("percent-vs-number", "flaw-in-reasoning"),
            capability="ratio",
            summary="A share fell while the base grew.",
        ),
    ),
)


def all_schemas() -> tuple[Schema, ...]:
    return _REGISTRY


def schema_ids() -> tuple[str, ...]:
    return tuple(s.meta.id for s in _REGISTRY)


def get_schema(schema_id: str) -> Schema:
    for schema in _REGISTRY:
        if schema.meta.id == schema_id:
            return schema
    raise SchemaError(f"unknown schema {schema_id!r} (have: {', '.join(schema_ids())})")
