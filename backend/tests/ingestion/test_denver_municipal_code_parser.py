"""Denver Municipal Code parser + scout (BL-20260509-05, "spec 016.b").

`Ordinance` / `OrdinanceSection` were declared by spec 015 and indexed by two
migrations, but nothing ever wrote one. These tests cover the write path end to
end at the unit level: parse a recorded chapter fixture, score its sections,
route them through `OrdinanceScout`, and MERGE only what a human accepted.

**No network.** The client exists for operators with a mirror they may crawl;
the upstream host's terms prohibit systematic downloading, so every test here
runs against the checked-in fixture.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from law_ai.core.neo4j import ordinance_queries
from law_ai.core.schemas.ordinance_extraction import (
    OrdinanceExtraction,
    OrdinanceSectionPayload,
)
from law_ai.ingestionapp.quarantine_kinds import KIND_ORDINANCE_SECTION
from law_ai.ingestionapp.services import denver_municipal_code as dmc
from law_ai.ingestionapp.services.ordinance_scout import (
    REQUIRED_COMMIT_METADATA,
    OrdinanceScout,
    section_envelope,
)

pytestmark = pytest.mark.unit

FIXTURE = Path(__file__).parent / "fixtures" / "denver" / "chapter-38.html"


@pytest.fixture(scope="module")
def chapter_html() -> str:
    return FIXTURE.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def extraction(chapter_html: str) -> OrdinanceExtraction:
    return dmc.parse_chapter_html(
        "38", chapter_html, source_url="https://example.test/denver/chapter-38/"
    )


# ---------------------------------------------------------------------------
# The parser
# ---------------------------------------------------------------------------
class TestParseChapterHtml:
    def test_builds_the_chapter_anchor(self, extraction: OrdinanceExtraction) -> None:
        assert extraction.ordinance_id == "us-co-denver/dmc/chapter-38"
        assert extraction.ordinance_citation == "D.R.M.C. ch. 38"
        assert "LAW ENFORCEMENT" in extraction.ordinance_title
        assert extraction.jurisdiction_code == "us-co-denver"
        assert extraction.jurisdiction_level == "municipal"
        assert extraction.source == "denver_municipal_code"

    def test_finds_every_section_exactly_once(
        self, extraction: OrdinanceExtraction
    ) -> None:
        ids = [s.id for s in extraction.sections]
        assert ids == [
            "us-co-denver/dmc/38-31",
            "us-co-denver/dmc/38-32",
            "us-co-denver/dmc/38-33",
            "us-co-denver/dmc/38-34.5",
        ]
        assert len(ids) == len(set(ids))

    def test_section_ids_and_citations_follow_the_spec_015_shape(
        self, extraction: OrdinanceExtraction
    ) -> None:
        section = extraction.sections[0]
        assert section.id == "us-co-denver/dmc/38-31"
        assert section.citation == "D.R.M.C. § 38-31"
        assert section.heading == "Definitions."

    def test_decimal_section_numbers_survive(
        self, extraction: OrdinanceExtraction
    ) -> None:
        """`38-34.5` is a real DRMC shape; truncating it would alias a section."""
        assert extraction.sections[-1].id == "us-co-denver/dmc/38-34.5"

    def test_body_text_is_captured_without_script_or_style(
        self, extraction: OrdinanceExtraction
    ) -> None:
        body = extraction.sections[0].text
        assert "peace officer" in body.lower()
        assert "__MUNICODE__" not in body
        assert "color: red" not in body

    def test_history_note_is_kept_verbatim(
        self, extraction: OrdinanceExtraction
    ) -> None:
        note = extraction.sections[0].history_note
        assert "Ord. No. 342-05" in note
        assert "Ord. No. 20-11" in note

    def test_effective_date_is_the_latest_amendment(
        self, extraction: OrdinanceExtraction
    ) -> None:
        assert extraction.sections[0].effective_from == date(2011, 1, 18)
        assert extraction.sections[1].effective_from == date(2008, 9, 15)

    def test_a_reserved_stub_never_clears_the_hitl_threshold(
        self, extraction: OrdinanceExtraction
    ) -> None:
        """A placeholder that keeps the numbering contiguous is not law."""
        reserved = next(s for s in extraction.sections if s.id.endswith("38-33"))
        assert reserved.confidence < 0.7
        assert reserved not in extraction.high_confidence_sections()

    def test_substantive_sections_clear_the_threshold(
        self, extraction: OrdinanceExtraction
    ) -> None:
        assert len(extraction.high_confidence_sections()) == 3

    def test_empty_document_yields_nothing_rather_than_a_fabrication(self) -> None:
        empty = dmc.parse_chapter_html("38", "<html><body></body></html>")
        assert empty.sections == []
        assert empty.confidence == 0.0
        assert empty.ordinance_id == "us-co-denver/dmc/chapter-38"

    def test_parsing_is_idempotent(self, chapter_html: str) -> None:
        a = dmc.parse_chapter_html("38", chapter_html)
        b = dmc.parse_chapter_html("38", chapter_html)
        assert [s.model_dump(exclude={"confidence"}) for s in a.sections] == [
            s.model_dump(exclude={"confidence"}) for s in b.sections
        ]


class TestHelpers:
    @pytest.mark.parametrize(
        ("designator", "expected"),
        [
            ("Sec. 38-31.", "38-31"),
            ("§ 38-31", "38-31"),
            ("Section 38-34.5", "38-34.5"),
            ("38-31.", "38-31"),
            ("Sec. 5-1a.", "5-1a"),
            ("", None),
            ("Editor's note", None),
        ],
    )
    def test_section_number(self, designator: str, expected: str | None) -> None:
        assert dmc.section_number(designator) == expected

    @pytest.mark.parametrize(
        ("note", "expected"),
        [
            ("(Ord. No. 342-05, § 1, 5-31-05)", date(2005, 5, 31)),
            (
                "(Ord. No. 342-05, § 1, 5-31-05; Ord. No. 20-11, § 2, 1-18-11)",
                date(2011, 1, 18),
            ),
            ("(Ord. No. 88-14, § 1, 2-24-2014)", date(2014, 2, 24)),
            ("(Code 1950, § 811.1)", None),
            ("", None),
            (None, None),
        ],
    )
    def test_parse_history_date_takes_the_latest(
        self, note: str | None, expected: date | None
    ) -> None:
        assert dmc.parse_history_date(note) == expected

    def test_parse_history_date_ignores_impossible_dates(self) -> None:
        assert dmc.parse_history_date("(Ord. No. 1, 13-45-99)") is None

    def test_two_digit_years_read_as_the_century_the_code_lives_in(self) -> None:
        assert dmc.parse_history_date("(Ord. 1, 1-1-95)") == date(1995, 1, 1)
        assert dmc.parse_history_date("(Ord. 1, 1-1-05)") == date(2005, 1, 1)


# ---------------------------------------------------------------------------
# The scout
# ---------------------------------------------------------------------------
class TestOrdinanceScout:
    def test_extract_stamps_the_agent_version(self, chapter_html: str) -> None:
        scout = OrdinanceScout()
        out = scout.extract({"chapter": "38", "html": chapter_html})
        assert out.agent_version == scout.agent_version
        assert len(out.sections) == 4

    def test_extract_requires_chapter_and_html(self) -> None:
        with pytest.raises(ValueError, match="requires 'chapter' and 'html'"):
            OrdinanceScout().extract({"chapter": "38"})

    async def test_commit_quarantines_everything_by_default(
        self, extraction: OrdinanceExtraction
    ) -> None:
        """The source requires human approval, so nothing auto-commits."""
        scout = OrdinanceScout()
        assert scout.requires_human_approval is True
        with patch.object(scout, "_quarantine_via_celery", MagicMock()) as q:
            result = await scout.commit(extraction)
        assert result["committed"] == 0
        assert result["pending"] == 4
        assert result["edges"] == 0
        assert q.call_count == 4

    async def test_quarantine_uses_the_ordinance_section_kind(
        self, extraction: OrdinanceExtraction
    ) -> None:
        sent: list[dict[str, Any]] = []

        class _Task:
            @staticmethod
            def delay(payload: dict[str, Any]) -> None:
                sent.append(payload)

        with patch.dict(
            "sys.modules",
            {"law_ai.ingestionapp.tasks": MagicMock(quarantine_extraction=_Task)},
        ):
            await OrdinanceScout().commit(extraction)

        assert sent
        assert {p["kind"] for p in sent} == {KIND_ORDINANCE_SECTION}
        assert {p["source"] for p in sent} == {"denver_municipal_code"}
        assert sent[0]["reason"] == "source_requires_human_approval"

    def test_quarantine_envelope_is_self_contained(
        self, extraction: OrdinanceExtraction
    ) -> None:
        """BL-20260811-03's lesson: a row that cannot be rehydrated is stuck."""
        envelope = json.loads(
            json.dumps(
                section_envelope(extraction, extraction.sections[0]), default=str
            )
        )
        assert all(envelope.get(key) for key in REQUIRED_COMMIT_METADATA)
        assert envelope["section"]["id"] == "us-co-denver/dmc/38-31"

    async def test_commit_writes_the_tree_when_approval_is_not_required(
        self, extraction: OrdinanceExtraction, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        session = _FakeSession()
        monkeypatch.setattr(
            "law_ai.ingestionapp.services.ordinance_scout.get_neo4j_driver",
            lambda: _FakeDriver(session),
        )
        with patch.object(OrdinanceScout, "_quarantine_via_celery", MagicMock()):
            result = await OrdinanceScout().commit(extraction, force_quarantine=False)
        assert result["committed"] == 3
        assert result["pending"] == 1
        cyphers = [c for c, _ in session.calls]
        assert ordinance_queries.MERGE_ORDINANCE_CYPHER in cyphers
        assert cyphers.count(ordinance_queries.MERGE_ORDINANCE_SECTION_CYPHER) == 3


# ---------------------------------------------------------------------------
# The Cypher
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

    async def __aenter__(self) -> _FakeSession:
        return self

    async def __aexit__(self, *exc: object) -> None:
        return None


class _FakeDriver:
    def __init__(self, session: _FakeSession) -> None:
        self._session = session

    def session(self) -> _FakeSession:
        return self._session


class TestOrdinanceQueries:
    async def test_commit_writes_nothing_without_a_committable_section(self) -> None:
        session = _FakeSession()
        empty = OrdinanceExtraction(
            jurisdiction_code="us-co-denver",
            jurisdiction_name="Denver, Colorado",
            ordinance_id="us-co-denver/dmc/chapter-38",
            ordinance_title="Chapter 38",
            sections=[
                OrdinanceSectionPayload(
                    id="us-co-denver/dmc/38-33",
                    citation="D.R.M.C. § 38-33",
                    heading="Reserved.",
                    text="Reserved.",
                    confidence=0.3,
                )
            ],
            confidence=0.3,
        )
        edges = await ordinance_queries.commit_ordinance_extraction(session, empty)  # type: ignore[arg-type]
        assert edges == 0
        # No empty chapter node left behind claiming coverage we do not have.
        assert session.calls == []

    async def test_every_node_carries_source_and_confidence(
        self, extraction: OrdinanceExtraction
    ) -> None:
        session = _FakeSession()
        edges = await ordinance_queries.commit_ordinance_extraction(session, extraction)  # type: ignore[arg-type]
        assert edges == 4  # 1 Ordinance->Jurisdiction + 3 Section->Ordinance
        for _, params in session.calls:
            assert params["source"] == "denver_municipal_code"
            assert params["confidence"] is not None
            assert params["ingest_timestamp"]

    def test_section_merge_never_creates_its_ordinance(self) -> None:
        cypher = ordinance_queries.MERGE_ORDINANCE_SECTION_CYPHER
        assert "MATCH (o:Ordinance {id: $ordinance_id})" in cypher
        assert "MERGE (o:Ordinance" not in cypher


# ---------------------------------------------------------------------------
# Approval dispatch (the only way an ordinance reaches the graph)
# ---------------------------------------------------------------------------
async def test_approval_routes_ordinance_sections_to_the_ordinance_scout() -> None:
    from law_ai.ingestionapp.services import approval

    seen: dict[str, Any] = {}

    async def _fake_commit_section(
        _self: Any, payload: dict[str, Any], *, force_commit: bool = True
    ) -> dict[str, Any]:
        seen["payload"] = payload
        seen["force_commit"] = force_commit
        return {"committed": True, "edges": 2}

    with patch.object(OrdinanceScout, "commit_section", _fake_commit_section):
        out = await approval._commit_by_kind(
            KIND_ORDINANCE_SECTION, {"section": {"id": "x"}}
        )
    assert out["committed"] is True
    assert seen["force_commit"] is True


async def test_commit_section_refuses_a_row_without_chapter_metadata() -> None:
    with pytest.raises(ValueError, match="lacks jurisdiction/chapter metadata"):
        await OrdinanceScout().commit_section(
            {
                "section": {
                    "id": "x",
                    "citation": "c",
                    "heading": "h",
                    "text": "t",
                    "confidence": 0.5,
                }
            }
        )


async def test_commit_section_refuses_a_payload_with_no_section() -> None:
    with pytest.raises(ValueError, match="has no 'section'"):
        await OrdinanceScout().commit_section({"ordinance_id": "x"})


async def test_commit_section_commits_an_approved_row(
    extraction: OrdinanceExtraction, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The "Reserved." stub: below the threshold, so only a human approval can
    # commit it — which is exactly what force_commit models.
    reserved = next(s for s in extraction.sections if s.id.endswith("38-33"))
    envelope = json.loads(
        json.dumps(section_envelope(extraction, reserved), default=str)
    )

    session = _FakeSession()
    monkeypatch.setattr(
        "law_ai.ingestionapp.services.ordinance_scout.get_neo4j_driver",
        lambda: _FakeDriver(session),
    )
    out = await OrdinanceScout().commit_section(envelope, force_commit=True)
    assert out["committed"] is True
    assert out["section_id"] == "us-co-denver/dmc/38-33"
    assert ordinance_queries.MERGE_ORDINANCE_SECTION_CYPHER in [
        c for c, _ in session.calls
    ]


# ---------------------------------------------------------------------------
# The adapter
# ---------------------------------------------------------------------------
def test_adapter_is_registered_and_requires_human_approval() -> None:
    from law_ai.ingestionapp.sources import SOURCE_REGISTRY

    adapter = SOURCE_REGISTRY["denver_municipal_code"]
    assert adapter.jurisdiction == "us-co-denver"
    # The whole safety posture for this source hangs on this flag.
    assert adapter.requires_human_approval is True
    assert adapter.rate_limit_rps <= 0.5
    assert "redistribution: false" in adapter.license


async def test_adapter_shapes_sections_into_rawdocs(chapter_html: str) -> None:
    from law_ai.ingestionapp.sources.denver_municipal_code import (
        DenverMunicipalCodeAdapter,
    )

    class _Client:
        async def __aenter__(self) -> _Client:
            return self

        async def __aexit__(self, *exc: object) -> None:
            return None

        async def fetch_chapter(self, chapter: str) -> str:
            return chapter_html

        def url_for_chapter(self, chapter: str) -> str:
            return f"https://example.test/chapter-{chapter}/"

    with patch(
        "law_ai.ingestionapp.services.denver_municipal_code."
        "DenverMunicipalCodeClient",
        _Client,
    ):
        docs = await DenverMunicipalCodeAdapter().afetch("38", limit=2)

    assert len(docs) == 2
    assert docs[0].source_name == "denver_municipal_code"
    assert docs[0].title == "D.R.M.C. § 38-31"
    assert docs[0].metadata["section_id"] == "us-co-denver/dmc/38-31"
    assert docs[0].metadata["ordinance_id"] == "us-co-denver/dmc/chapter-38"
    assert docs[0].source_url.endswith("/chapter-38/")
