"""`:Case.holding_summary` is populated at ingest (BL-20260810-19).

The field is fulltext-indexed (migration 007) and is what GraphRAG renders as
the passage snippet, but nothing ever wrote it, so every retrieved passage
degraded to "(no holding summary stored)". These tests cover the excerpt
deriver, its persistence, and the retrieval snippet it feeds.
"""

from __future__ import annotations

from typing import Any

import pytest

from law_ai.core.neo4j import queries as neo4j_queries
from law_ai.core.schemas.extraction import ExtractionResult
from law_ai.ingestionapp.services import scout as scout_module
from law_ai.ingestionapp.services.scout import IngestionScout

pytestmark = pytest.mark.unit

_PARAGRAPH = (
    "The district court held that the statute of limitations barred the "
    "plaintiff's claim because the cause of action accrued when the injury "
    "was discovered rather than when the negligent act occurred, and the "
    "complaint was filed more than two years after that date. "
)


# ---------------------------------------------------------------------------
# The deriver
# ---------------------------------------------------------------------------
def test_derive_holding_summary_returns_none_for_empty_text() -> None:
    assert scout_module.derive_holding_summary("") is None
    assert scout_module.derive_holding_summary("   \n\n  ") is None


def test_derive_holding_summary_skips_short_caption_lines() -> None:
    text = f"No. 21-1234\n\nDecided March 3, 2022\n\n{_PARAGRAPH}"
    out = scout_module.derive_holding_summary(text)
    assert out is not None
    assert out.startswith("The district court held")
    assert "No. 21-1234" not in out


def test_derive_holding_summary_falls_back_to_first_paragraph_when_all_short() -> None:
    out = scout_module.derive_holding_summary("Affirmed.\n\nSo ordered.")
    assert out == "Affirmed."


def test_derive_holding_summary_collapses_whitespace() -> None:
    out = scout_module.derive_holding_summary(f"{_PARAGRAPH}\n  with\t a   wrap")
    assert out is not None
    assert "\n" not in out
    assert "  " not in out


def test_derive_holding_summary_truncates_on_a_word_boundary() -> None:
    out = scout_module.derive_holding_summary(_PARAGRAPH * 10)
    assert out is not None
    assert len(out) <= scout_module.HOLDING_EXCERPT_MAX_CHARS + 1
    assert out.endswith("…")
    # Truncation must not cut mid-word.
    assert not out[:-1].rstrip().endswith(" ")


def test_derive_holding_summary_strips_html_when_flagged() -> None:
    html = f"<div class='opinion'><p>{_PARAGRAPH}</p></div>"
    out = scout_module.derive_holding_summary(html, is_html=True)
    assert out is not None
    assert "<p>" not in out and "div" not in out
    assert out.startswith("The district court held")


# ---------------------------------------------------------------------------
# End-to-end through IngestionScout.extract
# ---------------------------------------------------------------------------
def test_extract_populates_holding_summary_from_plain_text() -> None:
    result = IngestionScout().extract(
        {"id": 1, "case_name": "Doe v. Roe", "plain_text": _PARAGRAPH * 3}
    )
    assert result.holding_summary
    assert result.holding_summary.startswith("The district court held")
    assert result.holding_summary_kind == "excerpt"


def test_extract_populates_holding_summary_from_html_body() -> None:
    result = IngestionScout().extract(
        {
            "id": 2,
            "case_name": "Doe v. Roe",
            "html_with_citations": f"<p>{_PARAGRAPH}</p>",
        }
    )
    assert result.holding_summary
    assert "<p>" not in result.holding_summary
    assert result.holding_summary_kind == "excerpt"


def test_extract_leaves_holding_summary_none_for_bodyless_payload() -> None:
    result = IngestionScout().extract({"id": 3, "case_name": "Doe v. Roe"})
    assert result.holding_summary is None
    assert result.holding_summary_kind is None


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------
class _FakeResult:
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
async def test_commit_extraction_binds_and_merges_holding_summary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _no_embed(*args: Any, **kwargs: Any) -> None:
        return None

    monkeypatch.setattr(neo4j_queries, "embed_case", _no_embed)
    session = _FakeSession()
    await neo4j_queries.commit_extraction(  # type: ignore[arg-type]
        session,
        ExtractionResult(
            case_id="1",
            title="Doe v. Roe",
            confidence=0.9,
            holding_summary="Held: the claim is time-barred.",
            holding_summary_kind="excerpt",
        ),
    )
    cypher, params = session.calls[0]
    assert params["holding_summary"] == "Held: the claim is time-barred."
    assert params["holding_summary_kind"] == "excerpt"
    # The MERGE actually SETs it — the old query bound nothing at all.
    assert "c.holding_summary = $holding_summary" in cypher
    assert "c.holding_summary = coalesce($holding_summary, c.holding_summary)" in cypher


# ---------------------------------------------------------------------------
# Retrieval snippet
# ---------------------------------------------------------------------------
def test_case_passage_snippet_is_the_summary_not_the_placeholder() -> None:
    from law_ai.agents_runtime.tools import graph_rag

    passage = graph_rag._case_passage(
        {
            "id": "1",
            "title": "Doe v. Roe",
            "holding_summary": "Held: the claim is time-barred.",
            "holding_summary_kind": "excerpt",
        },
        retrieval_mode="lexical",
    )
    assert passage["snippet"] == "Held: the claim is time-barred."
    assert "no holding summary stored" not in passage["snippet"]
    assert passage["snippet_kind"] == "excerpt"


def test_case_passage_still_reports_absence_when_nothing_stored() -> None:
    from law_ai.agents_runtime.tools import graph_rag

    passage = graph_rag._case_passage(
        {"id": "1", "title": "Doe v. Roe"}, retrieval_mode="lexical"
    )
    assert "no holding summary stored" in passage["snippet"]
    assert passage["snippet_kind"] is None


def test_case_fulltext_cypher_returns_the_kind() -> None:
    from law_ai.agents_runtime.tools import graph_rag

    for cypher in (
        graph_rag.CASE_FULLTEXT_CYPHER,
        graph_rag.CASE_SUBSTRING_CYPHER,
        graph_rag.CASE_VECTOR_CYPHER,
        graph_rag.EXPAND_CITES_CYPHER,
    ):
        assert "holding_summary_kind" in cypher
