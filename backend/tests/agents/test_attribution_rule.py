"""Constitution §13 attribution assertions on agent output (BL-20260803-04).

The deterministic contract is per-citation: every citation an analysis crew
emits carries court + jurisdiction + decided_at + binding/persuasive, or the
output is pinned for human review. "Every legal proposition in prose" is not
mechanically checkable; an LLM-judged version belongs in a legalbench-marked
test, not here.
"""

from __future__ import annotations

from typing import Any

import pytest

from law_ai.agents_runtime.attribution import (
    Attribution,
    attribution_from_passage,
    check_attribution,
    classify_authority,
    jurisdiction_of,
    match_passage,
)


def _passage(**over: Any) -> dict[str, Any]:
    base = {
        "id": "case:1",
        "type": "Case",
        "title": "Marbury v. Madison",
        "snippet": "Established judicial review.",
        "source_url": "https://example.test/marbury",
        "court": "us-supreme",
        "decided_at": "1803-02-24",
    }
    base.update(over)
    return base


class TestPrimitives:
    def test_jurisdiction_of_strips_the_narrowing_segment(self) -> None:
        assert jurisdiction_of("us-ca-9") == "us-ca"
        assert jurisdiction_of("us-supreme") == "us"
        assert jurisdiction_of("us") == "us"
        assert jurisdiction_of(None) is None
        assert jurisdiction_of("  ") is None

    def test_binding_when_the_court_sits_under_the_request(self) -> None:
        assert classify_authority("us-ca-9", "us-ca") == "binding"
        assert classify_authority("us-ca", "us-ca") == "binding"

    def test_persuasive_when_it_sits_elsewhere(self) -> None:
        assert classify_authority("us-ny", "us-ca") == "persuasive"

    def test_unknown_rather_than_a_guess_when_either_side_is_missing(self) -> None:
        assert classify_authority("us-ca-9", None) == "unknown"
        assert classify_authority(None, "us-ca") == "unknown"
        assert classify_authority("", "") == "unknown"

    def test_attribution_from_passage_reads_the_graph_not_prose(self) -> None:
        attribution = attribution_from_passage(_passage(), "us")
        assert attribution.court == "us-supreme"
        assert attribution.jurisdiction == "us"
        assert attribution.decided_at == "1803-02-24"
        assert attribution.authority == "binding"
        assert attribution.opinion_part == "unknown"
        assert attribution.complete is True

    def test_missing_passage_yields_an_empty_attribution(self) -> None:
        attribution = attribution_from_passage(None, "us")
        assert attribution.complete is False
        assert attribution.authority == "unknown"

    def test_statute_jurisdiction_code_wins_over_the_court_derivation(self) -> None:
        attribution = attribution_from_passage(
            {"jurisdiction_code": "us-tx", "court": None, "decided_at": "1999-01-01"},
            "us-tx",
        )
        assert attribution.jurisdiction == "us-tx"


class TestMatching:
    def test_source_url_wins(self) -> None:
        other = _passage(id="case:2", title="Other", source_url="https://x/other")
        found = match_passage(
            {"text": "Other", "source_url": "https://example.test/marbury"},
            [other, _passage()],
        )
        assert found is not None and found["id"] == "case:1"

    def test_title_fallback_when_no_url(self) -> None:
        found = match_passage(
            {"text": "As held in Marbury v. Madison, courts may review."},
            [_passage()],
        )
        assert found is not None and found["id"] == "case:1"

    def test_no_fuzzy_guessing(self) -> None:
        assert match_passage({"text": "Some unrelated proposition."}, [_passage()]) is (
            None
        )


class TestChecker:
    def test_complete_attribution_passes(self) -> None:
        citation = {
            "text": "Marbury v. Madison",
            "attribution": attribution_from_passage(_passage(), "us").model_dump(),
        }
        assert check_attribution([citation]) == []

    def test_missing_attribution_is_reported(self) -> None:
        problems = check_attribution([{"text": "Phantom v. Mirage"}])
        assert problems == ["Phantom v. Mirage: no attribution recorded"]

    def test_partial_attribution_names_the_missing_fields(self) -> None:
        citation = {
            "text": "Half v. Attributed",
            "attribution": Attribution(court="us-ca-9").model_dump(),
        }
        problems = check_attribution([citation])
        assert problems and "missing" in problems[0]
        assert "decided_at" in problems[0]

    def test_unlabelled_citation_gets_a_positional_label(self) -> None:
        assert check_attribution([{}]) == ["citation #1: no attribution recorded"]


# ---------------------------------------------------------------------------
# Agent-output assertions
# ---------------------------------------------------------------------------


class _FakeMessage:
    def __init__(self, text: str) -> None:
        self.content = text


class _FakeLLM:
    def __init__(self, responses: list[str]) -> None:
        self._responses = list(responses)

    async def ainvoke(self, prompt: str) -> _FakeMessage:
        return _FakeMessage(self._responses.pop(0) if self._responses else "{}")


async def _run_workflow(citations_json: str, passages: list[dict[str, Any]], **kw):
    pytest.importorskip("langgraph")
    from law_ai.agents_runtime.graphs.legal_workflow import LegalWorkflow

    async def resolver(names):  # type: ignore[no-untyped-def]
        return {n: f"case-{i}" for i, n in enumerate(names)}

    async def retriever(state):  # type: ignore[no-untyped-def]
        return passages

    # One instance for the whole run: `llm_factory` is called per node, so a
    # fresh object per call would hand `analyze` the `retrieve` response.
    llm = _FakeLLM(['{"queries": ["q"], "rationale": "ok"}', citations_json])
    wf = LegalWorkflow(
        llm_factory=lambda: llm,
        cite_resolver=resolver,
        retriever=retriever,
    )
    return await wf.invoke("Did Marbury establish judicial review?", **kw)


class TestLegalWorkflowAttribution:
    @pytest.mark.asyncio
    async def test_attributed_citation_passes_the_gate(self) -> None:
        out = await _run_workflow(
            '{"answer": "yes", "citations": [{"text": "Marbury v. Madison", '
            '"source_url": "https://example.test/marbury"}], "confidence": 0.9}',
            [_passage()],
            jurisdiction="us",
        )
        assert len(out.citations) == 1
        attribution = out.citations[0].attribution
        assert attribution is not None
        assert attribution["court"] == "us-supreme"
        assert attribution["jurisdiction"] == "us"
        assert attribution["decided_at"] == "1803-02-24"
        assert attribution["authority"] == "binding"
        # Fully attributed + resolved ⇒ no review forced by attribution.
        assert out.human_approval_required is False
        assert check_attribution([c.model_dump() for c in out.citations]) == []

    @pytest.mark.asyncio
    async def test_unattributed_citation_forces_review(self) -> None:
        """A citation the retrieval set cannot account for is flagged."""
        out = await _run_workflow(
            '{"answer": "yes", "citations": [{"text": "Phantom v. Mirage", '
            '"source_url": "https://example.test/phantom"}], "confidence": 0.9}',
            [_passage()],
            jurisdiction="us",
        )
        assert out.human_approval_required is True
        problems = check_attribution([c.model_dump() for c in out.citations])
        assert problems and "missing" in problems[0]

    @pytest.mark.asyncio
    async def test_out_of_jurisdiction_authority_is_persuasive_not_binding(
        self,
    ) -> None:
        out = await _run_workflow(
            '{"answer": "yes", "citations": [{"text": "Marbury v. Madison", '
            '"source_url": "https://example.test/marbury"}], "confidence": 0.9}',
            [_passage()],
            jurisdiction="us-tx",
        )
        attribution = out.citations[0].attribution
        assert attribution is not None
        assert attribution["authority"] == "persuasive"

    @pytest.mark.asyncio
    async def test_no_requested_jurisdiction_reads_unknown_never_binding(self) -> None:
        out = await _run_workflow(
            '{"answer": "yes", "citations": [{"text": "Marbury v. Madison", '
            '"source_url": "https://example.test/marbury"}], "confidence": 0.9}',
            [_passage()],
        )
        attribution = out.citations[0].attribution
        assert attribution is not None
        assert attribution["authority"] == "unknown"
        # Court/jurisdiction/date are still present, so §13's minimum holds.
        assert check_attribution([c.model_dump() for c in out.citations]) == []


class TestPrecedentHunterAttribution:
    @pytest.mark.asyncio
    async def test_every_precedent_carries_its_issuing_authority(self) -> None:
        from unittest.mock import patch

        from law_ai.agents_runtime.crews.precedent_hunter import PrecedentHunter

        class _Retriever:
            last_coverage = None

            async def __call__(self, state):  # type: ignore[no-untyped-def]
                return [_passage(score=2.0)]

        with patch(
            "law_ai.agents_runtime.crews.precedent_hunter.provenance.log_agent_call",
            return_value="t",
        ):
            out = await PrecedentHunter(retriever=_Retriever()).run(
                {"text": "judicial review", "jurisdiction": "us"}
            )

        assert out.precedents
        for precedent in out.precedents:
            attribution = Attribution.model_validate(precedent.attribution)
            assert attribution.complete, precedent.case_id
            assert attribution.authority == "binding"


class TestLegalAnalystAttribution:
    @pytest.mark.asyncio
    async def test_unresolved_authorities_keep_requires_review(self) -> None:
        """The direct-LLM path has no retrieval, so it can never attribute."""
        import json
        from unittest.mock import AsyncMock, patch

        from law_ai.agents_runtime.crews import legal_analyst as mod
        from law_ai.core.llm.base import LLMResult

        payload = json.dumps(
            {
                "issue": "i",
                "rule": "r",
                "application": "a",
                "conclusion": "c",
                "key_authorities": ["Ghost v. Nobody"],
                "confidence": 0.8,
            }
        )

        async def resolver(names):  # type: ignore[no-untyped-def]
            return dict.fromkeys(names)

        class _Empty:
            async def __call__(self, state):  # type: ignore[no-untyped-def]
                return []

        agent = mod.LegalAnalyst(cite_resolver=resolver, name_retriever=_Empty())
        with (
            patch.object(
                mod.llm,
                "agenerate",
                new=AsyncMock(
                    return_value=LLMResult(
                        text=payload,
                        provider="claude_code",
                        model="claude-opus-5",
                        latency_ms=1.0,
                    )
                ),
            ),
            patch.object(mod.provenance, "log_agent_call", return_value="t"),
        ):
            out = await agent.run({"text": "q"})

        # Every non-degraded output either carries attributable sources or
        # requires review — never an unattributed statement of law presented
        # as settled.
        assert out.requires_review is True
        assert all(not s.get("verified") for s in out.sources)
