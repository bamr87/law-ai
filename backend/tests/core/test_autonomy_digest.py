"""Tests for ``lawgraph.core.autonomy.compose_digest`` (spec 018 T-010)."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from django.conf import settings

from lawgraph.core import autonomy

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
            patch("lawgraph.audit.models.AuditEvent") as mock_model,
            patch("lawgraph.core.autonomy._persist"),
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
            patch("lawgraph.audit.models.AuditEvent") as mock_model,
            patch("lawgraph.core.autonomy._persist"),
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
            patch("lawgraph.audit.models.AuditEvent") as mock_model,
            patch("lawgraph.core.autonomy._persist"),
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
            patch("lawgraph.audit.models.AuditEvent") as mock_model,
            patch("lawgraph.core.autonomy._persist", side_effect=captured.append),
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
            patch("lawgraph.core.autonomy._persist"),
            patch(
                "lawgraph.audit.models.AuditEvent",
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
        from lawgraph.core.management.commands.run_autonomy import _run_digest

        context: dict[str, Any] = {}
        with (
            patch("lawgraph.audit.models.AuditEvent") as mock_model,
            patch("lawgraph.core.autonomy._persist"),
        ):
            mock_model.objects = _mock_queryset([])
            result = _run_digest(context)

        assert "digest_path" in result
        assert Path(result["digest_path"]).exists()
        assert context["digest_path"] == result["digest_path"]
