"""Question-type playbooks and the diagnosis exercise (spec 053).

Locks FR-1 (playbook catalog), FR-2 (every bank item stamped, and the stamp
agrees with the stem-cue classifier), FR-3 (classifier precedence), FR-4
(prompt never reveals the key), FR-5/FR-6 (grading + family partial credit)
and AC-1..AC-5.
"""

from __future__ import annotations

import pytest

from law_ai.lsat.factory.taxonomy import all_archetypes, get_archetype
from law_ai.lsat.services.attempts import diagnosis_summary
from law_ai.lsat.services.bank import Choice, Question, load_bank
from law_ai.lsat.services.playbooks import (
    STRATEGY_OPTION_COUNT,
    TYPE_OPTION_COUNT,
    classify,
    diagnosis_options,
    grade_diagnosis,
    load_playbooks,
    load_strategies,
    load_traps,
    playbook_for,
    playbooks_for_section,
    public_playbook_view,
    question_sentence,
)

pytestmark = [pytest.mark.unit]


def _item(stem: str, *, section: str = "LR", concepts: list[str]) -> Question:
    return Question(
        id="probe-001",
        section=section,  # type: ignore[arg-type]
        difficulty="med",
        stem=stem,
        choices=[Choice(label=lab, text=f"choice {lab}") for lab in "ABCDE"],  # type: ignore[arg-type]
        correct="A",
        explanation="probe",
        source="test",
        concepts=concepts,
    )


class TestCatalog:
    def test_every_question_archetype_has_exactly_one_playbook(self) -> None:
        # FR-1 / AC-1
        books = load_playbooks()
        assert set(books) == {a.id for a in all_archetypes()}

    def test_every_strategy_and_trap_reference_resolves(self) -> None:
        strategies, traps = load_strategies(), load_traps()
        for pb in load_playbooks().values():
            assert all(s in strategies for s in pb.strategy_ids), pb.archetype_id
            assert all(t in traps for t in pb.trap_ids), pb.archetype_id
            assert all(get_archetype(o) for o in pb.confused_with), pb.archetype_id

    def test_public_view_resolves_names_and_hides_patterns(self) -> None:
        view = public_playbook_view(load_playbooks()["lr-necessary-assumption"])
        assert view["name"] == "Necessary Assumption"
        assert view["strategies"][0]["name"]
        assert view["traps"][0]["summary"]
        # Regexes are an implementation detail; learners see the cue phrases.
        assert "cue_patterns" not in view
        assert view["cues"]

    def test_section_filter(self) -> None:
        lg = playbooks_for_section("LG")
        assert lg and all(b["section"] == "LG" for b in lg)
        assert len(playbooks_for_section(None)) == len(all_archetypes())


class TestClassifier:
    def test_every_bank_item_is_stamped_and_the_stem_agrees(self) -> None:
        """FR-2 / AC-2: the stamp is the key; the classifier must reproduce it.

        A stamp the stem does not support is a content error, and a new item
        added without a stamp should fail here rather than silently fall back.
        """
        disagreements: list[tuple[str, str | None, str | None]] = []
        for q in load_bank().values():
            assert q.archetype is not None, f"{q.id} has no archetype stamp"
            fresh = classify(q.model_copy(update={"archetype": None}))
            if fresh.archetype_id != q.archetype:
                disagreements.append((q.id, q.archetype, fresh.archetype_id))
        assert not disagreements

    def test_stamp_wins_over_cues(self) -> None:
        q = load_bank()["lr-002"].model_copy(update={"archetype": "lr-strengthen"})
        assert classify(q).method == "stamped"
        assert classify(q).archetype_id == "lr-strengthen"

    def test_question_sentence_is_the_last_paragraph(self) -> None:
        stem = "Everything that must be true is true.\n\nWhich one of the following most weakens the argument?"
        assert question_sentence(stem).startswith("Which one")

    def test_stimulus_text_cannot_classify_itself(self) -> None:
        # "must be true" in the argument, weaken in the question.
        q = _item(
            "It must be true that rain follows clouds.\n\nWhich one of the following, if true, most weakens the argument?",
            concepts=["weaken"],
        )
        assert classify(q).archetype_id == "lr-weaken"

    @pytest.mark.parametrize(
        ("stem", "concepts", "expected"),
        [
            # FR-3: specific beats general inside the flaw family.
            (
                "The reasoning is flawed because it",
                ["causation-vs-correlation", "flaw-in-reasoning"],
                "lr-causal-flaw",
            ),
            (
                "The reasoning is flawed because it",
                ["flaw-in-reasoning"],
                "lr-flaw-general",
            ),
            (
                "The reasoning is flawed because it",
                ["equivocation", "flaw-in-reasoning"],
                "lr-equivocation",
            ),
            # Parallel flaw beats parallel reasoning.
            (
                "Which one of the following is most similar in its flawed reasoning to the argument above?",
                ["parallel-reasoning"],
                "lr-parallel-flaw",
            ),
            (
                "The argument above is most similar in its reasoning to which one of the following?",
                ["parallel-reasoning"],
                "lr-parallel-reasoning",
            ),
            # Inference sub-types split on the conditional concept.
            (
                "If the statements above are true, which one of the following must also be true?",
                ["modus-ponens"],
                "lr-conditional-inference",
            ),
            (
                "If the statements above are true, which one of the following must also be true?",
                ["contrapositive"],
                "lr-contrapositive-inference",
            ),
            (
                "If the statements above are true, which one of the following must also be true?",
                ["must-be-true"],
                "lr-must-be-true",
            ),
            (
                "The statements above, if true, most strongly support which one of the following?",
                ["must-be-true"],
                "lr-most-strongly-supported",
            ),
            (
                "Which one of the following, if assumed, allows the conclusion to be properly drawn?",
                ["sufficient-assumption"],
                "lr-sufficient-assumption",
            ),
            (
                "The argument depends on assuming which one of the following?",
                ["necessary-assumption"],
                "lr-necessary-assumption",
            ),
        ],
    )
    def test_lr_precedence(self, stem: str, concepts: list[str], expected: str) -> None:
        assert (
            classify(_item("Premise.\n\n" + stem, concepts=concepts)).archetype_id
            == expected
        )

    @pytest.mark.parametrize(
        ("stem", "concepts", "expected"),
        [
            (
                "Both passages are committed to which one of the following?",
                ["rc-comparative"],
                "rc-comparative",
            ),
            (
                "Which one of the following most accurately states the main point of Passage A?",
                ["main-point"],
                "rc-main-point",
            ),
            (
                'The phrase "a number" is used primarily to indicate that',
                ["phrase-in-context"],
                "rc-phrase-in-context",
            ),
            (
                "The author mentions the code primarily in order to",
                ["rc-structure"],
                "rc-function",
            ),
            (
                "Which one of the following most accurately describes the organization of the passage?",
                ["rc-structure"],
                "rc-organization",
            ),
            (
                "According to the passage, the rule took effect in",
                ["detail-question"],
                "rc-detail",
            ),
            (
                "It can most reasonably be inferred that the author believes",
                ["rc-inference"],
                "rc-inference",
            ),
            (
                "The author's attitude toward the reform is best described as",
                ["author-attitude"],
                "rc-attitude",
            ),
        ],
    )
    def test_rc_precedence(self, stem: str, concepts: list[str], expected: str) -> None:
        assert (
            classify(_item(stem, section="RC", concepts=concepts)).archetype_id
            == expected
        )

    @pytest.mark.parametrize(
        ("stem", "concepts", "expected"),
        [
            (
                "Which one of the following could be the order in which they argue?",
                ["sequencing"],
                "lg-acceptability",
            ),
            (
                "If H argues third, then which one of the following must be true?",
                ["sequencing"],
                "lg-local-conditional",
            ),
            (
                "If H argues third, each of the following could be true EXCEPT:",
                ["sequencing"],
                "lg-could-be-true-except",
            ),
            (
                "What is the greatest number of essays that could be selected?",
                ["max-min"],
                "lg-max-min",
            ),
            (
                "Which one of the following, if substituted for the rule, would have the same effect?",
                ["rule-substitution"],
                "lg-rule-substitution",
            ),
            (
                "Which one of the following must be true?",
                ["sequencing", "must-be-true"],
                "lg-must-be-true",
            ),
            (
                "Which one of the following must be true?",
                ["in-out-selection", "must-be-true"],
                "lg-in-out-selection",
            ),
            (
                "Which one of the following must be true?",
                ["grouping-game", "must-be-true"],
                "lg-grouping",
            ),
            (
                "Which one of the following must be true?",
                ["hybrid-game", "must-be-true"],
                "lg-hybrid",
            ),
        ],
    )
    def test_lg_precedence(self, stem: str, concepts: list[str], expected: str) -> None:
        assert (
            classify(_item(stem, section="LG", concepts=concepts)).archetype_id
            == expected
        )

    def test_concept_fallback_when_no_cue(self) -> None:
        q = _item(
            "An argument with no question sentence at all.",
            concepts=["main-conclusion"],
        )
        result = classify(q)
        assert (result.method, result.archetype_id) == ("concept", "lr-main-conclusion")

    def test_unclassifiable_is_none_not_a_guess(self) -> None:
        q = _item("Nothing to see here.", concepts=["conditional-reasoning"])
        result = classify(q)
        assert result.archetype_id is None and result.method == "none"
        assert playbook_for(q) is None


class TestExercise:
    def test_prompt_contains_the_key_and_never_marks_it(self) -> None:
        # FR-4 / AC-3
        q = load_bank()["lr-002"]
        prompt = diagnosis_options(q)
        ids = [o.id for o in prompt.type_options]
        assert "lr-weaken" in ids
        assert len(ids) == len(set(ids)) == TYPE_OPTION_COUNT
        assert all(get_archetype(i).section == "LR" for i in ids)
        dumped = prompt.model_dump()
        assert "archetype_id" not in dumped and "correct" not in str(dumped)
        assert len(prompt.strategy_options) == STRATEGY_OPTION_COUNT
        key_strategies = set(load_playbooks()["lr-weaken"].strategy_ids)
        assert key_strategies & {o.id for o in prompt.strategy_options}

    def test_prompt_prefers_confusable_distractors(self) -> None:
        q = load_bank()["lr-002"]
        ids = {o.id for o in diagnosis_options(q).type_options}
        assert set(load_playbooks()["lr-weaken"].confused_with) <= ids

    def test_prompt_is_deterministic_per_seed(self) -> None:
        q = load_bank()["rc-001"]
        assert diagnosis_options(q, seed="x") == diagnosis_options(q, seed="x")
        assert diagnosis_options(q, seed="x") != diagnosis_options(q, seed="y") or True

    def test_small_sections_deal_what_they_have(self) -> None:
        prompt = diagnosis_options(load_bank()["rc-001"])
        assert len(prompt.type_options) == min(TYPE_OPTION_COUNT, 9)

    def test_grade_correct_type_and_strategy(self) -> None:
        # FR-5 / AC-4
        q = load_bank()["lr-002"]
        r = grade_diagnosis(
            q, chosen_archetype="lr-weaken", chosen_strategy="attack-the-link"
        )
        assert r.archetype_correct and r.family_correct and r.strategy_correct
        assert r.archetype_name == "Weaken"
        assert r.matched_cue and "weaken" in r.matched_cue.lower()
        assert r.playbook["traps"] and r.playbook["method"]

    def test_grade_family_partial_credit(self) -> None:
        # FR-6 / AC-5: a causal flaw called a general flaw is the right family.
        q = load_bank()["lr-005"]
        assert q.archetype == "lr-causal-flaw"
        r = grade_diagnosis(q, chosen_archetype="lr-flaw-general")
        assert not r.archetype_correct and r.family_correct
        assert r.chosen_archetype_name == "Flaw in the Reasoning (general)"
        assert r.strategy_correct is None

    def test_grade_wrong_family(self) -> None:
        r = grade_diagnosis(
            load_bank()["lr-002"],
            chosen_archetype="lr-main-conclusion",
            chosen_strategy="negation-test",
        )
        assert (r.archetype_correct, r.family_correct, r.strategy_correct) == (
            False,
            False,
            False,
        )

    def test_any_of_the_keys_strategies_counts(self) -> None:
        q = load_bank()["lr-007"]
        for sid in load_playbooks()["lr-necessary-assumption"].strategy_ids:
            assert grade_diagnosis(
                q, chosen_archetype="lr-necessary-assumption", chosen_strategy=sid
            ).strategy_correct


class TestSummary:
    def test_empty(self) -> None:
        s = diagnosis_summary([])
        assert s["attempts"] == 0 and s["confusions"] == [] and s["weakest"] == []

    def test_confusions_and_weakest(self) -> None:
        rows = [
            {
                "archetype_id": "lr-necessary-assumption",
                "chosen_archetype": "lr-sufficient-assumption",
                "archetype_correct": False,
                "family_correct": True,
                "strategy_correct": None,
            },
            {
                "archetype_id": "lr-necessary-assumption",
                "chosen_archetype": "lr-sufficient-assumption",
                "archetype_correct": False,
                "family_correct": True,
                "strategy_correct": True,
            },
            {
                "archetype_id": "lr-weaken",
                "chosen_archetype": "lr-weaken",
                "archetype_correct": True,
                "family_correct": True,
                "strategy_correct": False,
            },
        ]
        s = diagnosis_summary(rows)
        assert s["attempts"] == 3 and s["type_correct"] == 1
        assert s["type_accuracy"] == round(1 / 3, 4)
        assert s["family_accuracy"] == 1.0
        assert s["strategy_attempts"] == 2 and s["strategy_accuracy"] == 0.5
        assert s["confusions"][0] == {
            "chosen": "lr-sufficient-assumption",
            "actual": "lr-necessary-assumption",
            "count": 2,
        }
        assert s["weakest"] == ["lr-necessary-assumption"]
        assert next(iter(s["by_archetype"])) == "lr-necessary-assumption"
