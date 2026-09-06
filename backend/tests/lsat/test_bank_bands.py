"""Difficulty-band coverage across the bank (BL-20260901-01).

Spec 047 FR-8 widened the scale to ``intro`` → ``elite``, and for a while the
bank held three intro items and one elite one: the bands routed correctly and
taught nothing. These tests are the floor that keeps a band from emptying
again — a band with one item cannot establish what the band means.
"""

from __future__ import annotations

import collections

from law_ai.lsat.services.bank import DIFFICULTY_ORDER, MCQ_SECTIONS, load_bank

#: Minimum items per band per section. Not a target — a regression floor.
#: Raise it when the bank grows; never lower it to make a run green.
MIN_PER_BAND = 5


def _by_section_and_band() -> dict[str, collections.Counter[str]]:
    out: dict[str, collections.Counter[str]] = collections.defaultdict(
        collections.Counter
    )
    for question in load_bank().values():
        out[question.section][question.difficulty] += 1
    return out


def test_every_section_fills_every_band() -> None:
    counts = _by_section_and_band()
    thin = {
        f"{section}/{band}": counts[section][band]
        for section in MCQ_SECTIONS
        for band in DIFFICULTY_ORDER
        if counts[section][band] < MIN_PER_BAND
    }
    assert not thin, f"bands below the floor of {MIN_PER_BAND}: {thin}"


def test_the_extreme_bands_are_not_one_item_deep() -> None:
    """The specific failure the item was filed for, stated on its own."""
    counts = _by_section_and_band()
    for band in ("intro", "elite"):
        for section in MCQ_SECTIONS:
            found = counts[section][band]
            assert found >= 2, (
                f"{section} has {found} {band} item(s); one item cannot "
                f"establish what {band} means"
            )


def test_intro_and_elite_items_carry_concept_tags() -> None:
    """A band item with no concepts cannot be routed to a learner who needs it."""
    untagged = [
        q.id
        for q in load_bank().values()
        if q.difficulty in ("intro", "elite") and not q.concepts
    ]
    assert not untagged, f"intro/elite items with no concept tags: {untagged}"


def test_every_band_is_spread_over_more_than_one_concept() -> None:
    """A band taught by a single concept is a band that teaches one pattern."""
    by_band: dict[str, set[str]] = collections.defaultdict(set)
    for question in load_bank().values():
        by_band[question.difficulty].update(question.concepts)
    for band in ("intro", "elite"):
        assert (
            len(by_band[band]) >= 5
        ), f"the {band} band draws on only {sorted(by_band[band])}"
