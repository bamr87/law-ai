"""PrecedentHunter on real GraphRAG retrieval (BL-20260511-06).

Every case here injects a fake retriever: the agent must be exercisable with
no Neo4j running, and the honesty contract (empty set ⇒ degraded, confidence
0.0, "not in this corpus" wording) must hold on every path.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

import pytest

from law_ai.agents_runtime.crews.precedent_hunter import (
    DEGRADED_MODEL_LABEL,
    RETRIEVAL_MODEL_LABEL,
    PrecedentHunter,
    _confidence_from,
    _to_precedent,
    _year_of,
)
from law_ai.agents_runtime.tools.graph_rag import RetrievalCoverage


def _case(
    case_id: str,
    *,
    score: float = 1.0,
    court: str = "SCOTUS",
    decided_at: str | None = "1954-05-17",
    mode: str = "lexical",
) -> dict[str, Any]:
    return {
        "id": case_id,
        "type": "Case",
        "title": f"{case_id} title",
        "snippet": "holding text",
        "source_url": f"https://example.test/{case_id}",
        "court": court,
        "decided_at": decided_at,
        "source": "courtlistener",
        "confidence": 0.9,
        "score": score,
        "retrieval_mode": mode,
    }


class _FakeRetriever:
    """Stands in for GraphRAGRetriever: records state, publishes coverage."""

    def __init__(
        self,
        passages: list[dict[str, Any]] | None = None,
        coverage: RetrievalCoverage | None = None,
        *,
        raises: Exception | None = None,
    ) -> None:
        self._passages = passages or []
        self.last_coverage = coverage or RetrievalCoverage()
        self._raises = raises
        self.calls: list[dict[str, Any]] = []

    async def __call__(self, state: dict[str, Any]) -> list[dict[str, Any]]:
        self.calls.append(dict(state))
        if self._raises is not None:
            raise self._raises
        return list(self._passages)


class TestMapping:
    def test_year_of(self) -> None:
        assert _year_of("1954-05-17") == 1954
        assert _year_of(None) == 0
        assert _year_of("n/a") == 0

    def test_statutes_are_not_precedent(self) -> None:
        assert (
            _to_precedent({"type": "StatuteSection", "id": "17 U.S.C. § 107"}) is None
        )

    def test_rows_without_an_id_are_dropped(self) -> None:
        assert _to_precedent({"type": "Case", "id": ""}) is None

    def test_case_row_carries_source_and_url(self) -> None:
        p = _to_precedent(_case("brown-v-board"))
        assert p is not None
        assert p.case_id == "brown-v-board"
        assert p.url == "https://example.test/brown-v-board"
        assert p.court == "SCOTUS"
        assert p.year == 1954
        assert p.source == "courtlistener"
        assert p.graph_confidence == 0.9

    def test_missing_court_is_blank_not_guessed(self) -> None:
        p = _to_precedent(_case("x", court="", decided_at=None))
        assert p is not None
        assert p.court == ""
        assert p.year == 0

    def test_confidence_never_rises_on_an_empty_set(self) -> None:
        assert _confidence_from([], RetrievalCoverage(result_count=0)) == 0.0

    def test_confidence_is_halved_when_the_jurisdiction_is_absent(self) -> None:
        ps = [_to_precedent(_case(f"c{i}")) for i in range(5)]
        found = [p for p in ps if p is not None]
        full = _confidence_from(found, RetrievalCoverage())
        lopsided = _confidence_from(found, RetrievalCoverage(jurisdiction_absent=True))
        assert lopsided == pytest.approx(full / 2)
        assert full <= 0.8


class TestRun:
    @pytest.mark.asyncio
    async def test_populated_retrieval_produces_ranked_precedents(self) -> None:
        retriever = _FakeRetriever(
            [
                _case("low", score=0.2),
                _case("high", score=9.0, mode="citation_expansion"),
                {"type": "StatuteSection", "id": "42 U.S.C. § 1983"},
            ],
            RetrievalCoverage(
                queries=["equal protection"],
                result_count=3,
                lexical_count=2,
                expanded_count=1,
                jurisdictions_present=["SCOTUS"],
            ),
        )
        agent = PrecedentHunter(retriever=retriever)
        with patch(
            "law_ai.agents_runtime.crews.precedent_hunter.provenance.log_agent_call",
            return_value="trace-1",
        ) as log:
            out = await agent.run(
                {"text": "equal protection in schools", "jurisdiction": "us"}
            )

        assert [p.case_id for p in out.precedents] == ["high", "low"]
        assert out.precedents[0].retrieval_mode == "citation_expansion"
        assert out.degraded is False
        assert 0.0 < out.confidence <= 0.8
        assert out.trace_id == "trace-1"
        # The coverage envelope is relayed verbatim, not paraphrased.
        assert out.coverage_note == retriever.last_coverage.note()
        assert out.coverage_note in out.summary
        # Provenance names the retriever, never a model that was not called.
        assert log.call_args.args[3] == RETRIEVAL_MODEL_LABEL
        assert len(log.call_args.kwargs["sources"]) == 2
        # The retriever saw the question and jurisdiction it was given.
        assert retriever.calls[0]["queries"] == ["equal protection in schools"]
        assert retriever.calls[0]["jurisdiction"] == "us"

    @pytest.mark.asyncio
    async def test_empty_corpus_stays_degraded_and_says_so(self) -> None:
        retriever = _FakeRetriever([], RetrievalCoverage(queries=["x"]))
        agent = PrecedentHunter(retriever=retriever)
        with patch(
            "law_ai.agents_runtime.crews.precedent_hunter.provenance.log_agent_call",
            return_value="t",
        ) as log:
            out = await agent.run({"text": "some question"})

        assert out.precedents == []
        assert out.degraded is True
        assert out.confidence == 0.0
        assert "does NOT mean no relevant precedent exists" in out.summary
        # It retrieved for real, so the label reflects that, not "unimplemented".
        assert log.call_args.args[3] == RETRIEVAL_MODEL_LABEL

    @pytest.mark.asyncio
    async def test_graph_fault_degrades_instead_of_raising(self) -> None:
        retriever = _FakeRetriever(raises=OSError("neo4j down"))
        agent = PrecedentHunter(retriever=retriever)
        with patch(
            "law_ai.agents_runtime.crews.precedent_hunter.provenance.log_agent_call",
            return_value="t",
        ) as log:
            out = await agent.run({"text": "some question"})

        assert out.degraded is True
        assert out.confidence == 0.0
        assert "knowledge graph was unreachable" in out.summary
        assert log.call_args.args[3] == DEGRADED_MODEL_LABEL

    @pytest.mark.asyncio
    async def test_no_question_does_not_touch_the_graph(self) -> None:
        retriever = _FakeRetriever([_case("never-seen")])
        agent = PrecedentHunter(retriever=retriever)
        with patch(
            "law_ai.agents_runtime.crews.precedent_hunter.provenance.log_agent_call",
            return_value="t",
        ):
            out = await agent.run({"text": "   "})

        assert retriever.calls == []
        assert out.degraded is True
        assert out.confidence == 0.0

    @pytest.mark.asyncio
    async def test_default_retriever_is_graph_rag(self) -> None:
        """The zero-arg constructor the API uses wires the real retriever."""
        from law_ai.agents_runtime.tools.graph_rag import GraphRAGRetriever

        assert isinstance(PrecedentHunter()._get_retriever(), GraphRAGRetriever)
