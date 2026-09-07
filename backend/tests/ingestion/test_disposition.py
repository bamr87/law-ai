"""Disposition + prevailing-party metadata on `:Case` ingestion (BL-20260803-01).

Constitution §13 / ADR 0004 P3 ("surface who prevailed") requires the graph to
be able to say how a case came out. The hard constraint the item states is the
one most of these tests are about: **when the record is silent, both fields
stay null** — no LLM, no guess from the opinion prose.
"""

from __future__ import annotations

from typing import Any

import pytest

from law_ai.core.neo4j import queries as neo4j_queries
from law_ai.core.schemas.extraction import ExtractionResult
from law_ai.ingestionapp.services import scout as scout_module
from law_ai.ingestionapp.services.scout import IngestionScout

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# The mapper
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Affirmed.", "affirmed"),
        ("AFFIRMED", "affirmed"),
        ("Reversed and remanded", "reversed"),
        ("Judgment vacated; cause remanded", "vacated"),
        ("Appeal dismissed for want of jurisdiction", "dismissed"),
        ("Remanded to the district court", "remanded"),
        ("Affirmed in part, reversed in part", "other"),
    ],
)
def test_map_disposition_known_phrases(raw: str, expected: str) -> None:
    assert scout_module.map_disposition(raw) == expected


@pytest.mark.parametrize("raw", [None, "", "   ", {}, "per curiam", "opinion filed"])
def test_map_disposition_returns_none_when_silent_or_unrecognised(raw: Any) -> None:
    """The item's constraint: never infer an outcome the record does not state."""
    assert scout_module.map_disposition(raw) is None


def test_map_disposition_logs_rather_than_guessing(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level("INFO", logger="law_ai.ingestion.scout"):
        assert scout_module.map_disposition("submitted on the briefs") is None
    assert any("unmapped disposition" in r.message for r in caplog.records)


# ---------------------------------------------------------------------------
# Prevailing party derivation
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("disposition", "expected"),
    [
        ("affirmed", "appellee"),
        ("reversed", "appellant"),
        ("remanded", None),
        ("dismissed", None),
        ("vacated", None),
        ("other", None),
        (None, None),
    ],
)
def test_derive_prevailing_party_type(disposition: Any, expected: str | None) -> None:
    assert scout_module.derive_prevailing_party_type(disposition) == expected


def test_derive_prevailing_party_type_declines_on_non_appellate_posture() -> None:
    assert (
        scout_module.derive_prevailing_party_type(
            "affirmed", "Motion for summary judgment"
        )
        is None
    )
    assert (
        scout_module.derive_prevailing_party_type("affirmed", "On appeal from ...")
        == "appellee"
    )


# ---------------------------------------------------------------------------
# End-to-end through IngestionScout.extract
# ---------------------------------------------------------------------------
def _payload(**cluster: Any) -> dict[str, Any]:
    return {
        "id": 4242,
        "case_name": "Doe v. Roe",
        "plain_text": "Some opinion body text. " * 40,
        "cluster": {"court": "Colo. Ct. App.", "date_filed": "2020-01-01", **cluster},
    }


def test_extract_populates_disposition_and_prevailing_party() -> None:
    result = IngestionScout().extract(
        _payload(disposition="Affirmed.", posture="Appeal from district court")
    )
    assert result.disposition == "affirmed"
    assert result.prevailing_party_type == "appellee"


def test_extract_leaves_both_null_when_cluster_is_silent() -> None:
    result = IngestionScout().extract(_payload())
    assert result.disposition is None
    assert result.prevailing_party_type is None


def test_extract_does_not_infer_from_opinion_prose() -> None:
    """Prose saying "we affirm" is not a disposition field — stay silent."""
    payload = _payload()
    payload["plain_text"] = "We affirm the judgment of the district court. " * 40
    result = IngestionScout().extract(payload)
    assert result.disposition is None
    assert result.prevailing_party_type is None


def test_extract_reads_top_level_disposition_fallback() -> None:
    payload = _payload()
    payload["disposition"] = "Reversed"
    result = IngestionScout().extract(payload)
    assert result.disposition == "reversed"
    assert result.prevailing_party_type == "appellant"


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------
class _FakeResult:
    async def single(self) -> None:  # pragma: no cover - protocol boilerplate
        return None

    def __aiter__(self) -> _FakeResult:
        return self

    async def __anext__(self) -> Any:  # pragma: no cover - protocol boilerplate
        raise StopAsyncIteration


class _FakeSession:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def run(self, cypher: str, params: dict[str, Any]) -> _FakeResult:
        self.calls.append((cypher, params))
        return _FakeResult()


@pytest.mark.asyncio
async def test_commit_extraction_binds_disposition_params(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _no_embed(*args: Any, **kwargs: Any) -> None:
        return None

    monkeypatch.setattr(neo4j_queries, "embed_case", _no_embed)
    session = _FakeSession()
    result = ExtractionResult(
        case_id="1",
        title="Doe v. Roe",
        confidence=0.9,
        disposition="reversed",
        prevailing_party_type="appellant",
    )
    await neo4j_queries.commit_extraction(session, result)  # type: ignore[arg-type]

    cypher, params = session.calls[0]
    assert params["disposition"] == "reversed"
    assert params["prevailing_party_type"] == "appellant"
    # Coalesced on MATCH so a later silent re-ingest cannot null a set value.
    assert "c.disposition = coalesce($disposition, c.disposition)" in cypher


@pytest.mark.asyncio
async def test_commit_extraction_binds_none_when_silent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _no_embed(*args: Any, **kwargs: Any) -> None:
        return None

    monkeypatch.setattr(neo4j_queries, "embed_case", _no_embed)
    session = _FakeSession()
    await neo4j_queries.commit_extraction(  # type: ignore[arg-type]
        session, ExtractionResult(case_id="2", title="Silent", confidence=0.9)
    )
    _, params = session.calls[0]
    assert params["disposition"] is None
    assert params["prevailing_party_type"] is None


# ---------------------------------------------------------------------------
# Retrieval surface (constitution §13 P3)
# ---------------------------------------------------------------------------
def test_case_passage_carries_outcome_fields() -> None:
    from law_ai.agents_runtime.tools import graph_rag

    passage = graph_rag._case_passage(
        {
            "id": "1",
            "title": "Doe v. Roe",
            "holding_summary": "Held.",
            "disposition": "affirmed",
            "prevailing_party_type": "appellee",
        },
        retrieval_mode="lexical",
    )
    assert passage["disposition"] == "affirmed"
    assert passage["prevailing_party_type"] == "appellee"


def test_case_passage_outcome_fields_default_to_none() -> None:
    from law_ai.agents_runtime.tools import graph_rag

    passage = graph_rag._case_passage(
        {"id": "1", "title": "X"}, retrieval_mode="lexical"
    )
    assert passage["disposition"] is None
    assert passage["prevailing_party_type"] is None
