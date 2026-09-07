"""The e2e fixture run — BL-20260429-27.

`manage.py seed_analysis_run` exists for one reason: the browser spec has to
assert the *healthy* Analysis Studio render (IRAC brief, precedent list,
trace-id copy), and the e2e sidecar is pinned to an unreachable Ollama so a
live run there can only produce the degraded engine-state panel.

That makes the seeded payload load-bearing. If it ever drifted into a shape
the healthy branch does not render — a `degraded` flag, an empty IRAC field, a
trace id shorter than the chip's eight-character elision — the browser spec
would fail with a timeout on a locator, hours away from the real cause. These
assertions put the failure here instead.
"""

from __future__ import annotations

import pytest
from django.core.management import call_command
from rest_framework.test import APIClient

from law_ai.analysis.management.commands.seed_analysis_run import ANALYSIS_ID, TRACE_ID
from law_ai.analysis.models import AnalysisRun

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


def test_seeding_is_idempotent() -> None:
    """`make test-e2e` runs it on every invocation."""
    call_command("seed_analysis_run")
    call_command("seed_analysis_run")
    assert AnalysisRun.objects.filter(analysis_id=ANALYSIS_ID).count() == 1


def test_a_previously_archived_run_comes_back() -> None:
    """Soft-delete must not make the fixture 404 forever."""
    call_command("seed_analysis_run")
    run = AnalysisRun.objects.get(analysis_id=ANALYSIS_ID)
    run.archived_at = "2026-01-01T00:00:00+00:00"
    run.save()

    call_command("seed_analysis_run")
    assert AnalysisRun.objects.get(analysis_id=ANALYSIS_ID).archived_at is None


def test_the_payload_takes_the_healthy_render_path() -> None:
    """Everything the browser spec asserts on, checked at the source."""
    call_command("seed_analysis_run")
    payload = AnalysisRun.objects.get(analysis_id=ANALYSIS_ID).as_payload()

    irac = payload["irac"]
    assert irac["degraded"] is False, (
        "a degraded payload renders EngineStatePanel — no IRAC card, no "
        "precedents, no trace-id chip for the spec to find"
    )
    for field in ("issue", "rule", "application", "conclusion"):
        assert irac[field].strip(), f"the spec asserts a non-empty <dd> for {field}"

    precedents = payload["precedents"]
    assert precedents["degraded"] is False
    assert precedents["precedents"], "the precedents region needs at least one row"

    trace_id = payload["agent_trace"][0]["trace_id"]
    assert trace_id == TRACE_ID
    # The chip shows the first eight characters and elides; a shorter id would
    # make "the clipboard carries the whole id" vacuously true.
    assert len(trace_id) > 8


def test_the_seeded_run_is_replayable_over_the_api() -> None:
    """`/analysis?id=…` in the browser is this request through the proxy."""
    call_command("seed_analysis_run")
    response = APIClient().get(f"/api/analysis/{ANALYSIS_ID}")
    assert response.status_code == 200
    body = response.json()
    assert body["id"] == ANALYSIS_ID
    assert body["persisted"] is True
    # The studio refills the form from the stored request.
    assert body["request"]["text"].strip()
