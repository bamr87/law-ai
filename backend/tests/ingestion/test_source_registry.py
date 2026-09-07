"""Unit tests for SOURCE_REGISTRY adapters (spec 018 T-006)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from law_ai.ingestionapp.sources import SOURCE_REGISTRY, RawDoc
from law_ai.ingestionapp.sources.base import SourceAdapter as BaseAdapter

# ---------------------------------------------------------------------------
# Registry structure
# ---------------------------------------------------------------------------


def test_registry_contains_exactly_the_declared_adapters() -> None:
    # denver_municipal_code joined in BL-20260509-05 (spec 016's deferred
    # "016.b"). It is registered with requires_human_approval=True, so being
    # in the registry cannot by itself put an ordinance in the graph.
    assert set(SOURCE_REGISTRY.keys()) == {
        "courtlistener",
        "colorado_statutes",
        "denver_municipal_code",
        "statute_scout",
    }


def test_all_adapters_are_source_adapter_subclasses() -> None:
    for name, adapter in SOURCE_REGISTRY.items():
        assert isinstance(adapter, BaseAdapter), f"{name} must subclass SourceAdapter"


def test_all_adapters_have_required_metadata() -> None:
    for name, adapter in SOURCE_REGISTRY.items():
        assert adapter.name == name, f"{name}: .name mismatch"
        assert adapter.jurisdiction, f"{name}: .jurisdiction empty"
        assert adapter.license, f"{name}: .license empty"
        assert isinstance(adapter.requires_human_approval, bool)
        assert adapter.rate_limit_rps > 0


def test_source_adapter_repr_is_informative() -> None:
    from law_ai.ingestionapp.sources.courtlistener import CourtListenerAdapter

    r = repr(CourtListenerAdapter())
    assert "courtlistener" in r
    assert "us" in r


# ---------------------------------------------------------------------------
# RawDoc
# ---------------------------------------------------------------------------


def test_rawdoc_is_immutable() -> None:
    doc = RawDoc(
        source_name="courtlistener",
        source_url="https://example.com",
        title="Test",
        text="body",
    )
    with pytest.raises((AttributeError, TypeError)):
        doc.title = "mutated"  # type: ignore[misc]


def test_rawdoc_default_metadata_is_empty_dict() -> None:
    doc = RawDoc(source_name="x", source_url="u", title="t", text="b")
    assert doc.metadata == {}


# ---------------------------------------------------------------------------
# CourtListenerAdapter
# ---------------------------------------------------------------------------


def test_courtlistener_adapter_fetch_returns_raw_docs() -> None:
    from law_ai.ingestionapp.sources.courtlistener import CourtListenerAdapter

    mock_opinion = {
        "id": 42,
        "case_name": "Test v. State",
        "absolute_url": "/opinion/42/test-v-state/",
        "plain_text": "The court held...",
        "cluster": {"court": "US Supreme Court", "date_filed": "2024-01-01"},
    }

    async def _fake_iter(**_kwargs):
        yield mock_opinion

    adapter = CourtListenerAdapter()
    with patch(
        "law_ai.ingestionapp.services.courtlistener.CourtListenerClient"
    ) as MockClient:
        mock_client = MagicMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.list_opinions = MagicMock(return_value=_fake_iter())
        MockClient.return_value = mock_client

        docs = list(adapter.fetch("Test v. State", limit=5))

    assert len(docs) == 1
    doc = docs[0]
    assert doc.source_name == "courtlistener"
    assert doc.title == "Test v. State"
    assert "courtlistener.com" in doc.source_url
    assert doc.metadata["opinion_id"] == 42


# ---------------------------------------------------------------------------
# ColoradoStatutesAdapter
# ---------------------------------------------------------------------------


def test_colorado_statutes_adapter_fetch_returns_raw_docs() -> None:
    from law_ai.ingestionapp.sources.colorado_statutes import ColoradoStatutesAdapter
    from law_ai.core.schemas.statute_extraction import (
        StatuteExtraction,
        StatuteSectionPayload,
    )

    mock_section = StatuteSectionPayload(
        id="us-co/crs/title-1/1-1-101",
        citation="C.R.S. § 1-1-101",
        heading="Definitions",
        text="As used in this article...",
        confidence=0.9,
    )
    mock_extraction = StatuteExtraction(
        jurisdiction_code="us-co",
        jurisdiction_name="Colorado",
        jurisdiction_level="state",
        code_id="us-co/crs",
        code_title="Colorado Revised Statutes",
        statute_id="us-co/crs/title-1",
        statute_title="Title 1 — Elections",
        source_url="https://law.justia.com/codes/colorado/2024/title-1/",
        sections=[mock_section],
        confidence=0.9,
        agent_version="0.1.0",
    )

    adapter = ColoradoStatutesAdapter()
    with (
        patch(
            "law_ai.ingestionapp.services.colorado_statutes.ColoradoStatutesClient"
        ) as MockClient,
        patch(
            "law_ai.ingestionapp.services.colorado_statutes.parse_title_html",
            return_value=mock_extraction,
        ),
    ):
        mock_client = MagicMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.fetch_title = AsyncMock(return_value="<html>...</html>")
        # BL-20260509-06: the adapter now asks for a *document* so it can fall
        # back to the PDF publication when the HTML page is unavailable.
        mock_client.fetch_title_document = AsyncMock(
            return_value=("html", "<html>...</html>")
        )
        MockClient.return_value = mock_client

        docs = list(adapter.fetch("1", limit=10))

    assert len(docs) == 1
    doc = docs[0]
    assert doc.source_name == "colorado_statutes"
    assert doc.title == "C.R.S. § 1-1-101"
    assert doc.metadata["jurisdiction"] == "us-co"


# ---------------------------------------------------------------------------
# list_sources management command
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_list_sources_command_prints_a_row_per_adapter(capsys) -> None:
    from django.core.management import call_command

    call_command("list_sources")
    out = capsys.readouterr().out
    for name in SOURCE_REGISTRY:
        assert name in out
    assert f"{len(SOURCE_REGISTRY)} source(s) registered" in out


@pytest.mark.django_db
def test_list_sources_prints_rate_limits_without_losing_precision(capsys) -> None:
    """Every printed RPS parses back to the adapter's exact rate (BL-20260511-09).

    ``:.1f`` rendered the Denver adapter's 0.25 rps as ``0.2``, which both
    misinformed the operator and broke the live-stack metadata test.
    """
    from django.core.management import call_command

    call_command("list_sources")
    lines = capsys.readouterr().out.splitlines()
    printed = {
        parts[0]: parts[3]
        for line in lines
        if line.strip()
        and not line.startswith(("NAME", "-"))
        and "registered" not in line
        for parts in [line.split(maxsplit=5)]
    }
    assert set(printed) == set(SOURCE_REGISTRY)
    for name, adapter in SOURCE_REGISTRY.items():
        assert float(printed[name]) == adapter.rate_limit_rps, (
            f"{name}: printed {printed[name]!r} for rate_limit_rps="
            f"{adapter.rate_limit_rps!r}"
        )
    assert printed["denver_municipal_code"] == "0.25"


# ---------------------------------------------------------------------------
# afetch contract (BL-20260511-08)
# ---------------------------------------------------------------------------


def test_every_adapter_implements_afetch_as_a_coroutine() -> None:
    import inspect

    for name, adapter in SOURCE_REGISTRY.items():
        assert inspect.iscoroutinefunction(
            adapter.afetch
        ), f"{name}.afetch must be a coroutine — the autonomy loop awaits it"


def test_afetch_is_the_abstract_method_not_fetch() -> None:
    """Adapters implement the coroutine; ``fetch`` is the base class's shim."""
    assert "afetch" in BaseAdapter.__abstractmethods__
    assert "fetch" not in BaseAdapter.__abstractmethods__
    for adapter in SOURCE_REGISTRY.values():
        assert type(adapter).fetch is BaseAdapter.fetch


@pytest.mark.asyncio
async def test_sync_fetch_refuses_to_run_inside_an_event_loop() -> None:
    """The old behaviour was a silent nested-asyncio.run failure."""

    class _Adapter(BaseAdapter):
        name = "unit-test"
        jurisdiction = "*"
        license = "n/a"

        async def afetch(self, query: str, *, limit: int = 10) -> list[RawDoc]:
            return [
                RawDoc(source_name=self.name, source_url="u", title=query, text="t")
            ]

    with pytest.raises(RuntimeError, match="afetch"):
        _Adapter().fetch("anything")


def test_sync_fetch_still_works_from_a_plain_thread() -> None:
    class _Adapter(BaseAdapter):
        name = "unit-test"
        jurisdiction = "*"
        license = "n/a"

        async def afetch(self, query: str, *, limit: int = 10) -> list[RawDoc]:
            return [
                RawDoc(source_name=self.name, source_url="u", title=query, text="t")
            ][:limit]

    docs = list(_Adapter().fetch("hello", limit=1))
    assert [d.title for d in docs] == ["hello"]


@pytest.mark.asyncio
async def test_courtlistener_afetch_is_awaitable_from_a_running_loop() -> None:
    from law_ai.ingestionapp.sources.courtlistener import CourtListenerAdapter

    async def _fake_iter(**_kwargs):
        yield {"id": 7, "case_name": "Async v. Loop", "plain_text": "body"}

    with patch(
        "law_ai.ingestionapp.services.courtlistener.CourtListenerClient"
    ) as MockClient:
        mock_client = MagicMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.list_opinions = MagicMock(return_value=_fake_iter())
        MockClient.return_value = mock_client

        docs = await CourtListenerAdapter().afetch("Async v. Loop", limit=5)

    assert [d.title for d in docs] == ["Async v. Loop"]


@pytest.mark.asyncio
async def test_colorado_afetch_is_awaitable_from_a_running_loop() -> None:
    from law_ai.core.schemas.statute_extraction import (
        StatuteExtraction,
        StatuteSectionPayload,
    )
    from law_ai.ingestionapp.sources.colorado_statutes import ColoradoStatutesAdapter

    extraction = StatuteExtraction(
        jurisdiction_code="us-co",
        jurisdiction_name="Colorado",
        jurisdiction_level="state",
        code_id="us-co/crs",
        code_title="Colorado Revised Statutes",
        statute_id="us-co/crs/title-1",
        statute_title="Title 1",
        source_url="https://law.justia.com/codes/colorado/2024/title-1/",
        sections=[
            StatuteSectionPayload(
                id="us-co/crs/1-1-101",
                citation="C.R.S. § 1-1-101",
                heading="Definitions",
                text="As used in this article...",
                confidence=0.9,
            )
        ],
        confidence=0.9,
    )
    with (
        patch(
            "law_ai.ingestionapp.services.colorado_statutes.ColoradoStatutesClient"
        ) as MockClient,
        patch(
            "law_ai.ingestionapp.services.colorado_statutes.parse_title_html",
            return_value=extraction,
        ),
    ):
        mock_client = MagicMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.fetch_title_document = AsyncMock(
            return_value=("html", "<html>...</html>")
        )
        MockClient.return_value = mock_client

        docs = await ColoradoStatutesAdapter().afetch("1", limit=10)

    assert [d.title for d in docs] == ["C.R.S. § 1-1-101"]


@pytest.mark.asyncio
async def test_statute_scout_afetch_is_awaitable_from_a_running_loop() -> None:
    from law_ai.ingestionapp.sources.statute_scout import StatuteScoutAdapter

    section = MagicMock()
    section.citation = "C.R.S. § 1-1-101"
    section.text = "As used in this article..."
    section.id = "us-co/crs/1-1-101"
    section.effective_from = None
    extraction = MagicMock()
    extraction.sections = [section]
    extraction.source_url = "https://law.justia.com/codes/colorado/2024/title-1/"
    extraction.confidence = 0.9
    extraction.agent_version = "0.1.0"

    with (
        patch(
            "law_ai.ingestionapp.services.colorado_statutes.ColoradoStatutesClient"
        ) as MockClient,
        patch("law_ai.ingestionapp.services.statute_scout.StatuteScout") as MockScout,
    ):
        mock_client = MagicMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.fetch_title = AsyncMock(return_value="<html>...</html>")
        mock_client._base_url = "https://law.justia.com/codes/colorado/2024"
        MockClient.return_value = mock_client
        MockScout.return_value.extract = MagicMock(return_value=extraction)

        docs = await StatuteScoutAdapter().afetch("1", limit=10)

    assert [d.title for d in docs] == ["C.R.S. § 1-1-101"]
