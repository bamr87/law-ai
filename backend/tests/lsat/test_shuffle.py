"""Per-attempt shuffling and the token that reverses it (BL-20260606-01).

The unit half. The API half — serve, grade, tamper — lives beside the other
endpoint tests in ``tests/api/test_lsat.py``.
"""

from __future__ import annotations

import pytest

from law_ai.lsat.services.bank import Choice, load_bank
from law_ai.lsat.services.shuffle import (
    LABELS,
    ShuffleError,
    display_mapping,
    label_references,
    new_order,
    order_from_token,
    permute,
    remap_labels,
    to_canonical,
    to_display,
    token_for,
)

_CHOICES = [Choice(label=label, text=f"choice {label} body text") for label in LABELS]


class TestPermutation:
    def test_the_display_order_relabels_top_to_bottom(self) -> None:
        shown, _token, order = permute(_CHOICES, "q1", (2, 0, 4, 1, 3))
        assert [c.label for c in shown] == list(LABELS)
        assert [c.text for c in shown] == [_CHOICES[i].text for i in order]

    def test_canonical_and_display_are_inverses(self) -> None:
        order = (3, 1, 4, 0, 2)
        for label in LABELS:
            assert to_display(to_canonical(label, order), order) == label
            assert to_canonical(to_display(label, order), order) == label

    def test_the_mapping_moves_the_key(self) -> None:
        order = (2, 0, 4, 1, 3)
        # Stored C sits first on screen, so a learner picking A picked C.
        assert to_display("C", order) == "A"
        assert to_canonical("A", order) == "C"
        assert display_mapping(order) == {
            "C": "A",
            "A": "B",
            "E": "C",
            "B": "D",
            "D": "E",
        }

    def test_a_fresh_order_is_a_permutation(self) -> None:
        for _ in range(20):
            order = new_order(5)
            assert sorted(order) == [0, 1, 2, 3, 4]

    def test_orders_vary_across_serves(self) -> None:
        """The point of the feature: the key does not sit still."""
        positions = {to_display("C", new_order(5)) for _ in range(40)}
        assert len(positions) > 1

    def test_an_order_that_is_not_a_permutation_is_refused(self) -> None:
        with pytest.raises(ShuffleError):
            permute(_CHOICES, "q1", (0, 0, 1, 2, 3))


class TestToken:
    def test_it_round_trips(self) -> None:
        order = (4, 3, 2, 1, 0)
        assert order_from_token("q1", token_for("q1", order)) == order

    def test_it_is_bound_to_its_question(self) -> None:
        """A token replayed against another item cannot move that item's key."""
        token = token_for("q1", (1, 0, 2, 3, 4))
        with pytest.raises(ShuffleError, match="not signed"):
            order_from_token("q2", token)

    def test_a_tampered_order_is_rejected(self) -> None:
        digits, _, signature = token_for("q1", (1, 0, 2, 3, 4)).partition(".")
        with pytest.raises(ShuffleError, match="not signed"):
            order_from_token("q1", f"01234.{signature}")
        with pytest.raises(ShuffleError, match="not signed"):
            order_from_token("q1", f"{digits}.{'0' * len(signature)}")

    @pytest.mark.parametrize(
        "token", ["", "nonsense", "12345", ".", "01223.abc", "abcde.abc"]
    )
    def test_malformed_tokens_raise(self, token: str) -> None:
        with pytest.raises(ShuffleError):
            order_from_token("q1", token)


class TestLabelRemapping:
    def test_the_shapes_a_label_reference_takes(self) -> None:
        mapping = {"A": "C", "B": "A", "C": "B", "D": "E", "E": "D"}
        assert remap_labels("A is correct: the chain runs forward.", mapping) == (
            "C is correct: the chain runs forward."
        )
        assert remap_labels("(D) is the exception.", mapping) == "(E) is the exception."
        assert remap_labels("Choice B overreaches.", mapping) == "Choice A overreaches."
        assert remap_labels("B and C are both possible.", mapping) == (
            "A and B are both possible."
        )

    def test_prose_that_merely_starts_with_a_letter_is_left_alone(self) -> None:
        mapping = {"A": "E", "E": "A"}
        for text in (
            "A recent study of commuters found the opposite.",
            "A study concludes that the policy worked.",
            "Anderson signed the report.",
            "Each of the following could be true.",
        ):
            assert remap_labels(text, mapping) == text

    def test_a_swap_is_applied_once(self) -> None:
        """The bug a chain of str.replace() always has."""
        assert remap_labels("A is wrong, B is right.", {"A": "B", "B": "A"}) == (
            "B is wrong, A is right."
        )

    def test_the_identity_mapping_changes_nothing_in_the_shipped_bank(self) -> None:
        identity = {label: label for label in LABELS}
        for question in load_bank().values():
            assert remap_labels(question.explanation, identity) == question.explanation

    def test_the_bank_is_label_bound_which_is_why_this_exists(self) -> None:
        """Evidence for the remap rather than an assumption behind it."""
        bound = [q.id for q in load_bank().values() if label_references(q.explanation)]
        assert bound, "no explanation references a label — the remap is dead code"

    def test_every_reference_the_bank_makes_survives_a_round_trip(self) -> None:
        order = (2, 0, 4, 1, 3)
        forward = display_mapping(order)
        backward = {display: canonical for canonical, display in forward.items()}
        for question in load_bank().values():
            moved = remap_labels(question.explanation, forward)
            assert remap_labels(moved, backward) == question.explanation
