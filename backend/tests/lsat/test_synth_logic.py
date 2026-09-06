"""The proof engine and the domain packs (spec 049 T-001/T-002/T-010).

These are the tests that matter most: everything downstream inherits its
correctness from the checker, so the checker is tested against hand-worked
entailments rather than against itself.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from law_ai.lsat.synth import lexicon as lex
from law_ai.lsat.synth.logic import (
    Adjacent,
    All,
    And,
    AssignSpace,
    AtLeast,
    AtSlot,
    Atom,
    Before,
    DiffGroup,
    Exactly,
    Implies,
    InGroup,
    InconsistentPremises,
    Most,
    No,
    Not,
    NotAll,
    NotAtSlot,
    OrderSpace,
    PropSpace,
    RegionSpace,
    SameGroup,
    Some,
    SpaceTooLarge,
    SymbolicRegionSpace,
    classify,
    classify_all,
    entails,
    equivalent,
    evaluate,
    satisfiable,
)


class TestPropSpace:
    def test_enumerates_every_assignment(self) -> None:
        space = PropSpace(atoms=("P", "Q", "R"))
        assert space.size() == 8
        assert len(list(space.models())) == 8

    def test_modus_ponens(self) -> None:
        space = PropSpace(atoms=("P", "Q"))
        premises = [Implies(Atom("P"), Atom("Q")), Atom("P")]
        assert entails(space, premises, Atom("Q"))

    def test_modus_tollens(self) -> None:
        space = PropSpace(atoms=("P", "Q"))
        premises = [Implies(Atom("P"), Atom("Q")), Not(Atom("Q"))]
        assert entails(space, premises, Not(Atom("P")))

    def test_affirming_the_consequent_is_not_entailed(self) -> None:
        """The invalid move the exam tests constantly must come back contingent."""
        space = PropSpace(atoms=("P", "Q"))
        premises = [Implies(Atom("P"), Atom("Q")), Atom("Q")]
        assert classify(space, premises, Atom("P")).status == "contingent"

    def test_denying_the_antecedent_is_not_entailed(self) -> None:
        space = PropSpace(atoms=("P", "Q"))
        premises = [Implies(Atom("P"), Atom("Q")), Not(Atom("P"))]
        assert classify(space, premises, Not(Atom("Q"))).status == "contingent"

    def test_chained_conditionals(self) -> None:
        space = PropSpace(atoms=("P", "Q", "R"))
        premises = [
            Implies(Atom("P"), Atom("Q")),
            Implies(Atom("Q"), Atom("R")),
            Not(Atom("R")),
        ]
        assert entails(space, premises, Not(Atom("P")))
        assert classify(space, premises, Atom("P")).status == "contradicted"


class TestRegionSpace:
    def test_most_plus_most_yields_some(self) -> None:
        """The exam's favourite overlap inference."""
        space = RegionSpace(predicates=("P", "Q", "R"))
        premises = [Most("P", "Q"), Most("P", "R")]
        assert entails(space, premises, Some("Q", "R"))

    def test_most_plus_most_does_not_yield_most(self) -> None:
        """And its characteristic trap: the overlap is only 'at least one'."""
        space = RegionSpace(predicates=("P", "Q", "R"))
        premises = [Most("P", "Q"), Most("P", "R")]
        assert classify(space, premises, Most("Q", "R")).status == "contingent"

    def test_all_chains(self) -> None:
        space = RegionSpace(predicates=("P", "Q", "R"))
        assert entails(space, [All("P", "Q"), All("Q", "R")], All("P", "R"))

    def test_all_does_not_reverse(self) -> None:
        space = RegionSpace(predicates=("P", "Q", "R"))
        assert classify(space, [All("P", "Q")], All("Q", "P")).status == "contingent"

    def test_all_plus_some_combines(self) -> None:
        space = RegionSpace(predicates=("P", "Q", "R"))
        assert entails(space, [All("P", "Q"), Some("P", "R")], Some("Q", "R"))

    def test_some_is_symmetric(self) -> None:
        space = RegionSpace(predicates=("P", "Q"))
        assert entails(space, [Some("P", "Q")], Some("Q", "P"))

    def test_no_is_symmetric(self) -> None:
        space = RegionSpace(predicates=("P", "Q"))
        assert entails(space, [No("P", "Q")], No("Q", "P"))

    def test_most_of_an_empty_group_is_false(self) -> None:
        """ "Most A are B" asserts there are As — the exam's reading."""
        space = RegionSpace(predicates=("P", "Q"))
        assert classify(space, [No("P", "P")], Most("P", "Q")).status == "contradicted"

    def test_space_bound_is_enforced(self) -> None:
        space = RegionSpace(predicates=("A", "B", "C", "D", "E"), max_count=3)
        with pytest.raises(SpaceTooLarge):
            satisfiable(space, [])


class TestOrderSpace:
    def test_permutations(self) -> None:
        space = OrderSpace(entities=("a", "b", "c"))
        assert space.size() == 6
        assert len(list(space.models())) == 6

    def test_transitivity_of_before(self) -> None:
        space = OrderSpace(entities=("a", "b", "c"))
        assert entails(space, [Before("a", "b"), Before("b", "c")], Before("a", "c"))

    def test_before_pins_the_ends(self) -> None:
        space = OrderSpace(entities=("a", "b", "c"))
        premises = [Before("a", "b"), Before("b", "c")]
        assert entails(space, premises, AtSlot("a", 1))
        assert entails(space, premises, AtSlot("c", 3))

    def test_adjacency_and_exclusion(self) -> None:
        space = OrderSpace(entities=("a", "b", "c"))
        assert (
            classify(space, [Adjacent("a", "b")], AtSlot("c", 2)).status
            == "contradicted"
        )
        assert entails(space, [NotAtSlot("a", 1), NotAtSlot("a", 2)], AtSlot("a", 3))


class TestAssignSpace:
    def test_enumerates_every_function(self) -> None:
        space = AssignSpace(entities=("a", "b"), groups=("g1", "g2"))
        assert space.size() == 4

    def test_same_and_different_group(self) -> None:
        space = AssignSpace(entities=("a", "b", "c"), groups=("g1", "g2"))
        premises = [InGroup("a", "g1"), DiffGroup("a", "b")]
        assert entails(space, premises, InGroup("b", "g2"))
        assert entails(
            space, [SameGroup("a", "b"), InGroup("a", "g1")], InGroup("b", "g1")
        )


class TestEntailment:
    def test_inconsistent_premises_raise_rather_than_pass(self) -> None:
        """A contradiction entails everything; reporting that as a pass would
        certify all five choices of an item at once."""
        space = PropSpace(atoms=("P",))
        with pytest.raises(InconsistentPremises):
            classify(space, [Atom("P"), Not(Atom("P"))], Atom("P"))

    def test_classification_counts_are_reported(self) -> None:
        space = PropSpace(atoms=("P", "Q"))
        result = classify(space, [Atom("P")], Atom("Q"))
        assert result.space_models == 4
        assert result.premise_models == 2
        assert result.supporting == 1
        assert result.status == "contingent"

    def test_evaluate_masks_agree_with_classify(self) -> None:
        space = PropSpace(atoms=("P", "Q"))
        premises = [Implies(Atom("P"), Atom("Q"))]
        candidates = [Atom("Q"), Not(Atom("P")), Implies(Atom("P"), Atom("Q"))]
        result = evaluate(space, premises, candidates)
        for i, candidate in enumerate(candidates):
            assert result.status_of(i) == classify(space, premises, candidate).status

    def test_equivalent_candidates_share_a_mask(self) -> None:
        space = PropSpace(atoms=("P", "Q"))
        result = evaluate(space, [Atom("P")], [Atom("Q"), And((Atom("P"), Atom("Q")))])
        assert result.masks[0] == result.masks[1]


class TestDomainPacks:
    def test_every_shipped_pack_loads(self) -> None:
        packs = lex.load_domains()
        assert len(packs) >= 4
        for pack in packs.values():
            assert pack.source == "original (CC0)"

    def test_every_pack_supports_every_capability(self) -> None:
        for pack in lex.load_domains().values():
            for capability in ("prop", "region", "order", "assign", "causal", "ratio"):
                assert pack.supports(capability), f"{pack.id} lacks {capability}"

    def test_properties_carry_every_form_the_realizer_needs(self) -> None:
        for pack in lex.load_domains().values():
            for prop in pack.properties:
                assert prop.vp_affirm and prop.vp_affirm_plural
                assert prop.vp_negate and prop.vp_negate_plural
                assert prop.modifier
                assert prop.modifier_for(plural=True)

    def test_ordering_frames_are_templated_on_the_entity_count(self) -> None:
        """A frame hard-coding 'six' contradicts a five-entity game."""
        for pack in lex.load_domains().values():
            for ordering in pack.orderings:
                assert "{n}" in ordering.frame, f"{pack.id}/{ordering.id}"
                assert "{n}" in ordering.slot_phrase

    def test_causal_scenarios_carry_all_three_attacks_and_a_control(self) -> None:
        for pack in lex.load_domains().values():
            for scenario in pack.causal_scenarios:
                assert scenario.alternative_cause
                assert scenario.reverse_causation
                assert scenario.sampling_flaw
                assert scenario.control_comparison
                assert len(scenario.inert_facts) >= 4

    def test_inert_facts_never_restate_an_attack(self) -> None:
        """The structural guarantee is exactly this disjointness."""
        for pack in lex.load_domains().values():
            for scenario in pack.causal_scenarios:
                attacks = {
                    scenario.alternative_cause,
                    scenario.reverse_causation,
                    scenario.sampling_flaw,
                    scenario.control_comparison,
                }
                assert not (attacks & set(scenario.inert_facts)), scenario.id

    def test_incomplete_pack_fails_to_load(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        sandbox = tmp_path / "domains"
        sandbox.mkdir()
        (sandbox / "broken.json").write_text(
            json.dumps({"id": "broken", "name": "Broken", "summary": "x", "tone": "x"}),
            encoding="utf-8",
        )
        monkeypatch.setattr(lex, "DATA_DIR", sandbox)
        lex.reset_lexicon_cache()
        with pytest.raises(lex.LexiconError, match=r"broken\.json"):
            lex.load_domains()
        lex.reset_lexicon_cache()

    def test_pack_id_must_match_its_file_name(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        real = lex.load_domains()["municipal-policy"]
        sandbox = tmp_path / "domains"
        sandbox.mkdir()
        (sandbox / "renamed.json").write_text(real.model_dump_json(), encoding="utf-8")
        monkeypatch.setattr(lex, "DATA_DIR", sandbox)
        lex.reset_lexicon_cache()
        with pytest.raises(lex.LexiconError, match="does not match the file name"):
            lex.load_domains()
        lex.reset_lexicon_cache()


class TestSymbolicRegionSpace:
    """BL-20260903-16: four predicates, decided instead of enumerated.

    The soundness claim is the whole point, so it is tested where both answers
    exist — every K <= 3 case, where the enumerated space can be asked the same
    question — and only then applied where enumeration cannot go.
    """

    @staticmethod
    def _pool(slots: tuple[str, ...]) -> list[object]:
        pool: list[object] = []
        for a in slots:
            for b in slots:
                if a == b:
                    continue
                pool.extend([All(a, b), No(a, b), Some(a, b), NotAll(a, b), Most(a, b)])
        for a in slots:
            pool.extend([AtLeast(a, 1), AtLeast(a, 2), Exactly(a, 1)])
        return pool

    def test_it_agrees_with_enumeration_on_every_three_term_case(self) -> None:
        """The cross-check: same premises, same pool, same status, every time."""
        import itertools

        slots = ("P", "Q", "R")
        enumerated = RegionSpace(predicates=slots)
        symbolic = SymbolicRegionSpace(predicates=slots)
        pool = self._pool(slots)
        premise_sets = [
            [pool[i], pool[j]]
            for i, j in itertools.islice(
                itertools.combinations(range(len(pool)), 2), 0, 300, 8
            )
        ]
        compared = 0
        for premises in premise_sets:
            try:
                expected = classify_all(enumerated, premises, pool)
            except InconsistentPremises:
                assert not satisfiable(symbolic, premises)
                continue
            actual = classify_all(symbolic, premises, pool)
            for candidate, one, other in zip(pool, expected, actual, strict=True):
                compared += 1
                assert one.status == other.status, (premises, candidate)
        assert compared > 1000

    def test_equivalence_agrees_with_enumeration(self) -> None:
        slots = ("P", "Q", "R")
        enumerated = RegionSpace(predicates=slots)
        symbolic = SymbolicRegionSpace(predicates=slots)
        premises = [All("P", "Q"), Some("P", "R")]
        pairs = [
            (Some("Q", "R"), Some("R", "Q")),
            (All("P", "Q"), Most("P", "Q")),
            (No("P", "Q"), All("P", "Q")),
        ]
        for one, other in pairs:
            assert equivalent(symbolic, premises, one, other) == equivalent(
                enumerated, premises, one, other
            )

    def test_a_four_term_chain_is_decided(self) -> None:
        """What enumeration could not reach: 43 million count vectors."""
        space = SymbolicRegionSpace(predicates=("P", "Q", "R", "S"))
        premises = [All("P", "Q"), Most("Q", "R"), All("R", "S")]
        # Most Q are R and every R is S, so most Q are S.
        assert entails(space, premises, Most("Q", "S"))
        assert entails(space, premises, Some("Q", "S"))
        # But nothing forces a majority of P, whose only link is upward.
        assert not entails(space, premises, Most("P", "S"))
        assert not entails(space, premises, All("Q", "S"))

    def test_two_majorities_meet_only_as_some(self) -> None:
        space = SymbolicRegionSpace(predicates=("P", "Q", "R", "S"))
        premises = [Most("P", "Q"), Most("P", "R"), All("R", "S")]
        assert entails(space, premises, Some("Q", "S"))
        assert not entails(space, premises, Most("Q", "S"))

    def test_inconsistent_premises_still_raise(self) -> None:
        space = SymbolicRegionSpace(predicates=("P", "Q", "R", "S"))
        with pytest.raises(InconsistentPremises):
            classify_all(space, [Some("P", "Q"), No("P", "Q")], [All("P", "Q")])

    def test_it_never_enumerates(self) -> None:
        space = SymbolicRegionSpace(predicates=("P", "Q", "R", "S"))
        assert space.size() == 3 ** (2**4)
        assert "symbolically" in space.describe()
        with pytest.raises(SpaceTooLarge):
            next(space.models())

    def test_it_refuses_statements_it_cannot_compile(self) -> None:
        from law_ai.lsat.synth.logic import UndecidableStatement

        space = SymbolicRegionSpace(predicates=("P", "Q", "R", "S"))
        with pytest.raises(UndecidableStatement):
            satisfiable(space, [Atom("P")])
