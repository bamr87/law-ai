"""Unit tests for SOURCE_REGISTRY adapters (spec 018 T-006)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from lawgraph.ingestionapp.sources import SOURCE_REGISTRY, RawDoc
from lawgraph.ingestionapp.sources.base import SourceAdapter as BaseAdapter

# ---------------------------------------------------------------------------
# Registry structure
# ---------------------------------------------------------------------------


def test_registry_contains_exactly_three_adapters() -> None:
    assert set(SOURCE_REGISTRY.keys()) == {
        "courtlistener",
        "colorado_statutes",
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
    from lawgraph.ingestionapp.sources.courtlistener import CourtListenerAdapter

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
    from lawgraph.ingestionapp.sources.courtlistener import CourtListenerAdapter

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
        "lawgraph.ingestionapp.services.courtlistener.CourtListenerClient"
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
    from lawgraph.ingestionapp.sources.colorado_statutes import ColoradoStatutesAdapter
    from lawgraph.core.schemas.statute_extraction import (
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
            "lawgraph.ingestionapp.services.colorado_statutes.ColoradoStatutesClient"
        ) as MockClient,
        patch(
            "lawgraph.ingestionapp.services.colorado_statutes.parse_title_html",
            return_value=mock_extraction,
        ),
    ):
        mock_client = MagicMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.fetch_title = AsyncMock(return_value="<html>...</html>")
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
def test_list_sources_command_prints_three_rows(capsys) -> None:
    from django.core.management import call_command

    call_command("list_sources")
    out = capsys.readouterr().out
    assert "courtlistener" in out
    assert "colorado_statutes" in out
    assert "statute_scout" in out
    assert "3 source(s) registered" in out
