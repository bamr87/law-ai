"""`manage.py backfill_holding_summaries` (BL-20260905-99).

Cases ingested before the deterministic excerpt landed still render
"(no holding summary stored)" in every GraphRAG passage. `:Case` stores no
opinion text, so the backfill re-fetches the opinion and re-derives the same
excerpt an ingest would write. Hermetic: the Neo4j driver and the source
client are both faked — no network, no live graph.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from io import StringIO
from typing import Any
from unittest.mock import patch

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from law_ai.core.neo4j import queries
from law_ai.ingestionapp.management.commands import backfill_holding_summaries as cmd

pytestmark = pytest.mark.unit

_COMMAND = "backfill_holding_summaries"

_BODY = (
    "The judgment of the district court is affirmed. Because the findings are "
    "supported by substantial evidence in the record as a whole, and because "
    "the legal conclusions drawn from those findings comport with our "
    "precedent, we decline to disturb the judgment entered below."
)


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


class _FakeSession:
    """Answers the scan by page and records every write."""

    def __init__(self, pages: list[list[dict[str, Any]]]) -> None:
        self._pages = list(pages)
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def run(self, cypher: str, params: dict[str, Any]) -> _FakeResult:
        self.calls.append((cypher, params))
        if cypher is queries.LIST_CASES_MISSING_HOLDING_SUMMARY_CYPHER:
            return _FakeResult(self._pages.pop(0) if self._pages else [])
        if cypher is queries.SET_HOLDING_SUMMARY_CYPHER:
            return _FakeResult([{"id": params["case_id"]}])
        return _FakeResult([])

    @property
    def writes(self) -> list[dict[str, Any]]:
        return [
            params
            for cypher, params in self.calls
            if cypher is queries.SET_HOLDING_SUMMARY_CYPHER
        ]


class _FakeDriver:
    def __init__(self, session: _FakeSession) -> None:
        self._session = session

    def session(self) -> Any:
        @asynccontextmanager
        async def _ctx() -> Any:
            yield self._session

        return _ctx()


class _FakeClient:
    """Stands in for ``CourtListenerClient`` — no network, no key."""

    def __init__(self, opinions: dict[str, dict[str, Any]]) -> None:
        self._opinions = opinions
        self.fetched: list[str] = []

    async def __aenter__(self) -> _FakeClient:
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        return None

    async def fetch_opinion(self, opinion_id: int | str) -> dict[str, Any]:
        self.fetched.append(str(opinion_id))
        try:
            return self._opinions[str(opinion_id)]
        except KeyError as exc:
            raise RuntimeError(f"404 for {opinion_id}") from exc


_ONE_PAGE = [
    [
        {
            "case_id": "case-1",
            "title": "Doe v. Roe",
            "source": "courtlistener",
            "source_url": "https://example.test/1",
        },
        {
            "case_id": "case-2",
            "title": "Statute import",
            "source": "colorado_statutes",
            "source_url": None,
        },
    ],
    [],
]


def _run(session: _FakeSession, client: _FakeClient | None, *args: str) -> str:
    out = StringIO()
    patches = [
        patch.object(cmd, "get_neo4j_driver", lambda: _FakeDriver(session)),
        patch.object(cmd.provenance, "log_graph_query", lambda **kw: None),
    ]
    if client is not None:
        patches.append(
            patch(
                "law_ai.ingestionapp.services.courtlistener.CourtListenerClient",
                lambda *a, **k: client,
            )
        )
    for p in patches:
        p.start()
    try:
        call_command(_COMMAND, *args, stdout=out)
    finally:
        for p in reversed(patches):
            p.stop()
    return out.getvalue()


def test_audit_run_reports_the_gap_and_writes_nothing() -> None:
    session = _FakeSession(_ONE_PAGE)
    text = _run(session, None, "--verbose-cases")
    assert "scanned=2" in text
    assert "written=0" in text
    assert "case-1: no holding_summary" in text
    assert session.writes == []
    # §13: the caveat is printed on every run.
    assert "Offline limit" in text


def test_refetch_dry_run_derives_but_does_not_write() -> None:
    session = _FakeSession(_ONE_PAGE)
    client = _FakeClient({"case-1": {"plain_text": _BODY}})
    text = _run(session, client, "--refetch", "--verbose-cases")
    assert client.fetched == ["case-1"]
    assert "derived=1" in text
    assert "written=0" in text
    assert "Re-run with --commit" in text
    assert session.writes == []


def test_commit_writes_the_same_excerpt_an_ingest_would() -> None:
    from law_ai.ingestionapp.services.scout import derive_holding_summary

    session = _FakeSession(_ONE_PAGE)
    client = _FakeClient({"case-1": {"plain_text": _BODY}})
    text = _run(session, client, "--refetch", "--commit")
    assert "written=1" in text
    assert session.writes == [
        {
            "case_id": "case-1",
            "holding_summary": derive_holding_summary(_BODY),
            "holding_summary_kind": "excerpt",
        }
    ]


def test_non_refetchable_sources_are_counted_not_fetched() -> None:
    session = _FakeSession(_ONE_PAGE)
    client = _FakeClient({"case-1": {"plain_text": _BODY}})
    text = _run(session, client, "--refetch", "--verbose-cases")
    assert "unfetchable=1" in text
    assert "case-2" not in client.fetched
    assert "colorado_statutes" in text


def test_a_failed_fetch_is_counted_not_fatal() -> None:
    session = _FakeSession(_ONE_PAGE)
    client = _FakeClient({})  # every fetch 404s
    text = _run(session, client, "--refetch", "--commit", "--verbose-cases")
    assert "failed=1" in text
    assert "written=0" in text
    assert "fetch failed" in text


def test_html_body_is_used_when_there_is_no_plain_text() -> None:
    session = _FakeSession(_ONE_PAGE)
    client = _FakeClient({"case-1": {"plain_text": "", "html": f"<p>{_BODY}</p>"}})
    text = _run(session, client, "--refetch", "--commit")
    assert "written=1" in text
    assert "<p>" not in session.writes[0]["holding_summary"]


def test_commit_without_refetch_is_refused() -> None:
    session = _FakeSession(_ONE_PAGE)
    with pytest.raises(CommandError, match="--commit needs --refetch"):
        _run(session, None, "--commit")


def test_commit_and_dry_run_are_mutually_exclusive() -> None:
    session = _FakeSession(_ONE_PAGE)
    with pytest.raises(CommandError, match="mutually exclusive"):
        _run(session, None, "--commit", "--dry-run")


def test_limit_bounds_the_walk() -> None:
    session = _FakeSession([[_ONE_PAGE[0][0]], [_ONE_PAGE[0][1]], []])
    text = _run(session, None, "--limit", "1")
    assert "scanned=1" in text


def test_bad_batch_size_is_rejected() -> None:
    session = _FakeSession(_ONE_PAGE)
    with pytest.raises(CommandError, match="--batch-size must be >= 1"):
        _run(session, None, "--batch-size", "0")
