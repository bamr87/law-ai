"""Slice-2 expansion: archetypes, difficulty bands, comparative passages.

Spec 047 FR-7 / FR-8 / FR-9 and AC-7. These pin the properties that the
widened taxonomy and difficulty scale must keep — not the exact contents,
which are expected to keep growing.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from law_ai.lsat.factory.config import FactoryConfig, route_tier
from law_ai.lsat.factory.coverage import (
    DIFFICULTIES,
    _passage_traits,
    coverage_matrix,
    plan_targets,
)
from law_ai.lsat.factory.taxonomy import (
    all_archetypes,
    archetypes_for,
    by_id,
    validate_taxonomy,
)
from law_ai.lsat.services.bank import (
    DIFFICULTY_ORDER,
    PassageContext,
    load_bank,
    load_concepts,
    load_passages,
)

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# FR-7 / AC-7 — the expanded archetype registry
# ---------------------------------------------------------------------------

#: Patterns spec 047 FR-7 names as missing. Listed explicitly so deleting one
#: is a deliberate edit to this file rather than a silent regression.
REQUIRED_ARCHETYPES = (
    "lr-point-at-issue",
    "lr-role-of-claim",
    "lr-most-strongly-supported",
    "lr-cannot-be-true",
    "lr-evaluate-argument",
    "lr-complete-the-argument",
    "lr-percent-vs-number",
    "lr-sampling-flaw",
    "lr-circular-reasoning",
    "rc-comparative",
    "rc-analogous-situation",
    "rc-phrase-in-context",
    "lg-in-out-selection",
    "lg-numeric-distribution",
    "lg-max-min",
    "lg-hybrid",
    "lg-rule-substitution",
)


class TestArchetypeExpansion:
    def test_every_required_archetype_exists(self) -> None:
        missing = sorted(set(REQUIRED_ARCHETYPES) - set(by_id()))
        assert not missing, f"spec 047 FR-7 archetypes not registered: {missing}"

    def test_registry_is_internally_valid(self) -> None:
        validate_taxonomy()

    def test_new_archetype_concepts_are_in_the_catalog(self) -> None:
        catalog = set(load_concepts())
        for aid in REQUIRED_ARCHETYPES:
            unknown = sorted(set(by_id()[aid].concepts) - catalog)
            assert not unknown, f"{aid} references unknown concept(s): {unknown}"

    def test_weights_use_only_declared_bands(self) -> None:
        for arch in all_archetypes():
            outside = sorted(set(arch.difficulty_weights) - set(DIFFICULTY_ORDER))
            assert not outside, f"{arch.id} weights an unknown band: {outside}"

    def test_every_section_grew(self) -> None:
        # The pre-047 registry was LR 17 / RC 6 / LG 5.
        assert len(archetypes_for("LR")) > 17
        assert len(archetypes_for("RC")) > 6
        assert len(archetypes_for("LG")) > 5

    def test_passage_bound_archetypes_declare_it(self) -> None:
        for aid in ("rc-comparative", "lg-in-out-selection", "lg-hybrid"):
            assert by_id()[aid].requires_passage is True


# ---------------------------------------------------------------------------
# FR-8 — the widened difficulty scale
# ---------------------------------------------------------------------------


class TestDifficultyBands:
    def test_original_bands_survive_in_order(self) -> None:
        # The mapping FR-8 requires: the three original bands keep their names
        # and their relative order, so no stored item was invalidated.
        assert DIFFICULTY_ORDER.index("easy") < DIFFICULTY_ORDER.index("med")
        assert DIFFICULTY_ORDER.index("med") < DIFFICULTY_ORDER.index("hard")

    def test_scale_extends_at_both_ends(self) -> None:
        assert DIFFICULTY_ORDER[0] == "intro"
        assert DIFFICULTY_ORDER[-1] == "elite"

    def test_census_axis_covers_the_whole_scale(self) -> None:
        assert tuple(DIFFICULTIES) == DIFFICULTY_ORDER

    def test_every_band_routes_to_a_tier(self) -> None:
        for band in DIFFICULTY_ORDER:
            assert route_tier(band) in ("bulk", "standard", "premium")

    def test_new_ends_route_like_their_neighbours(self) -> None:
        assert route_tier("intro") == route_tier("easy")
        assert route_tier("elite") == route_tier("hard")

    def test_widening_did_not_inflate_existing_targets(self) -> None:
        # The budget scales with the bands an archetype declares, not with the
        # length of DIFFICULTY_ORDER — otherwise adding two bands would have
        # multiplied every pre-047 archetype's target by 5/3 overnight.
        config = FactoryConfig(target_per_cell=2)
        cells = {
            (c.archetype_id, c.difficulty): c
            for c in coverage_matrix(config)
            if c.archetype_id == "lr-weaken"
        }
        # lr-weaken declares easy/med/hard at 0.3/0.5/0.2 over a 3-band budget
        # of 6, so med wants 3 — the same as before the scale widened.
        assert cells[("lr-weaken", "med")].want == 3
        assert cells[("lr-weaken", "intro")].want == 0
        assert cells[("lr-weaken", "elite")].want == 0

    def test_bank_uses_more_than_the_original_three_bands(self) -> None:
        used = {q.difficulty for q in load_bank().values()}
        assert used - {
            "easy",
            "med",
            "hard",
        }, "the widened scale has no content — an unused band teaches nothing"


# ---------------------------------------------------------------------------
# FR-9 — comparative passages
# ---------------------------------------------------------------------------


def _comparative() -> PassageContext:
    sets = [p for p in load_passages().values() if p.is_comparative]
    assert sets, "no comparative RC set exists (spec 047 FR-9)"
    return sets[0]


class TestComparativePassages:
    def test_a_comparative_set_ships(self) -> None:
        passage = _comparative()
        assert passage.section == "RC"
        assert passage.passage and passage.passage_b
        assert passage.title_a and passage.title_b

    def test_questions_are_linked_to_it(self) -> None:
        passage = _comparative()
        linked = [q for q in load_bank().values() if q.passage_id == passage.id]
        assert len(linked) >= 3

    def test_comparative_is_a_structural_trait_not_a_word(self) -> None:
        # The planner matches on this string, so it must be derived from the
        # model rather than from prose the author happened to write.
        assert "comparative" in _passage_traits(_comparative())

    def test_single_text_passage_is_not_comparative(self) -> None:
        single = next(p for p in load_passages().values() if not p.passage_b)
        assert single.is_comparative is False
        assert "comparative" not in _passage_traits(single)

    @pytest.mark.parametrize(
        "overrides, why",
        [
            ({"section": "LG", "setup": "x"}, "passage_b outside RC"),
            ({"passage": None}, "Passage B with no Passage A"),
            ({"title_b": None}, "an unnamed second passage"),
        ],
    )
    def test_malformed_comparative_sets_are_rejected(
        self, overrides: dict[str, object], why: str
    ) -> None:
        base: dict[str, object] = {
            "id": "x-001",
            "section": "RC",
            "title": "T",
            "passage": "A text",
            "passage_b": "B text",
            "title_a": "Passage A",
            "title_b": "Passage B",
        }
        with pytest.raises(ValidationError):
            PassageContext.model_validate({**base, **overrides})

    def test_planner_will_not_write_comparative_items_against_a_single_text(
        self,
    ) -> None:
        comparative_ids = {p.id for p in load_passages().values() if p.is_comparative}
        for target in plan_targets(FactoryConfig()):
            if target.archetype_id != "rc-comparative":
                continue
            assert target.mode == "passage_set" or target.passage_id in comparative_ids
