"""The proof engine — statements, bounded model spaces, and entailment.

Spec 049 FR-1/FR-2/FR-3. This module is the reason a synthesized item's key can
be *proved* rather than asserted: it enumerates every model of a bounded space,
keeps the ones satisfying the premises, and reports for each candidate answer
whether it holds in all of them (``entailed``), some of them (``contingent``),
or none (``contradicted``).

**It contains no English.** A statement is a structure over abstract slot names
(``"A"``, ``"B"``, ``"e1"``). Swapping the domain pack that supplies the words
therefore cannot change a single entailment — which is the whole basis for the
claim that surface variation does not diminish validity.

Four model spaces, each enumerated exhaustively within a declared bound:

``PropSpace``
    Truth assignments over K atoms — conditionals about one subject. 2^K models,
    K ≤ 8. Decides propositional entailment outright.

``RegionSpace``
    The load-bearing one. Every LSAT quantifier statement is a function of *how
    many* things fall in each Venn region of the predicates, not of which, so a
    model is a count vector over the 2^K regions rather than an assignment to
    individuals. That makes ``most`` exact and keeps the space enumerable:
    (C+1)^(2^K) models for counts capped at C. Emptiness patterns decide
    ``all``/``some``/``no`` completely; C = 2 is enough to witness every
    cardinality comparison ``most`` can make between two disjoint regions.

``OrderSpace``
    Permutations of E entities — sequencing games. E! models, E ≤ 7. Exact.

``AssignSpace``
    Functions from entities to groups — grouping games. G^E models. Exact.

Every space refuses to enumerate past its bound rather than hanging, so a schema
that outgrows the engine fails loudly at authoring time.

The one guard that matters most: an **inconsistent premise set entails
everything**, which would silently certify all five choices. :func:`classify_all`
raises rather than reporting that as a pass.
"""

from __future__ import annotations

import itertools
from collections.abc import Iterable, Iterator, Sequence
from dataclasses import dataclass
from typing import Literal, Protocol

Status = Literal["entailed", "contingent", "contradicted"]

#: Refuse to enumerate a space larger than this. Chosen so the slowest space a
#: shipped schema uses stays in the low hundreds of milliseconds, and so an
#: over-wide schema fails at authoring time instead of hanging CI.
MAX_MODELS = 200_000


class SynthLogicError(ValueError):
    """A schema asks the checker for something it cannot soundly decide."""


class InconsistentPremises(SynthLogicError):
    """The premise set has no model.

    Never reported as a pass: everything is entailed by a contradiction, so a
    schema that reaches this state would certify all five of its choices.
    """


class SpaceTooLarge(SynthLogicError):
    """Enumerating this space would exceed :data:`MAX_MODELS`."""


# ---------------------------------------------------------------------------
# Statements
# ---------------------------------------------------------------------------


class Statement(Protocol):
    """Anything a model space can evaluate. Frozen, hashable, word-free."""

    def holds(self, model: object) -> bool: ...

    def slots(self) -> frozenset[str]:
        """Abstract names this statement references (for the realizer)."""
        ...


# --- propositional ---------------------------------------------------------


@dataclass(frozen=True)
class Atom:
    name: str

    def holds(self, model: object) -> bool:
        assert isinstance(model, frozenset)
        return self.name in model

    def slots(self) -> frozenset[str]:
        return frozenset({self.name})


@dataclass(frozen=True)
class Not:
    inner: Statement

    def holds(self, model: object) -> bool:
        return not self.inner.holds(model)

    def slots(self) -> frozenset[str]:
        return self.inner.slots()


@dataclass(frozen=True)
class And:
    parts: tuple[Statement, ...]

    def holds(self, model: object) -> bool:
        return all(p.holds(model) for p in self.parts)

    def slots(self) -> frozenset[str]:
        return (
            frozenset().union(*(p.slots() for p in self.parts))
            if self.parts
            else frozenset()
        )


@dataclass(frozen=True)
class Or:
    parts: tuple[Statement, ...]

    def holds(self, model: object) -> bool:
        return any(p.holds(model) for p in self.parts)

    def slots(self) -> frozenset[str]:
        return (
            frozenset().union(*(p.slots() for p in self.parts))
            if self.parts
            else frozenset()
        )


@dataclass(frozen=True)
class Implies:
    antecedent: Statement
    consequent: Statement

    def holds(self, model: object) -> bool:
        return (not self.antecedent.holds(model)) or self.consequent.holds(model)

    def slots(self) -> frozenset[str]:
        return self.antecedent.slots() | self.consequent.slots()


@dataclass(frozen=True)
class Iff:
    left: Statement
    right: Statement

    def holds(self, model: object) -> bool:
        return self.left.holds(model) == self.right.holds(model)

    def slots(self) -> frozenset[str]:
        return self.left.slots() | self.right.slots()


# --- monadic / quantified --------------------------------------------------
#
# Evaluated against a `RegionModel`: counts[r] is how many individuals fall in
# Venn region r, where bit i of r means "in predicate i".


@dataclass(frozen=True)
class RegionModel:
    counts: tuple[int, ...]
    predicates: tuple[str, ...]

    def _index(self, name: str) -> int:
        return self.predicates.index(name)

    def size_of(self, *, inside: Sequence[str], outside: Sequence[str] = ()) -> int:
        """How many individuals are in every ``inside`` predicate and no ``outside`` one."""
        in_bits = sum(1 << self._index(n) for n in inside)
        out_bits = sum(1 << self._index(n) for n in outside)
        return sum(
            count
            for region, count in enumerate(self.counts)
            if (region & in_bits) == in_bits and (region & out_bits) == 0
        )


@dataclass(frozen=True)
class All:
    """Every A is B — no individual is A-and-not-B."""

    a: str
    b: str

    def holds(self, model: object) -> bool:
        assert isinstance(model, RegionModel)
        return model.size_of(inside=[self.a], outside=[self.b]) == 0

    def slots(self) -> frozenset[str]:
        return frozenset({self.a, self.b})


@dataclass(frozen=True)
class No:
    """No A is B."""

    a: str
    b: str

    def holds(self, model: object) -> bool:
        assert isinstance(model, RegionModel)
        return model.size_of(inside=[self.a, self.b]) == 0

    def slots(self) -> frozenset[str]:
        return frozenset({self.a, self.b})


@dataclass(frozen=True)
class Some:
    """At least one A is B."""

    a: str
    b: str

    def holds(self, model: object) -> bool:
        assert isinstance(model, RegionModel)
        return model.size_of(inside=[self.a, self.b]) > 0

    def slots(self) -> frozenset[str]:
        return frozenset({self.a, self.b})


@dataclass(frozen=True)
class NotAll:
    """At least one A is not B — the negation of :class:`All`."""

    a: str
    b: str

    def holds(self, model: object) -> bool:
        assert isinstance(model, RegionModel)
        return model.size_of(inside=[self.a], outside=[self.b]) > 0

    def slots(self) -> frozenset[str]:
        return frozenset({self.a, self.b})


@dataclass(frozen=True)
class Most:
    """More than half of A is B.

    An empty A makes this false (0 > 0 fails), which matches the exam's reading:
    "most of the applicants were approved" asserts there were applicants.
    """

    a: str
    b: str

    def holds(self, model: object) -> bool:
        assert isinstance(model, RegionModel)
        yes = model.size_of(inside=[self.a, self.b])
        no = model.size_of(inside=[self.a], outside=[self.b])
        return yes > no

    def slots(self) -> frozenset[str]:
        return frozenset({self.a, self.b})


@dataclass(frozen=True)
class AtLeast:
    predicate: str
    count: int

    def holds(self, model: object) -> bool:
        assert isinstance(model, RegionModel)
        return model.size_of(inside=[self.predicate]) >= self.count

    def slots(self) -> frozenset[str]:
        return frozenset({self.predicate})


@dataclass(frozen=True)
class Exactly:
    predicate: str
    count: int

    def holds(self, model: object) -> bool:
        assert isinstance(model, RegionModel)
        return model.size_of(inside=[self.predicate]) == self.count

    def slots(self) -> frozenset[str]:
        return frozenset({self.predicate})


# --- ordering --------------------------------------------------------------
#
# Evaluated against an `OrderModel`: a permutation of the entities, slot 1 first.


@dataclass(frozen=True)
class OrderModel:
    sequence: tuple[str, ...]

    def slot_of(self, entity: str) -> int:
        """1-based position."""
        return self.sequence.index(entity) + 1


@dataclass(frozen=True)
class Before:
    early: str
    late: str

    def holds(self, model: object) -> bool:
        assert isinstance(model, OrderModel)
        return model.slot_of(self.early) < model.slot_of(self.late)

    def slots(self) -> frozenset[str]:
        return frozenset({self.early, self.late})


@dataclass(frozen=True)
class Immediately:
    early: str
    late: str

    def holds(self, model: object) -> bool:
        assert isinstance(model, OrderModel)
        return model.slot_of(self.late) - model.slot_of(self.early) == 1

    def slots(self) -> frozenset[str]:
        return frozenset({self.early, self.late})


@dataclass(frozen=True)
class Adjacent:
    one: str
    other: str

    def holds(self, model: object) -> bool:
        assert isinstance(model, OrderModel)
        return abs(model.slot_of(self.one) - model.slot_of(self.other)) == 1

    def slots(self) -> frozenset[str]:
        return frozenset({self.one, self.other})


@dataclass(frozen=True)
class AtSlot:
    entity: str
    slot: int

    def holds(self, model: object) -> bool:
        assert isinstance(model, OrderModel)
        return model.slot_of(self.entity) == self.slot

    def slots(self) -> frozenset[str]:
        return frozenset({self.entity})


@dataclass(frozen=True)
class NotAtSlot:
    entity: str
    slot: int

    def holds(self, model: object) -> bool:
        assert isinstance(model, OrderModel)
        return model.slot_of(self.entity) != self.slot

    def slots(self) -> frozenset[str]:
        return frozenset({self.entity})


# --- grouping --------------------------------------------------------------
#
# Evaluated against an `AssignModel`: entity -> group name.


@dataclass(frozen=True)
class AssignModel:
    placement: tuple[tuple[str, str], ...]

    def group_of(self, entity: str) -> str:
        for name, group in self.placement:
            if name == entity:
                return group
        raise KeyError(entity)

    def size_of(self, group: str) -> int:
        return sum(1 for _, g in self.placement if g == group)


@dataclass(frozen=True)
class InGroup:
    entity: str
    group: str

    def holds(self, model: object) -> bool:
        assert isinstance(model, AssignModel)
        return model.group_of(self.entity) == self.group

    def slots(self) -> frozenset[str]:
        return frozenset({self.entity, self.group})


@dataclass(frozen=True)
class NotInGroup:
    entity: str
    group: str

    def holds(self, model: object) -> bool:
        assert isinstance(model, AssignModel)
        return model.group_of(self.entity) != self.group

    def slots(self) -> frozenset[str]:
        return frozenset({self.entity, self.group})


@dataclass(frozen=True)
class SameGroup:
    one: str
    other: str

    def holds(self, model: object) -> bool:
        assert isinstance(model, AssignModel)
        return model.group_of(self.one) == model.group_of(self.other)

    def slots(self) -> frozenset[str]:
        return frozenset({self.one, self.other})


@dataclass(frozen=True)
class DiffGroup:
    one: str
    other: str

    def holds(self, model: object) -> bool:
        assert isinstance(model, AssignModel)
        return model.group_of(self.one) != model.group_of(self.other)

    def slots(self) -> frozenset[str]:
        return frozenset({self.one, self.other})


@dataclass(frozen=True)
class GroupSize:
    group: str
    count: int

    def holds(self, model: object) -> bool:
        assert isinstance(model, AssignModel)
        return model.size_of(self.group) == self.count

    def slots(self) -> frozenset[str]:
        return frozenset({self.group})


# ---------------------------------------------------------------------------
# Model spaces
# ---------------------------------------------------------------------------


class ModelSpace(Protocol):
    # A read-only property, not a bare attribute: every space is a frozen
    # dataclass, and a settable protocol member would exclude all of them.
    @property
    def kind(self) -> str: ...

    def size(self) -> int: ...
    def models(self) -> Iterator[object]: ...
    def describe(self) -> str: ...


@dataclass(frozen=True)
class PropSpace:
    """Truth assignments over ``atoms``. Decides propositional entailment."""

    atoms: tuple[str, ...]
    kind: str = "prop"

    def size(self) -> int:
        return int(2 ** len(self.atoms))

    def models(self) -> Iterator[frozenset[str]]:
        for bits in range(self.size()):
            yield frozenset(
                name for i, name in enumerate(self.atoms) if bits & (1 << i)
            )

    def describe(self) -> str:
        return f"prop[{len(self.atoms)} atoms] = {self.size()} models"


@dataclass(frozen=True)
class RegionSpace:
    """Count vectors over the 2^K Venn regions of ``predicates``.

    ``max_count`` caps how many individuals a single region may hold. Two is
    enough for every cardinality comparison ``Most`` makes between a region and
    its complement within a predicate (2 > 1, 1 > 0), and keeps K = 3 at 6,561
    models. Raising it multiplies the space by (C+1)^(2^K), so the bound is
    enforced rather than advisory.
    """

    predicates: tuple[str, ...]
    max_count: int = 2
    kind: str = "region"

    def size(self) -> int:
        return int((self.max_count + 1) ** (2 ** len(self.predicates)))

    def models(self) -> Iterator[RegionModel]:
        regions = 2 ** len(self.predicates)
        for counts in itertools.product(range(self.max_count + 1), repeat=regions):
            yield RegionModel(counts=counts, predicates=self.predicates)

    def describe(self) -> str:
        return (
            f"region[{len(self.predicates)} predicates, "
            f"max {self.max_count} per region] = {self.size()} models"
        )


@dataclass(frozen=True)
class OrderSpace:
    """Permutations of ``entities`` — one entity per slot, slot 1 first."""

    entities: tuple[str, ...]
    kind: str = "order"

    def size(self) -> int:
        result = 1
        for n in range(2, len(self.entities) + 1):
            result *= n
        return result

    def models(self) -> Iterator[OrderModel]:
        for perm in itertools.permutations(self.entities):
            yield OrderModel(sequence=perm)

    def describe(self) -> str:
        return f"order[{len(self.entities)} entities] = {self.size()} models"


@dataclass(frozen=True)
class AssignSpace:
    """Every function from ``entities`` to ``groups``."""

    entities: tuple[str, ...]
    groups: tuple[str, ...]
    kind: str = "assign"

    def size(self) -> int:
        return int(len(self.groups) ** len(self.entities))

    def models(self) -> Iterator[AssignModel]:
        for combo in itertools.product(self.groups, repeat=len(self.entities)):
            yield AssignModel(placement=tuple(zip(self.entities, combo, strict=True)))

    def describe(self) -> str:
        return (
            f"assign[{len(self.entities)} entities -> "
            f"{len(self.groups)} groups] = {self.size()} models"
        )


# ---------------------------------------------------------------------------
# Entailment
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Classification:
    """One candidate's standing against a premise set."""

    status: Status
    #: Models satisfying premises *and* the candidate.
    supporting: int
    #: Models satisfying the premises at all. Zero is an error, never a pass.
    premise_models: int
    #: Total models in the space, before premises.
    space_models: int


def _satisfying(space: ModelSpace, statements: Sequence[Statement]) -> list[object]:
    total = space.size()
    if total > MAX_MODELS:
        raise SpaceTooLarge(
            f"{space.describe()} exceeds the {MAX_MODELS:,}-model bound — "
            "narrow the schema (fewer predicates, or a lower max_count)"
        )
    return [m for m in space.models() if all(s.holds(m) for s in statements)]


@dataclass(frozen=True)
class Evaluation:
    """Every candidate's truth pattern across the premise-satisfying models.

    A candidate's *mask* has one bit per surviving model. That single structure
    answers three questions at once — entailed (all bits set), contradicted (no
    bits set), and equivalent-to-another-candidate (identical masks) — so an
    item is classified with one enumeration instead of one per question.
    """

    masks: tuple[int, ...]
    premise_models: int
    space_models: int

    def status_of(self, index: int) -> Status:
        mask = self.masks[index]
        if mask == (1 << self.premise_models) - 1:
            return "entailed"
        if mask == 0:
            return "contradicted"
        return "contingent"

    def supporting(self, index: int) -> int:
        return bin(self.masks[index]).count("1")


def evaluate(
    space: ModelSpace,
    premises: Sequence[Statement],
    candidates: Sequence[Statement],
) -> Evaluation:
    """Enumerate once and record where each candidate holds.

    Raises :class:`InconsistentPremises` for the same reason
    :func:`classify_all` does: a contradiction entails everything, so reporting
    it as a pass would certify all five choices at once.
    """
    kept = _satisfying(space, premises)
    if not kept:
        raise InconsistentPremises(
            f"premise set has no model in {space.describe()} — "
            "the schema's premises contradict each other"
        )
    masks: list[int] = []
    for candidate in candidates:
        mask = 0
        for i, model in enumerate(kept):
            if candidate.holds(model):
                mask |= 1 << i
        masks.append(mask)
    return Evaluation(
        masks=tuple(masks), premise_models=len(kept), space_models=space.size()
    )


def classify_all(
    space: ModelSpace,
    premises: Sequence[Statement],
    candidates: Iterable[Statement],
) -> list[Classification]:
    """Classify every candidate against one premise set, enumerating once.

    Enumerating per candidate would multiply the cost by five for no gain; the
    premise-satisfying models are the same set every time.

    Raises :class:`InconsistentPremises` when the premises have no model. That
    is not a technicality: a contradiction entails every candidate, so a schema
    in that state would report all five choices as correct answers.
    """
    kept = _satisfying(space, premises)
    if not kept:
        raise InconsistentPremises(
            f"premise set has no model in {space.describe()} — "
            "the schema's premises contradict each other"
        )
    total = space.size()
    out: list[Classification] = []
    for candidate in candidates:
        supporting = sum(1 for m in kept if candidate.holds(m))
        if supporting == len(kept):
            status: Status = "entailed"
        elif supporting == 0:
            status = "contradicted"
        else:
            status = "contingent"
        out.append(
            Classification(
                status=status,
                supporting=supporting,
                premise_models=len(kept),
                space_models=total,
            )
        )
    return out


def classify(
    space: ModelSpace, premises: Sequence[Statement], candidate: Statement
) -> Classification:
    """Single-candidate convenience wrapper around :func:`classify_all`."""
    return classify_all(space, premises, [candidate])[0]


def entails(
    space: ModelSpace, premises: Sequence[Statement], candidate: Statement
) -> bool:
    return classify(space, premises, candidate).status == "entailed"


def satisfiable(space: ModelSpace, statements: Sequence[Statement]) -> bool:
    """True when some model satisfies every statement."""
    return bool(_satisfying(space, statements))


def equivalent(
    space: ModelSpace,
    premises: Sequence[Statement],
    one: Statement,
    other: Statement,
) -> bool:
    """True when two candidates hold in exactly the same premise-models.

    Two choices that are equivalent given the premises are two correct answers
    (or two wrong ones that a reviewer will argue about), so the verifier
    rejects an item where any pair is.
    """
    kept = _satisfying(space, premises)
    return all(one.holds(m) == other.holds(m) for m in kept)
