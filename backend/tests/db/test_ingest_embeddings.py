"""Ingest-time embedding writes for the GraphRAG vector leg (BL-20260810-17).

The item asks for "nomic-embed-text embeddings **at ingest**". Every other test
in the suite stubs ``embed_case`` / ``embed_statute_section`` out so it can
inspect the structural MERGEs, which left the ingest wiring itself uncovered:
deleting the two ``await embed_*`` lines used to leave the suite green.

These tests run the real helpers against a recording fake session, with only
``core.llm.embeddings.embed_text`` stubbed, so they fail if either call site is
removed, if the helper stops writing, or if its fail-open contract regresses
into raising or into writing a partial vector.
"""

from __future__ import annotations

from typing import Any

import pytest

from law_ai.core.neo4j import queries as neo4j_queries
from law_ai.core.neo4j import statute_queries
from law_ai.core.schemas.extraction import ExtractionResult
from law_ai.core.schemas.statute_extraction import (
    StatuteExtraction,
    StatuteSectionPayload,
)

VECTOR = [0.25] * 768


class _FakeResult:
    def __aiter__(self) -> _FakeResult:
        return self

    async def __anext__(self) -> Any:  # pragma: no cover - protocol boilerplate
        raise StopAsyncIteration


class _FakeSession:
    """Records every Cypher statement and its parameters."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def run(self, cypher: str, params: dict[str, Any]) -> _FakeResult:
        self.calls.append((cypher, params))
        return _FakeResult()

    def params_for(self, cypher: str) -> list[dict[str, Any]]:
        return [p for c, p in self.calls if c == cypher]


@pytest.fixture
def embedder(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, str]]:
    """Stub the local embedder; returns the (text, component) pairs it saw."""
    from law_ai.core.llm import embeddings

    seen: list[tuple[str, str]] = []

    async def fake_embed_text(text: str, *, component: str = "graph") -> list[float]:
        seen.append((text, component))
        return list(VECTOR)

    monkeypatch.setattr(embeddings, "embed_text", fake_embed_text)
    monkeypatch.setattr(embeddings, "embedding_model", lambda: "nomic-embed-text")
    return seen


@pytest.fixture
def dead_embedder(monkeypatch: pytest.MonkeyPatch) -> None:
    """Stub an unreachable embedder — the fail-open path (no Ollama)."""
    from law_ai.core.llm import embeddings

    async def fake_embed_text(text: str, *, component: str = "graph") -> None:
        return None

    monkeypatch.setattr(embeddings, "embed_text", fake_embed_text)


# ---------------------------------------------------------------------------
# :Case
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_commit_extraction_writes_the_case_embedding(
    embedder: list[tuple[str, str]],
) -> None:
    """Committing an opinion embeds it — the ingest half of the vector leg."""
    session = _FakeSession()
    await neo4j_queries.commit_extraction(  # type: ignore[arg-type]
        session,
        ExtractionResult(
            case_id="case:1",
            title="Doe v. Roe",
            confidence=0.9,
            holding_summary="Held: the claim is time-barred.",
        ),
    )
    written = session.params_for(neo4j_queries.SET_CASE_EMBEDDING_CYPHER)
    assert len(written) == 1, "commit_extraction must write exactly one case vector"
    assert written[0]["id"] == "case:1"
    assert written[0]["embedding"] == VECTOR
    assert written[0]["model"] == "nomic-embed-text"
    assert written[0]["embedded_at"]
    # Embedded from the same fields the fulltext index covers.
    assert embedder == [("Doe v. Roe\nHeld: the claim is time-barred.", "ingest_case")]


@pytest.mark.asyncio
async def test_commit_extraction_still_commits_when_the_embedder_is_down(
    dead_embedder: None,
) -> None:
    """Fail-open: no vector, but the case node is still MERGEd."""
    session = _FakeSession()
    await neo4j_queries.commit_extraction(  # type: ignore[arg-type]
        session,
        ExtractionResult(case_id="case:2", title="Doe v. Roe", confidence=0.9),
    )
    assert session.params_for(neo4j_queries.SET_CASE_EMBEDDING_CYPHER) == []
    assert session.calls[0][0] == neo4j_queries.MERGE_CASE_CYPHER


@pytest.mark.asyncio
async def test_embed_case_writes_and_reports_success(
    embedder: list[tuple[str, str]],
) -> None:
    session = _FakeSession()
    wrote = await neo4j_queries.embed_case(  # type: ignore[arg-type]
        session, "case:3", title="Doe v. Roe", holding_summary=None
    )
    assert wrote is True
    assert session.params_for(neo4j_queries.SET_CASE_EMBEDDING_CYPHER)[0]["embedding"]


@pytest.mark.asyncio
async def test_embed_case_skips_a_textless_case(
    embedder: list[tuple[str, str]],
) -> None:
    """No title and no summary → nothing to embed, and no network call."""
    session = _FakeSession()
    wrote = await neo4j_queries.embed_case(  # type: ignore[arg-type]
        session, "case:4", title=None, holding_summary="   "
    )
    assert wrote is False
    assert session.calls == []
    assert embedder == []


@pytest.mark.asyncio
async def test_embed_case_fails_open_without_writing(dead_embedder: None) -> None:
    session = _FakeSession()
    wrote = await neo4j_queries.embed_case(  # type: ignore[arg-type]
        session, "case:5", title="Doe v. Roe", holding_summary=None
    )
    assert wrote is False
    assert session.calls == [], "a None vector must never reach the graph"


# ---------------------------------------------------------------------------
# :StatuteSection
# ---------------------------------------------------------------------------


def _extraction(*confidences: float) -> StatuteExtraction:
    return StatuteExtraction(
        jurisdiction_code="us-co",
        jurisdiction_name="Colorado",
        code_id="us-co/crs",
        code_title="Colorado Revised Statutes",
        statute_id="us-co/crs/title-38",
        statute_title="Title 38",
        confidence=max(confidences),
        sections=[
            StatuteSectionPayload(
                id=f"us-co/crs/38-12-10{i}",
                citation=f"C.R.S. § 38-12-10{i}",
                heading="Security deposits",
                text="A landlord shall return the deposit within one month.",
                confidence=c,
            )
            for i, c in enumerate(confidences)
        ],
    )


@pytest.mark.asyncio
async def test_commit_statute_extraction_embeds_every_committed_section(
    embedder: list[tuple[str, str]],
) -> None:
    session = _FakeSession()
    await statute_queries.commit_statute_extraction(  # type: ignore[arg-type]
        session, _extraction(0.9, 0.8)
    )
    written = session.params_for(statute_queries.SET_SECTION_EMBEDDING_CYPHER)
    assert [p["id"] for p in written] == [
        "us-co/crs/38-12-100",
        "us-co/crs/38-12-101",
    ]
    assert all(p["embedding"] == VECTOR for p in written)
    assert [component for _, component in embedder] == [
        "ingest_statute_section",
        "ingest_statute_section",
    ]
    assert embedder[0][0].startswith("C.R.S. § 38-12-100\nSecurity deposits\n")


@pytest.mark.asyncio
async def test_quarantined_sections_are_not_embedded(
    embedder: list[tuple[str, str]],
) -> None:
    """Below the HITL threshold → no node, so no vector either."""
    session = _FakeSession()
    await statute_queries.commit_statute_extraction(  # type: ignore[arg-type]
        session, _extraction(0.9, 0.1)
    )
    written = session.params_for(statute_queries.SET_SECTION_EMBEDDING_CYPHER)
    assert [p["id"] for p in written] == ["us-co/crs/38-12-100"]


@pytest.mark.asyncio
async def test_commit_statute_extraction_survives_a_dead_embedder(
    dead_embedder: None,
) -> None:
    session = _FakeSession()
    edges = await statute_queries.commit_statute_extraction(  # type: ignore[arg-type]
        session, _extraction(0.9)
    )
    assert edges  # the tree still committed
    assert session.params_for(statute_queries.SET_SECTION_EMBEDDING_CYPHER) == []


@pytest.mark.asyncio
async def test_embed_statute_section_skips_an_empty_section(
    embedder: list[tuple[str, str]],
) -> None:
    session = _FakeSession()
    wrote = await statute_queries.embed_statute_section(  # type: ignore[arg-type]
        session, "us-co/crs/38-12-999", citation=None, heading=" ", text=None
    )
    assert wrote is False
    assert session.calls == []
    assert embedder == []


@pytest.mark.asyncio
async def test_embed_statute_section_fails_open_without_writing(
    dead_embedder: None,
) -> None:
    session = _FakeSession()
    wrote = await statute_queries.embed_statute_section(  # type: ignore[arg-type]
        session,
        "us-co/crs/38-12-103",
        citation="C.R.S. § 38-12-103",
        heading="Security deposits",
        text="Return within one month.",
    )
    assert wrote is False
    assert session.calls == []
