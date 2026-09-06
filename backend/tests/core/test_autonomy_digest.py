"""Tests for ``law_ai.core.autonomy.compose_digest`` (spec 018 T-010)."""

from __future__ import annotations

import contextlib
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from django.conf import settings

from law_ai.core import autonomy

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_ANCHOR = datetime(2026, 5, 11, 7, 0, 0, tzinfo=UTC)
_DATE_LABEL = "2026-05-11"  # window_end = midnight 2026-05-11 UTC


def _mock_queryset(rows: list[dict[str, Any]]) -> MagicMock:
    """Return a mock that quacks like a Django queryset for our query."""
    objs: list[MagicMock] = []
    for r in rows:
        m = MagicMock()
        m.kind = r["kind"]
        m.payload = r.get("payload", {})
        objs.append(m)
    qs = MagicMock()
    qs.filter.return_value = qs
    qs.order_by.return_value = iter(objs)
    return qs


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestComposeDigestEmpty:
    """Digest renders correctly when no audit rows exist."""

    def test_file_created_with_four_headers(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(settings, "AUTONOMY_DIGEST_DIR", str(tmp_path))

        with (
            patch("law_ai.audit.models.AuditEvent") as mock_model,
            patch("law_ai.core.autonomy._persist"),
        ):
            mock_model.objects = _mock_queryset([])
            path = autonomy.compose_digest(date=_ANCHOR)

        assert path == tmp_path / f"digest-{_DATE_LABEL}.md"
        text = path.read_text()
        assert "## PRs Opened" in text
        assert "## BACKLOG Items Appended" in text
        assert "## Docs Quarantined" in text
        assert "## LegalBench Delta" in text

    def test_empty_sections_show_none_marker(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(settings, "AUTONOMY_DIGEST_DIR", str(tmp_path))

        with (
            patch("law_ai.audit.models.AuditEvent") as mock_model,
            patch("law_ai.core.autonomy._persist"),
        ):
            mock_model.objects = _mock_queryset([])
            path = autonomy.compose_digest(date=_ANCHOR)

        text = path.read_text()
        assert "*(none)*" in text


class TestComposeDigestWithRows:
    """Digest aggregates seeded AuditEvent rows correctly."""

    def test_pr_url_appears_in_digest(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(settings, "AUTONOMY_DIGEST_DIR", str(tmp_path))

        rows = [
            {
                "kind": "autonomy_pr_opened",
                "payload": {"url": "https://github.com/bamr87/law-ai/pull/42"},
            },
            {
                "kind": "autonomy_backlog_appended",
                "payload": {"bl_id": "BL-20260511-22"},
            },
            {
                "kind": "autonomy_doc_quarantined",
                "payload": {"source_url": "https://example.com/case.pdf"},
            },
            {
                "kind": "autonomy_legalbench_delta",
                "payload": {"task": "core_reasoning", "delta": 0.03},
            },
        ]

        with (
            patch("law_ai.audit.models.AuditEvent") as mock_model,
            patch("law_ai.core.autonomy._persist"),
        ):
            mock_model.objects = _mock_queryset(rows)
            path = autonomy.compose_digest(date=_ANCHOR)

        text = path.read_text()
        assert "https://github.com/bamr87/law-ai/pull/42" in text
        assert "BL-20260511-22" in text
        assert "https://example.com/case.pdf" in text
        assert "core_reasoning" in text

    def test_provenance_event_emitted(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(settings, "AUTONOMY_DIGEST_DIR", str(tmp_path))
        captured: list[dict[str, Any]] = []

        with (
            patch("law_ai.audit.models.AuditEvent") as mock_model,
            patch("law_ai.core.autonomy._persist", side_effect=captured.append),
        ):
            mock_model.objects = _mock_queryset([])
            autonomy.compose_digest(date=_ANCHOR)

        assert len(captured) == 1
        event = captured[0]
        assert event["type"] == "autonomy_digest.composed"
        assert event["date_label"] == _DATE_LABEL


class TestComposeDigestDbFailure:
    """Digest survives a DB error and writes a partial file."""

    def test_writes_file_even_on_db_error(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(settings, "AUTONOMY_DIGEST_DIR", str(tmp_path))

        with (
            patch("law_ai.core.autonomy._persist"),
            patch(
                "law_ai.audit.models.AuditEvent",
                side_effect=Exception("db down"),
            ),
        ):
            path = autonomy.compose_digest(date=_ANCHOR)

        assert path.exists()
        text = path.read_text()
        # All four headers must still be present
        for header in (
            "## PRs Opened",
            "## BACKLOG Items Appended",
            "## Docs Quarantined",
            "## LegalBench Delta",
        ):
            assert header in text


class TestRunDigestIntegration:
    """_run_digest stub wires correctly to compose_digest."""

    def test_run_digest_returns_digest_path(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(settings, "AUTONOMY_DIGEST_DIR", str(tmp_path))
        from law_ai.core.management.commands.run_autonomy import _run_digest

        context: dict[str, Any] = {}
        with (
            patch("law_ai.audit.models.AuditEvent") as mock_model,
            patch("law_ai.core.autonomy._persist"),
        ):
            mock_model.objects = _mock_queryset([])
            result = _run_digest(context)

        assert "digest_path" in result
        assert Path(result["digest_path"]).exists()
        assert context["digest_path"] == result["digest_path"]


class TestComposeDigestRaiseOnDbError:
    """BL-20260511-23: the retrying task needs the DB error to escape."""

    def test_default_still_degrades_to_a_file(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(settings, "AUTONOMY_DIGEST_DIR", str(tmp_path))
        qs = MagicMock()
        qs.filter.return_value = qs
        qs.order_by.side_effect = RuntimeError("db down")

        with (
            patch("law_ai.core.autonomy._persist"),
            patch("law_ai.audit.models.AuditEvent") as mock_model,
        ):
            mock_model.objects = qs
            path = autonomy.compose_digest(date=_ANCHOR)

        assert path.exists()
        assert "Error querying audit log" in path.read_text()

    def test_flag_propagates_the_error_and_writes_nothing(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from django.db import OperationalError

        monkeypatch.setattr(settings, "AUTONOMY_DIGEST_DIR", str(tmp_path))
        qs = MagicMock()
        qs.filter.return_value = qs
        qs.order_by.side_effect = OperationalError("connection closed")

        with (
            patch("law_ai.core.autonomy._persist"),
            patch("law_ai.audit.models.AuditEvent") as mock_model,
            pytest.raises(OperationalError, match="connection closed"),
        ):
            mock_model.objects = qs
            autonomy.compose_digest(date=_ANCHOR, raise_on_db_error=True)

        # No half-written digest is left behind for an operator to trust.
        assert not (tmp_path / f"digest-{_DATE_LABEL}.md").exists()


class TestComposeDigestTask:
    """BL-20260511-23: the retrying Celery task + its AuditEvent payload."""

    def test_task_is_registered_with_retry_policy(self) -> None:
        from django.db import InterfaceError, OperationalError

        from law_ai.celery import app
        import law_ai.core.tasks  # noqa: F401  (registers the task)

        task = app.tasks["law_ai.core.tasks.compose_digest_task"]
        assert task.max_retries == 3
        assert set(task.autoretry_for) == {OperationalError, InterfaceError}
        assert task.retry_backoff is True
        assert task.retry_jitter is True

    def test_beat_entry_uses_the_retrying_task(self) -> None:
        from law_ai.celery import app

        entry = app.conf.beat_schedule["autonomy-daily-digest"]
        assert entry["task"] == "law_ai.core.tasks.compose_digest_task"
        assert entry["kwargs"]["kind"] == "digest"
        assert entry["options"]["queue"] == "autonomy"

    def test_kill_switch_still_short_circuits(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from law_ai.core.tasks import compose_digest_task

        monkeypatch.setattr(settings, "AUTONOMY_ENABLED", False)
        monkeypatch.setattr(settings, "AUDIT_PATH", str(tmp_path / "audit.jsonl"))
        called: list[int] = []

        def _boom(**_: Any) -> Path:
            called.append(1)
            raise AssertionError("compose_digest must not run when disabled")

        monkeypatch.setattr(autonomy, "compose_digest", _boom)
        result = compose_digest_task(kind="digest")

        assert result["status"] == "disabled"
        assert called == []

    def test_transient_db_error_is_retried_then_succeeds(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from celery.exceptions import Retry
        from django.db import OperationalError

        from law_ai.core.tasks import compose_digest_task

        monkeypatch.setattr(settings, "AUTONOMY_ENABLED", True)
        monkeypatch.setattr(settings, "AUDIT_PATH", str(tmp_path / "audit.jsonl"))
        digest = tmp_path / f"digest-{_DATE_LABEL}.md"
        digest.write_text("# stub\n", encoding="utf-8")
        attempts: list[bool] = []

        def _flaky(*, raise_on_db_error: bool = False) -> Path:
            attempts.append(raise_on_db_error)
            if len(attempts) == 1:
                raise OperationalError("server closed the connection unexpectedly")
            return digest

        monkeypatch.setattr(autonomy, "compose_digest", _flaky)

        # Celery signals an eager retry differently across versions; the
        # attempt count below is the real assertion either way.
        with contextlib.suppress(Retry):
            compose_digest_task.apply(kwargs={"kind": "digest"}, throw=False)

        assert len(attempts) == 2, "the transient failure was not retried"
        assert attempts == [True, True], "the task must let DB errors escape"

    def test_digest_path_lands_on_the_audit_events(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The stored path is the point of the item: no artefact hunting."""
        from law_ai.core.tasks import compose_digest_task

        monkeypatch.setattr(settings, "AUTONOMY_ENABLED", True)
        digest = tmp_path / f"digest-{_DATE_LABEL}.md"
        digest.write_text("# stub\n", encoding="utf-8")
        monkeypatch.setattr(autonomy, "compose_digest", lambda **_: digest)
        captured: list[dict[str, Any]] = []
        monkeypatch.setattr(autonomy, "_persist", captured.append)

        result = compose_digest_task(kind="digest")

        assert result["status"] == "ok"
        assert result["digest_path"] == str(digest)
        end = [e for e in captured if e["type"] == "autonomy_cycle.end"]
        assert len(end) == 1
        assert end[0]["digest_path"] == str(digest)
        assert end[0]["retries"] == 0

    def test_exhausted_retries_still_close_the_audit_trail(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A failed attempt always writes an ``autonomy_cycle.end`` error event."""
        from django.db import OperationalError

        from law_ai.core.tasks import compose_digest_task

        monkeypatch.setattr(settings, "AUTONOMY_ENABLED", True)

        def _always_down(**_: Any) -> Path:
            raise OperationalError("db down")

        monkeypatch.setattr(autonomy, "compose_digest", _always_down)
        captured: list[dict[str, Any]] = []
        monkeypatch.setattr(autonomy, "_persist", captured.append)

        with pytest.raises(OperationalError, match="db down"):
            compose_digest_task(kind="digest")

        types = [e["type"] for e in captured]
        assert types == ["autonomy_cycle.start", "autonomy_cycle.end"]
        assert captured[-1]["status"] == "error"
        assert "OperationalError" in captured[-1]["error"]


class TestLegalBenchDeltaSection:
    """The digest's LegalBench section, fed by the eval harness (BL-20260811-12).

    `compose_digest` has rendered this section since spec 018, but nothing
    emitted `autonomy_legalbench_delta` until the eval report writer did, so
    it printed `*(none)*` on every digest ever produced. This pins the shape
    the emitter and the renderer agree on.
    """

    def test_emitted_payload_renders_as_a_signed_delta(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(settings, "AUTONOMY_DIGEST_DIR", str(tmp_path))

        # Exactly what law_ai.eval.report._emit_delta_events writes.
        payload = {
            "task": "core_reasoning",
            "accuracy": 0.75,
            "baseline": 0.70,
            "delta": 5.0,
            "scorer": "default_match",
            "synthetic": False,
            "model": "mistral:7b-instruct-q4_K_M",
            "source": "legalbench",
        }
        rows = [{"kind": "autonomy_legalbench_delta", "payload": payload}]

        with (
            patch("law_ai.audit.models.AuditEvent") as mock_model,
            patch("law_ai.core.autonomy._persist"),
        ):
            mock_model.objects = _mock_queryset(rows)
            path = autonomy.compose_digest(date=_ANCHOR)

        text = path.read_text()
        assert "## LegalBench Delta" in text
        assert "- core_reasoning: +5.0" in text


class TestComposeDigestWindowEnd:
    """BL-20260511-19: a CI run needs a digest of its own work."""

    def test_default_window_still_ends_at_midnight(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(settings, "AUTONOMY_DIGEST_DIR", str(tmp_path))

        with (
            patch("law_ai.audit.models.AuditEvent") as mock_model,
            patch("law_ai.core.autonomy._persist"),
        ):
            mock_model.objects = _mock_queryset([])
            path = autonomy.compose_digest(date=_ANCHOR)

        assert "2026-05-10T00:00:00+00:00 → 2026-05-11T00:00:00+00:00" in (
            path.read_text()
        )

    def test_explicit_window_end_moves_both_bounds_and_the_label(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The 06:00 UTC nightly run's own events fall inside this window."""
        monkeypatch.setattr(settings, "AUTONOMY_DIGEST_DIR", str(tmp_path))
        now = datetime(2026, 5, 11, 6, 30, tzinfo=UTC)

        with (
            patch("law_ai.audit.models.AuditEvent") as mock_model,
            patch("law_ai.core.autonomy._persist"),
        ):
            mock_model.objects = _mock_queryset([])
            path = autonomy.compose_digest(date=_ANCHOR, window_end=now)

        # Same-day label, and the window now reaches 06:30 rather than 00:00.
        assert path.name == "digest-2026-05-11.md"
        assert "2026-05-10T06:30:00+00:00 → 2026-05-11T06:30:00+00:00" in (
            path.read_text()
        )

    def test_the_window_is_passed_to_the_audit_query(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(settings, "AUTONOMY_DIGEST_DIR", str(tmp_path))
        now = datetime(2026, 5, 11, 6, 30, tzinfo=UTC)
        qs = _mock_queryset([])

        with (
            patch("law_ai.audit.models.AuditEvent") as mock_model,
            patch("law_ai.core.autonomy._persist"),
        ):
            mock_model.objects = qs
            autonomy.compose_digest(date=_ANCHOR, window_end=now)

        kwargs = qs.filter.call_args.kwargs
        assert kwargs["timestamp__lt"] == now
        assert kwargs["timestamp__gte"] == datetime(2026, 5, 10, 6, 30, tzinfo=UTC)


class TestRunDigestWindowFlag:
    """The CLI flag the nightly workflow passes through `make autonomy-run`."""

    def test_flag_is_accepted_and_forwarded(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from law_ai.core.management.commands.run_autonomy import _run_digest

        monkeypatch.setattr(settings, "AUTONOMY_DIGEST_DIR", str(tmp_path))
        seen: list[datetime | None] = []

        def _capture(*, window_end: datetime | None = None, **_: Any) -> Path:
            seen.append(window_end)
            target = tmp_path / "digest-2026-05-11.md"
            target.write_text("# stub\n", encoding="utf-8")
            return target

        monkeypatch.setattr(autonomy, "compose_digest", _capture)
        monkeypatch.setattr(autonomy, "deliver_digest", lambda p: {"delivered": 0})

        _run_digest({}, window_to_now=False)
        _run_digest({}, window_to_now=True)

        assert seen[0] is None
        assert seen[1] is not None and seen[1].tzinfo is not None

    def test_argparse_exposes_the_flag(self) -> None:
        from law_ai.core.management.commands.run_autonomy import Command

        parser = Command().create_parser("manage.py", "run_autonomy")
        opts = parser.parse_args(["--kind", "digest", "--window-to-now"])
        assert opts.window_to_now is True
        assert parser.parse_args(["--kind", "digest"]).window_to_now is False
