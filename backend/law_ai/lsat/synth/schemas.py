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

import itertools
import random
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
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
    GroupSize,
    Immediately,
    Implies,
    InGroup,
    ModelSpace,
    Most,
    No,
    Not,
    NotAll,
    NotAtSlot,
    NotInGroup,
    Or,
    OrderModel,
    OrderSpace,
    PropSpace,
    RegionSpace,
    SymbolicRegionSpace,
    SameGroup,
    Some,
    Statement,
    classify_all,
    entails,
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
    #: A supposition the *question* adds rather than the stimulus — "if the
    #: audit is third, then…". It is a premise like any other for the proof;
    #: this field only tells the renderer to put it in the question sentence
    #: instead of the board, which is where the exam puts it.
    local_condition: Statement | None = None
    #: The premise *arrangement* the schema drew for this item — chain length,
    #: trigger position, rule count, which rule menu entries — so provenance
    #: records the shape and not only the seed that produced it. Empty for a
    #: schema whose arrangement is fixed.
    arrangement: dict[str, int | str] = field(default_factory=dict)


#: How many times a schema re-draws its arrangement before giving up. A draw
#: that pins every atom, or contradicts itself, or entails nothing from the
#: pool is discarded and the next is tried; the cap is what stops a bad menu
#: from hanging a sweep.
MAX_ARRANGEMENT_DRAWS = 40


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
    credited_key = result.key(0)

    contingent: list[tuple[int, Statement]] = []
    contradicted: list[tuple[int, Statement]] = []
    for i, candidate in enumerate(candidates, start=1):
        # Status decides *whether* a candidate may be a distractor and the key
        # decides whether it is a duplicate of one already chosen. They are the
        # same thing in an enumerated space (the truth mask answers both) and
        # deliberately different in a symbolic one, where the status is proved
        # and the key is only a witness sample.
        status = result.status_of(i)
        key = result.key(i)
        if status == "entailed" or key == credited_key:
            continue
        (contradicted if status == "contradicted" else contingent).append(
            (key, candidate)
        )
    target_shape = _shape(exclude)
    for bucket in (contingent, contradicted):
        rng.shuffle(bucket)
        bucket.sort(key=lambda pair: _shape(pair[1]) != target_shape)

    chosen: list[Statement] = []
    used_keys: set[int] = {credited_key}

    def _take(source: list[tuple[int, Statement]], limit: int) -> None:
        for key, candidate in source:
            if len(chosen) >= limit:
                return
            if key in used_keys:
                continue
            used_keys.add(key)
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


#: Chain lengths a :class:`ConditionalChain` may draw. Two is a single
#: conditional plus its trigger; four uses every slot but one.
_CHAIN_LENGTHS = (2, 3, 4)
#: How many extra conditionals hang off the chain. At least one, or a short
#: chain with an early trigger pins every atom it mentions.
_SIDE_COUNTS = (1, 2)


def _draw_until(
    rng: random.Random,
    attempt: Callable[[random.Random], Blueprint],
    *,
    what: str,
) -> Blueprint:
    """Re-draw an arrangement until it yields a verifiable blueprint.

    Every draw is a deterministic function of ``rng``, so the item is still
    fully determined by its seed; the loop only skips the draws the proof
    engine rejects. It gives up after :data:`MAX_ARRANGEMENT_DRAWS` with the
    last reason attached, so a menu that can never succeed fails loudly.
    """
    last: SchemaError | None = None
    for _ in range(MAX_ARRANGEMENT_DRAWS):
        try:
            return attempt(rng)
        except SchemaError as exc:
            last = exc
    raise SchemaError(
        f"{what}: no arrangement verified in {MAX_ARRANGEMENT_DRAWS} draws "
        f"(last: {last})"
    )


@dataclass(frozen=True)
class ConditionalChain:
    """A → B → C plus a triggering fact; what must follow.

    ``forward`` runs modus ponens from the antecedent end; otherwise the chain is
    triggered at the far end and the credited answer is a contrapositive.

    The arrangement is drawn per item rather than fixed: the chain is two to
    four conditionals long, the trigger lands on any chain atom that leaves
    something to infer, and one or two further conditionals hang off it. Every
    draw goes through the same proof, so the variety costs nothing in validity —
    a draw the checker cannot certify is simply re-drawn.
    """

    forward: bool
    meta: SchemaMeta

    def _attempt(self, rng: random.Random) -> Blueprint:
        space = PropSpace(atoms=_PROP_SLOTS)
        length = rng.choice(_CHAIN_LENGTHS)
        slots = list(_PROP_SLOTS)
        rng.shuffle(slots)
        chain_atoms = slots[:length]
        spare = slots[length:]
        sides = min(rng.choice(_SIDE_COUNTS), len(spare))
        side_atoms = spare[:sides]
        chain: list[Statement] = [
            Implies(Atom(a), Atom(b)) for a, b in itertools.pairwise(chain_atoms)
        ]
        # Forward: the trigger affirms a chain atom and everything downstream
        # follows, so it must not sit on the last atom. Backward: the trigger
        # denies one and everything upstream is denied by contraposition, so
        # it must not sit on the first.
        if self.forward:
            trigger_index = rng.randrange(0, length - 1)
            trigger: Statement = Atom(chain_atoms[trigger_index])
            credited_pool: list[Statement] = [
                Atom(a) for a in chain_atoms[trigger_index + 1 :]
            ]
        else:
            trigger_index = rng.randrange(1, length)
            trigger = Not(Atom(chain_atoms[trigger_index]))
            credited_pool = [Not(Atom(a)) for a in chain_atoms[:trigger_index]]
        # The side conditionals hang off the chain in the direction that stays
        # *unresolved* once the trigger fires, so the premises leave models in
        # which the side atoms vary. Without them the premises pin every atom,
        # one model survives, and every true statement becomes entailed — an
        # item with five correct answers. The direction matters: pointing into
        # a chain that the trigger falsifies pins the new atoms too.
        for side in side_atoms:
            anchor = rng.choice(chain_atoms)
            chain.append(
                Implies(Atom(side), Atom(anchor))
                if self.forward
                else Implies(Atom(anchor), Atom(side))
            )
        premises = tuple([*chain, trigger])
        pool = _prop_pool(_PROP_SLOTS)
        credited = _entailed_from(space, premises, credited_pool, rng)
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
            arrangement={
                "chain_length": length,
                "trigger_index": trigger_index,
                "side_conditionals": len(side_atoms),
                "rule_count": len(premises),
            },
        )

    def build(self, rng: random.Random, domain: DomainPack) -> Blueprint:
        return _draw_until(rng, self._attempt, what=self.meta.id)

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

    def _pairs(self) -> tuple[tuple[str, tuple[Statement, ...]], ...]:
        """The premise arrangements this variant rotates through, by name.

        Each keeps the variant's characteristic inference — two majorities of
        one set, or a universal feeding a weaker quantifier — while changing
        the premise order, the weaker quantifier, or adding a third premise
        that narrows the picture without touching the credited answer.
        """
        if self.most_most:
            return (
                ("most-most", (Most("P", "Q"), Most("P", "R"))),
                ("most-most-reversed", (Most("P", "R"), Most("P", "Q"))),
                (
                    "most-most-not-all",
                    (Most("P", "Q"), Most("P", "R"), NotAll("P", "Q")),
                ),
                (
                    "most-most-not-all-far",
                    (Most("P", "Q"), NotAll("P", "R"), Most("P", "R")),
                ),
            )
        return (
            ("all-some", (All("P", "Q"), Some("P", "R"))),
            ("some-all", (Some("P", "R"), All("P", "Q"))),
            ("all-some-flipped", (All("P", "Q"), Some("R", "P"))),
            ("all-most", (All("P", "Q"), Most("P", "R"))),
        )

    def build(self, rng: random.Random, domain: DomainPack) -> Blueprint:
        space = RegionSpace(predicates=_REGION_SLOTS)
        name, premises = rng.choice(self._pairs())
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
            arrangement={"pair": name, "rule_count": len(premises)},
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
            else "A universal premise licenses substitution into the weaker "
            "one — an existential or a majority — so the overlap follows, and "
            "follows only as 'at least one'."
        )
        return f"{core} The credited answer is the one that holds in every consistent case: {credited}"

    def method(self) -> str:
        return (
            "Write each premise as a relation between two groups, look for the "
            "shared term, and combine only as far as the weaker quantifier allows."
        )


#: Four predicates, which enumeration cannot reach: the count space is 43
#: million vectors. :class:`SymbolicRegionSpace` decides it instead
#: (BL-20260903-16), which is what makes a genuine four-term chain provable.
_REGION_SLOTS_4 = ("P", "Q", "R", "S")


def _region_pool_for(slots: Sequence[str]) -> list[Statement]:
    pool: list[Statement] = []
    for a in slots:
        for b in slots:
            if a == b:
                continue
            pool.extend([All(a, b), No(a, b), Some(a, b), NotAll(a, b), Most(a, b)])
    return pool


@dataclass(frozen=True)
class QuantifierChainFour:
    """Three quantified premises over four terms; what reaches the far end.

    The exam's harder quantifier items are not two-premise combinations — they
    chain, and the trap is that the chain's *weakest* link caps the conclusion:
    a majority run through two universals is still only a majority, and a
    majority run through a majority is not even a majority. Four terms is where
    that becomes visible, and four terms is exactly what enumeration could not
    afford: 2^4 Venn regions at three counts each is 43 million vectors.

    So this schema is proved against :class:`SymbolicRegionSpace`, which decides
    the same entailments by constraint solving. Nothing else about the item is
    different — same pool, same distractor rule, same verifier.
    """

    meta: SchemaMeta

    def _chains(
        self,
    ) -> tuple[tuple[str, tuple[Statement, ...], tuple[Statement, ...]], ...]:
        """``(name, premises, candidate conclusions)``.

        The candidates are the *far-end* claims — the ones that need all three
        premises — so the credited answer can never be a premise restated. The
        checker still has the last word: :func:`_entailed_from` raises unless
        one of them is genuinely entailed.
        """
        return (
            (
                "all-most-all",
                (All("P", "Q"), Most("Q", "R"), All("R", "S")),
                (Most("Q", "S"), Some("Q", "S")),
            ),
            (
                "most-all-all",
                (Most("P", "Q"), All("Q", "R"), All("R", "S")),
                (Most("P", "S"), Some("P", "S")),
            ),
            (
                "most-most-all",
                (Most("P", "Q"), Most("P", "R"), All("R", "S")),
                (Most("P", "S"), Some("Q", "S")),
            ),
            (
                "all-all-no",
                (All("P", "Q"), All("Q", "R"), No("R", "S")),
                (No("P", "S"), NotAll("P", "S")),
            ),
            (
                "all-most-no",
                (All("P", "Q"), Most("Q", "R"), No("R", "S")),
                (NotAll("Q", "S"), Some("Q", "S")),
            ),
        )

    def build(self, rng: random.Random, domain: DomainPack) -> Blueprint:
        space = SymbolicRegionSpace(predicates=_REGION_SLOTS_4)
        name, premises, targets = rng.choice(self._chains())
        pool = _region_pool_for(_REGION_SLOTS_4)
        credited = _entailed_from(space, premises, targets, rng)
        distractors = select_distractors(space, premises, pool, rng, exclude=credited)
        return Blueprint(
            family="must_be_true",
            proof_kind="logical",
            binding_spec=BindingSpec(property_slots=_REGION_SLOTS_4),
            premises=premises,
            choices=(
                FormalChoice(role="credited", statement=credited),
                *(FormalChoice(role="distractor", statement=d) for d in distractors),
            ),
            space=space,
            arrangement={"chain": name, "rule_count": len(premises)},
        )

    def stem(self, rng: random.Random) -> str:
        return rng.choice(
            [
                "If the statements above are true, which one of the following must also be true?",
                "The statements above, if true, most strongly support which one of the following?",
            ]
        )

    def explain(self, blueprint: Blueprint, binding: Binding, credited: str) -> str:
        return (
            "Run the chain one link at a time and keep the weakest quantifier "
            "you passed through: a universal preserves whatever came into it, a "
            "majority weakens a universal to a majority, and two majorities meet "
            "only as 'at least one'. Choices that carry a stronger quantifier "
            "than the chain allows, or that run a link backwards, overreach. "
            f"The credited answer is what survives every consistent case: {credited}"
        )

    def method(self) -> str:
        return (
            "Write the four terms in order, mark each link with its quantifier, "
            "and carry the weakest one to the far end."
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

#: Rule counts a game may draw. Two rules is a loose game, four a tight one.
_RULE_COUNTS = (2, 3, 4)
#: The arrangement band a sequencing rule set must leave. Fewer than the floor
#: makes every true statement entailed (one arrangement) or leaves too few
#: truth patterns for four distinct distractors; more than the ceiling means
#: the rules barely constrain and the must-be-true variant has nothing to say.
MIN_ORDERINGS = 2
MAX_ORDERINGS = 30


def _order_menu(entities: Sequence[str]) -> list[tuple[str, Statement]]:
    """Every ordering rule the game may draw, tagged with its menu id."""
    menu: list[tuple[str, Statement]] = []
    slots = range(1, len(entities) + 1)
    for a in entities:
        for b in entities:
            if a == b:
                continue
            menu.append(("before", Before(a, b)))
            menu.append(("immediately", Immediately(a, b)))
            if a < b:
                menu.append(("adjacent", Adjacent(a, b)))
        for slot in slots:
            menu.append(("at", AtSlot(a, slot)))
            menu.append(("not-at", NotAtSlot(a, slot)))
    return menu


def _draw_rules(
    rng: random.Random,
    menu: list[tuple[str, Statement]],
    count: int,
) -> tuple[tuple[str, ...], tuple[Statement, ...]]:
    """``count`` rules over pairwise-distinct slot sets.

    Two rules about the same entities are usually one rule written twice
    (``Before`` plus ``Immediately``) or a contradiction; either way the item
    reads as machine-made, so each draw mentions a fresh set of slots.
    """
    shuffled = list(menu)
    rng.shuffle(shuffled)
    ids: list[str] = []
    rules: list[Statement] = []
    seen: set[frozenset[str]] = set()
    for menu_id, rule in shuffled:
        if len(rules) >= count:
            break
        key = rule.slots()
        if key in seen:
            continue
        seen.add(key)
        ids.append(menu_id)
        rules.append(rule)
    return tuple(ids), tuple(rules)


def _order_rules(
    rng: random.Random,
    *,
    min_valid: int = MIN_ORDERINGS,
    max_valid: int = MAX_ORDERINGS,
) -> tuple[tuple[str, ...], tuple[Statement, ...], list[OrderModel]]:
    """A rule set that constrains without over-determining.

    Two to four rules are drawn from the menu and re-drawn until they leave
    between ``min_valid`` and ``max_valid`` valid arrangements: one arrangement
    makes every true statement entailed, and too many makes the must-be-true
    variant have no answer. Returns the menu ids drawn, the rules, and the
    arrangements they permit.
    """
    space = OrderSpace(entities=_GAME_ENTITIES)
    menu = _order_menu(_GAME_ENTITIES)
    for _ in range(MAX_ARRANGEMENT_DRAWS):
        count = rng.choice(_RULE_COUNTS)
        ids, rules = _draw_rules(rng, menu, count)
        valid = [m for m in space.models() if all(r.holds(m) for r in rules)]
        if min_valid <= len(valid) <= max_valid:
            return ids, rules, valid
    raise SchemaError(
        f"sequencing rules never landed in the {min_valid}-{max_valid} "
        f"arrangement band in {MAX_ARRANGEMENT_DRAWS} draws"
    )


@dataclass(frozen=True)
class SequencingGame:
    """An ordering game: acceptability, or what must be true of every arrangement.

    The rule set is drawn per item from a menu of before / immediately-before /
    adjacent / at-slot / not-at-slot rules, two to four at a time, and re-drawn
    until it leaves a usable number of arrangements. Every draw is proved the
    same way, so a loose three-rule game and a tight four-rule one carry the
    same guarantee.
    """

    acceptability: bool
    meta: SchemaMeta

    def build(self, rng: random.Random, domain: DomainPack) -> Blueprint:
        return _draw_until(rng, self._attempt, what=self.meta.id)

    def _attempt(self, rng: random.Random) -> Blueprint:
        space = OrderSpace(entities=_GAME_ENTITIES)
        # The must-be-true variant needs enough arrangements for four distinct
        # truth patterns; an acceptability item only needs one valid ordering.
        rule_ids, premises, valid = _order_rules(
            rng, min_valid=MIN_ORDERINGS if self.acceptability else CHOICE_COUNT
        )
        arrangement: dict[str, int | str] = {
            "rule_count": len(premises),
            "rules": "+".join(rule_ids),
            "valid_orderings": len(valid),
        }

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
                arrangement=arrangement,
            )

        pool: list[Statement] = []
        for a in _GAME_ENTITIES:
            for b in _GAME_ENTITIES:
                if a != b:
                    pool.append(Before(a, b))
            for slot in range(1, len(_GAME_ENTITIES) + 1):
                pool.extend([AtSlot(a, slot), NotAtSlot(a, slot)])
        # A stated rule is entailed by itself; restating one is not an inference.
        credited = _entailed_from(
            space, premises, [p for p in pool if p not in premises], rng
        )
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
            arrangement=arrangement,
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


def _group_menu(
    entities: Sequence[str], groups: Sequence[str]
) -> list[tuple[str, Statement]]:
    """Every grouping rule the game may draw, tagged with its menu id."""
    menu: list[tuple[str, Statement]] = []
    for i, a in enumerate(entities):
        for b in entities[i + 1 :]:
            menu.append(("same", SameGroup(a, b)))
            menu.append(("different", DiffGroup(a, b)))
        for g in groups:
            menu.append(("in", InGroup(a, g)))
            menu.append(("not-in", NotInGroup(a, g)))
    return menu


@dataclass(frozen=True)
class GroupingGame:
    """A distribution game: which assignment could be accurate.

    Two to four rules are drawn per item from a menu of same-group /
    different-group / placed-in / not-placed-in rules and re-drawn until they
    leave more than one valid split and enough invalid ones for the distractors.
    """

    meta: SchemaMeta

    def build(self, rng: random.Random, domain: DomainPack) -> Blueprint:
        return _draw_until(rng, self._attempt, what=self.meta.id)

    def _attempt(self, rng: random.Random) -> Blueprint:
        space = AssignSpace(entities=_GROUP_ENTITIES, groups=_GROUP_SLOTS)
        rule_ids, premises = _draw_rules(
            rng, _group_menu(_GROUP_ENTITIES, _GROUP_SLOTS), rng.choice(_RULE_COUNTS)
        )
        valid = [m for m in space.models() if all(r.holds(m) for r in premises)]
        invalid = [m for m in space.models() if not all(r.holds(m) for r in premises)]
        # A rule set that every assignment satisfies is no game, and one that
        # leaves a single split has been solved by the setup.
        if len(valid) < 2 or len(invalid) < CHOICE_COUNT - 1:
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
            arrangement={
                "rule_count": len(premises),
                "rules": "+".join(rule_ids),
                "valid_splits": len(valid),
            },
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


def _order_pool(entities: Sequence[str]) -> list[Statement]:
    """Every simple claim about an ordering the checker can settle."""
    pool: list[Statement] = []
    for a in entities:
        for b in entities:
            if a == b:
                continue
            pool.append(Before(a, b))
            if a < b:
                pool.append(Adjacent(a, b))
        for slot in range(1, len(entities) + 1):
            pool.extend([AtSlot(a, slot), NotAtSlot(a, slot)])
    return pool


@dataclass(frozen=True)
class SequencingCannotBeTrue:
    """Four claims each hold in some valid ordering; one holds in none.

    The exam writes this as "could be true EXCEPT", which is the same question
    as "cannot be true" and the same proof: enumerate every ordering the rules
    permit, and the credited answer is the claim no surviving ordering makes
    true. What the family demands — exactly one contradicted choice, and four
    that are genuinely possible — is what the checker settles.
    """

    meta: SchemaMeta

    def build(self, rng: random.Random, domain: DomainPack) -> Blueprint:
        return _draw_until(rng, self._attempt, what=self.meta.id)

    def _attempt(self, rng: random.Random) -> Blueprint:
        space = OrderSpace(entities=_GAME_ENTITIES)
        # Enough surviving arrangements that four claims can each be possible
        # without all being possible in the same single ordering.
        rule_ids, premises, valid = _order_rules(rng, min_valid=3)
        pool = [p for p in _order_pool(_GAME_ENTITIES) if p not in premises]
        result = evaluate(space, premises, pool)
        impossible = [
            (result.key(i), c)
            for i, c in enumerate(pool)
            if result.status_of(i) == "contradicted"
        ]
        possible = [
            (result.key(i), c)
            for i, c in enumerate(pool)
            if result.status_of(i) == "contingent"
        ]
        if not impossible:
            raise SchemaError("every claim about this board is possible")
        rng.shuffle(impossible)
        credited = impossible[0][1]
        distractors = _distinct_picks(
            possible, CHOICE_COUNT - 1, rng, used=set(), like=credited
        )
        if len(distractors) < CHOICE_COUNT - 1:
            raise SchemaError("too few distinct possible claims for the distractors")
        return Blueprint(
            family="cannot_be_true",
            proof_kind="logical",
            binding_spec=BindingSpec(entity_slots=_GAME_ENTITIES, needs_ordering=True),
            premises=premises,
            choices=(
                FormalChoice(role="credited", statement=credited),
                *(FormalChoice(role="distractor", statement=d) for d in distractors),
            ),
            space=space,
            arrangement={
                "rule_count": len(premises),
                "rules": "+".join(rule_ids),
                "valid_orderings": len(valid),
            },
        )

    def stem(self, rng: random.Random) -> str:
        return rng.choice(
            [
                "Each of the following could be true EXCEPT:",
                "Which one of the following CANNOT be true?",
            ]
        )

    def explain(self, blueprint: Blueprint, binding: Binding, credited: str) -> str:
        return (
            "Four of the choices are realizable: each holds in at least one "
            "ordering the rules permit. The credited answer holds in none of "
            f"them: {credited} Do not test the choices against your favourite "
            "arrangement — a claim is only impossible when *every* surviving "
            "arrangement rules it out."
        )

    def method(self) -> str:
        return (
            "Build the arrangements the rules permit, then ask of each choice "
            "whether any one of them makes it true."
        )


@dataclass(frozen=True)
class SequencingLocalConditional:
    """A supposition the question adds, and what it forces.

    The exam's local question puts one extra condition in the question sentence
    — "If the audit is third, then…" — and asks what follows *given that*. The
    proof is the global one with the supposition added as a premise, which is
    exactly what the condition means; the only new machinery is that the
    condition is rendered into the question rather than into the stimulus, so
    the board itself stays the board the other questions would share.
    """

    meta: SchemaMeta

    def build(self, rng: random.Random, domain: DomainPack) -> Blueprint:
        return _draw_until(rng, self._attempt, what=self.meta.id)

    def _attempt(self, rng: random.Random) -> Blueprint:
        space = OrderSpace(entities=_GAME_ENTITIES)
        rule_ids, rules, _valid = _order_rules(rng, min_valid=CHOICE_COUNT)
        pool = _order_pool(_GAME_ENTITIES)
        # A supposition worth asking about: it must leave more than one
        # arrangement (otherwise the board is solved and every true statement
        # is entailed) and fewer than the rules alone allowed.
        conditions = [
            c for c in pool if isinstance(c, AtSlot | Adjacent) and c not in rules
        ]
        rng.shuffle(conditions)
        for condition in conditions:
            premises = (*rules, condition)
            survivors = [m for m in space.models() if all(r.holds(m) for r in premises)]
            if not MIN_ORDERINGS <= len(survivors) <= MAX_ORDERINGS:
                continue
            candidates = [p for p in pool if p not in premises]
            try:
                credited = _entailed_from(space, premises, candidates, rng)
                distractors = select_distractors(
                    space, premises, candidates, rng, exclude=credited
                )
            except SchemaError:
                continue
            return Blueprint(
                family="must_be_true",
                proof_kind="logical",
                binding_spec=BindingSpec(
                    entity_slots=_GAME_ENTITIES, needs_ordering=True
                ),
                premises=premises,
                choices=(
                    FormalChoice(role="credited", statement=credited),
                    *(
                        FormalChoice(role="distractor", statement=d)
                        for d in distractors
                    ),
                ),
                space=space,
                local_condition=condition,
                arrangement={
                    "rule_count": len(rules),
                    "rules": "+".join(rule_ids),
                    "valid_orderings": len(survivors),
                },
            )
        raise SchemaError("no supposition left a usable board")

    def stem(self, rng: random.Random) -> str:
        return rng.choice(
            [
                "Which one of the following must be true?",
                "Which one of the following must be true of the ordering?",
            ]
        )

    def explain(self, blueprint: Blueprint, binding: Binding, credited: str) -> str:
        return (
            "The supposition in the question is not a new rule for the whole "
            "game — it holds for this question only. Add it to the board, "
            "enumerate what survives, and one choice is true in every surviving "
            f"arrangement: {credited} The others hold in some and fail in "
            "others, which is a could-be, not a must-be."
        )

    def method(self) -> str:
        return (
            "Redraw the board with the supposition in place, chase the forced "
            "placements it creates, and test each choice against what is left."
        )


_SELECT_ENTITIES = ("e1", "e2", "e3", "e4")
_SELECT_GROUPS = ("g1", "g2")


@dataclass(frozen=True)
class ConditionalSelection:
    """Membership rules that are conditionals, chased through contrapositives.

    Each element is in one side or the other, and the rules are "if this one is
    here, that one is not" — the selection game's characteristic shape, and the
    one place a games item is solved by the same contrapositive move a
    conditional Logical Reasoning item needs. The space is every assignment of
    the elements to the two sides, so the rules and their contrapositives are
    both accounted for without either being stated twice.
    """

    meta: SchemaMeta

    def build(self, rng: random.Random, domain: DomainPack) -> Blueprint:
        return _draw_until(rng, self._attempt, what=self.meta.id)

    def _menu(self) -> list[tuple[str, Statement]]:
        menu: list[tuple[str, Statement]] = []
        for a in _SELECT_ENTITIES:
            for b in _SELECT_ENTITIES:
                if a == b:
                    continue
                for g in _SELECT_GROUPS:
                    other = _SELECT_GROUPS[1 - _SELECT_GROUPS.index(g)]
                    menu.append(
                        ("if-in-then-in", Implies(InGroup(a, g), InGroup(b, g)))
                    )
                    menu.append(
                        ("if-in-then-out", Implies(InGroup(a, g), InGroup(b, other)))
                    )
        for a in _SELECT_ENTITIES:
            for g in _SELECT_GROUPS:
                menu.append(("fixed", InGroup(a, g)))
        return menu

    def _attempt(self, rng: random.Random) -> Blueprint:
        space = AssignSpace(entities=_SELECT_ENTITIES, groups=_SELECT_GROUPS)
        _ids, premises = _draw_rules(rng, self._menu(), rng.choice(_RULE_COUNTS))
        valid = [m for m in space.models() if all(r.holds(m) for r in premises)]
        if len(valid) < MIN_ORDERINGS:
            raise SchemaError("selection rules leave no room to reason")
        pool: list[Statement] = []
        for a in _SELECT_ENTITIES:
            for g in _SELECT_GROUPS:
                pool.extend([InGroup(a, g), NotInGroup(a, g)])
            for b in _SELECT_ENTITIES:
                if a < b:
                    pool.extend([SameGroup(a, b), DiffGroup(a, b)])
        # A credited answer that follows from one rule on its own is a
        # restatement, not an inference — the whole point of a selection item is
        # that the chain runs through a conditional and its contrapositive.
        candidates = [
            c
            for c in pool
            if c not in premises
            and not any(entails(space, [rule], c) for rule in premises)
        ]
        credited = _entailed_from(space, premises, candidates, rng)
        distractors = select_distractors(
            space, premises, candidates, rng, exclude=credited
        )
        return Blueprint(
            family="must_be_true",
            proof_kind="logical",
            binding_spec=BindingSpec(
                entity_slots=_SELECT_ENTITIES, group_slots=_SELECT_GROUPS
            ),
            premises=premises,
            choices=(
                FormalChoice(role="credited", statement=credited),
                *(FormalChoice(role="distractor", statement=d) for d in distractors),
            ),
            space=space,
            arrangement={"rule_count": len(premises), "valid_splits": len(valid)},
        )

    def stem(self, rng: random.Random) -> str:
        return rng.choice(
            [
                "Which one of the following must be true?",
                "Which one of the following is determined by the conditions above?",
            ]
        )

    def explain(self, blueprint: Blueprint, binding: Binding, credited: str) -> str:
        return (
            "Each rule is a conditional, so each carries its contrapositive: "
            "the rule that puts one element with another also keeps the second "
            "away from where the first cannot go. Chase both directions and one "
            f"placement is forced in every acceptable selection: {credited}"
        )

    def method(self) -> str:
        return (
            "Write each rule and its contrapositive, then follow the chain from "
            "whichever element the conditions place outright."
        )


_DIST_ENTITIES = ("e1", "e2", "e3", "e4", "e5")
_DIST_GROUPS = ("g1", "g2", "g3")


@dataclass(frozen=True)
class NumericDistribution:
    """Three unequal groups; what the counts force before anything is placed.

    The distinctive move is arithmetic rather than placement: five elements
    across three groups with one group's size fixed leaves the other two with a
    small number of splits, and the credited answer follows from the counting
    alone. The space is every assignment, so a claim about counts and a claim
    about a particular element are settled the same way.
    """

    meta: SchemaMeta

    def build(self, rng: random.Random, domain: DomainPack) -> Blueprint:
        return _draw_until(rng, self._attempt, what=self.meta.id)

    def _menu(self) -> list[tuple[str, Statement]]:
        menu: list[tuple[str, Statement]] = []
        for g in _DIST_GROUPS:
            for size in (1, 2, 3):
                menu.append(("size", GroupSize(g, size)))
        for i, a in enumerate(_DIST_ENTITIES):
            for b in _DIST_ENTITIES[i + 1 :]:
                menu.append(("same", SameGroup(a, b)))
                menu.append(("different", DiffGroup(a, b)))
            for g in _DIST_GROUPS:
                menu.append(("not-in", NotInGroup(a, g)))
        return menu

    def _attempt(self, rng: random.Random) -> Blueprint:
        space = AssignSpace(entities=_DIST_ENTITIES, groups=_DIST_GROUPS)
        _ids, premises = _draw_rules(rng, self._menu(), rng.choice(_RULE_COUNTS))
        # At least one rule must be about counts, or this is an ordinary
        # grouping item wearing a numeric label.
        if not any(isinstance(p, GroupSize) for p in premises):
            raise SchemaError("no numeric rule in the draw")
        valid = [m for m in space.models() if all(r.holds(m) for r in premises)]
        if len(valid) < MIN_ORDERINGS:
            raise SchemaError("numeric rules leave no room to reason")
        pool: list[Statement] = []
        for g in _DIST_GROUPS:
            for size in range(0, len(_DIST_ENTITIES) + 1):
                pool.append(GroupSize(g, size))
        for i, a in enumerate(_DIST_ENTITIES):
            for b in _DIST_ENTITIES[i + 1 :]:
                pool.extend([SameGroup(a, b), DiffGroup(a, b)])
            for g in _DIST_GROUPS:
                pool.extend([InGroup(a, g), NotInGroup(a, g)])
        candidates = [p for p in pool if p not in premises]
        # Prefer a claim about the counts: this family's inference is arithmetic
        # and a credited answer about two elements sharing a group hides that.
        numeric = [c for c in candidates if isinstance(c, GroupSize)]
        try:
            credited = _entailed_from(space, premises, numeric, rng)
        except SchemaError:
            credited = _entailed_from(space, premises, candidates, rng)
        distractors = select_distractors(
            space, premises, candidates, rng, exclude=credited
        )
        return Blueprint(
            family="must_be_true",
            proof_kind="logical",
            binding_spec=BindingSpec(
                entity_slots=_DIST_ENTITIES, group_slots=_DIST_GROUPS
            ),
            premises=premises,
            choices=(
                FormalChoice(role="credited", statement=credited),
                *(FormalChoice(role="distractor", statement=d) for d in distractors),
            ),
            space=space,
            arrangement={"rule_count": len(premises), "valid_splits": len(valid)},
        )

    def stem(self, rng: random.Random) -> str:
        return rng.choice(
            [
                "Which one of the following must be true?",
                "Which one of the following must be true about the assignment?",
            ]
        )

    def explain(self, blueprint: Blueprint, binding: Binding, credited: str) -> str:
        return (
            "Count before you place. With the group sizes the conditions fix, "
            "only a few splits of the remaining elements are available at all, "
            f"and every one of them makes the credited answer true: {credited}"
        )

    def method(self) -> str:
        return (
            "Write the possible size distributions first, discard the ones the "
            "rules forbid, and read the answer off what every survivor shares."
        )


@dataclass(frozen=True)
class SupportedInference:
    """Most strongly supported — asked as the exam asks it, proved regardless.

    The exam's "most strongly supported" is weaker than entailment: the
    credited answer is the modest claim the findings favour. This engine cannot
    measure "favours", so it does the safe thing and proves entailment: a claim
    the premises *entail* is certainly the claim they most strongly support,
    and the hedged distractors are the ones the checker shows do not follow.
    The question sentence is the exam's; the guarantee is stronger than the
    question demands.
    """

    meta: SchemaMeta

    def build(self, rng: random.Random, domain: DomainPack) -> Blueprint:
        space = RegionSpace(predicates=_REGION_SLOTS)
        name, premises, targets = rng.choice(
            (
                (
                    "most-all",
                    (Most("P", "Q"), All("Q", "R")),
                    (Some("P", "R"), Most("P", "R")),
                ),
                (
                    "all-some",
                    (All("P", "Q"), Some("P", "R")),
                    (Some("Q", "R"), Some("R", "Q")),
                ),
                (
                    "no-some",
                    (No("P", "Q"), Some("R", "P")),
                    (NotAll("R", "Q"), Some("R", "P")),
                ),
            )
        )
        credited = _entailed_from(space, premises, targets, rng)
        distractors = select_distractors(
            space, premises, _region_pool(), rng, exclude=credited
        )
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
            arrangement={"pair": name, "rule_count": len(premises)},
        )

    def stem(self, rng: random.Random) -> str:
        return rng.choice(
            [
                "The statements above, if true, most strongly support which one of the following?",
                "Which one of the following is most strongly supported by the information above?",
            ]
        )

    def explain(self, blueprint: Blueprint, binding: Binding, credited: str) -> str:
        return (
            "A support question rewards the most modest claim the statements "
            "reach, not the most interesting one. Here the credited answer is "
            f"not merely supported but forced: {credited} Each other choice "
            "goes further than the premises license — a stronger quantifier, or "
            "a relation the statements never connect."
        )

    def method(self) -> str:
        return (
            "Take the weakest reading of each statement, combine only on the "
            "shared term, and prefer the choice that claims the least."
        )


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
    SequencingCannotBeTrue(
        meta=_meta(
            "lg-sequencing-cannot-be-true",
            section="LG",
            archetype="lg-could-be-true-except",
            family="cannot_be_true",
            proof="logical",
            difficulty="hard",
            concepts=("could-be-true-except", "must-be-true", "sequencing"),
            capability="order",
            summary="Four claims are realizable; one is impossible.",
        ),
    ),
    SequencingLocalConditional(
        meta=_meta(
            "lg-sequencing-local-conditional",
            section="LG",
            archetype="lg-local-conditional",
            family="must_be_true",
            proof="logical",
            difficulty="med",
            concepts=("sequencing", "conditional-reasoning", "must-be-true"),
            capability="order",
            summary="One supposition in the question, and what it forces.",
        ),
    ),
    ConditionalSelection(
        meta=_meta(
            "lg-conditional-selection",
            section="LG",
            archetype="lg-in-out-selection",
            family="must_be_true",
            proof="logical",
            difficulty="med",
            concepts=("in-out-selection", "contrapositive", "must-be-true"),
            capability="assign",
            summary="Conditional membership rules chased through contrapositives.",
        ),
    ),
    NumericDistribution(
        meta=_meta(
            "lg-numeric-distribution",
            section="LG",
            archetype="lg-numeric-distribution",
            family="must_be_true",
            proof="logical",
            difficulty="hard",
            concepts=("numeric-distribution", "grouping-game", "must-be-true"),
            capability="assign",
            summary="Fixed group sizes; what the counting forces.",
        ),
    ),
    SupportedInference(
        meta=_meta(
            "lr-supported-inference",
            section="LR",
            archetype="lr-most-strongly-supported",
            family="must_be_true",
            proof="logical",
            difficulty="med",
            concepts=("most-strongly-supported", "must-be-true"),
            capability="region",
            summary="The modest claim the statements reach — proved, not judged.",
        ),
    ),
    QuantifierChainFour(
        meta=_meta(
            "lr-quantifier-chain-four-term",
            section="LR",
            archetype="lr-must-be-true",
            family="must_be_true",
            proof="logical",
            difficulty="hard",
            concepts=("must-be-true", "universal-instantiation"),
            capability="region",
            summary="Chain three quantified premises across four terms.",
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
