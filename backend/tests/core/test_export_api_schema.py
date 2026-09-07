"""Contract-export gate (spec 051 / BL-20260811-16).

``frontend/__tests__/fixtures/api-schema.json`` is the only link between the
backend's Pydantic contracts and the hand-written TypeScript in
``frontend/lib/api.ts``. If a model changes and the fixture is not regenerated,
the frontend gate keeps comparing against yesterday's contract and the drift
stays invisible — so the staleness check has to live on this side.
"""

from __future__ import annotations

import json
from io import StringIO

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from law_ai.core.management.commands.export_api_schema import (
    build_document,
    fixture_path,
    serialise,
)

pytestmark = pytest.mark.unit


EXPECTED_CONTRACTS = {
    "AnalysisRequest",
    "AnalysisResponse",
    "IRACOutput",
    "LsatGradeRequest",
    "LsatGradeResponse",
    "LsatQuestion",
    "LsatTutorRequest",
    "LsatTutorResponse",
    "PrecedentList",
}


def test_document_covers_the_browser_facing_contracts() -> None:
    document = build_document()
    assert set(document["contracts"]) == EXPECTED_CONTRACTS


def test_every_contract_is_a_real_object_schema() -> None:
    for name, schema in build_document()["contracts"].items():
        assert schema["type"] == "object", name
        assert schema["properties"], name


def test_checked_in_fixture_is_current() -> None:
    """Fails when a model moved and nobody re-ran the exporter."""
    path = fixture_path()
    assert (
        path.is_file()
    ), f"{path} is missing — run `make manage CMD=export_api_schema`"
    assert path.read_text(encoding="utf-8") == serialise(build_document()), (
        "frontend/__tests__/fixtures/api-schema.json is stale — run "
        "`make manage CMD=export_api_schema`"
    )


def test_check_flag_passes_against_the_checked_in_fixture() -> None:
    out = StringIO()
    call_command("export_api_schema", "--check", stdout=out)
    assert "is current" in out.getvalue()


def test_check_flag_fails_when_the_fixture_drifts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "law_ai.core.management.commands.export_api_schema.build_document",
        lambda: {"contracts": {"Drifted": {}}},
    )
    with pytest.raises(CommandError, match="stale"):
        call_command("export_api_schema", "--check", stdout=StringIO())


def test_print_flag_emits_parseable_json_without_writing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _explode() -> None:  # pragma: no cover - must never be reached
        raise AssertionError("--print must not touch the fixture")

    monkeypatch.setattr(
        "law_ai.core.management.commands.export_api_schema.fixture_path",
        _explode,
    )
    out = StringIO()
    call_command("export_api_schema", "--print", stdout=out)
    assert set(json.loads(out.getvalue())["contracts"]) == EXPECTED_CONTRACTS


def test_analysis_request_required_fields_match_the_api() -> None:
    """The one field the client must always send stays required."""
    schema = build_document()["contracts"]["AnalysisRequest"]
    assert schema["required"] == ["text"]
    assert "stream_id" in schema["properties"]
