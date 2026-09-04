"""Realization — where the word-free skeleton meets the logic-free domain pack.

Spec 049 FR-8. This is the *only* module that sees both, and it is a template
fill: no inference happens here, and nothing here can change one.

The central piece is :func:`render_statement`, a single renderer that turns any
:mod:`~law_ai.lsat.synth.logic` statement into a sentence given a
:class:`Binding`. Rendering generically rather than per-schema matters for more
than brevity — it means a premise and an answer choice expressing the same form
are always worded the same way, so a learner cannot tell the credited answer
from its phrasing, which is a real distractor-craft failure in hand-authored
banks.
"""

from __future__ import annotations

import random
from collections.abc import Callable
from dataclasses import dataclass, field

from law_ai.lsat.synth.lexicon import (
    DomainPack,
    GroupSet,
    LexiconError,
    OrderingSetting,
    Property,
    Subject,
)
from law_ai.lsat.synth.logic import (
    All,
    And,
    Adjacent,
    AtLeast,
    AtSlot,
    Atom,
    Before,
    DiffGroup,
    Exactly,
    GroupSize,
    Iff,
    Immediately,
    Implies,
    InGroup,
    Most,
    No,
    NotAll,
    NotAtSlot,
    NotInGroup,
    Not,
    Or,
    SameGroup,
    Some,
    Statement,
)


@dataclass(frozen=True)
class Binding:
    """Which words stand for which abstract slots, for one item.

    Chosen once per item from the domain pack and then held fixed, so every
    sentence in the item talks about the same things.
    """

    domain_id: str
    subject: Subject
    properties: dict[str, Property] = field(default_factory=dict)
    entities: dict[str, str] = field(default_factory=dict)
    groups: dict[str, str] = field(default_factory=dict)
    ordering: OrderingSetting | None = None
    group_set: GroupSet | None = None

    def prop(self, slot: str) -> Property:
        try:
            return self.properties[slot]
        except KeyError as exc:
            raise LexiconError(f"no property bound for slot {slot!r}") from exc

    def entity(self, slot: str) -> str:
        try:
            return self.entities[slot]
        except KeyError as exc:
            raise LexiconError(f"no entity bound for slot {slot!r}") from exc

    def group(self, slot: str) -> str:
        try:
            return self.groups[slot]
        except KeyError as exc:
            raise LexiconError(f"no group bound for slot {slot!r}") from exc


def bind(
    domain: DomainPack,
    rng: random.Random,
    *,
    property_slots: tuple[str, ...] = (),
    entity_slots: tuple[str, ...] = (),
    group_slots: tuple[str, ...] = (),
    needs_ordering: bool = False,
) -> Binding:
    """Draw one item's vocabulary from a pack.

    Sampling without replacement is the point: two slots sharing a property
    would produce a premise like "if it was reviewed, then it was reviewed",
    which is valid, useless, and obviously machine-made.
    """
    if len(property_slots) > len(domain.properties):
        raise LexiconError(
            f"{domain.id} has {len(domain.properties)} properties but the schema "
            f"needs {len(property_slots)} distinct ones"
        )
    if len(entity_slots) > len(domain.entities):
        raise LexiconError(
            f"{domain.id} has {len(domain.entities)} entities but the schema "
            f"needs {len(entity_slots)}"
        )
    chosen_props = rng.sample(domain.properties, len(property_slots))
    chosen_entities = rng.sample(domain.entities, len(entity_slots))
    group_set = rng.choice(domain.groups) if group_slots else None
    if group_set is not None and len(group_slots) > len(group_set.names):
        group_set = max(domain.groups, key=lambda g: len(g.names))
        if len(group_slots) > len(group_set.names):
            raise LexiconError(
                f"{domain.id} has no group set with {len(group_slots)} names"
            )
    chosen_groups = (
        rng.sample(group_set.names, len(group_slots)) if group_set is not None else []
    )
    return Binding(
        domain_id=domain.id,
        subject=rng.choice(domain.subjects),
        properties=dict(zip(property_slots, chosen_props, strict=True)),
        entities=dict(zip(entity_slots, chosen_entities, strict=True)),
        groups=dict(zip(group_slots, chosen_groups, strict=True)),
        ordering=rng.choice(domain.orderings) if needs_ordering else None,
        group_set=group_set,
    )


# ---------------------------------------------------------------------------
# Statement rendering
# ---------------------------------------------------------------------------


def _vp(binding: Binding, slot: str, *, negated: bool, plural: bool) -> str:
    prop = binding.prop(slot)
    if negated:
        return prop.vp_negate_plural if plural else prop.vp_negate
    return prop.vp_affirm_plural if plural else prop.vp_affirm


def _literal(statement: Statement) -> tuple[str, bool]:
    """Unwrap ``Atom`` / ``Not(Atom)`` into (slot, negated)."""
    if isinstance(statement, Atom):
        return statement.name, False
    if isinstance(statement, Not) and isinstance(statement.inner, Atom):
        return statement.inner.name, True
    raise ValueError(f"not a literal: {statement!r}")


def _cap(text: str) -> str:
    return text[0].upper() + text[1:] if text else text


def _ordering(binding: Binding) -> OrderingSetting:
    if binding.ordering is None:
        raise LexiconError("statement needs an ordering setting but none is bound")
    return binding.ordering


def _group_unit(binding: Binding) -> str:
    return binding.group_set.unit if binding.group_set else "group"


def _render_propositional(  # noqa: PLR0911 — one return per statement type; this is a dispatch table
    statement: Statement, binding: Binding
) -> str | None:
    subject = binding.subject
    if isinstance(statement, Atom | Not) and _is_literal(statement):
        slot, negated = _literal(statement)
        return _cap(
            f"{subject.singular} {_vp(binding, slot, negated=negated, plural=False)}."
        )

    if isinstance(statement, Implies):
        a_slot, a_neg = _literal(statement.antecedent)
        b_slot, b_neg = _literal(statement.consequent)
        return _cap(
            f"if {subject.singular} {_vp(binding, a_slot, negated=a_neg, plural=False)}, "
            f"then it {_vp(binding, b_slot, negated=b_neg, plural=False)}."
        )

    if isinstance(statement, Iff):
        a_slot, a_neg = _literal(statement.left)
        b_slot, b_neg = _literal(statement.right)
        return _cap(
            f"{subject.singular} {_vp(binding, a_slot, negated=a_neg, plural=False)} "
            f"if and only if it {_vp(binding, b_slot, negated=b_neg, plural=False)}."
        )

    if isinstance(statement, And):
        return " ".join(render_statement(p, binding) for p in statement.parts)

    if isinstance(statement, Or):
        parts = [render_statement(p, binding).rstrip(".") for p in statement.parts]
        joined = (
            ", or ".join(parts)
            if len(parts) == 2
            else ", or ".join([", ".join(parts[:-1]), parts[-1]])
        )
        return _cap(f"either {joined}.")

    if isinstance(statement, Not):
        return _cap(
            f"it is not the case that {render_statement(statement.inner, binding).rstrip('.').lower()}."
        )

    return None


def _render_quantified(  # noqa: PLR0911 — one return per statement type; this is a dispatch table
    statement: Statement, binding: Binding
) -> str | None:
    subject = binding.subject
    if isinstance(statement, All):
        return _cap(
            f"every {subject.bare_singular} {binding.prop(statement.a).modifier} "
            f"{_vp(binding, statement.b, negated=False, plural=False)}."
        )
    if isinstance(statement, No):
        return _cap(
            f"no {subject.bare_singular} {binding.prop(statement.a).modifier} "
            f"{_vp(binding, statement.b, negated=False, plural=False)}."
        )
    if isinstance(statement, Some):
        return _cap(
            f"at least one {subject.bare_singular} {binding.prop(statement.a).modifier} "
            f"{_vp(binding, statement.b, negated=False, plural=False)}."
        )
    if isinstance(statement, NotAll):
        return _cap(
            f"not every {subject.bare_singular} {binding.prop(statement.a).modifier} "
            f"{_vp(binding, statement.b, negated=False, plural=False)}."
        )
    if isinstance(statement, Most):
        return _cap(
            f"most {subject.plural} "
            f"{binding.prop(statement.a).modifier_for(plural=True)} "
            f"{_vp(binding, statement.b, negated=False, plural=True)}."
        )
    if isinstance(statement, AtLeast):
        return _cap(
            f"at least {statement.count} {subject.plural} "
            f"{binding.prop(statement.predicate).modifier} were recorded."
        )
    if isinstance(statement, Exactly):
        return _cap(
            f"exactly {statement.count} {subject.plural} "
            f"{binding.prop(statement.predicate).modifier} were recorded."
        )

    return None


def _render_ordering(statement: Statement, binding: Binding) -> str | None:
    if isinstance(statement, Before):
        order = _ordering(binding)
        return (
            f"{binding.entity(statement.early)} {order.verb} before "
            f"{binding.entity(statement.late)}."
        )
    if isinstance(statement, Immediately):
        order = _ordering(binding)
        return (
            f"{binding.entity(statement.late)} {order.verb} in the "
            f"{order.slot_noun} immediately after {binding.entity(statement.early)}."
        )
    if isinstance(statement, Adjacent):
        order = _ordering(binding)
        return (
            f"{binding.entity(statement.one)} and {binding.entity(statement.other)} "
            f"are {_participle(order.verb)} {order.consecutive_phrase}."
        )
    if isinstance(statement, AtSlot):
        order = _ordering(binding)
        return (
            f"{binding.entity(statement.entity)} {order.verb} "
            f"{order.slot_phrase.format(n=statement.slot)}."
        )
    if isinstance(statement, NotAtSlot):
        order = _ordering(binding)
        return (
            f"{binding.entity(statement.entity)} {_negate_verb(order.verb)} "
            f"{order.slot_phrase.format(n=statement.slot)}."
        )

    return None


def _render_grouping(statement: Statement, binding: Binding) -> str | None:
    if isinstance(statement, InGroup):
        group_set = binding.group_set
        frame = group_set.frame if group_set else "is assigned to"
        return f"{binding.entity(statement.entity)} {frame} {binding.group(statement.group)}."
    if isinstance(statement, NotInGroup):
        group_set = binding.group_set
        frame = _negate_verb(group_set.frame if group_set else "is assigned to")
        return f"{binding.entity(statement.entity)} {frame} {binding.group(statement.group)}."
    if isinstance(statement, SameGroup):
        return (
            f"{binding.entity(statement.one)} and {binding.entity(statement.other)} "
            f"are placed in the same {_group_unit(binding)}."
        )
    if isinstance(statement, DiffGroup):
        return (
            f"{binding.entity(statement.one)} and {binding.entity(statement.other)} "
            f"are not placed in the same {_group_unit(binding)}."
        )
    if isinstance(statement, GroupSize):
        return (
            f"Exactly {statement.count} of them are placed in "
            f"{binding.group(statement.group)}."
        )

    return None


def render_statement(statement: Statement, binding: Binding) -> str:
    """One statement → one sentence. No inference, no schema knowledge.

    Dispatch is split by statement family rather than written as one long
    chain: the four families take different grammatical frames, and keeping
    them apart is what stops a quantifier frame from being applied to an
    ordering rule.
    """
    for render in (
        _render_propositional,
        _render_quantified,
        _render_ordering,
        _render_grouping,
    ):
        rendered = render(statement, binding)
        if rendered is not None:
            return rendered
    raise ValueError(f"no renderer for {type(statement).__name__}")  # pragma: no cover


def _is_literal(statement: Statement) -> bool:
    return isinstance(statement, Atom) or (
        isinstance(statement, Not) and isinstance(statement.inner, Atom)
    )


def _negate_verb(verb: str) -> str:
    """'is heard' → 'is not heard'; 'works' → 'does not work'."""
    words = verb.split()
    if words and words[0] in {"is", "are", "was", "were"}:
        return " ".join([words[0], "not", *words[1:]])
    return "does not " + _base_form(verb)


def _base_form(verb: str) -> str:
    words = verb.split()
    head = words[0]
    if head.endswith("ies"):
        head = head[:-3] + "y"
    elif head.endswith("sses") or head.endswith("ches") or head.endswith("shes"):
        head = head[:-2]
    elif head.endswith("s") and not head.endswith("ss"):
        head = head[:-1]
    return " ".join([head, *words[1:]])


def _participle(verb: str) -> str:
    """'is heard' → 'heard', for 'X and Y are heard on consecutive days'."""
    words = verb.split()
    if words and words[0] in {"is", "are", "was", "were"}:
        return " ".join(words[1:])
    return verb


def render_all(statements: tuple[Statement, ...], binding: Binding) -> list[str]:
    return [render_statement(s, binding) for s in statements]


# ---------------------------------------------------------------------------
# Symbolic notation (for the proof-derived solve guide)
# ---------------------------------------------------------------------------


def symbolize(statement: Statement, binding: Binding | None = None) -> str:
    """A statement's short symbolic form, for the guide's notation board.

    Abstract slots keep their letters; entities and groups use their bound names,
    because a board reading ``e1 … e2`` teaches nothing while ``Alvarez … Brennan``
    is the notation a test taker would actually write.
    """

    def name(slot: str) -> str:
        if binding is None:
            return slot
        if slot in binding.entities:
            return binding.entities[slot]
        if slot in binding.groups:
            return binding.groups[slot]
        return slot

    propositional = _symbolize_propositional(statement, binding)
    if propositional is not None:
        return propositional
    quantified = _symbolize_quantified(statement)
    if quantified is not None:
        return quantified
    game = _symbolize_game(statement, name)
    if game is not None:
        return game
    raise ValueError(f"no notation for {type(statement).__name__}")  # pragma: no cover


def _symbolize_propositional(  # noqa: PLR0911 — one return per statement type; this is a dispatch table
    statement: Statement, binding: Binding | None
) -> str | None:
    if isinstance(statement, Atom):
        return statement.name
    if isinstance(statement, Not):
        return f"¬{symbolize(statement.inner, binding)}"
    if isinstance(statement, Implies):
        return f"{symbolize(statement.antecedent, binding)} → {symbolize(statement.consequent, binding)}"
    if isinstance(statement, Iff):
        return f"{symbolize(statement.left, binding)} ↔ {symbolize(statement.right, binding)}"
    if isinstance(statement, And):
        return " ; ".join(symbolize(p, binding) for p in statement.parts)
    if isinstance(statement, Or):
        # Deliberate logic notation, not a stray letter.
        return " ∨ ".join(  # noqa: RUF001 — deliberate logic notation, not a letter
            symbolize(p, binding) for p in statement.parts
        )
    return None


def _symbolize_quantified(  # noqa: PLR0911 — one return per statement type; this is a dispatch table
    statement: Statement,
) -> str | None:
    if isinstance(statement, All):
        return f"{statement.a} → {statement.b}"
    if isinstance(statement, No):
        return f"{statement.a} → ¬{statement.b}"
    if isinstance(statement, Some):
        return f"{statement.a} ←s→ {statement.b}"
    if isinstance(statement, NotAll):
        return f"{statement.a} ←s→ ¬{statement.b}"
    if isinstance(statement, Most):
        return f"{statement.a} —m→ {statement.b}"
    if isinstance(statement, AtLeast):
        return f"|{statement.predicate}| ≥ {statement.count}"
    if isinstance(statement, Exactly):
        return f"|{statement.predicate}| = {statement.count}"
    return None


def _symbolize_game(  # noqa: PLR0911 — one return per statement type; this is a dispatch table
    statement: Statement, name: Callable[[str], str]
) -> str | None:
    if isinstance(statement, Before):
        return f"{name(statement.early)} … {name(statement.late)}"
    if isinstance(statement, Immediately):
        return f"[{name(statement.early)}{name(statement.late)}]"
    if isinstance(statement, Adjacent):
        return f"[{name(statement.one)} {name(statement.other)}]"
    if isinstance(statement, AtSlot):
        return f"{name(statement.entity)} = {statement.slot}"
    if isinstance(statement, NotAtSlot):
        return f"{name(statement.entity)} ≠ {statement.slot}"
    if isinstance(statement, InGroup):
        return f"{name(statement.entity)} ∈ {name(statement.group)}"
    if isinstance(statement, NotInGroup):
        return f"{name(statement.entity)} ∉ {name(statement.group)}"
    if isinstance(statement, SameGroup):
        return f"{name(statement.one)} = {name(statement.other)}"
    if isinstance(statement, DiffGroup):
        return f"{name(statement.one)} ≠ {name(statement.other)}"
    if isinstance(statement, GroupSize):
        return f"|{name(statement.group)}| = {statement.count}"
    return None


def legend(binding: Binding) -> list[str]:
    """``A = reviewed by the planning board`` lines for the notation board."""
    return [
        f"{slot} = {prop.modifier}" for slot, prop in sorted(binding.properties.items())
    ]


def render_arrangement(statement: Statement, binding: Binding) -> str:
    """A whole game arrangement as a list, for acceptability choices.

    An acceptability choice is a complete assignment, and reading it as five
    sentences would bury the one rule violation the item turns on.
    """
    if not isinstance(statement, And):
        return render_statement(statement, binding)
    parts = statement.parts
    if parts and all(isinstance(p, AtSlot) for p in parts):
        placements = [p for p in parts if isinstance(p, AtSlot)]
        ordered = sorted(placements, key=lambda p: p.slot)
        return ", ".join(binding.entity(p.entity) for p in ordered)
    if parts and all(isinstance(p, InGroup) for p in parts):
        # Seed every group, so an arrangement that leaves one empty says so
        # rather than silently omitting it — "none" is information a test taker
        # needs to check the rules against.
        buckets: dict[str, list[str]] = {
            binding.groups[slot]: [] for slot in sorted(binding.groups)
        }
        for p in parts:
            assert isinstance(p, InGroup)
            buckets.setdefault(binding.group(p.group), []).append(
                binding.entity(p.entity)
            )
        return "; ".join(
            f"{group}: {', '.join(members) if members else 'none'}"
            for group, members in sorted(buckets.items())
        )
    return render_statement(statement, binding)
