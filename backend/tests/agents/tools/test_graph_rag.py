"""Tests for the hybrid GraphRAG retriever (BL-20260810-01).

Uses a fake Neo4j session so no database is required.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any

import pytest

from law_ai.agents_runtime.tools.graph_rag import (
    CASE_FULLTEXT_CYPHER,
    CASE_VECTOR_CYPHER,
    EXPAND_CITES_CYPHER,
    STATUTE_FULLTEXT_CYPHER,
    STATUTE_VECTOR_CYPHER,
    GraphRAGRetriever,
    RetrievalCoverage,
    escape_lucene,
    reciprocal_rank_fusion,
)


class _FakeResult:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self._rows = rows

    def __aiter__(self):
        async def gen():
            for row in self._rows:
                yield row

        return gen()


class FakeSession:
    """Routes each Cypher string to a canned row list; records calls."""

    def __init__(self, routes: dict[str, Any]) -> None:
        self.routes = routes
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def run(self, cypher: str, params: dict[str, Any]) -> _FakeResult:
        self.calls.append((cypher, params))
        for marker, value in self.routes.items():
            if marker in cypher:
                if isinstance(value, Exception):
                    raise value
                return _FakeResult(value)
        return _FakeResult([])


def _session_factory(session: FakeSession) -> Any:
    @asynccontextmanager
    async def factory() -> Any:
        yield session

    return factory


_CASE_ROW = {
    "id": "case:1",
    "title": "Marbury v. Madison",
    "holding_summary": "Established judicial review.",
    "court": "us-supreme",
    "decided_at": "1803-02-24",
    "source": "courtlistener",
    "source_url": "https://example.test/marbury",
    "confidence": 0.95,
    "score": 3.2,
}

_NEIGHBOR_ROW = {
    "id": "case:2",
    "title": "Cohens v. Virginia",
    "holding_summary": "Extended federal review.",
    "court": "us-supreme",
    "decided_at": "1821-03-03",
    "source": "courtlistener",
    "source_url": "https://example.test/cohens",
    "confidence": 0.9,
    "cited_by_seeds": 1,
}


class TestEscapeLucene:
    def test_escapes_metacharacters(self) -> None:
        assert escape_lucene("negligence?") == "negligence\\?"
        assert escape_lucene('a "quoted" term') == 'a \\"quoted\\" term'
        assert escape_lucene("a:b") == "a\\:b"

    def test_leaves_plain_text_alone(self) -> None:
        assert escape_lucene("judicial review") == "judicial review"


class TestRetrieval:
    @pytest.mark.asyncio
    async def test_lexical_hits_plus_graph_expansion(self) -> None:
        session = FakeSession(
            {
                "node.holding_summary AS holding_summary": [_CASE_ROW],
                "MATCH (seed:Case)-[r:CITES]": [_NEIGHBOR_ROW],
            }
        )
        retriever = GraphRAGRetriever(session_factory=_session_factory(session))
        passages = await retriever(
            {"question": "judicial review?", "queries": ["judicial review"]}
        )

        by_id = {p["id"]: p for p in passages}
        assert set(by_id) == {"case:1", "case:2"}
        # §13 attribution travels with the passage.
        assert by_id["case:1"]["court"] == "us-supreme"
        assert by_id["case:1"]["decided_at"] == "1803-02-24"
        assert by_id["case:1"]["retrieval_mode"] == "lexical"
        # The graph hop is what makes this GraphRAG, not plain search.
        assert by_id["case:2"]["retrieval_mode"] == "cites_expansion"
        assert retriever.last_coverage.expanded_count == 1
        assert retriever.last_coverage.result_count == 2

    @pytest.mark.asyncio
    async def test_falls_back_to_substring_when_index_missing(self) -> None:
        session = FakeSession(
            {
                "node.holding_summary AS holding_summary": RuntimeError(
                    "no such index"
                ),
                "MATCH (c:Case)": [_CASE_ROW],
                "MATCH (seed:Case)-[r:CITES]": [],
            }
        )
        retriever = GraphRAGRetriever(session_factory=_session_factory(session))
        passages = await retriever({"queries": ["judicial review"]})

        assert [p["id"] for p in passages] == ["case:1"]
        assert retriever.last_coverage.index_available is False
        assert "fulltext index is missing" not in retriever.last_coverage.note()

    @pytest.mark.asyncio
    async def test_reports_absent_jurisdiction(self) -> None:
        session = FakeSession(
            {
                "node.holding_summary AS holding_summary": [_CASE_ROW],
                "MATCH (seed:Case)-[r:CITES]": [],
            }
        )
        retriever = GraphRAGRetriever(session_factory=_session_factory(session))
        await retriever({"queries": ["q"], "jurisdiction": "co-district"})

        cov = retriever.last_coverage
        assert cov.jurisdiction_absent is True
        assert "no results from the requested jurisdiction" in cov.note()

    @pytest.mark.asyncio
    async def test_graph_failure_degrades_to_empty(self) -> None:
        session = FakeSession(
            {"node.holding_summary AS holding_summary": RuntimeError("neo4j down")}
        )
        # Substring fallback also fails ⇒ retrieval yields nothing, honestly.
        session.routes["MATCH (c:Case)"] = RuntimeError("neo4j down")
        retriever = GraphRAGRetriever(session_factory=_session_factory(session))
        passages = await retriever({"queries": ["q"]})

        assert passages == []
        assert retriever.last_coverage.result_count == 0
        assert "does NOT mean no such law exists" in retriever.last_coverage.note()

    @pytest.mark.asyncio
    async def test_no_queries_returns_empty_without_touching_db(self) -> None:
        session = FakeSession({})
        retriever = GraphRAGRetriever(session_factory=_session_factory(session))
        assert await retriever({}) == []
        assert session.calls == []

    @pytest.mark.asyncio
    async def test_logs_every_cypher_through_provenance(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Constitution §4: retrievals are audited, not silent."""
        import law_ai.agents_runtime.tools.graph_rag as mod

        logged: list[tuple[str, int]] = []
        monkeypatch.setattr(
            mod.provenance,
            "log_graph_query",
            lambda cypher, params, count, latency: logged.append((cypher, count)),
        )
        session = FakeSession(
            {
                "node.holding_summary AS holding_summary": [_CASE_ROW],
                "MATCH (seed:Case)-[r:CITES]": [_NEIGHBOR_ROW],
            }
        )
        retriever = GraphRAGRetriever(session_factory=_session_factory(session))
        await retriever({"queries": ["q"]})

        assert logged, "no graph queries were logged"
        assert any(c == CASE_FULLTEXT_CYPHER for c, _ in logged)
        assert any(c == EXPAND_CITES_CYPHER for c, _ in logged)


class TestCoverageNote:
    def test_empty_corpus_note_names_the_distinction(self) -> None:
        note = RetrievalCoverage(result_count=0).note()
        assert "does NOT mean no such law exists" in note

    def test_missing_index_is_disclosed(self) -> None:
        note = RetrievalCoverage(result_count=0, index_available=False).note()
        assert "fulltext index is missing" in note


class TestCoverageDateSpan:
    """BL-20260803-02: the envelope reports the date range it can speak to."""

    @pytest.mark.asyncio
    async def test_span_is_computed_from_retrieved_passages(self) -> None:
        session = FakeSession(
            {
                "node.holding_summary AS holding_summary": [_CASE_ROW],
                "MATCH (seed:Case)-[r:CITES]": [_NEIGHBOR_ROW],
            }
        )
        retriever = GraphRAGRetriever(session_factory=_session_factory(session))
        await retriever({"question": "judicial review", "queries": ["judicial review"]})

        coverage = retriever.last_coverage
        assert coverage.date_earliest == "1803-02-24"
        assert coverage.date_latest == "1821-03-03"
        assert "1803-02-24 to 1821-03-03" in coverage.note()

    @pytest.mark.asyncio
    async def test_no_dates_leaves_the_span_unset(self) -> None:
        undated = {**_CASE_ROW, "decided_at": None}
        session = FakeSession({"node.holding_summary AS holding_summary": [undated]})
        retriever = GraphRAGRetriever(
            session_factory=_session_factory(session), include_statutes=False
        )
        await retriever({"question": "x", "queries": ["x"]})

        coverage = retriever.last_coverage
        assert coverage.date_earliest is None
        assert coverage.date_latest is None
        assert "Decision dates represented" not in coverage.note()

    def test_single_date_reads_as_one_date_not_a_range(self) -> None:
        note = RetrievalCoverage(
            result_count=1,
            lexical_count=1,
            date_earliest="1954-05-17",
            date_latest="1954-05-17",
        ).note()
        assert "Decision dates represented: 1954-05-17;" in note
        # One date, not a range: no "<from> to <to>" span rendered.
        assert "1954-05-17 to " not in note


# ---------------------------------------------------------------------------
# BL-20260810-17: the vector leg + reciprocal-rank fusion
# ---------------------------------------------------------------------------


def _passage(pid: str, mode: str = "lexical") -> dict[str, Any]:
    return {"id": pid, "type": "Case", "retrieval_mode": mode}


class TestReciprocalRankFusion:
    def test_agreement_beats_a_single_strong_hit(self) -> None:
        """A doc ranked 2nd on both legs outranks one ranked 1st on only one."""
        lexical = [_passage("a"), _passage("b")]
        vector = [_passage("c", "vector"), _passage("b", "vector")]
        fused = reciprocal_rank_fusion([lexical, vector])
        assert fused[0]["id"] == "b"

    def test_marks_passages_found_by_both_legs(self) -> None:
        fused = reciprocal_rank_fusion([[_passage("b")], [_passage("b", "vector")]])
        assert fused[0]["retrieval_mode"] == "lexical+vector"
        assert fused[0]["fusion_score"] > 0

    def test_single_leg_keeps_its_own_order_and_mode(self) -> None:
        fused = reciprocal_rank_fusion([[_passage("a"), _passage("b")], []])
        assert [p["id"] for p in fused] == ["a", "b"]
        assert fused[0]["retrieval_mode"] == "lexical"

    def test_is_deterministic_for_equal_scores(self) -> None:
        first = reciprocal_rank_fusion([[_passage("z")], [_passage("a", "vector")]])
        second = reciprocal_rank_fusion([[_passage("z")], [_passage("a", "vector")]])
        assert [p["id"] for p in first] == [p["id"] for p in second]

    def test_empty_input_is_empty_output(self) -> None:
        assert reciprocal_rank_fusion([]) == []
        assert reciprocal_rank_fusion([[], []]) == []


_VECTOR_ROW = {
    "id": "case:3",
    "title": "Semantic Match v. Corpus",
    "holding_summary": "Only the embeddings found this one.",
    "court": "us-supreme",
    "decided_at": "1990-01-01",
    "source": "courtlistener",
    "source_url": "https://example.test/semantic",
    "confidence": 0.8,
    "score": 0.91,
}


class TestVectorLeg:
    @staticmethod
    def _patch_embedder(monkeypatch: pytest.MonkeyPatch, vector) -> None:
        from law_ai.core.llm import embeddings

        async def fake_embed(text: str, *, component: str = "graph"):
            return vector

        monkeypatch.setattr(embeddings, "embed_text", fake_embed)

    @pytest.mark.asyncio
    async def test_vector_hits_are_fused_with_lexical_hits(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        self._patch_embedder(monkeypatch, [0.1] * 768)
        session = FakeSession(
            {
                CASE_VECTOR_CYPHER: [_VECTOR_ROW],
                "node.holding_summary AS holding_summary": [_CASE_ROW],
                "MATCH (seed:Case)-[r:CITES]": [],
            }
        )
        retriever = GraphRAGRetriever(session_factory=_session_factory(session))
        passages = await retriever({"queries": ["judicial review"]})

        by_id = {p["id"]: p for p in passages}
        assert "case:3" in by_id, "the vector-only hit must survive fusion"
        assert by_id["case:3"]["retrieval_mode"] == "vector"
        assert retriever.last_coverage.vector_available is True
        assert retriever.last_coverage.vector_count == 1
        # The query embedding is bound as a parameter, never interpolated.
        vector_call = next(
            params for cypher, params in session.calls if cypher == CASE_VECTOR_CYPHER
        )
        assert vector_call["embedding"] == [0.1] * 768
        assert vector_call["index"] == "case_embedding_vec"

    @pytest.mark.asyncio
    async def test_missing_embedder_degrades_to_lexical(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """No Ollama → the pre-BL-20260810-17 behaviour, and the note says so."""
        self._patch_embedder(monkeypatch, None)
        session = FakeSession(
            {
                "node.holding_summary AS holding_summary": [_CASE_ROW],
                "MATCH (seed:Case)-[r:CITES]": [],
            }
        )
        retriever = GraphRAGRetriever(session_factory=_session_factory(session))
        passages = await retriever({"queries": ["judicial review"]})

        assert [p["id"] for p in passages] == ["case:1"]
        assert retriever.last_coverage.vector_available is False
        assert "semantic (vector) leg was unavailable" in (
            retriever.last_coverage.note()
        )
        assert not any(
            "db.index.vector.queryNodes" in cypher for cypher, _ in session.calls
        )

    @pytest.mark.asyncio
    async def test_missing_vector_index_degrades_to_lexical(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Migration 008 not applied → skip the leg, do not fail the run."""
        self._patch_embedder(monkeypatch, [0.2] * 768)
        session = FakeSession(
            {
                CASE_VECTOR_CYPHER: RuntimeError("no such index"),
                "node.holding_summary AS holding_summary": [_CASE_ROW],
                "MATCH (seed:Case)-[r:CITES]": [],
            }
        )
        retriever = GraphRAGRetriever(session_factory=_session_factory(session))
        passages = await retriever({"queries": ["judicial review"]})

        assert [p["id"] for p in passages] == ["case:1"]
        assert retriever.last_coverage.vector_available is False

    @pytest.mark.asyncio
    async def test_coverage_note_counts_the_semantic_leg(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        self._patch_embedder(monkeypatch, [0.3] * 768)
        session = FakeSession(
            {
                CASE_VECTOR_CYPHER: [_VECTOR_ROW],
                "node.holding_summary AS holding_summary": [_CASE_ROW],
                "MATCH (seed:Case)-[r:CITES]": [_NEIGHBOR_ROW],
            }
        )
        retriever = GraphRAGRetriever(session_factory=_session_factory(session))
        await retriever({"queries": ["judicial review"]})
        note = retriever.last_coverage.note()
        assert "semantic" in note
        assert "via citation expansion" in note


# ---------------------------------------------------------------------------
# BL-20260810-17: the :StatuteSection half of the vector leg
# ---------------------------------------------------------------------------


_STATUTE_ROW = {
    "citation": "C.R.S. § 38-12-103",
    "heading": "Return of security deposit",
    "text": "A landlord shall return the security deposit within one month.",
    "jurisdiction_code": "us-co",
    "source": "colorado_statutes",
    "source_url": "https://example.test/38-12-103",
    "confidence": 0.9,
    "score": 2.1,
}

_STATUTE_VECTOR_ROW = {
    "citation": "C.R.S. § 38-12-104",
    "heading": "Wrongful withholding",
    "text": "Wilful retention of a deposit exposes the landlord to treble damages.",
    "jurisdiction_code": "us-co",
    "source": "colorado_statutes",
    "source_url": "https://example.test/38-12-104",
    "confidence": 0.88,
    "score": 0.77,
}


def _statute_routes(vector: Any, lexical: Any) -> dict[str, Any]:
    """Route the two statute queries apart.

    Both Cypher strings contain ``db.index.vector.queryNodes`` /
    ``node.citation AS citation``, so the exact constants are used as the
    markers; :class:`FakeSession` matches them in insertion order.
    """
    return {
        STATUTE_VECTOR_CYPHER: vector,
        STATUTE_FULLTEXT_CYPHER: lexical,
        "db.index.vector.queryNodes": [],
        "node.holding_summary AS holding_summary": [_CASE_ROW],
        "MATCH (seed:Case)-[r:CITES]": [],
    }


class TestStatuteVectorLeg:
    @staticmethod
    def _patch_embedder(monkeypatch: pytest.MonkeyPatch, vector: Any) -> None:
        from law_ai.core.llm import embeddings

        async def fake_embed(text: str, *, component: str = "graph") -> Any:
            return vector

        monkeypatch.setattr(embeddings, "embed_text", fake_embed)

    @pytest.mark.asyncio
    async def test_vector_only_section_survives_fusion(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A section only the embeddings found is retrieved and counted."""
        self._patch_embedder(monkeypatch, [0.5] * 768)
        session = FakeSession(_statute_routes([_STATUTE_VECTOR_ROW], [_STATUTE_ROW]))
        retriever = GraphRAGRetriever(session_factory=_session_factory(session))
        passages = await retriever({"queries": ["can my landlord keep the deposit"]})

        by_id = {p["id"]: p for p in passages}
        assert "C.R.S. § 38-12-104" in by_id, "vector-only section must survive fusion"
        assert by_id["C.R.S. § 38-12-104"]["retrieval_mode"] == "vector"
        assert by_id["C.R.S. § 38-12-104"]["type"] == "StatuteSection"
        assert by_id["C.R.S. § 38-12-103"]["retrieval_mode"] == "lexical"
        assert retriever.last_coverage.vector_available is True
        # Both statute passages plus the lexical case; one came from vectors.
        assert retriever.last_coverage.vector_count == 1

    @pytest.mark.asyncio
    async def test_query_is_bound_to_the_statute_vector_index(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The statute index is actually queried, with the embedding bound."""
        self._patch_embedder(monkeypatch, [0.5] * 768)
        session = FakeSession(_statute_routes([_STATUTE_VECTOR_ROW], [_STATUTE_ROW]))
        retriever = GraphRAGRetriever(session_factory=_session_factory(session))
        await retriever({"queries": ["security deposit"]})

        call = next(
            params
            for cypher, params in session.calls
            if cypher == STATUTE_VECTOR_CYPHER
        )
        assert call["index"] == "statute_section_embedding_vec"
        assert call["embedding"] == [0.5] * 768

    @pytest.mark.asyncio
    async def test_a_section_on_both_legs_is_marked_as_such(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        self._patch_embedder(monkeypatch, [0.5] * 768)
        session = FakeSession(_statute_routes([_STATUTE_ROW], [_STATUTE_ROW]))
        retriever = GraphRAGRetriever(session_factory=_session_factory(session))
        passages = await retriever({"queries": ["security deposit"]})

        section = next(p for p in passages if p["type"] == "StatuteSection")
        assert section["retrieval_mode"] == "lexical+vector"
        assert section["fusion_score"] > 0

    @pytest.mark.asyncio
    async def test_missing_statute_vector_index_degrades_to_lexical(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Migration 008 not applied → keep the fulltext sections, flag it."""
        self._patch_embedder(monkeypatch, [0.5] * 768)
        session = FakeSession(
            _statute_routes(RuntimeError("no such index"), [_STATUTE_ROW])
        )
        retriever = GraphRAGRetriever(session_factory=_session_factory(session))
        passages = await retriever({"queries": ["security deposit"]})

        assert [p["id"] for p in passages if p["type"] == "StatuteSection"] == [
            "C.R.S. § 38-12-103"
        ]
        assert retriever.last_coverage.vector_available is False

    @pytest.mark.asyncio
    async def test_no_embedder_means_no_statute_vector_query(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        self._patch_embedder(monkeypatch, None)
        session = FakeSession(_statute_routes([_STATUTE_VECTOR_ROW], [_STATUTE_ROW]))
        retriever = GraphRAGRetriever(session_factory=_session_factory(session))
        passages = await retriever({"queries": ["security deposit"]})

        assert not any(cypher == STATUTE_VECTOR_CYPHER for cypher, _ in session.calls)
        assert [p["id"] for p in passages if p["type"] == "StatuteSection"] == [
            "C.R.S. § 38-12-103"
        ]
        assert retriever.last_coverage.vector_available is False

    @pytest.mark.asyncio
    async def test_statutes_excluded_skips_the_statute_vector_query(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        self._patch_embedder(monkeypatch, [0.5] * 768)
        session = FakeSession(_statute_routes([_STATUTE_VECTOR_ROW], [_STATUTE_ROW]))
        retriever = GraphRAGRetriever(
            session_factory=_session_factory(session), include_statutes=False
        )
        await retriever({"queries": ["security deposit"]})
        assert not any(cypher == STATUTE_VECTOR_CYPHER for cypher, _ in session.calls)

    @pytest.mark.asyncio
    async def test_one_embedding_serves_both_label_legs(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Both vector queries reuse a single embed call per query string."""
        from law_ai.core.llm import embeddings

        calls: list[str] = []

        async def fake_embed(text: str, *, component: str = "graph") -> Any:
            calls.append(text)
            return [0.5] * 768

        monkeypatch.setattr(embeddings, "embed_text", fake_embed)
        session = FakeSession(_statute_routes([_STATUTE_VECTOR_ROW], [_STATUTE_ROW]))
        retriever = GraphRAGRetriever(session_factory=_session_factory(session))
        await retriever({"queries": ["security deposit", "landlord duties"]})

        assert calls == ["security deposit", "landlord duties"]
        assert (
            sum(1 for cypher, _ in session.calls if cypher == STATUTE_VECTOR_CYPHER)
            == 2
        )
