"""Action-stage deadlines: tasks, calendar, reminders (BL-20260817-02).

Spec 036 NG1 stands and is worth stating in a test file: nothing here computes
a court deadline from a rule of procedure. A due date is something the user
typed, and the only thing the system does with it is show it and remind them.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from law_ai.matters.models import Matter, MatterTask
from law_ai.matters.services.tasks import calendar_for_user, sweep_due_reminders

pytestmark = [pytest.mark.unit, pytest.mark.django_db]

NOW = datetime(2026, 9, 6, 12, 0, tzinfo=UTC)


@pytest.fixture
def owner():
    return get_user_model().objects.create_user(
        username="ada", password="pw-12345678", email="ada@example.test"
    )


@pytest.fixture
def matter(owner) -> Matter:
    return Matter.objects.create(owner=owner, slug="lease", name="Smith lease")


@pytest.fixture
def client(owner) -> APIClient:
    api = APIClient()
    api.force_authenticate(user=owner)
    return api


def _task(matter: Matter, title: str, *, days: float | None, **kw: Any) -> MatterTask:
    return MatterTask.objects.create(
        matter=matter,
        title=title,
        due_at=None if days is None else NOW + timedelta(days=days),
        **kw,
    )


class TestTaskCrud:
    def test_create_read_and_complete(self, client: APIClient, matter: Matter) -> None:
        res = client.post(
            "/api/matters/lease/tasks",
            {"title": "File answer", "due_at": "2026-10-14T17:00:00Z"},
            format="json",
        )
        assert res.status_code == 201
        task_id = res.json()["id"]
        assert res.json()["status"] == "open"

        listed = client.get("/api/matters/lease/tasks").json()["tasks"]
        assert [t["title"] for t in listed] == ["File answer"]

        done = client.patch(
            f"/api/matters/lease/tasks/{task_id}", {"status": "done"}, format="json"
        )
        assert done.status_code == 200
        assert done.json()["completed_at"] is not None

    def test_a_task_may_cite_the_artifact_that_produced_it(
        self, client: APIClient, matter: Matter
    ) -> None:
        artifact = client.post(
            "/api/matters/lease/artifacts", {"kind": "analysis"}, format="json"
        ).json()
        res = client.post(
            "/api/matters/lease/tasks",
            {"title": "Follow up", "source_artifact_id": artifact["id"]},
            format="json",
        )
        assert res.status_code == 201
        assert res.json()["source_artifact_id"] == artifact["id"]

    def test_an_artifact_from_another_matter_is_refused(
        self, client: APIClient, matter: Matter, owner
    ) -> None:
        from law_ai.matters.models import MatterArtifact

        other = Matter.objects.create(owner=owner, slug="other", name="Other")
        stray = MatterArtifact.objects.create(matter=other, kind="note")
        res = client.post(
            "/api/matters/lease/tasks",
            {"title": "x", "source_artifact_id": stray.pk},
            format="json",
        )
        assert res.status_code == 422

    def test_an_unknown_status_is_refused(
        self, client: APIClient, matter: Matter
    ) -> None:
        task = _task(matter, "x", days=1)
        res = client.patch(
            f"/api/matters/lease/tasks/{task.pk}", {"status": "vibes"}, format="json"
        )
        assert res.status_code == 422

    def test_archiving_hides_without_deleting(
        self, client: APIClient, matter: Matter
    ) -> None:
        task = _task(matter, "x", days=1)
        client.patch(
            f"/api/matters/lease/tasks/{task.pk}", {"archived": True}, format="json"
        )
        assert client.get("/api/matters/lease/tasks").json()["tasks"] == []
        assert MatterTask.objects.filter(pk=task.pk).exists()

    def test_tasks_of_another_users_matter_are_unreachable(
        self, client: APIClient
    ) -> None:
        other = get_user_model().objects.create_user(
            username="mallory", password="pw-12345678"
        )
        Matter.objects.create(owner=other, slug="theirs", name="Theirs")
        assert client.get("/api/matters/theirs/tasks").status_code == 404


class TestCalendar:
    def test_buckets_by_urgency_across_matters(self, owner, matter: Matter) -> None:
        second = Matter.objects.create(owner=owner, slug="second", name="Second")
        _task(matter, "overdue", days=-3)
        _task(matter, "later today", days=0.2)
        _task(second, "next week", days=6)
        _task(second, "far future", days=200)
        _task(second, "no date", days=None)
        _task(second, "already done", days=1, status=MatterTask.STATUS_DONE)

        cal = calendar_for_user(owner, days=30, now=NOW)
        assert [t["title"] for t in cal["overdue"]] == ["overdue"]
        assert [t["title"] for t in cal["today"]] == ["later today"]
        assert [t["title"] for t in cal["upcoming"]] == ["next week"]
        assert cal["count"] == 3
        assert cal["overdue"][0]["matter_slug"] == "lease"
        assert cal["overdue"][0]["overdue_days"] == 3.0

    def test_it_never_shows_another_users_deadlines(self, owner, matter) -> None:
        other = get_user_model().objects.create_user(
            username="mallory", password="pw-12345678"
        )
        theirs = Matter.objects.create(owner=other, slug="theirs", name="Theirs")
        _task(theirs, "their deadline", days=1)
        _task(matter, "mine", days=1)
        cal = calendar_for_user(owner, now=NOW)
        assert [t["title"] for t in cal["upcoming"] + cal["today"]] == ["mine"]

    def test_an_archived_matters_tasks_drop_out(self, owner, matter) -> None:
        _task(matter, "mine", days=1)
        matter.archived_at = NOW
        matter.save()
        assert calendar_for_user(owner, now=NOW)["count"] == 0

    def test_the_endpoint_serves_the_calendar(
        self, client: APIClient, matter: Matter
    ) -> None:
        _task(matter, "soon", days=2)
        body = client.get("/api/matters/calendar?days=7").json()
        assert body["window_days"] == 7
        assert body["count"] == 1


class TestReminders:
    def _events(self) -> tuple[list[Any], Any]:
        from law_ai.matters.services import tasks as tasks_mod

        events: list[Any] = []
        return events, patch.object(
            tasks_mod.provenance,
            "log_event",
            lambda t, p: events.append((t, p)),
        )

    def test_a_task_inside_the_lead_window_is_reminded_once(
        self, matter: Matter
    ) -> None:
        task = _task(matter, "File answer", days=0.5)
        events, patcher = self._events()
        with patcher:
            first = sweep_due_reminders(now=NOW, lead_hours=24)
            second = sweep_due_reminders(now=NOW, lead_hours=24)
        assert [r["task_id"] for r in first] == [task.pk]
        assert second == []  # idempotent
        assert [k for k, _ in events] == ["matter.task_reminder"]
        task.refresh_from_db()
        assert task.reminded_at is not None

    def test_a_task_outside_the_window_waits(self, matter: Matter) -> None:
        _task(matter, "later", days=5)
        with self._events()[1]:
            assert sweep_due_reminders(now=NOW, lead_hours=24) == []

    def test_completed_and_undated_tasks_never_remind(self, matter: Matter) -> None:
        _task(matter, "done", days=0.1, status=MatterTask.STATUS_DONE)
        _task(matter, "undated", days=None)
        with self._events()[1]:
            assert sweep_due_reminders(now=NOW, lead_hours=24) == []

    def test_rescheduling_earns_a_fresh_reminder(
        self, client: APIClient, matter: Matter
    ) -> None:
        task = _task(matter, "File answer", days=0.5)
        with self._events()[1]:
            sweep_due_reminders(now=NOW, lead_hours=24)
        client.patch(
            f"/api/matters/lease/tasks/{task.pk}",
            {"due_at": (NOW + timedelta(days=10)).isoformat()},
            format="json",
        )
        task.refresh_from_db()
        assert task.reminded_at is None

    def test_email_stays_off_unless_the_flag_is_set(
        self, matter: Matter, settings
    ) -> None:
        _task(matter, "File answer", days=0.5)
        with self._events()[1]:
            settings.MATTER_TASK_EMAIL_REMINDERS = False
            assert sweep_due_reminders(now=NOW, lead_hours=24)[0]["emailed"] is False

    def test_email_goes_out_when_enabled(self, matter: Matter, settings) -> None:
        from django.core import mail

        _task(matter, "File answer", days=0.5)
        settings.MATTER_TASK_EMAIL_REMINDERS = True
        settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
        with self._events()[1]:
            results = sweep_due_reminders(now=NOW, lead_hours=24)
        assert results[0]["emailed"] is True
        assert len(mail.outbox) == 1
        assert "File answer" in mail.outbox[0].subject

    def test_the_celery_task_summarises_the_sweep(self, matter: Matter) -> None:
        from law_ai.matters.tasks import sweep_task_reminders

        _task(matter, "File answer", days=0.5)
        with self._events()[1]:
            assert sweep_task_reminders() == {"reminded": 1, "emailed": 0}
