"""Bank size, schema, and review provenance (BL-20260429-19).

Three checks the item asks CI to keep true:

* the LR bank is past its floor and keeps growing;
* every bank item validates — five A-E choices in order, a keyed label inside
  that set, a known section and difficulty (``load_bank`` enforces this and
  raises otherwise, so simply loading the real bank is the gate);
* every item that a *machine* produced carries a review record saying what
  review it actually got. Bulk-imported factory items used to be
  indistinguishable from hand-authored ones after the fact; a "machine-judge"
  record is not editorial review and must never claim to be.
"""

from __future__ import annotations

import pytest

from law_ai.lsat.services.bank import Question, load_bank

#: The floor BL-20260429-19 set for Logical Reasoning.
_LR_FLOOR = 50

#: Items whose source names a generating system rather than a person.
_MACHINE_SOURCES = ("LSATContentFactory", "LSATContentAuthor", "LSATSynth")


def _bank_questions() -> list[Question]:
    return list(load_bank().values())


class TestBankSize:
    def test_lr_bank_is_past_its_floor(self) -> None:
        lr = [q for q in _bank_questions() if q.section == "LR"]
        assert len(lr) >= _LR_FLOOR, (
            f"LR bank has {len(lr)} items; BL-20260429-19 requires " f">= {_LR_FLOOR}"
        )


class TestBankSchema:
    def test_every_item_carries_exactly_five_labelled_choices(self) -> None:
        # load_bank() already refuses anything else; asserting here states the
        # contract in the place a reader looks for it.
        for q in _bank_questions():
            assert [c.label for c in q.choices] == ["A", "B", "C", "D", "E"]
            assert q.correct in {c.label for c in q.choices}

    def test_ids_are_unique(self) -> None:
        ids = [q.id for q in _bank_questions()]
        assert len(set(ids)) == len(ids)


class TestReviewProvenance:
    def test_machine_authored_items_declare_their_review(self) -> None:
        unreviewed = [
            q.id
            for q in _bank_questions()
            if q.source.startswith(_MACHINE_SOURCES) and q.review is None
        ]
        assert not unreviewed, (
            "machine-authored bank items with no review on record: "
            f"{unreviewed[:10]} — record how they were reviewed "
            "(BL-20260429-19)"
        )

    def test_review_records_are_well_formed(self) -> None:
        for q in _bank_questions():
            if q.review is None:
                continue
            assert q.review.method in {"editorial", "machine-judge", "proof"}
            assert q.review.reviewed_by.strip()
            assert len(q.review.reviewed_at) >= 10  # ISO date at minimum

    def test_machine_review_is_not_labelled_editorial(self) -> None:
        """An automated pass must not masquerade as a human reading the item."""
        for q in _bank_questions():
            if q.review is None or q.review.method != "editorial":
                continue
            assert (
                "judge" not in q.review.reviewed_by.lower()
            ), f"{q.id}: an adversarial judge is not editorial review"


class TestApprovalStampsEditorialReview:
    """The HITL queue is the editorial-review path for everything new."""

    def test_promotion_records_the_reviewer_on_the_item(
        self, factory_env: object
    ) -> None:
        from law_ai.lsat.services import bank as bank_mod
        from law_ai.lsat.services import proposals

        draft = {
            "section": "LR",
            "difficulty": "med",
            "stem": "A survey showed X, so the analyst concluded Y. Which one "
            "of the following, if true, most weakens the conclusion?",
            "choices": [
                {"label": label, "text": f"choice {label}"}
                for label in ("A", "B", "C", "D", "E")
            ],
            "correct": "C",
            "explanation": "C breaks the link; the others do not.",
            "concepts": [],
            "confidence": 0.7,
        }
        pid = proposals.record_proposal(
            draft, agent_trace_id="", model="test/model", confidence=0.7
        )
        promoted = proposals.promote_to_bank(
            pid, reviewer="editor@example.com", note="Read and approved."
        )

        bank_mod.load_bank.cache_clear()
        item = load_bank()[promoted["question_id"]]
        assert item.review is not None
        assert item.review.method == "editorial"
        assert item.review.reviewed_by == "editor@example.com"
        assert item.review.note == "Read and approved."

    def test_unattributed_approval_says_so(self, factory_env: object) -> None:
        from law_ai.lsat.services import bank as bank_mod
        from law_ai.lsat.services import proposals

        draft = {
            "section": "LR",
            "difficulty": "med",
            "stem": "Ferry ridership fell after tolls rose; the council blames "
            "the tolls. Which one of the following most weakens that?",
            "choices": [
                {"label": label, "text": f"opt {label}"}
                for label in ("A", "B", "C", "D", "E")
            ],
            "correct": "B",
            "explanation": "B names the confound.",
            "concepts": [],
            "confidence": 0.7,
        }
        pid = proposals.record_proposal(
            draft, agent_trace_id="", model="test/model", confidence=0.7
        )
        promoted = proposals.promote_to_bank(pid)

        bank_mod.load_bank.cache_clear()
        item = load_bank()[promoted["question_id"]]
        assert item.review is not None
        assert item.review.reviewed_by in {"anonymous", "(unattributed)"}


@pytest.mark.parametrize("section", ["LR", "RC", "LG"])
def test_every_section_has_content(section: str) -> None:
    assert [q for q in _bank_questions() if q.section == section]
