"""Per-learner attempt history + spaced repetition (BL-20260503-05).

The regression these lock in: ``/api/lsat/stats`` used to be an instance-wide
audit-log readout with no learner dimension and nothing to practise next. A
signed-in learner now gets their own history and a Leitner queue; an
anonymous learner must still get exactly the old numbers.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from django.conf import settings
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from law_ai.lsat.services import attempts as attempts_mod
from law_ai.lsat.services.attempts import (
    MAX_BOX,
    interval_days,
    record_attempt,
    review_queue,
    user_stats,
)

pytestmark = [pytest.mark.unit]

NOW = datetime(2026, 9, 5, 12, 0, tzinfo=UTC)


@pytest.fixture
def learner():
    return get_user_model().objects.create_user(username="lee", password="pw-123456")


@pytest.fixture(autouse=True)
def _audit_tmp(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "AUDIT_PATH", str(tmp_path / "audit.jsonl"))


def _row(
    question_id: str,
    correct: bool,
    *,
    days_ago: float = 0.0,
    section: str = "LR",
    hints: int = 0,
    concepts: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "question_id": question_id,
        "section": section,
        "difficulty": "med",
        "correct": correct,
        "hints_used": hints,
        "concepts": concepts or ["assumption"],
        "created_at": NOW - timedelta(days=days_ago),
    }


# ---------------------------------------------------------------------------
# Leitner schedule
# ---------------------------------------------------------------------------
class TestSchedule:
    def test_a_miss_is_due_immediately(self) -> None:
        assert interval_days(0) == 0

    def test_intervals_double_per_box(self) -> None:
        assert [interval_days(k) for k in (1, 2, 3, 4)] == [1, 2, 4, 8]

    def test_the_interval_is_capped(self) -> None:
        assert interval_days(99) == interval_days(MAX_BOX)

    def test_wrong_answer_is_due_now_and_labelled_missed(self) -> None:
        queue = review_queue([_row("q1", False)], now=NOW)
        assert [i["question_id"] for i in queue] == ["q1"]
        assert queue[0]["reason"] == "missed"
        assert queue[0]["streak"] == 0

    def test_a_fresh_correct_answer_is_not_due_yet(self) -> None:
        assert review_queue([_row("q1", True)], now=NOW) == []

    def test_a_correct_answer_returns_after_its_interval(self) -> None:
        assert review_queue([_row("q1", True, days_ago=0.5)], now=NOW) == []
        due = review_queue([_row("q1", True, days_ago=1.5)], now=NOW)
        assert due[0]["question_id"] == "q1"
        assert due[0]["reason"] == "spaced-review"

    def test_a_streak_pushes_the_question_further_out(self) -> None:
        rows = [
            _row("q1", True, days_ago=5),
            _row("q1", True, days_ago=4),
            _row("q1", True, days_ago=3),
        ]
        # streak 3 → 4 days, last attempt 3 days ago → not due.
        assert review_queue(rows, now=NOW) == []
        assert review_queue(rows, now=NOW + timedelta(days=2))[0]["box"] == 3

    def test_a_miss_after_a_streak_resets_the_box(self) -> None:
        rows = [
            _row("q1", True, days_ago=9),
            _row("q1", True, days_ago=8),
            _row("q1", False, days_ago=7),
        ]
        due = review_queue(rows, now=NOW)
        assert due[0]["streak"] == 0
        assert due[0]["attempts"] == 3

    def test_most_overdue_first_and_limit_applies(self) -> None:
        rows = [
            _row("q1", False, days_ago=1),
            _row("q2", False, days_ago=9),
            _row("q3", False, days_ago=4),
        ]
        queue = review_queue(rows, now=NOW)
        assert [i["question_id"] for i in queue] == ["q2", "q3", "q1"]
        assert len(review_queue(rows, now=NOW, limit=2)) == 2


# ---------------------------------------------------------------------------
# Aggregation
# ---------------------------------------------------------------------------
@pytest.mark.django_db
class TestUserStats:
    def test_empty_history_is_zeroed_not_missing(self, learner) -> None:
        body = user_stats(learner)
        assert body["attempts"] == 0
        assert body["accuracy"] == 0.0
        assert body["review_queue"] == []
        assert body["accuracy_over_time"] == []
        assert body["scope"] == "user"

    def test_counts_are_per_learner(self, learner) -> None:
        other = get_user_model().objects.create_user(
            username="mo", password="pw-1234567"
        )
        record_attempt(
            learner, question_id="q1", section="LR", correct=True, hints_used=1
        )
        record_attempt(learner, question_id="q2", section="RC", correct=False)
        for _ in range(5):
            record_attempt(other, question_id="q9", section="LR", correct=True)

        body = user_stats(learner)
        assert body["attempts"] == 2
        assert body["correct"] == 1
        assert body["accuracy"] == 0.5
        assert body["assisted"] == 1
        assert body["unassisted"] == 1
        assert body["questions_seen"] == 2
        assert set(body["by_section"]) == {"LR", "RC"}
        assert body["by_section"]["LR"]["attempts"] == 1

    def test_section_filter_narrows_totals_but_not_the_queue(self, learner) -> None:
        record_attempt(learner, question_id="q1", section="LR", correct=False)
        record_attempt(learner, question_id="q2", section="RC", correct=False)
        body = user_stats(learner, section="LR")
        assert body["attempts"] == 1
        assert {i["question_id"] for i in body["review_queue"]} == {"q1", "q2"}

    def test_accuracy_over_time_is_oldest_first(self, learner) -> None:
        for i in range(10):
            record_attempt(learner, question_id=f"q{i}", section="LR", correct=i >= 5)
        trend = user_stats(learner)["accuracy_over_time"]
        assert len(trend) >= 2
        assert trend[0]["accuracy"] <= trend[-1]["accuracy"]
        assert sum(point["attempts"] for point in trend) == 10

    def test_a_storage_failure_does_not_raise(self, learner, monkeypatch) -> None:
        class _Boom:
            @property
            def objects(self):  # pragma: no cover - attribute access raises
                raise RuntimeError("db down")

        monkeypatch.setattr(
            attempts_mod,
            "record_attempt",
            attempts_mod.record_attempt,
        )
        from law_ai.lsat import models as lsat_models

        monkeypatch.setattr(lsat_models, "LsatAttempt", _Boom())
        assert (
            record_attempt(learner, question_id="q1", section="LR", correct=True)
            is None
        )


# ---------------------------------------------------------------------------
# The endpoints
# ---------------------------------------------------------------------------
@pytest.mark.django_db
class TestStatsEndpoint:
    def test_anonymous_stats_keep_the_audit_log_reading(self) -> None:
        from law_ai.core import audit_jsonl as audit_store

        audit_store.record(
            {"type": "lsat_grade", "section": "LR", "correct": True, "hints_used": 0}
        )
        res = APIClient().get("/api/lsat/stats")
        assert res.status_code == 200
        body = res.json()
        assert body["scope"] == "instance"
        assert body["attempts"] == 1
        assert body["review_queue"] == []

    def test_signed_in_stats_are_the_learners_own(self, learner) -> None:
        from law_ai.core import audit_jsonl as audit_store

        # Instance noise the learner did not create.
        for _ in range(4):
            audit_store.record({"type": "lsat_grade", "section": "LR", "correct": True})
        record_attempt(learner, question_id="q1", section="LR", correct=False)

        client = APIClient()
        client.force_authenticate(user=learner)
        body = client.get("/api/lsat/stats").json()
        assert body["scope"] == "user"
        assert body["attempts"] == 1
        assert body["correct"] == 0
        assert [i["question_id"] for i in body["review_queue"]] == ["q1"]

    def test_grading_signed_in_persists_an_attempt(self, learner) -> None:
        from law_ai.lsat.models import LsatAttempt
        from law_ai.lsat.services.bank import load_bank

        question = next(iter(load_bank().values()))
        client = APIClient()
        client.force_authenticate(user=learner)
        res = client.post(
            "/api/lsat/grade",
            {"question_id": question.id, "choice": question.correct, "hints_used": 2},
            format="json",
        )
        assert res.status_code == 200
        row = LsatAttempt.objects.get(user=learner)
        assert row.question_id == question.id
        assert row.correct is True
        assert row.hints_used == 2
        assert row.section == question.section
        assert row.assisted is True

    def test_grading_anonymously_persists_nothing(self) -> None:
        from law_ai.lsat.models import LsatAttempt
        from law_ai.lsat.services.bank import load_bank

        question = next(iter(load_bank().values()))
        res = APIClient().post(
            "/api/lsat/grade",
            {"question_id": question.id, "choice": question.correct},
            format="json",
        )
        assert res.status_code == 200
        assert LsatAttempt.objects.count() == 0
