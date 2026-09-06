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


# ---------------------------------------------------------------------------
# Symbolic cardinality reasoning (BL-20260903-16)
# ---------------------------------------------------------------------------
#
# ``RegionSpace`` enumerates, and enumeration ends at three predicates: a fourth
# takes the space from 6,561 models to 43,046,721, two orders of magnitude past
# :data:`MAX_MODELS`. Dropping ``max_count`` to 1 would fit, but a per-region
# cap of 1 removes the 2-vs-1 margin ``Most`` relies on inside a single region,
# and an entailment decided over a truncated space is not the entailment the
# item claims.
#
# So a four-predicate space is decided rather than enumerated. Every monadic
# statement is a linear constraint over the 2^K region counts:
#
#     All(a, b)      sum(a ∧ ¬b) <= 0        Some(a, b)     sum(a ∧ b)  >= 1
#     No(a, b)       sum(a ∧ b)  <= 0        NotAll(a, b)   sum(a ∧ ¬b) >= 1
#     Most(a, b)     sum(a ∧ b) - sum(a ∧ ¬b) >= 1
#     AtLeast(p, n)  sum(p) >= n             Exactly(p, n)  sum(p) >= n and <= n
#
# and entailment is two satisfiability questions: ``premises ∧ ¬candidate`` has
# no model (entailed) and ``premises ∧ candidate`` has none (contradicted).
#
# Two things keep the search small. Constraints of the form ``sum <= 0`` fix
# every region they mention to zero before the search starts — one universal
# premise removes a quarter of the variables. And regions that appear in every
# constraint with the same coefficient are interchangeable: only their *sum* is
# ever read, so they collapse into one variable. What is left is a handful of
# variables searched depth-first with interval pruning.
#
# The soundness claim is not taken on faith: ``test_synth_logic.py`` cross-checks
# the solver against full enumeration on every K ≤ 3 pool, where both answers are
# available.


@dataclass(frozen=True)
class _CountConstraint:
    """``sum(plus) - sum(minus) op rhs`` over region indices."""

    plus: frozenset[int]
    minus: frozenset[int]
    op: str  # ">=" or "<="
    rhs: int

    def negated(self) -> _CountConstraint:
        if self.op == ">=":
            return _CountConstraint(self.plus, self.minus, "<=", self.rhs - 1)
        return _CountConstraint(self.plus, self.minus, ">=", self.rhs + 1)


#: A conjunction of constraints; a problem is a disjunction of these.
_Conjunction = tuple[_CountConstraint, ...]

#: How many search nodes the solver may open before giving up. Like
#: :data:`MAX_MODELS`, this is a bound that fails loudly rather than a hope.
MAX_SEARCH_NODES = 400_000


class UndecidableStatement(SynthLogicError):
    """A statement the symbolic solver has no constraint form for."""


def _regions(
    predicates: Sequence[str], inside: Sequence[str], outside: Sequence[str]
) -> frozenset[int]:
    in_bits = sum(1 << predicates.index(n) for n in inside)
    out_bits = sum(1 << predicates.index(n) for n in outside)
    return frozenset(
        r
        for r in range(2 ** len(predicates))
        if (r & in_bits) == in_bits and (r & out_bits) == 0
    )


def _pair_constraint(
    statement: Statement, predicates: Sequence[str]
) -> _CountConstraint | None:
    """The two-predicate quantifiers, each one linear constraint."""
    empty: frozenset[int] = frozenset()
    if isinstance(statement, All):
        return _CountConstraint(
            _regions(predicates, [statement.a], [statement.b]), empty, "<=", 0
        )
    if isinstance(statement, No):
        return _CountConstraint(
            _regions(predicates, [statement.a, statement.b], []), empty, "<=", 0
        )
    if isinstance(statement, Some):
        return _CountConstraint(
            _regions(predicates, [statement.a, statement.b], []), empty, ">=", 1
        )
    if isinstance(statement, NotAll):
        return _CountConstraint(
            _regions(predicates, [statement.a], [statement.b]), empty, ">=", 1
        )
    if isinstance(statement, Most):
        return _CountConstraint(
            _regions(predicates, [statement.a, statement.b], []),
            _regions(predicates, [statement.a], [statement.b]),
            ">=",
            1,
        )
    return None


def _atom_constraints(
    statement: Statement, predicates: Sequence[str]
) -> tuple[_Conjunction, ...]:
    """One monadic statement as a disjunction of constraint conjunctions."""
    empty: frozenset[int] = frozenset()
    pair = _pair_constraint(statement, predicates)
    if pair is not None:
        return ((pair,),)
    if isinstance(statement, AtLeast):
        here = _regions(predicates, [statement.predicate], [])
        return ((_CountConstraint(here, empty, ">=", statement.count),),)
    if isinstance(statement, Exactly):
        here = _regions(predicates, [statement.predicate], [])
        return (
            (
                _CountConstraint(here, empty, ">=", statement.count),
                _CountConstraint(here, empty, "<=", statement.count),
            ),
        )
    raise UndecidableStatement(
        f"{type(statement).__name__} has no cardinality form — the symbolic "
        "region space decides monadic quantifier statements only"
    )


def _negate_dnf(dnf: tuple[_Conjunction, ...]) -> tuple[_Conjunction, ...]:
    """De Morgan over a disjunction of conjunctions, back into the same shape."""
    out: list[_Conjunction] = [()]
    for conjunction in dnf:
        expanded: list[_Conjunction] = []
        for prefix in out:
            for constraint in conjunction:
                expanded.append((*prefix, constraint.negated()))
        out = expanded
    return tuple(out)


def region_constraints(
    statement: Statement, predicates: Sequence[str], *, negated: bool = False
) -> tuple[_Conjunction, ...]:
    """A statement (or its negation) as a disjunction of constraint conjunctions."""
    if isinstance(statement, Not):
        return region_constraints(statement.inner, predicates, negated=not negated)
    if isinstance(statement, And):
        parts = [region_constraints(p, predicates) for p in statement.parts]
        merged: tuple[_Conjunction, ...] = ((),)
        for part in parts:
            merged = tuple((*left, *right) for left in merged for right in part)
        return _negate_dnf(merged) if negated else merged
    if isinstance(statement, Or):
        merged = tuple(
            conj for p in statement.parts for conj in region_constraints(p, predicates)
        )
        return _negate_dnf(merged) if negated else merged
    dnf = _atom_constraints(statement, predicates)
    return _negate_dnf(dnf) if negated else dnf


@dataclass(frozen=True)
class _Variable:
    """Regions that every constraint treats identically, and their shared bound."""

    regions: tuple[int, ...]
    bound: int


def _group(
    constraints: Sequence[_CountConstraint], region_count: int, cap: int
) -> list[_Variable]:
    """Collapse interchangeable regions into one variable each.

    A region's *signature* is its coefficient in every constraint. Two regions
    with the same signature are read only through their sum, so searching them
    separately multiplies the work for nothing. Regions mentioned by no
    constraint are dropped entirely: setting them to zero can never break a
    constraint that does not see them.
    """
    signatures: dict[tuple[int, ...], list[int]] = {}
    for region in range(region_count):
        signature = tuple(
            (1 if region in c.plus else 0) - (1 if region in c.minus else 0)
            for c in constraints
        )
        if not any(signature):
            continue
        signatures.setdefault(signature, []).append(region)
    return [
        _Variable(regions=tuple(regions), bound=len(regions) * cap)
        for regions in signatures.values()
    ]


def _solve(
    conjunction: Sequence[_CountConstraint], predicates: Sequence[str], cap: int
) -> tuple[int, ...] | None:
    """A witness region-count vector for one conjunction, or None if there is none.

    Depth-first over the grouped variables with interval pruning: a constraint
    whose best case still fails prunes the branch immediately. Raises
    :class:`SpaceTooLarge` rather than running unboundedly.
    """
    region_count = 2 ** len(predicates)
    constraints = list(conjunction)
    # Regions forced to zero by a `sum <= 0` constraint (no negative side).
    zeroed: set[int] = set()
    for constraint in constraints:
        if constraint.op == "<=" and constraint.rhs <= 0 and not constraint.minus:
            if constraint.rhs < 0:
                return None  # a non-negative sum cannot be negative
            zeroed |= constraint.plus
    live = [
        _CountConstraint(
            frozenset(constraint.plus - zeroed),
            frozenset(constraint.minus - zeroed),
            constraint.op,
            constraint.rhs,
        )
        for constraint in constraints
    ]
    for constraint in live:
        if not constraint.plus and not constraint.minus:
            if constraint.op == ">=" and constraint.rhs > 0:
                return None
            if constraint.op == "<=" and constraint.rhs < 0:
                return None
    variables = _group(live, region_count, cap)
    assignment: list[int] = [0] * len(variables)
    nodes = 0

    def _feasible(depth: int) -> bool:
        """Could every constraint still be met with variables past ``depth`` free?"""
        for constraint in live:
            low = 0
            high = 0
            for i, var in enumerate(variables):
                plus = len(set(var.regions) & constraint.plus)
                minus = len(set(var.regions) & constraint.minus)
                if plus == 0 and minus == 0:
                    continue
                # Each region in the group carries the same coefficient, so the
                # group's contribution is its value times that coefficient.
                coefficient = 1 if plus else -1
                if i < depth:
                    low += coefficient * assignment[i]
                    high += coefficient * assignment[i]
                elif coefficient > 0:
                    high += var.bound
                else:
                    low -= var.bound
            if constraint.op == ">=" and high < constraint.rhs:
                return False
            if constraint.op == "<=" and low > constraint.rhs:
                return False
        return True

    def _search(depth: int) -> bool:
        nonlocal nodes
        if depth == len(variables):
            return _feasible(depth)
        for value in range(variables[depth].bound + 1):
            nodes += 1
            if nodes > MAX_SEARCH_NODES:
                raise SpaceTooLarge(
                    f"symbolic search over {len(predicates)} predicates opened "
                    f"more than {MAX_SEARCH_NODES:,} nodes — narrow the schema"
                )
            assignment[depth] = value
            if _feasible(depth + 1) and _search(depth + 1):
                return True
        assignment[depth] = 0
        return False

    if not _search(0):
        return None
    counts = [0] * region_count
    for i, var in enumerate(variables):
        remaining = assignment[i]
        for region in var.regions:
            take = min(cap, remaining)
            counts[region] = take
            remaining -= take
        # A group's bound is len(regions) * cap, so the remainder is always
        # placed; this is belt and braces.
        if remaining:  # pragma: no cover - unreachable by construction
            counts[var.regions[-1]] += remaining
    for region in zeroed:
        counts[region] = 0
    return tuple(counts)


@dataclass(frozen=True)
class SymbolicRegionSpace:
    """A region space decided by constraint solving instead of enumeration.

    Same statements, same answers, no ``models()``: four predicates make the
    count space 43 million vectors wide, and the questions an item asks of it
    ("is this entailed?", "is this consistent?") are decided in milliseconds
    without visiting one of them.

    ``max_count`` is the per-region cap the search respects, kept for the same
    reason :class:`RegionSpace` has one — it bounds the witnesses the solver may
    build, and 2 is enough for every margin ``Most`` can require.
    """

    predicates: tuple[str, ...]
    max_count: int = 2
    kind: str = "region"

    def size(self) -> int:
        """The space this decides over, reported but never enumerated."""
        return int((self.max_count + 1) ** (2 ** len(self.predicates)))

    def models(self) -> Iterator[RegionModel]:
        raise SpaceTooLarge(
            f"{self.describe()} is decided symbolically and is never enumerated"
        )

    def describe(self) -> str:
        return (
            f"region[{len(self.predicates)} predicates, "
            f"max {self.max_count} per region] decided symbolically"
        )

    def witness(
        self, statements: Sequence[Statement], *, refuting: Statement | None = None
    ) -> RegionModel | None:
        """A model of ``statements`` (and of ``¬refuting``), or None if there is none."""
        problem: list[tuple[_Conjunction, ...]] = [
            region_constraints(s, self.predicates) for s in statements
        ]
        if refuting is not None:
            problem.append(region_constraints(refuting, self.predicates, negated=True))
        combined: tuple[_Conjunction, ...] = ((),)
        for dnf in problem:
            combined = tuple((*left, *right) for left in combined for right in dnf)
        for conjunction in combined:
            counts = _solve(conjunction, self.predicates, self.max_count)
            if counts is not None:
                return RegionModel(counts=counts, predicates=self.predicates)
        return None

    def consistent(
        self, statements: Sequence[Statement], *, refuting: Statement | None = None
    ) -> bool:
        return self.witness(statements, refuting=refuting) is not None


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

    def key(self, index: int) -> int:
        """An identity for "holds in exactly these cases".

        Two candidates with the same key are the same choice written twice.
        The enumerated space can answer that exactly — the mask *is* the key.
        """
        return self.masks[index]

    @property
    def decision(self) -> str:
        return "enumerated"


@dataclass(frozen=True)
class SymbolicEvaluation:
    """The same answers for a space that is decided rather than enumerated.

    Statuses and keys are both exact: the solver decides each candidate's
    standing, and :func:`_symbolic_keys` decides sameness by mutual entailment.
    The *masks* are the approximation — a truth pattern over the witness models
    the solver happened to build, used to skip the pairs that obviously differ
    and to report a supporting-model sample where the enumerated space reports
    a census.
    """

    statuses: tuple[Status, ...]
    masks: tuple[int, ...]
    keys: tuple[int, ...]
    premise_models: int
    space_models: int

    def status_of(self, index: int) -> Status:
        return self.statuses[index]

    def supporting(self, index: int) -> int:
        """Witness models the candidate holds in — a sample, not a census."""
        return bin(self.masks[index]).count("1")

    def key(self, index: int) -> int:
        return self.keys[index]

    @property
    def decision(self) -> str:
        return "symbolic"


#: What :func:`evaluate` returns: an exact enumeration, or a solved space.
EvaluationResult = Evaluation | SymbolicEvaluation


def _evaluate_symbolic(
    space: SymbolicRegionSpace,
    premises: Sequence[Statement],
    candidates: Sequence[Statement],
) -> SymbolicEvaluation:
    """Decide each candidate with two satisfiability questions, not a census.

    ``entailed`` is "no model of the premises refutes it" and ``contradicted``
    is "no model of the premises satisfies it" — both exact. The witnesses the
    solver produces along the way are kept as a sample, so choices can still be
    compared for sameness without an enumeration to compare over.
    """
    base = space.witness(premises)
    if base is None:
        raise InconsistentPremises(
            f"premise set has no model in {space.describe()} — "
            "the schema's premises contradict each other"
        )
    statuses: list[Status] = []
    witnesses: list[RegionModel] = [base]
    for candidate in candidates:
        with_it = space.witness([*premises, candidate])
        against_it = space.witness(premises, refuting=candidate)
        if with_it is not None and with_it not in witnesses:
            witnesses.append(with_it)
        if against_it is not None and against_it not in witnesses:
            witnesses.append(against_it)
        if against_it is None:
            statuses.append("entailed")
        elif with_it is None:
            statuses.append("contradicted")
        else:
            statuses.append("contingent")
    masks = tuple(
        sum(1 << i for i, model in enumerate(witnesses) if candidate.holds(model))
        for candidate in candidates
    )
    return SymbolicEvaluation(
        statuses=tuple(statuses),
        masks=masks,
        keys=_symbolic_keys(space, premises, candidates, masks),
        premise_models=len(witnesses),
        space_models=space.size(),
    )


def _symbolic_keys(
    space: SymbolicRegionSpace,
    premises: Sequence[Statement],
    candidates: Sequence[Statement],
    masks: Sequence[int],
) -> tuple[int, ...]:
    """Exact equivalence-class ids for the candidates, cheaply.

    Two candidates are the same choice iff each entails the other given the
    premises — two solver calls to decide, and far too many pairs to ask about
    directly when the pool is sixty statements wide. So the witness masks do
    the coarse work first: candidates that differ on any witness are certainly
    different, and only those that agree everywhere are compared exactly. The
    result is the same partition the enumerated space computes with masks.
    """
    keys = [0] * len(candidates)
    buckets: dict[int, list[int]] = {}
    for index, mask in enumerate(masks):
        buckets.setdefault(mask, []).append(index)
    next_key = 0
    for members in buckets.values():
        classes: list[list[int]] = []
        for index in members:
            for group in classes:
                other = candidates[group[0]]
                one = candidates[index]
                if not space.consistent(
                    [*premises, one], refuting=other
                ) and not space.consistent([*premises, other], refuting=one):
                    group.append(index)
                    break
            else:
                classes.append([index])
        for group in classes:
            for index in group:
                keys[index] = next_key
            next_key += 1
    return tuple(keys)


def evaluate(
    space: ModelSpace,
    premises: Sequence[Statement],
    candidates: Sequence[Statement],
) -> EvaluationResult:
    """Enumerate once and record where each candidate holds.

    A :class:`SymbolicRegionSpace` is decided instead of enumerated; the result
    answers the same questions and says which way it was reached.

    Raises :class:`InconsistentPremises` for the same reason
    :func:`classify_all` does: a contradiction entails everything, so reporting
    it as a pass would certify all five choices at once.
    """
    if isinstance(space, SymbolicRegionSpace):
        return _evaluate_symbolic(space, premises, candidates)
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
    if isinstance(space, SymbolicRegionSpace):
        pool = list(candidates)
        result = _evaluate_symbolic(space, premises, pool)
        return [
            Classification(
                status=result.status_of(i),
                supporting=result.supporting(i),
                premise_models=result.premise_models,
                space_models=result.space_models,
            )
            for i in range(len(pool))
        ]
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
    if isinstance(space, SymbolicRegionSpace):
        return space.consistent(statements)
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
    if isinstance(space, SymbolicRegionSpace):
        # Mutual entailment, which is what "same in every case" means when
        # there is no enumeration to compare over.
        return not space.consistent([*premises, one], refuting=other) and not (
            space.consistent([*premises, other], refuting=one)
        )
    kept = _satisfying(space, premises)
    return all(one.holds(m) == other.holds(m) for m in kept)
