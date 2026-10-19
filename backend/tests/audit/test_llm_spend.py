"""The spend rollup reads the accounting back out (BL-20260905-69).

BL-20260811-21 put ``input_tokens``/``output_tokens``/``cost_usd`` on every
``llm_call`` audit event; nothing read them. These tests pin the read side:
the pure rollup, the ORM window, and the ``llm_spend`` command that operators
actually run. No model is called — the events are written directly, which is
the point: the accounting has to be answerable from the audit log alone.
"""

from __future__ import annotations

import json
from datetime import timedelta
from io import StringIO

import pytest
from django.core.management import call_command
from django.utils import timezone

from law_ai.audit.models import AuditEvent
from law_ai.audit.spend import UNATTRIBUTED, rollup, spend_report

pytestmark = pytest.mark.unit


def _payload(**over: object) -> dict[str, object]:
    base: dict[str, object] = {
        "agent": "legal_analyst",
        "provider": "claude",
        "model": "claude-sonnet-5-5",
        "ok": True,
        "input_tokens": 1000,
        "output_tokens": 500,
        "cost_usd": 0.012,
    }
    base.update(over)
    return base


class TestRollup:
    def test_groups_by_agent_and_by_tier(self) -> None:
        report = rollup(
            [
                _payload(),
                _payload(agent="lsat_content_author", cost_usd=0.004),
                _payload(provider="ollama", model="llama3", cost_usd=None),
            ]
        )
        assert report.total.calls == 3
        assert [b.key for b in report.by_agent] == [
            "legal_analyst",
            "lsat_content_author",
        ]
        assert {b.key for b in report.by_tier} == {
            "claude/claude-sonnet-5-5",
            "ollama/llama3",
        }
        analyst = next(b for b in report.by_agent if b.key == "legal_analyst")
        # Two legal_analyst calls: the priced Claude one and the Ollama one.
        assert analyst.calls == 2
        assert analyst.input_tokens == 2000

    def test_unpriced_is_counted_not_summed_as_zero(self) -> None:
        """An unpriced hosted model is unknown cost, never free cost."""
        report = rollup([_payload(cost_usd=None), _payload(cost_usd=0.01)])
        assert report.total.cost_usd == pytest.approx(0.01)
        assert report.total.unpriced_calls == 1

    def test_failed_calls_are_counted_but_not_flagged_unpriced(self) -> None:
        """A chain-wide failure has no usage; that is not a price-table gap."""
        report = rollup(
            [{"agent": "a", "ok": False, "chain": ["claude", "ollama"]}, _payload()]
        )
        assert report.total.calls == 2
        assert report.total.failed_calls == 1
        assert report.total.unpriced_calls == 0
        assert "(failed: claude,ollama)" in {b.key for b in report.by_tier}

    def test_agentless_calls_get_a_visible_bucket(self) -> None:
        report = rollup([_payload(agent=None)])
        assert [b.key for b in report.by_agent] == [UNATTRIBUTED]

    def test_junk_payload_fields_do_not_crash_the_rollup(self) -> None:
        report = rollup([_payload(input_tokens="lots", cost_usd="free")])
        assert report.total.calls == 1
        assert report.total.input_tokens == 0
        assert report.total.unpriced_calls == 1


@pytest.mark.django_db
class TestSpendReportQuery:
    def test_only_llm_call_events_inside_the_window_are_counted(self) -> None:
        AuditEvent.objects.create(kind="llm_call", payload=_payload())
        AuditEvent.objects.create(kind="agent_call", payload=_payload())
        stale = AuditEvent.objects.create(kind="llm_call", payload=_payload())
        AuditEvent.objects.filter(pk=stale.pk).update(
            timestamp=timezone.now() - timedelta(days=45)
        )

        report = spend_report(days=30)
        assert report.total.calls == 1
        assert report.since is not None

        everything = spend_report(days=None)
        assert everything.total.calls == 2
        assert everything.since is None


@pytest.mark.django_db
class TestLlmSpendCommand:
    def test_table_reports_agent_tier_and_the_unpriced_caveat(self) -> None:
        AuditEvent.objects.create(kind="llm_call", payload=_payload())
        AuditEvent.objects.create(
            kind="llm_call", payload=_payload(agent="lsat_tutor", cost_usd=None)
        )

        out = StringIO()
        call_command("llm_spend", stdout=out)
        text = out.getvalue()
        assert "legal_analyst" in text
        assert "lsat_tutor" in text
        assert "claude/claude-sonnet-5-5" in text
        assert "floor, not the bill" in text

    def test_json_mode_emits_the_same_rollup(self) -> None:
        AuditEvent.objects.create(kind="llm_call", payload=_payload())
        out = StringIO()
        call_command("llm_spend", "--json", "--days", "7", stdout=out)
        body = json.loads(out.getvalue())
        assert body["total"]["calls"] == 1
        assert body["total"]["cost_usd"] == pytest.approx(0.012)
        assert body["by_agent"][0]["key"] == "legal_analyst"

    def test_empty_window_says_so_rather_than_printing_zeroes(self) -> None:
        out = StringIO()
        call_command("llm_spend", stdout=out)
        assert "No llm_call events" in out.getvalue()

    def test_days_zero_means_all_time(self) -> None:
        stale = AuditEvent.objects.create(kind="llm_call", payload=_payload())
        AuditEvent.objects.filter(pk=stale.pk).update(
            timestamp=timezone.now() - timedelta(days=400)
        )
        out = StringIO()
        call_command("llm_spend", "--days", "0", "--json", stdout=out)
        body = json.loads(out.getvalue())
        assert body["since"] is None
        assert body["total"]["calls"] == 1
