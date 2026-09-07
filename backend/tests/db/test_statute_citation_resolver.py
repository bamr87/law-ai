"""Citation → StatuteSection resolution and CITES_STATUTE edges (BL-20260509-07).

`(:Case)-[:CITES_STATUTE]->(:StatuteSection)` was declared in the data model
from spec 015 but had no writer, so an opinion citing the CRS and the CRS
section it cited sat in the same graph unconnected. Hermetic — a fake session,
in the style of `tests/db/test_citation_resolver.py`.
"""

from __future__ import annotations

from typing import Any

import pytest

from law_ai.core.neo4j import citation_resolver, queries
from law_ai.core.schemas.extraction import Citation, ExtractionResult

pytestmark = pytest.mark.unit


class _FakeResult:
    def __init__(self, records: list[dict[str, Any]]) -> None:
        self._records = records

    def __aiter__(self) -> _FakeResult:
        self._iter = iter(self._records)
        return self

    async def __anext__(self) -> dict[str, Any]:
        try:
            return next(self._iter)
        except StopIteration as exc:  # pragma: no cover - protocol boilerplate
            raise StopAsyncIteration from exc


class FakeAsyncSession:
    def __init__(self, canned: list[list[dict[str, Any]]] | None = None) -> None:
        self._canned = list(canned or [])
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def run(self, cypher: str, params: dict[str, Any]) -> _FakeResult:
        self.calls.append((cypher, params))
        records = self._canned.pop(0) if self._canned else []
        return _FakeResult(records)


# ---------------------------------------------------------------------------
# The normalizer
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("normalized", "expected"),
    [
        ("colo. rev. stat. § 18-3-102", "us-co/crs/18-3-102"),
        ("colo. rev. stat. ann. § 18-3-102", "us-co/crs/18-3-102"),
        ("c.r.s. § 18-3-102", "us-co/crs/18-3-102"),
        ("c.r.s. § 18-3-102(1)(a)", "us-co/crs/18-3-102"),
        ("§ 13-80-102, c.r.s.", "us-co/crs/13-80-102"),
        ("c.r.s. § 13-21-115.7", "us-co/crs/13-21-115.7"),
        # Decimal articles are ordinary in the CRS (BL-20260906-89): the older
        # pattern allowed a decimal only in the last part, so this whole
        # family of sections produced no CITES_STATUTE edge.
        ("c.r.s. § 18-1.3-401", "us-co/crs/18-1.3-401"),
        ("c.r.s. § 18-1.3-401(1)(a)(V)", "us-co/crs/18-1.3-401"),
        ("§ 24-4.1-302, c.r.s.", "us-co/crs/24-4.1-302"),
    ],
)
def test_statute_section_id_matches_the_spec_015_id_format(
    normalized: str, expected: str
) -> None:
    assert citation_resolver.statute_section_id_from_normalized(normalized) == expected


@pytest.mark.parametrize(
    "normalized",
    [
        "",
        "410 u.s. 113",
        "brown v. board of education, 347 u.s. 483",
        "42 u.s.c. § 1983",
        # A section-shaped number with no recognised reporter: not a guess.
        "18-3-102",
        # A CRS reporter with no section number to hang an id on.
        "c.r.s.",
    ],
)
def test_statute_section_id_returns_none_rather_than_guessing(normalized: str) -> None:
    assert citation_resolver.statute_section_id_from_normalized(normalized) is None


def test_crs_reporters_all_keep_their_periods() -> None:
    """A bare "crs" would match inside unrelated words; a false link is worse."""
    assert all("." in reporter for reporter in citation_resolver.CRS_REPORTERS)


def test_every_corpus_is_reachable_through_the_table() -> None:
    """BL-20260906-02: the mapper reads STATUTE_CORPORA, not a hard-coded CRS."""
    corpora = citation_resolver.STATUTE_CORPORA
    assert [c.code_id for c in corpora] == ["us-co/crs"]
    # The scan vocabulary is the union of the table's reporters, so a second
    # corpus is picked up by `list_cases_with_statute_citations` for free.
    assert set(citation_resolver.STATUTE_REPORTERS) == {
        reporter for corpus in corpora for reporter in corpus.reporters
    }
    assert all("." in reporter for reporter in citation_resolver.STATUTE_REPORTERS)


def test_a_new_corpus_needs_no_change_to_the_mapper(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An added table entry maps its own citations; CRS keeps working."""
    import re

    usc = citation_resolver.StatuteCorpus(
        code_id="us/usc",
        id_prefix="us/usc",
        reporters=("u.s.c.",),
        section_re=re.compile(r"§\s*(\d{1,5})"),
    )
    monkeypatch.setattr(
        citation_resolver,
        "STATUTE_CORPORA",
        (*citation_resolver.STATUTE_CORPORA, usc),
    )
    assert (
        citation_resolver.statute_section_id_from_normalized("42 u.s.c. § 1983")
        == "us/usc/1983"
    )
    assert (
        citation_resolver.statute_section_id_from_normalized("c.r.s. § 18-3-102")
        == "us-co/crs/18-3-102"
    )


# ---------------------------------------------------------------------------
# The resolver
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_resolve_statute_citations_issues_no_query_when_empty() -> None:
    session = FakeAsyncSession()
    assert await citation_resolver.resolve_statute_citations(session, []) == {}  # type: ignore[arg-type]
    assert session.calls == []


@pytest.mark.asyncio
async def test_resolve_statute_citations_maps_hits_and_misses() -> None:
    session = FakeAsyncSession(
        canned=[
            [
                {"section_id": "us-co/crs/18-3-102", "resolved": "us-co/crs/18-3-102"},
                {"section_id": "us-co/crs/99-9-999", "resolved": None},
            ]
        ]
    )
    out = await citation_resolver.resolve_statute_citations(  # type: ignore[arg-type]
        session, ["us-co/crs/18-3-102", "us-co/crs/99-9-999"]
    )
    assert out == {
        "us-co/crs/18-3-102": "us-co/crs/18-3-102",
        "us-co/crs/99-9-999": None,
    }
    cypher, _ = session.calls[0]
    # Verification only — the resolver must never create a section node.
    assert "MERGE" not in cypher
    assert "OPTIONAL MATCH (sec:StatuteSection" in cypher


@pytest.mark.asyncio
async def test_densify_statute_extraction_fills_only_verified_targets() -> None:
    result = ExtractionResult(
        case_id="1",
        title="People v. Doe",
        confidence=0.9,
        citations=[
            Citation(text="C.R.S. § 18-3-102", normalized="c.r.s. § 18-3-102"),
            Citation(text="C.R.S. § 99-9-999", normalized="c.r.s. § 99-9-999"),
            Citation(text="410 U.S. 113", normalized="410 u.s. 113"),
        ],
    )
    session = FakeAsyncSession(
        canned=[
            [
                {"section_id": "us-co/crs/18-3-102", "resolved": "us-co/crs/18-3-102"},
                {"section_id": "us-co/crs/99-9-999", "resolved": None},
            ]
        ]
    )
    await citation_resolver.densify_statute_extraction(session, result)  # type: ignore[arg-type]

    assert result.citations[0].target_statute_section_id == "us-co/crs/18-3-102"
    assert result.citations[1].target_statute_section_id is None
    assert result.citations[2].target_statute_section_id is None
    assert len(session.calls) == 1


@pytest.mark.asyncio
async def test_densify_statute_extraction_costs_nothing_without_statutes() -> None:
    result = ExtractionResult(
        case_id="1",
        title="Roe v. Wade",
        confidence=0.9,
        citations=[Citation(text="410 U.S. 113", normalized="410 u.s. 113")],
    )
    session = FakeAsyncSession()
    await citation_resolver.densify_statute_extraction(session, result)  # type: ignore[arg-type]
    assert session.calls == []


# ---------------------------------------------------------------------------
# The edge
# ---------------------------------------------------------------------------
def test_merge_cites_statute_cypher_carries_provenance_and_never_creates_sections() -> (
    None
):
    cypher = queries.MERGE_CITES_STATUTE_CYPHER
    assert "MATCH (sec:StatuteSection {id: $section_id})" in cypher
    assert "MERGE (sec:StatuteSection" not in cypher
    assert "r.confidence = $confidence" in cypher
    assert "r.source = $source" in cypher


@pytest.mark.asyncio
async def test_commit_extraction_merges_cites_statute_for_resolved_citations(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _no_embed(*args: Any, **kwargs: Any) -> None:
        return None

    monkeypatch.setattr(queries, "embed_case", _no_embed)
    session = FakeAsyncSession()
    result = ExtractionResult(
        case_id="1",
        title="People v. Doe",
        confidence=0.9,
        source="courtlistener",
        citations=[
            Citation(
                text="C.R.S. § 18-3-102",
                normalized="c.r.s. § 18-3-102",
                target_statute_section_id="us-co/crs/18-3-102",
            ),
            Citation(text="410 U.S. 113", normalized="410 u.s. 113"),
        ],
    )
    await queries.commit_extraction(session, result)  # type: ignore[arg-type]

    statute_calls = [
        params
        for cypher, params in session.calls
        if cypher is queries.MERGE_CITES_STATUTE_CYPHER
    ]
    assert len(statute_calls) == 1
    assert statute_calls[0]["case_id"] == "1"
    assert statute_calls[0]["section_id"] == "us-co/crs/18-3-102"
    assert statute_calls[0]["confidence"] == 0.9
    assert statute_calls[0]["source"] == "courtlistener"


@pytest.mark.asyncio
async def test_commit_extraction_writes_no_statute_edge_when_unresolved(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _no_embed(*args: Any, **kwargs: Any) -> None:
        return None

    monkeypatch.setattr(queries, "embed_case", _no_embed)
    session = FakeAsyncSession()
    await queries.commit_extraction(  # type: ignore[arg-type]
        session,
        ExtractionResult(
            case_id="1",
            title="People v. Doe",
            confidence=0.9,
            citations=[
                Citation(text="C.R.S. § 99-9-999", normalized="c.r.s. § 99-9-999")
            ],
        ),
    )
    assert not [
        1 for cypher, _ in session.calls if cypher is queries.MERGE_CITES_STATUTE_CYPHER
    ]


# ---------------------------------------------------------------------------
# The backfill scan
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_list_cases_with_statute_citations_prunes_by_reporter() -> None:
    session = FakeAsyncSession(
        canned=[
            [
                {
                    "case_id": "1",
                    "pending": [
                        {"normalized": "c.r.s. § 18-3-102", "confidence": 0.8},
                        {"normalized": None, "confidence": 0.5},
                    ],
                }
            ]
        ]
    )
    batch = await queries.list_cases_with_statute_citations(  # type: ignore[arg-type]
        session, reporters=["c.r.s."], after="", limit=10
    )
    assert batch == [
        {
            "case_id": "1",
            "pending": [{"normalized": "c.r.s. § 18-3-102", "confidence": 0.8}],
        }
    ]
    cypher, params = session.calls[0]
    assert params == {"after": "", "limit": 10, "reporters": ["c.r.s."]}
    # Keyset cursor, archived cases excluded (constitution §4 soft delete).
    assert "c.id > $after" in cypher
    assert "c.archived_at IS NULL" in cypher


# ---------------------------------------------------------------------------
# The extractor must actually produce the citation the resolver needs
# ---------------------------------------------------------------------------
def test_scout_extracts_crs_citations_eyecite_misses() -> None:
    """eyecite knows "Colo. Rev. Stat." but not "C.R.S." — the form courts use."""
    from law_ai.ingestionapp.services.scout import IngestionScout

    text = (
        "The defendant was convicted under C.R.S. § 18-3-102(1)(a). "
        "The limitations period in section 13-80-102, C.R.S., had run. "
        "See also Colo. Rev. Stat. § 24-4-106. "
    )
    result = IngestionScout().extract(
        {"id": 7, "case_name": "People v. Doe", "plain_text": text}
    )
    ids = {
        citation_resolver.statute_section_id_from_normalized(c.normalized)
        for c in result.citations
    }
    assert "us-co/crs/18-3-102" in ids
    assert "us-co/crs/13-80-102" in ids
    assert "us-co/crs/24-4-106" in ids


def test_scout_extracts_decimal_article_crs_citations() -> None:
    """BL-20260906-89: "18-1.3-401" must survive extraction *and* resolution."""
    from law_ai.ingestionapp.services.scout import IngestionScout

    text = (
        "He was sentenced under C.R.S. § 18-1.3-401(1)(a)(V)(A). "
        "See also section 24-4.1-302, C.R.S. "
    )
    result = IngestionScout().extract(
        {"id": 9, "case_name": "People v. Doe", "plain_text": text}
    )
    ids = {
        citation_resolver.statute_section_id_from_normalized(c.normalized)
        for c in result.citations
    }
    assert "us-co/crs/18-1.3-401" in ids
    assert "us-co/crs/24-4.1-302" in ids


def test_scout_does_not_invent_crs_citations_from_bare_numbers() -> None:
    from law_ai.ingestionapp.services.scout import IngestionScout

    result = IngestionScout().extract(
        {
            "id": 8,
            "case_name": "People v. Doe",
            "plain_text": "Docket 18-3-102 was consolidated with docket 19-4-201.",
        }
    )
    assert all(
        citation_resolver.statute_section_id_from_normalized(c.normalized) is None
        for c in result.citations
    )
