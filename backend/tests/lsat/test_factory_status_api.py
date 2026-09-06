"""``GET /api/lsat/factory/status`` (BL-20260702-06).

``factory.status()`` has answered "what will the next batch target" for the
CLI since spec 024, but nothing exposed it over HTTP — so the reviewer working
the Authoring queue could see the proposals in front of them and not the
coverage holes that produced them. These pin the route, its shape, and the two
things the view adds on top of ``status()``: a summary of the last manifest,
and gate counts read off the proposals actually in the queue.
"""

from __future__ import annotations

from typing import Any

import pytest
from rest_framework.test import APIClient

from law_ai.lsat.services import proposals as proposals_store

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


def _get() -> Any:
    res = APIClient().get("/api/lsat/factory/status")
    assert res.status_code == 200, res.content
    return res.json()


def test_status_reports_the_bank_census_and_coverage_holes() -> None:
    body = _get()
    assert body["bank_total"] > 0
    assert set(body["bank_by_section"]) <= {"LR", "RC", "LG"}
    assert body["coverage_cells"] >= body["cells_with_deficit"]
    # The "next batch targets" the reviewer came for.
    assert isinstance(body["top_deficits"], list)
    for cell in body["top_deficits"]:
        assert set(cell) == {"archetype_id", "difficulty", "have", "want"}
        assert cell["want"] > cell["have"]


def test_status_reports_the_writing_library_too() -> None:
    body = _get()
    assert body["writing_prompts"] >= 0
    assert isinstance(body["writing_by_difficulty"], dict)


def test_status_has_a_manifest_summary_slot_even_with_no_manifest() -> None:
    """A status page must not 500, or omit a key, because no batch has run."""
    body = _get()
    assert "latest_manifest" in body
    assert "latest_manifest_summary" in body
    if body["latest_manifest"] is None:
        assert body["latest_manifest_summary"] is None


def test_manifest_summary_reads_the_manifest_on_disk(factory_env: Any) -> None:
    """With a real manifest planned, the summary is read off *that* file.

    The None branch above is the empty-factory case; this is the one a
    reviewer actually sees after a batch has been compiled (BL-20260905-43).
    """
    from law_ai.lsat.factory.pipeline import compile_plan

    manifest, path = compile_plan(factory_env)
    assert manifest.jobs, "expected the sandboxed bank to yield generation jobs"

    body = _get()
    assert body["latest_manifest"] == str(path)
    summary = body["latest_manifest_summary"]
    assert summary is not None
    assert summary["manifest_id"] == manifest.manifest_id
    assert summary["created_at"] == manifest.created_at
    assert summary["jobs"] == len(manifest.jobs)

    expected_tiers: dict[str, int] = {}
    expected_archetypes: dict[str, int] = {}
    for job in manifest.jobs:
        expected_tiers[str(job.tier)] = expected_tiers.get(str(job.tier), 0) + 1
        aid = str(job.target.archetype_id)
        expected_archetypes[aid] = expected_archetypes.get(aid, 0) + 1
    assert summary["by_tier"] == expected_tiers
    assert summary["by_archetype"] == expected_archetypes
    assert sum(summary["by_tier"].values()) == len(manifest.jobs)


def test_gate_counts_come_from_the_proposals_actually_queued() -> None:
    before = _get()["pending_gates"]
    assert set(before) == {"by_executor", "by_tier", "answer_balance_flagged"}

    proposals_store.record_proposal(
        {
            "section": "LR",
            "difficulty": "med",
            "stem": "A stem long enough to look like a real question stem here.",
            "choices": [
                {"label": label, "text": f"option {label}"}
                for label in ("A", "B", "C", "D", "E")
            ],
            "correct": "B",
            "explanation": "Because the key holds and the others do not.",
            "concepts": [],
        },
        agent_trace_id="tr-factory-status",
        model="test/executor",
        confidence=0.8,
        meta={
            "factory": {
                "manifest_id": "mfst-test",
                "job_id": "mfst-test-job01",
                "archetype_id": "weaken",
                "tier": "bulk",
                "executor": "OllamaExecutor",
                "template_version": "v1",
                "mode": "single",
                "balance_flag": "skewed",
            }
        },
    )

    after = _get()
    assert after["pending_from_factory"] == before_count(before) + 1
    gates = after["pending_gates"]
    assert gates["by_executor"]["OllamaExecutor"] >= 1
    assert gates["by_tier"]["bulk"] >= 1
    # A flagged answer distribution is exactly the kind of thing a reviewer
    # needs to see *before* opening the queue.
    assert gates["answer_balance_flagged"] >= 1


def before_count(gates: dict[str, Any]) -> int:
    """How many factory proposals the gate counts already covered."""
    return sum(gates["by_executor"].values())
