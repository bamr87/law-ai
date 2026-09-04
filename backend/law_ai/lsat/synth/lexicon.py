"""Domain packs — the swappable surface, with no logic in it.

Spec 049 FR-5/FR-7. A domain pack supplies every English word a synthesized item
contains: what the items are about, what can be said of them, who the entities in
a game are, and the scenarios the causal and statistical families are built on.
It contains no premises, no inferences and no answer keys, so swapping packs
changes every noun in an item and cannot change a single entailment.

That separation is the spec's central claim, and it is enforced by construction:
:mod:`law_ai.lsat.synth.logic` never sees a pack, and a pack never sees a
statement.

**Why properties carry four verb-phrase forms.** Realization has to produce
"every application reviewed by the board *was filed on time*" and "most
applications reviewed by the board *were filed on time*" from the same property.
Deriving one from the other needs morphology; a package for that is a dependency
and a source of wrong-sounding output. Authoring both, plus both negations, is
mechanical, is checked at load, and makes every rendered sentence grammatical by
construction.

Adding a pack is a data change — drop a JSON file in ``data/domains/`` and it is
picked up. See ``docs/lsat-synthesis.md``.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

DATA_DIR = Path(__file__).resolve().parent / "data" / "domains"

#: A pack thinner than this cannot supply distinct vocabulary for the slots a
#: schema needs, and would start repeating nouns inside one item.
MIN_SUBJECTS = 2
MIN_PROPERTIES = 6
MIN_ENTITIES = 6


class LexiconError(ValueError):
    """A domain pack is missing something a realizer needs."""


class Subject(BaseModel):
    """What the items are about — the noun the properties attach to."""

    model_config = ConfigDict(extra="forbid")

    id: str
    singular: str = Field(description="With article: 'the zoning application'.")
    plural: str = Field(description="Bare plural: 'zoning applications'.")
    bare_singular: str = Field(
        description="No article, for quantifier frames: 'every zoning application'."
    )


class Property(BaseModel):
    """Something that can be true of a subject, in every form realization needs."""

    model_config = ConfigDict(extra="forbid")

    id: str
    vp_affirm: str = Field(description="Singular: 'was reviewed by the board'.")
    vp_affirm_plural: str = Field(description="Plural: 'were reviewed by the board'.")
    vp_negate: str = Field(description="Singular negation: 'was not reviewed …'.")
    vp_negate_plural: str = Field(description="Plural negation: 'were not reviewed …'.")
    modifier: str = Field(
        description="Restrictive modifier: 'reviewed by the board', so a frame can "
        "build 'every application reviewed by the board'."
    )
    modifier_plural: str | None = Field(
        default=None,
        description="The modifier under a plural head ('most applications …'). "
        "Only needed when it differs — a participial modifier is invariant, a "
        "relative clause ('that was sequenced') is not. Defaults to `modifier`.",
    )

    def modifier_for(self, *, plural: bool) -> str:
        if plural and self.modifier_plural:
            return self.modifier_plural
        return self.modifier


class GroupSet(BaseModel):
    """Named containers for a grouping game."""

    model_config = ConfigDict(extra="forbid")

    id: str
    unit: str = Field(description="What one container is called: 'panel'.")
    frame: str = Field(description="How the assignment reads: 'is assigned to'.")
    names: list[str] = Field(min_length=2)


class OrderingSetting(BaseModel):
    """The line a sequencing game is laid out along."""

    model_config = ConfigDict(extra="forbid")

    id: str
    frame: str = Field(
        description="How the line is laid out, with an {n} placeholder for the "
        "number of positions: 'on {n} consecutive weekdays, one per day'. "
        "Templated because the schema decides how many entities there are, and "
        "a frame hard-coding 'six' contradicts a five-entity game."
    )
    slot_noun: str = Field(description="'day'.")
    verb: str = Field(description="What the entities do: 'is scheduled'.")
    slot_phrase: str = Field(
        description="One position, with its preposition and a {n} placeholder: "
        "'on day {n}'. Authored rather than derived, so the renderer never has "
        "to guess whether a setting takes 'on' or 'in'."
    )
    consecutive_phrase: str = Field(
        description="Two adjacent positions: 'on consecutive days'."
    )


class CausalScenario(BaseModel):
    """A correlation plus the enumerated ways it can fail to be causal.

    The causal family's guarantee is *structural*: the item is built so exactly
    one enumerated attack applies and the inert facts provably do not. Authoring
    the attacks alongside the observation is what makes that guarantee real
    rather than hoped for — see :mod:`law_ai.lsat.synth.verify`.
    """

    model_config = ConfigDict(extra="forbid")

    id: str
    population: str = Field(description="'households in the county'.")
    cause_vp: str = Field(description="'installed rooftop solar'.")
    cause_np: str = Field(description="'rooftop solar installation'.")
    effect_vp: str = Field(description="'reported lower winter energy bills'.")
    effect_np: str = Field(description="'the drop in winter energy bills'.")
    alternative_cause: str = Field(
        description="A third factor that would produce the effect on its own."
    )
    reverse_causation: str = Field(
        description="Why the effect could be producing the cause."
    )
    sampling_flaw: str = Field(
        description="Why the observed group may not represent the population."
    )
    control_comparison: str = Field(
        description="A controlled comparison that rules the alternatives out — "
        "the strengthen family's credited answer."
    )
    inert_facts: list[str] = Field(
        min_length=4,
        description="On-topic facts that bear on neither direction. These become "
        "the distractors, so each must be genuinely inert.",
    )


class RatioScenario(BaseModel):
    """A rate and a base that moved independently."""

    model_config = ConfigDict(extra="forbid")

    id: str
    population: str = Field(description="'the county's licensed contractors'.")
    measure_np: str = Field(description="'permit violations'.")
    early_period: str
    late_period: str
    base_change: str = Field(
        description="What the denominator did: 'the number of licensed contractors "
        "nearly doubled over the same period'."
    )
    inert_facts: list[str] = Field(min_length=4)


class DomainPack(BaseModel):
    """One subject area's worth of vocabulary."""

    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    summary: str
    tone: str = Field(
        description="Register label, for reporting: 'civic', 'scientific'."
    )
    subjects: list[Subject] = Field(min_length=MIN_SUBJECTS)
    properties: list[Property] = Field(min_length=MIN_PROPERTIES)
    entities: list[str] = Field(min_length=MIN_ENTITIES)
    entity_noun: str = Field(
        description="What the game's entities are, in the plural: 'applicants'. "
        "The entity list is surnames, and a setup that calls them 'items' reads "
        "like a placeholder because it is one."
    )
    groups: list[GroupSet] = Field(min_length=1)
    orderings: list[OrderingSetting] = Field(min_length=1)
    causal_scenarios: list[CausalScenario] = Field(default_factory=list)
    ratio_scenarios: list[RatioScenario] = Field(default_factory=list)
    source: str = "original (CC0)"

    @model_validator(mode="after")
    def _ids_are_unique(self) -> DomainPack:
        for label, items in (
            ("subject", self.subjects),
            ("property", self.properties),
            ("group", self.groups),
            ("ordering", self.orderings),
            ("causal scenario", self.causal_scenarios),
            ("ratio scenario", self.ratio_scenarios),
        ):
            ids = [i.id for i in items]
            if len(set(ids)) != len(ids):
                raise ValueError(f"{self.id}: duplicate {label} id")
        if len(set(self.entities)) != len(self.entities):
            raise ValueError(f"{self.id}: duplicate entity name")
        return self

    def supports(self, capability: str) -> bool:
        """Whether this pack can realize a schema needing ``capability``."""
        return {
            "prop": bool(self.subjects and len(self.properties) >= 3),
            "region": bool(self.subjects and len(self.properties) >= 3),
            "order": bool(self.orderings and len(self.entities) >= MIN_ENTITIES),
            "assign": bool(self.groups and len(self.entities) >= 4),
            "causal": bool(self.causal_scenarios),
            "ratio": bool(self.ratio_scenarios),
        }.get(capability, False)


@lru_cache(maxsize=1)
def load_domains() -> dict[str, DomainPack]:
    """Load every pack under ``data/domains/``, keyed by id.

    Fails loudly on a malformed pack: a missing verb form produces ungrammatical
    items, and an item that reads wrong is as unusable as one that is wrong.
    """
    if not DATA_DIR.is_dir():
        return {}
    packs: dict[str, DomainPack] = {}
    for path in sorted(DATA_DIR.glob("*.json")):
        raw: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
        try:
            pack = DomainPack.model_validate(raw)
        except Exception as exc:
            raise LexiconError(f"domains/{path.name}: {exc}") from exc
        if pack.id != path.stem:
            raise LexiconError(
                f"domains/{path.name}: pack id {pack.id!r} does not match the file name"
            )
        packs[pack.id] = pack
    return packs


def get_domain(domain_id: str) -> DomainPack:
    packs = load_domains()
    pack = packs.get(domain_id)
    if pack is None:
        raise LexiconError(
            f"unknown domain {domain_id!r} (have: {', '.join(sorted(packs)) or 'none'})"
        )
    return pack


def reset_lexicon_cache() -> None:
    """Drop the pack cache. Tests and the polish path use this after edits."""
    load_domains.cache_clear()
