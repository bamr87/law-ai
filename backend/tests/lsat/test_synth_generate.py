"""Schemas, realization and verification end to end (spec 049 T-011/T-020/T-021/T-022).

The property under test throughout is the spec's central claim: swapping the
domain changes every noun and cannot change an entailment.
"""

from __future__ import annotations

import random
import re

import pytest

from law_ai.lsat.services.bank import Question
from law_ai.lsat.services.guides import validate_guide_quality
from law_ai.lsat.synth.generate import (
    generate,
    generate_batch,
    sweep,
)
from law_ai.lsat.synth.lexicon import load_domains
from law_ai.lsat.synth.schemas import (
    Blueprint,
    FormalChoice,
    all_schemas,
    get_schema,
    schema_ids,
)
from law_ai.lsat.synth.verify import LabelledChoice, verify

#: Spec 049 FR-6. The floor the spec commits to, not the current count.
MIN_SCHEMAS = 12

_STOPWORDS = {
    "the",
    "a",
    "an",
    "and",
    "or",
    "if",
    "then",
    "was",
    "were",
    "is",
    "are",
    "not",
    "no",
    "every",
    "most",
    "some",
    "at",
    "least",
    "one",
    "it",
    "that",
    "which",
    "of",
    "following",
    "above",
    "statements",
    "true",
    "must",
    "also",
    "argument",
    "before",
    "in",
    "on",
    "to",
    "for",
    "by",
    "with",
    "each",
    "than",
    "this",
    "there",
    "be",
    "been",
    "has",
    "have",
    "had",
    "does",
    "do",
    "more",
    "other",
    "any",
    "all",
    "who",
    "whose",
    "its",
    "their",
    "them",
    "from",
    "into",
    "over",
    "same",
    "placed",
    "taken",
    "up",
    "could",
    "would",
    "accurate",
    "assuming",
    "depends",
    "cannot",
    "properly",
    "drawn",
    "assumed",
    "allows",
    "conclusion",
    "logically",
    "follows",
    "supported",
    "strongly",
    "inferred",
    "incompatible",
    "possibility",
    "vulnerable",
    "criticism",
    "overlooks",
    "seriously",
    "weakens",
    "strengthens",
    "calls",
    "question",
    "support",
    "provides",
    "undermines",
    "reasoning",
    "recent",
    "study",
    "found",
    "those",
    "did",
    "far",
    "often",
    "concludes",
    "produced",
    "share",
    "responsible",
    "lower",
    "last",
    "year",
    "first",
    "occurred",
    "fewer",
    "items",
    "consecutive",
    "day",
    "days",
    "week",
    "weeks",
    "position",
    "positions",
    "slot",
    "slots",
    "stop",
    "stops",
    "single",
    "per",
    "after",
    "another",
    "run",
    "five",
    "four",
    "two",
    "three",
    "six",
    "seven",
    "eight",
}


def _content_words(text: str) -> set[str]:
    return {
        w
        for w in re.findall(r"[a-z]+", text.lower())
        if len(w) > 3 and w not in _STOPWORDS
    }


class TestRegistry:
    def test_registry_meets_the_schema_floor(self) -> None:
        assert len(all_schemas()) >= MIN_SCHEMAS

    def test_schema_ids_are_unique(self) -> None:
        ids = schema_ids()
        assert len(set(ids)) == len(ids)

    def test_every_schema_names_a_real_archetype(self) -> None:
        from law_ai.lsat.factory import taxonomy

        known = set(taxonomy.by_id())
        for schema in all_schemas():
            assert schema.meta.archetype_id in known, schema.meta.id

    def test_every_schema_names_real_concepts(self) -> None:
        from law_ai.lsat.services.bank import load_concepts

        catalog = set(load_concepts())
        for schema in all_schemas():
            for concept in schema.meta.concepts:
                assert concept in catalog, f"{schema.meta.id}: {concept}"

    def test_both_proof_kinds_are_represented_and_labelled(self) -> None:
        kinds = {s.meta.proof_kind for s in all_schemas()}
        assert kinds == {"logical", "structural"}

    def test_unknown_schema_raises(self) -> None:
        with pytest.raises(Exception, match="unknown schema"):
            get_schema("no-such-schema")


class TestGeneration:
    @pytest.mark.parametrize("schema_id", schema_ids())
    def test_every_schema_generates_and_verifies(self, schema_id: str) -> None:
        schema = get_schema(schema_id)
        for domain in load_domains().values():
            if not domain.supports(schema.meta.capability):
                continue
            item = generate(schema_id, domain.id, seed=1)
            assert item.report.ok, item.report.failures
            assert item.report.proof_kind == schema.meta.proof_kind

    @pytest.mark.parametrize("schema_id", schema_ids())
    def test_output_is_a_valid_bank_question(self, schema_id: str) -> None:
        item = generate(schema_id, "municipal-policy", seed=3)
        Question.model_validate(item.question.model_dump())
        assert item.question.correct in {c.label for c in item.question.choices}
        assert [c.label for c in item.question.choices] == ["A", "B", "C", "D", "E"]

    @pytest.mark.parametrize("schema_id", schema_ids())
    def test_every_item_ships_a_valid_guide(self, schema_id: str) -> None:
        """Guide coverage cannot fall behind the bank when it is a by-product."""
        item = generate(schema_id, "field-biology", seed=4)
        assert validate_guide_quality(item.guide, item.question) == []
        assert item.guide.steps[-1].kind == "answer"
        assert item.guide.steps[-1].spoiler is True

    def test_generation_is_deterministic(self) -> None:
        first = generate("lr-necessary-assumption", "academic-publishing", seed=9)
        second = generate("lr-necessary-assumption", "academic-publishing", seed=9)
        assert first.question.model_dump() == second.question.model_dump()
        assert first.guide.model_dump() == second.guide.model_dump()

    def test_different_seeds_give_different_items(self) -> None:
        ids = {
            generate(
                "lr-conditional-chain-forward", "municipal-policy", seed=s
            ).question.id
            for s in range(6)
        }
        assert len(ids) > 1

    def test_swapping_the_domain_changes_the_words_not_the_logic(self) -> None:
        """Spec 049 G2 / AC-5, stated as an assertion."""
        one = generate("lr-quantifier-most-overlap", "municipal-policy", seed=2)
        other = generate("lr-quantifier-most-overlap", "field-biology", seed=2)
        shared = _content_words(one.question.stem) & _content_words(other.question.stem)
        assert not shared, f"domains share content words: {sorted(shared)}"
        # Same skeleton, so the same proof holds in both.
        assert one.report.premise_models == other.report.premise_models
        assert one.report.space == other.report.space

    def test_provenance_regenerates_the_item(self) -> None:
        item = generate("lg-sequencing-must-be-true", "commercial-logistics", seed=5)
        again = generate(
            item.provenance.schema_id,
            item.provenance.domain_id,
            seed=item.provenance.seed,
        )
        assert again.question.model_dump() == item.question.model_dump()

    def test_synthetic_ids_are_distinguishable_from_bank_ids(self) -> None:
        item = generate("lr-causal-weaken", "field-biology", seed=0)
        assert item.question.id.startswith("syn-")

    def test_a_domain_that_cannot_serve_a_schema_is_refused(self) -> None:
        with pytest.raises(Exception, match="unknown domain"):
            generate("lr-causal-weaken", "no-such-domain", seed=0)

    def test_batch_items_are_distinct(self) -> None:
        items = generate_batch(
            "lr-conditional-chain-forward", "municipal-policy", count=8
        )
        assert len({i.question.id for i in items}) == 8
        assert all(i.report.ok for i in items)

    def test_key_position_is_not_always_the_same(self) -> None:
        """A generator that always keyed (A) would be trivially gameable."""
        keys = {
            generate(
                "lr-conditional-chain-forward", "municipal-policy", seed=s
            ).question.correct
            for s in range(12)
        }
        assert len(keys) >= 3


#: Schemas whose premise arrangement is drawn per item (BL-20260903-15). The
#: assumption and structural schemas keep a fixed skeleton on purpose.
_DRAWN_SCHEMAS = (
    "lr-conditional-chain-forward",
    "lr-conditional-chain-contrapositive",
    "lr-quantifier-most-overlap",
    "lr-quantifier-all-some",
    "lg-sequencing-acceptability",
    "lg-sequencing-must-be-true",
    "lg-grouping-acceptability",
)


class TestArrangements:
    """One schema, many premise shapes — under the same proof."""

    @pytest.mark.parametrize("schema_id", _DRAWN_SCHEMAS)
    def test_seeds_draw_at_least_two_premise_shapes(self, schema_id: str) -> None:
        items = [generate(schema_id, "municipal-policy", seed=s) for s in range(16)]
        shapes = {tuple(sorted(i.provenance.arrangement.items())) for i in items}
        assert len(shapes) >= 2, shapes
        assert all(i.report.ok for i in items)
        # Every drawn schema records what it drew, so provenance carries the
        # shape and not only the seed that produced it.
        assert all(i.provenance.arrangement for i in items)

    @pytest.mark.parametrize(
        "schema_id",
        ("lr-conditional-chain-forward", "lr-conditional-chain-contrapositive"),
    )
    def test_chain_length_trigger_and_rule_count_all_vary(self, schema_id: str) -> None:
        seen: dict[str, set[int | str]] = {
            "chain_length": set(),
            "trigger_index": set(),
            "rule_count": set(),
        }
        for seed in range(24):
            arrangement = generate(
                schema_id, "field-biology", seed=seed
            ).provenance.arrangement
            for key, bucket in seen.items():
                bucket.add(arrangement[key])
        for key, values in seen.items():
            assert len(values) >= 2, f"{schema_id}: {key} never varied"

    def test_game_rule_counts_vary(self) -> None:
        counts = {
            generate(
                "lg-sequencing-must-be-true", "field-biology", seed=s
            ).provenance.arrangement["rule_count"]
            for s in range(16)
        }
        assert len(counts) >= 2

    def test_same_seed_draws_the_same_arrangement_in_every_domain(self) -> None:
        """The skeleton is keyed on the seed alone, so a domain swap cannot
        change the proof — that is the spec's central claim made literal."""
        arrangements = {
            tuple(
                sorted(
                    generate(
                        "lg-sequencing-must-be-true", d.id, seed=7
                    ).provenance.arrangement.items()
                )
            )
            for d in load_domains().values()
        }
        assert len(arrangements) == 1

    def test_a_sequencing_key_never_restates_a_rule(self) -> None:
        schema = get_schema("lg-sequencing-must-be-true")
        for seed in range(12):
            blueprint = schema.build(
                random.Random(seed), load_domains()["municipal-policy"]
            )
            credited = blueprint.choices[0].statement
            assert credited not in blueprint.premises

    def test_redraw_gives_up_after_the_cap(self) -> None:
        from law_ai.lsat.synth import schemas as mod

        calls = 0

        def _never(rng: random.Random) -> Blueprint:
            nonlocal calls
            calls += 1
            raise mod.SchemaError("no good")

        with pytest.raises(mod.SchemaError, match="no arrangement verified"):
            mod._draw_until(random.Random(0), _never, what="test")
        assert calls == mod.MAX_ARRANGEMENT_DRAWS

    def test_fixed_schemas_report_an_empty_arrangement(self) -> None:
        item = generate("lr-necessary-assumption", "municipal-policy", seed=1)
        assert item.provenance.arrangement == {}


class TestVerificationCatchesDefects:
    def _blueprint_with_broken_key(self) -> tuple[Blueprint, list[LabelledChoice]]:
        """Take a real skeleton and promote a distractor to credited."""
        schema = get_schema("lr-conditional-chain-forward")
        blueprint = schema.build(
            random.Random("fixed"), load_domains()["municipal-policy"]
        )
        credited = blueprint.choices[0]
        distractor = blueprint.choices[1]
        swapped = (
            FormalChoice(role="credited", statement=distractor.statement),
            FormalChoice(role="distractor", statement=credited.statement),
            *blueprint.choices[2:],
        )
        broken = Blueprint(
            family=blueprint.family,
            proof_kind=blueprint.proof_kind,
            binding_spec=blueprint.binding_spec,
            premises=blueprint.premises,
            conclusion=blueprint.conclusion,
            choices=swapped,
            space=blueprint.space,
        )
        labelled = [
            LabelledChoice(
                label=label,
                role=choice.role,
                text=f"choice {label} text goes here",
                statement=choice.statement,
            )
            for label, choice in zip("ABCDE", swapped, strict=True)
        ]
        return broken, labelled

    def test_a_mislabelled_key_fails_verification(self) -> None:
        blueprint, labelled = self._blueprint_with_broken_key()
        report = verify(blueprint, labelled, schema_id="broken")
        assert not report.ok
        failed = {c.name for c in report.failures}
        assert "credited_is_entailed" in failed or "no_other_choice_entailed" in failed

    def test_duplicate_choice_text_fails(self) -> None:
        schema = get_schema("lr-causal-weaken")
        blueprint = schema.build(
            random.Random("fixed"), load_domains()["municipal-policy"]
        )
        labelled = [
            LabelledChoice(
                label=label,
                role=choice.role,
                text="identical text here",
                statement=choice.statement,
            )
            for label, choice in zip("ABCDE", blueprint.choices, strict=True)
        ]
        report = verify(blueprint, labelled, schema_id="dupes")
        assert not report.ok
        assert "choices_distinct" in {c.name for c in report.failures}

    def test_report_states_what_was_enumerated(self) -> None:
        item = generate("lr-quantifier-most-overlap", "municipal-policy", seed=1)
        assert item.report.space_models > 0
        assert 0 < item.report.premise_models <= item.report.space_models
        assert "region" in item.report.space

    def test_structural_reports_say_so_and_check_nothing_logical(self) -> None:
        item = generate("lr-causal-weaken", "municipal-policy", seed=1)
        assert item.report.proof_kind == "structural"
        assert all(c.status == "not-checked" for c in item.report.choices)
        assert "distractors_from_inert_pool" in {c.name for c in item.report.checks}


class TestSweep:
    def test_the_whole_matrix_verifies(self) -> None:
        """Spec 049 AC-1, and the engine's own regression test."""
        result = sweep(seeds=3)
        assert result.combinations >= len(all_schemas())
        assert result.generated > 0
        assert result.ok, [f.model_dump() for f in result.failures[:5]]


class TestFourTermQuantifierChain:
    """BL-20260903-16: the schema enumeration could not afford."""

    def test_it_is_proved_symbolically(self) -> None:
        item = generate("lr-quantifier-chain-four-term", "municipal-policy", seed=0)
        assert item.report.ok
        assert item.report.proof_kind == "logical"
        assert item.report.decision == "symbolic"
        # Four predicates: the space is reported, never walked.
        assert item.report.space_models == 3 ** (2**4)
        assert "symbolically" in item.report.summary()

    def test_it_uses_four_distinct_properties(self) -> None:
        item = generate("lr-quantifier-chain-four-term", "field-biology", seed=2)
        schema = get_schema("lr-quantifier-chain-four-term")
        assert len(schema.meta.concepts) >= 2
        # Three premises plus the question sentence.
        assert item.question.stem.count(".") >= 3
        assert len(item.question.choices) == 5

    def test_the_chain_shape_is_recorded(self) -> None:
        shapes = {
            generate(
                "lr-quantifier-chain-four-term", "municipal-policy", seed=s
            ).provenance.arrangement["chain"]
            for s in range(8)
        }
        assert len(shapes) > 1

    def test_every_domain_that_supports_region_content_works(self) -> None:
        from law_ai.lsat.synth.lexicon import load_domains

        for domain in load_domains().values():
            if not domain.supports("region"):
                continue
            item = generate("lr-quantifier-chain-four-term", domain.id, seed=1)
            assert item.report.ok, (domain.id, item.report.failures)

    def test_an_assumption_family_cannot_be_proved_symbolically(self) -> None:
        """The one thing the solver is not allowed to certify, refused loudly."""
        from law_ai.lsat.synth.logic import (
            All,
            Most,
            No,
            Some,
            SymbolicRegionSpace,
            SynthLogicError,
        )
        from law_ai.lsat.synth.schemas import BindingSpec, Blueprint, FormalChoice
        from law_ai.lsat.synth.verify import LabelledChoice, verify

        slots = ("P", "Q", "R", "S")
        space = SymbolicRegionSpace(predicates=slots)
        blueprint = Blueprint(
            family="sufficient_assumption",
            proof_kind="logical",
            binding_spec=BindingSpec(property_slots=slots),
            premises=(All("P", "Q"), Most("Q", "R")),
            conclusion=Some("P", "S"),
            choices=(FormalChoice(role="credited", statement=All("Q", "S")),),
            space=space,
        )
        choices = [
            LabelledChoice(
                label=label,
                role="credited" if i == 0 else "distractor",
                text=f"choice {label} text here",
                statement=statement,
            )
            for i, (label, statement) in enumerate(
                zip(
                    ("A", "B", "C", "D", "E"),
                    (
                        All("Q", "S"),
                        All("R", "S"),
                        Some("Q", "S"),
                        Most("Q", "S"),
                        No("Q", "S"),
                    ),
                    strict=True,
                )
            )
        ]
        with pytest.raises(SynthLogicError, match="enumerated space"):
            verify(blueprint, choices, schema_id="test-symbolic-assumption")


#: Every archetype the engine can *prove* today. BL-20260903-13 grew this from
#: twelve; it is written out rather than derived so that adding or losing a
#: schema is a visible change to a test, not a silent change to coverage.
PROVABLE_ARCHETYPES = {
    "lg-acceptability",
    "lg-could-be-true-except",
    "lg-grouping",
    "lg-in-out-selection",
    "lg-local-conditional",
    "lg-must-be-true",
    "lg-numeric-distribution",
    "lr-cannot-be-true",
    "lr-conditional-inference",
    "lr-contrapositive-inference",
    "lr-most-strongly-supported",
    "lr-must-be-true",
    "lr-necessary-assumption",
    "lr-percent-vs-number",
    "lr-strengthen",
    "lr-sufficient-assumption",
    "lr-weaken",
}


class TestArchetypeCoverage:
    """BL-20260903-13: which of the taxonomy's 45 archetypes are provable."""

    def test_the_covered_set_is_exactly_the_documented_one(self) -> None:
        covered = {s.meta.archetype_id for s in all_schemas()}
        assert covered == PROVABLE_ARCHETYPES

    def test_coverage_is_a_third_of_the_taxonomy(self) -> None:
        from law_ai.lsat.factory import taxonomy

        total = len(list(taxonomy.all_archetypes()))
        assert total == 45
        assert len(PROVABLE_ARCHETYPES) >= 17

    def test_an_uncovered_archetype_is_still_refused(self) -> None:
        """The engine must not substitute something else for a miss."""
        covered = {s.meta.archetype_id for s in all_schemas()}
        assert "rc-main-point" not in covered
        assert "lr-parallel-reasoning" not in covered


class TestGamesFamilies:
    """The LG schemas added in BL-20260903-13, each proved by enumeration."""

    def test_cannot_be_true_has_exactly_one_impossible_choice(self) -> None:
        item = generate("lg-sequencing-cannot-be-true", "municipal-policy", seed=1)
        statuses = [c.status for c in item.report.choices]
        assert statuses.count("contradicted") == 1
        credited = next(
            c for c in item.report.choices if c.label == item.question.correct
        )
        assert credited.status == "contradicted"
        # Every other choice is realizable in some surviving arrangement.
        assert all(
            c.status == "contingent"
            for c in item.report.choices
            if c.label != item.question.correct
        )

    def test_a_local_supposition_lives_in_the_question(self) -> None:
        item = generate("lg-sequencing-local-conditional", "municipal-policy", seed=3)
        stimulus, question = item.question.stem.split("\n\n")
        assert question.startswith("If ")
        assert "must be true" in question
        # The supposition is a premise for the proof but not a rule on the board.
        rules = [s for s in stimulus.split(". ") if s]
        assert len(rules) >= 2
        assert question.rstrip("?").split(", which")[0][3:] not in stimulus

    def test_the_selection_item_needs_more_than_one_rule(self) -> None:
        from law_ai.lsat.synth.logic import entails

        schema = get_schema("lg-conditional-selection")
        blueprint = schema.build(
            random.Random("selection"), load_domains()["field-biology"]
        )
        credited = next(c for c in blueprint.choices if c.role.startswith("credited"))
        assert credited.statement is not None
        assert blueprint.space is not None
        for rule in blueprint.premises:
            assert not entails(blueprint.space, [rule], credited.statement)

    def test_the_numeric_item_always_draws_a_counting_rule(self) -> None:
        from law_ai.lsat.synth.logic import GroupSize

        schema = get_schema("lg-numeric-distribution")
        for seed in range(4):
            blueprint = schema.build(
                random.Random(f"numeric-{seed}"), load_domains()["municipal-policy"]
            )
            assert any(isinstance(p, GroupSize) for p in blueprint.premises)

    def test_the_supported_inference_answer_is_actually_entailed(self) -> None:
        item = generate("lr-supported-inference", "academic-publishing", seed=2)
        credited = next(
            c for c in item.report.choices if c.label == item.question.correct
        )
        assert credited.status == "entailed"
        assert "most strongly support" in item.question.stem
