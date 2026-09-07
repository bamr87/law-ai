"""Per-task LegalBench scorers (BL-20260811-11).

Spec 031 shipped one task-agnostic matcher for every subset. That floor
mis-scores two of the five tracked subsets in opposite directions:
`precedent_retrieval` marks a correctly named case wrong because the sentence
around it does not match, and `contract_nli` marks an entailment label wrong
because the key says "Yes". These tests pin the dispatch, both scorers, and
the fallback that every other subset keeps.
"""

from __future__ import annotations

import pytest

from law_ai.eval.scoring import (
    BM25,
    SCORERS,
    get_scorer,
    score_default,
    score_entailment,
    score_precedent,
    score_response,
    scorer_name,
    tokenise_case_name,
)


class TestDispatch:
    def test_registry_covers_the_two_specialised_subsets(self) -> None:
        assert set(SCORERS) == {"precedent_retrieval", "contract_nli"}

    @pytest.mark.parametrize(
        ("subset", "expected_name"),
        [
            ("precedent_retrieval", "bm25_recall@1"),
            ("contract_nli", "entailment_class"),
            ("core_reasoning", "default_match"),
            ("definitions", "default_match"),
            ("causation", "default_match"),
        ],
    )
    def test_scorer_name_per_subset(self, subset: str, expected_name: str) -> None:
        assert scorer_name(subset) == expected_name

    def test_unknown_subset_falls_back_to_the_floor(self) -> None:
        name, scorer = get_scorer("something_new")
        assert name == "default_match"
        assert scorer is score_default


class TestDefaultScorer:
    @pytest.mark.parametrize(
        ("response", "expected"),
        [
            ("True", "True"),
            ("TRUE", "true"),
            ("True, because the mailbox rule applies.", "True"),
            ("Yes.", "Yes"),
            ("The answer is False.", "False"),
        ],
    )
    def test_accepts(self, response: str, expected: str) -> None:
        assert score_default(response, expected)[0] is True

    @pytest.mark.parametrize(
        ("response", "expected"),
        [("False", "True"), ("", "True"), ("I cannot determine this.", "True")],
    )
    def test_rejects(self, response: str, expected: str) -> None:
        assert score_default(response, expected)[0] is False

    def test_unchanged_for_non_dispatched_subsets(self) -> None:
        assert score_response("The answer is True.", "True", "core_reasoning") == (
            True,
            "the answer is true.",
        )


class TestCaseNameTokenisation:
    def test_drops_corporate_noise_and_the_v(self) -> None:
        assert tokenise_case_name("International Shoe Co. v. Washington") == [
            "international",
            "shoe",
            "washington",
        ]

    def test_drops_single_letter_abbreviations(self) -> None:
        """ "R.R." splits into two one-letter tokens, which carry no signal."""
        assert tokenise_case_name("Erie R.R. Co. vs. Tompkins") == [
            "erie",
            "tompkins",
        ]


class TestBM25:
    def test_ranks_the_matching_document_first(self) -> None:
        ranker = BM25([["erie", "tompkins"], ["international", "shoe", "washington"]])
        assert ranker.rank(["shoe", "washington"])[0] == 1

    def test_scores_are_zero_when_nothing_overlaps(self) -> None:
        ranker = BM25([["erie", "tompkins"]])
        assert ranker.scores(["marbury", "madison"]) == [0.0]

    def test_empty_pool_is_survivable(self) -> None:
        assert BM25([]).scores(["anything"]) == []


class TestPrecedentScorer:
    POOL = [
        "International Shoe Co. v. Washington",
        "Erie Railroad Co. v. Tompkins",
        "Marbury v. Madison",
    ]

    def test_recall_at_1_over_the_candidate_pool(self) -> None:
        ok, _ = score_precedent(
            "The best citation is Int'l Shoe Co. v. Washington.",
            "International Shoe Co. v. Washington",
            self.POOL,
        )
        assert ok is True

    def test_naming_a_different_case_is_a_miss(self) -> None:
        ok, _ = score_precedent(
            "The best citation is Marbury v. Madison.",
            "International Shoe Co. v. Washington",
            self.POOL,
        )
        assert ok is False

    def test_no_overlap_with_the_pool_is_a_miss(self) -> None:
        ok, _ = score_precedent(
            "I am not able to answer that.",
            "International Shoe Co. v. Washington",
            self.POOL,
        )
        assert ok is False

    def test_token_recall_fallback_without_a_pool(self) -> None:
        ok, _ = score_precedent(
            "The case is International Shoe Co. v. Washington",
            "International Shoe Co. v. Washington",
        )
        assert ok is True

    def test_token_recall_fallback_rejects_a_weak_overlap(self) -> None:
        """One shared token out of three is below RECALL_THRESHOLD."""
        ok, _ = score_precedent(
            "Something about Washington, probably.",
            "International Shoe Co. v. Washington",
        )
        assert ok is False

    def test_closed_vocabulary_answers_keep_the_default_rule(self) -> None:
        """`citation_prediction_classification` answers Yes/No, not case names."""
        assert score_precedent("Yes", "Yes", self.POOL)[0] is True
        assert score_precedent("No", "Yes", self.POOL)[0] is False

    def test_empty_response_is_a_miss(self) -> None:
        assert score_precedent("", "Marbury v. Madison", self.POOL)[0] is False


class TestEntailmentScorer:
    @pytest.mark.parametrize(
        ("response", "expected"),
        [
            ("Entailment", "Yes"),
            ("Yes", "Entailment"),
            ("No", "Contradiction"),
            ("Contradiction", "No"),
            ("The answer is Yes.", "Entailment"),
            ("Neutral", "Neutral"),
        ],
    )
    def test_accepts_equivalent_labels(self, response: str, expected: str) -> None:
        assert score_entailment(response, expected)[0] is True

    @pytest.mark.parametrize(
        ("response", "expected"),
        [
            ("Contradiction", "Yes"),
            ("No", "Entailment"),
            ("Neutral", "Yes"),
            ("", "Yes"),
        ],
    )
    def test_rejects_opposite_labels(self, response: str, expected: str) -> None:
        assert score_entailment(response, expected)[0] is False

    def test_free_text_key_falls_back_to_the_default_rule(self) -> None:
        ok, _ = score_entailment("Perpetual", "Perpetual")
        assert ok is True

    def test_dispatch_reaches_it_through_score_response(self) -> None:
        assert score_response("Entailment", "Yes", "contract_nli")[0] is True
