"""Digest delivery to Slack and email (BL-20260511-05).

Before this the ``digest-<date>.md`` file was the only surface: a nightly
autonomy run that found something interesting only reached a human who went
looking for it. ``law_ai.core.autonomy.deliver_digest`` fans the file out to
two env-driven channels, both off by default.

No network: the Slack leg is mocked with ``respx``, the email leg uses
Django's locmem backend via ``django.core.mail.outbox``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import httpx
import pytest
import respx
from django.conf import settings
from django.core import mail

from law_ai.core import autonomy

_WEBHOOK = "https://hooks.slack.com/services/T000/B000/abcdefghijklmnop"


@pytest.fixture()
def digest(tmp_path: Path) -> Path:
    path = tmp_path / "digest-2026-05-11.md"
    path.write_text("# Autonomy Digest — 2026-05-11\n\n- one PR\n", encoding="utf-8")
    return path


@pytest.fixture(autouse=True)
def _no_channels(monkeypatch: pytest.MonkeyPatch) -> None:
    """Every test opts *in* to a channel; the default posture is off."""
    monkeypatch.setattr(settings, "AUTONOMY_DIGEST_SLACK_WEBHOOK_URL", "")
    monkeypatch.setattr(settings, "AUTONOMY_DIGEST_EMAIL_TO", [])
    monkeypatch.setattr(
        settings, "EMAIL_BACKEND", "django.core.mail.backends.locmem.EmailBackend"
    )
    mail.outbox.clear()


@pytest.fixture()
def events(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    captured: list[dict[str, Any]] = []
    monkeypatch.setattr(autonomy, "_persist", captured.append)
    return captured


class TestNoChannelsConfigured:
    def test_unconfigured_delivery_is_a_no_op(
        self, digest: Path, events: list[dict[str, Any]]
    ) -> None:
        summary = autonomy.deliver_digest(digest)

        assert summary["channels"] == []
        assert summary["attempted"] == 0
        assert summary["delivered"] == 0
        assert mail.outbox == []

    def test_event_is_still_emitted_so_absence_is_reported(
        self, digest: Path, events: list[dict[str, Any]]
    ) -> None:
        autonomy.deliver_digest(digest)

        assert [e["type"] for e in events] == ["autonomy_digest.delivered"]
        assert events[0]["digest_path"] == str(digest)
        assert events[0]["delivered"] == 0


class TestSlackDelivery:
    @respx.mock
    def test_markdown_body_is_posted_to_the_webhook(
        self,
        digest: Path,
        events: list[dict[str, Any]],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr(settings, "AUTONOMY_DIGEST_SLACK_WEBHOOK_URL", _WEBHOOK)
        route = respx.post(_WEBHOOK).mock(return_value=httpx.Response(200, text="ok"))

        summary = autonomy.deliver_digest(digest)

        assert route.called
        posted = route.calls.last.request
        assert b"Autonomy Digest" in posted.content
        assert summary["delivered"] == 1
        assert summary["channels"][0]["channel"] == "slack"
        assert summary["channels"][0]["ok"] is True
        assert summary["channels"][0]["truncated"] is False

    @respx.mock
    def test_webhook_url_is_never_written_to_the_audit_log(
        self,
        digest: Path,
        events: list[dict[str, Any]],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """The webhook path *is* the credential (constitution §6)."""
        monkeypatch.setattr(settings, "AUTONOMY_DIGEST_SLACK_WEBHOOK_URL", _WEBHOOK)
        respx.post(_WEBHOOK).mock(return_value=httpx.Response(200))

        autonomy.deliver_digest(digest)

        blob = repr(events)
        assert _WEBHOOK not in blob
        assert "abcdefghijklmnop" not in blob
        assert "hooks.slack.com" in blob  # host alone is not a secret

    @respx.mock
    def test_oversized_digest_is_truncated_with_a_pointer_to_the_file(
        self,
        tmp_path: Path,
        events: list[dict[str, Any]],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Slack caps `text` at 40 000 chars; a rejected post is a lost digest."""
        big = tmp_path / "digest-2026-05-11.md"
        big.write_text("x" * 60_000, encoding="utf-8")
        monkeypatch.setattr(settings, "AUTONOMY_DIGEST_SLACK_WEBHOOK_URL", _WEBHOOK)
        route = respx.post(_WEBHOOK).mock(return_value=httpx.Response(200))

        summary = autonomy.deliver_digest(big)

        body = route.calls.last.request.content.decode("utf-8")
        assert len(body) < 45_000
        assert "truncated" in body
        assert str(big) in body
        assert summary["channels"][0]["truncated"] is True

    @respx.mock
    def test_a_dead_webhook_never_fails_the_cycle(
        self,
        digest: Path,
        events: list[dict[str, Any]],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr(settings, "AUTONOMY_DIGEST_SLACK_WEBHOOK_URL", _WEBHOOK)
        respx.post(_WEBHOOK).mock(side_effect=httpx.ConnectError("no route to host"))

        summary = autonomy.deliver_digest(digest)

        assert summary["delivered"] == 0
        assert summary["channels"][0]["ok"] is False
        assert "ConnectError" in summary["channels"][0]["error"]

    @respx.mock
    def test_a_non_2xx_response_is_recorded_as_a_failure(
        self,
        digest: Path,
        events: list[dict[str, Any]],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr(settings, "AUTONOMY_DIGEST_SLACK_WEBHOOK_URL", _WEBHOOK)
        respx.post(_WEBHOOK).mock(return_value=httpx.Response(404, text="no_service"))

        summary = autonomy.deliver_digest(digest)

        assert summary["delivered"] == 0
        assert summary["channels"][0]["status_code"] == 404
        assert summary["channels"][0]["error"] == "HTTP 404"


class TestEmailDelivery:
    def test_recipients_receive_the_digest(
        self,
        digest: Path,
        events: list[dict[str, Any]],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr(
            settings, "AUTONOMY_DIGEST_EMAIL_TO", ["ops@example.com", "law@example.com"]
        )

        summary = autonomy.deliver_digest(digest)

        assert len(mail.outbox) == 1
        message = mail.outbox[0]
        assert message.subject == "Law AI autonomy digest — 2026-05-11"
        assert "Autonomy Digest" in message.body
        assert message.to == ["ops@example.com", "law@example.com"]
        assert summary["delivered"] == 1
        assert summary["channels"][0]["recipients"] == 2

    def test_a_refused_smtp_connection_never_fails_the_cycle(
        self,
        digest: Path,
        events: list[dict[str, Any]],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr(settings, "AUTONOMY_DIGEST_EMAIL_TO", ["ops@example.com"])

        def _boom(**_: Any) -> int:
            raise OSError("connection refused")

        monkeypatch.setattr("django.core.mail.send_mail", _boom)
        summary = autonomy.deliver_digest(digest)

        assert summary["delivered"] == 0
        assert summary["channels"][0]["ok"] is False
        assert "connection refused" in summary["channels"][0]["error"]

    def test_blank_recipients_are_ignored(
        self,
        digest: Path,
        events: list[dict[str, Any]],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """`AUTONOMY_DIGEST_EMAIL_TO=` in .env parses to a list with one blank."""
        monkeypatch.setattr(settings, "AUTONOMY_DIGEST_EMAIL_TO", ["", "  "])

        summary = autonomy.deliver_digest(digest)

        assert summary["channels"] == []
        assert mail.outbox == []


class TestBothChannels:
    @respx.mock
    def test_each_channel_reports_its_own_outcome(
        self,
        digest: Path,
        events: list[dict[str, Any]],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr(settings, "AUTONOMY_DIGEST_SLACK_WEBHOOK_URL", _WEBHOOK)
        monkeypatch.setattr(settings, "AUTONOMY_DIGEST_EMAIL_TO", ["ops@example.com"])
        respx.post(_WEBHOOK).mock(return_value=httpx.Response(500))

        summary = autonomy.deliver_digest(digest)

        assert summary["attempted"] == 2
        assert summary["delivered"] == 1  # email succeeded, Slack did not
        by_channel = {c["channel"]: c for c in summary["channels"]}
        assert by_channel["slack"]["ok"] is False
        assert by_channel["email"]["ok"] is True
        assert events[0]["attempted"] == 2


class TestMissingDigestFile:
    def test_an_unreadable_digest_degrades_rather_than_raising(
        self,
        tmp_path: Path,
        events: list[dict[str, Any]],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr(settings, "AUTONOMY_DIGEST_EMAIL_TO", ["ops@example.com"])

        summary = autonomy.deliver_digest(tmp_path / "does-not-exist.md")

        assert summary["delivered"] == 0
        assert summary["channels"][0]["channel"] == "read"
        assert summary["channels"][0]["ok"] is False
        assert mail.outbox == []


class TestRunDigestWiring:
    def test_the_cycle_runner_delivers_after_composing(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        from law_ai.core.management.commands.run_autonomy import _run_digest

        monkeypatch.setattr(settings, "AUTONOMY_DIGEST_DIR", str(tmp_path))
        monkeypatch.setattr(settings, "AUDIT_PATH", str(tmp_path / "audit.jsonl"))
        monkeypatch.setattr(settings, "AUTONOMY_DIGEST_EMAIL_TO", ["ops@example.com"])

        context: dict[str, Any] = {}
        result = _run_digest(context)

        assert Path(result["digest_path"]).exists()
        assert result["delivery"]["delivered"] == 1
        assert context["digest_delivered"] == 1
        assert len(mail.outbox) == 1
