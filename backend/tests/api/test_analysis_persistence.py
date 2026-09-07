"""Persisted analyses (BL-20260429-25).

A run has to survive the response that carried it: the request, the response
and the trace ids land in Postgres under the ``analysis_id`` the API already
mints, and ``GET /api/analysis/<id>`` gives them back. The agents themselves
are stubbed — this is about storage and retrieval, not about the model.
"""

from __future__ import annotations

from typing import Any

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from law_ai.agents_runtime.crews.legal_analyst import IRACOutput
from law_ai.agents_runtime.crews.precedent_hunter import Precedent, PrecedentList
from law_ai.analysis import urls as analysis_api
from law_ai.analysis.models import AnalysisRun

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


@pytest.fixture
def client() -> APIClient:
    return APIClient()


@pytest.fixture(autouse=True)
def stub_agents(monkeypatch: pytest.MonkeyPatch) -> None:
    """Deterministic agents: no model, no network, stable trace ids."""

    async def fake_analyst(self: Any, payload: dict[str, Any]) -> IRACOutput:
        return IRACOutput(
            issue="Was the contract breached?",
            rule="A promise unperformed is a breach.",
            application="It was not performed.",
            conclusion="Breach.",
            confidence=0.9,
            sources=[{"title": "Restatement", "url": "https://example.test/r2d"}],
            trace_id="trace-analyst",
        )

    async def fake_hunter(self: Any, payload: dict[str, Any]) -> PrecedentList:
        return PrecedentList(
            precedents=[
                Precedent(
                    case_id="hadley-1854",
                    title="Hadley v Baxendale",
                    court="Court of Exchequer",
                    year=1854,
                    relevance_score=0.8,
                    url="https://example.test/hadley",
                )
            ],
            summary="One controlling authority on remoteness of damage.",
            confidence=0.8,
            trace_id="trace-hunter",
        )

    monkeypatch.setattr(analysis_api.LegalAnalyst, "run", fake_analyst, raising=True)
    monkeypatch.setattr(analysis_api.PrecedentHunter, "run", fake_hunter, raising=True)


def _run(client: APIClient, **extra: Any) -> dict[str, Any]:
    res = client.post(
        "/api/analysis",
        {"text": "Did the seller breach?", "use_langgraph": False, **extra},
        format="json",
    )
    assert res.status_code == 200, res.content
    return res.json()


def test_a_run_is_persisted_with_request_response_and_traces(
    client: APIClient,
) -> None:
    body = _run(client, jurisdiction="US-NY")

    run = AnalysisRun.objects.get(analysis_id=body["id"])
    assert run.request["text"] == "Did the seller breach?"
    assert run.request["jurisdiction"] == "US-NY"
    assert run.response["irac"]["conclusion"] == "Breach."
    assert sorted(run.child_trace_ids) == ["trace-analyst", "trace-hunter"]
    assert run.trace_id  # parent AnalysisStudio provenance trace
    assert run.engine == AnalysisRun.ENGINE_DIRECT
    assert run.confidence == pytest.approx(body["confidence"])
    assert run.requires_human_review == body["requires_human_review"]
    assert run.created_by is None
    assert run.archived_at is None


def test_the_run_can_be_revisited_by_analysis_id(client: APIClient) -> None:
    body = _run(client)

    res = client.get(f"/api/analysis/{body['id']}")
    assert res.status_code == 200
    payload = res.json()
    assert payload["id"] == body["id"]
    assert payload["irac"] == body["irac"]
    assert payload["persisted"] is True
    assert payload["created_at"]
    assert sorted(payload["child_trace_ids"]) == ["trace-analyst", "trace-hunter"]
    assert payload["request"]["text"] == "Did the seller breach?"


def test_unknown_analysis_id_is_404(client: APIClient) -> None:
    res = client.get("/api/analysis/an-doesnotexist")
    assert res.status_code == 404
    assert "not found" in res.json()["detail"]


def test_archived_run_is_404_but_the_row_survives(client: APIClient) -> None:
    body = _run(client)
    run = AnalysisRun.objects.get(analysis_id=body["id"])
    run.archived_at = timezone.now()
    run.save()

    assert client.get(f"/api/analysis/{body['id']}").status_code == 404
    # Soft delete: the row is still there (constitution §5).
    assert AnalysisRun.objects.filter(analysis_id=body["id"]).exists()


def test_langgraph_engine_is_recorded(client: APIClient) -> None:
    body = _run(client, use_langgraph=True)
    run = AnalysisRun.objects.get(analysis_id=body["id"])
    assert run.engine == AnalysisRun.ENGINE_LANGGRAPH


def test_signed_in_user_is_recorded_as_the_owner(client: APIClient) -> None:
    from django.contrib.auth import get_user_model

    user = get_user_model().objects.create_user(username="ada", password="pw-12345")
    client.force_login(user)

    body = _run(client)
    assert AnalysisRun.objects.get(analysis_id=body["id"]).created_by == user


def test_a_persistence_failure_never_fails_the_run(
    client: APIClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The analysis already happened — a DB blip must not turn it into a 500."""

    def boom(*args: Any, **kwargs: Any) -> None:
        raise RuntimeError("postgres is having a day")

    monkeypatch.setattr(AnalysisRun.objects, "update_or_create", boom, raising=True)

    body = _run(client)
    assert body["irac"]["conclusion"] == "Breach."
    assert not AnalysisRun.objects.filter(analysis_id=body["id"]).exists()


def test_the_wire_shape_has_no_private_trace_field(client: APIClient) -> None:
    """``_parent_trace_id`` is a PrivateAttr — it must not leak into JSON."""
    body = _run(client)
    assert "_parent_trace_id" not in body


def test_rerunning_the_same_id_updates_rather_than_duplicates(
    client: APIClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(analysis_api, "_new_analysis_id", lambda: "an-fixed")

    first = _run(client)
    second = _run(client, jurisdiction="US-CA")
    assert first["id"] == second["id"] == "an-fixed"
    assert AnalysisRun.objects.filter(analysis_id="an-fixed").count() == 1
    assert (
        AnalysisRun.objects.get(analysis_id="an-fixed").request["jurisdiction"]
        == "US-CA"
    )
