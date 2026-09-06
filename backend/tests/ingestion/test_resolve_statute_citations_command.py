"""`manage.py resolve_statute_citations` backfill (BL-20260509-07).

The item asks for a pass that "creates CITES_STATUTE edges from existing
opinion text once the CRS corpus is loaded". `:Case` nodes never stored the
opinion body, so the command works from the `Citation.normalized` strings the
original ingests already wrote — which keeps the backfill offline. Hermetic:
the Neo4j driver is faked, no network and no live graph.
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
from law_ai.ingestionapp.management.commands import resolve_statute_citations as cmd

pytestmark = pytest.mark.unit

_COMMAND = "resolve_statute_citations"


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
    """Answers each Cypher by shape, so the walk terminates deterministically."""

    def __init__(self, pages: list[list[dict[str, Any]]]) -> None:
        self._pages = list(pages)
        self.calls: list[tuple[str, dict[str, Any]]] = []
        #: Pages answered for the BL-20260906-88 recall scan.
        self.recall_pages: list[list[dict[str, Any]]] = []

    async def run(self, cypher: str, params: dict[str, Any]) -> _FakeResult:
        self.calls.append((cypher, params))
        if cypher is queries.LIST_CASES_WITHOUT_STATUTE_CITATIONS_CYPHER:
            return _FakeResult(self.recall_pages.pop(0) if self.recall_pages else [])
        if cypher is queries.LIST_CASES_WITH_STATUTE_CITATIONS_CYPHER:
            return _FakeResult(self._pages.pop(0) if self._pages else [])
        if "OPTIONAL MATCH (sec:StatuteSection" in cypher:
            return _FakeResult(
                [
                    {
                        "section_id": sid,
                        # us-co/crs/99-9-999 is the "not in the corpus" case.
                        "resolved": None if "99-9-999" in sid else sid,
                    }
                    for sid in params["section_ids"]
                ]
            )
        if cypher is queries.MERGE_CITES_STATUTE_CYPHER:
            return _FakeResult([{"r": 1}])
        return _FakeResult([])


class _FakeDriver:
    def __init__(self, session: _FakeSession) -> None:
        self._session = session

    def session(self) -> Any:
        @asynccontextmanager
        async def _ctx() -> Any:
            yield self._session

        return _ctx()


_ONE_PAGE = [
    [
        {
            "case_id": "case-1",
            "pending": [
                {"normalized": "c.r.s. § 18-3-102", "confidence": 0.85},
                {"normalized": "c.r.s. § 99-9-999", "confidence": 0.85},
                {"normalized": "410 u.s. 113", "confidence": 0.85},
            ],
        }
    ]
]


def _run(
    *args: str, pages: list[list[dict[str, Any]]] | None = None
) -> tuple[str, Any]:
    session = _FakeSession(list(pages if pages is not None else _ONE_PAGE))
    out = StringIO()
    with patch.object(cmd, "get_neo4j_driver", return_value=_FakeDriver(session)):
        call_command(_COMMAND, *args, stdout=out)
    return out.getvalue(), session


def test_dry_run_reports_without_writing() -> None:
    output, session = _run()
    assert "dry run" in output
    assert "scanned=3 candidates=2 resolved=1 edges_created=0" in output
    assert "Re-run with --commit" in output
    assert not [c for c, _ in session.calls if c is queries.MERGE_CITES_STATUTE_CYPHER]


def test_commit_merges_only_sections_that_exist() -> None:
    output, session = _run("--commit")
    assert "COMMIT mode" in output
    assert "scanned=3 candidates=2 resolved=1 edges_created=1" in output

    merges = [p for c, p in session.calls if c is queries.MERGE_CITES_STATUTE_CYPHER]
    assert len(merges) == 1
    assert merges[0]["case_id"] == "case-1"
    assert merges[0]["section_id"] == "us-co/crs/18-3-102"
    assert merges[0]["confidence"] == 0.85
    # Backfilled edges are distinguishable from ingest-time ones.
    assert merges[0]["source"] == cmd.BACKFILL_SOURCE


def test_verbose_pairs_lists_each_resolution() -> None:
    output, _ = _run("--verbose-pairs")
    assert "case-1:" in output
    assert "c.r.s. § 18-3-102 -> us-co/crs/18-3-102 (would merge)" in output
    # Unresolved and non-statutory citations are not reported as pending work.
    assert "99-9-999 ->" not in output
    assert "410 u.s. 113" not in output


def test_scan_prunes_by_the_shared_reporter_vocabulary() -> None:
    _, session = _run()
    _, params = next(
        (c, p)
        for c, p in session.calls
        if c is queries.LIST_CASES_WITH_STATUTE_CITATIONS_CYPHER
    )
    assert params["reporters"] == list(cmd.STATUTE_REPORTERS)
    assert params["after"] == ""


def test_walk_uses_a_keyset_cursor_across_pages() -> None:
    pages = [
        [{"case_id": "case-1", "pending": []}],
        [{"case_id": "case-2", "pending": []}],
        [],
    ]
    _, session = _run(pages=pages)
    cursors = [
        p["after"]
        for c, p in session.calls
        if c is queries.LIST_CASES_WITH_STATUTE_CITATIONS_CYPHER
    ]
    assert cursors == ["", "case-1", "case-2"]


def test_limit_bounds_the_run() -> None:
    pages = [[{"case_id": "case-1", "pending": []}], []]
    _, session = _run("--limit", "1", pages=pages)
    takes = [
        p["limit"]
        for c, p in session.calls
        if c is queries.LIST_CASES_WITH_STATUTE_CITATIONS_CYPHER
    ]
    assert takes == [1]


def test_commit_and_dry_run_are_mutually_exclusive() -> None:
    with pytest.raises(CommandError):
        _run("--commit", "--dry-run")


@pytest.mark.parametrize("args", [("--batch-size", "0"), ("--limit", "0")])
def test_rejects_nonsense_bounds(args: tuple[str, ...]) -> None:
    with pytest.raises(CommandError):
        _run(*args)


# ---------------------------------------------------------------------------
# Recall envelope (BL-20260509-07). The backfill reads stored citation strings,
# so a clean summary does not mean "nothing left to link" — opinions ingested
# before the C.R.S. patterns landed carry no such string at all. Constitution
# §13: absence must be reported as absence, not read as coverage.
# ---------------------------------------------------------------------------


def test_every_run_states_what_the_offline_pass_cannot_recover() -> None:
    for args in ((), ("--commit",)):
        output, _ = _run(*args)
        assert cmd.RECALL_CAVEAT in output, f"missing recall caveat for {args!r}"


def test_the_caveat_names_the_forms_it_misses_and_the_remedy() -> None:
    """Specific enough to act on: which citation forms, and what to do."""
    caveat = cmd.RECALL_CAVEAT
    assert "C.R.S. § 18-3-102" in caveat
    assert "section 13-80-102, C.R.S." in caveat
    assert "re-ingest" in caveat.lower()


def test_the_caveat_survives_an_empty_corpus() -> None:
    """Nothing scanned is exactly when a reader could mistake it for done."""
    output, _ = _run(pages=[[]])
    assert "scanned=0 candidates=0 resolved=0 edges_created=0" in output
    assert cmd.RECALL_CAVEAT in output


# ---------------------------------------------------------------------------
# Recall pass: re-read opinions that stored no statutory citation at all
# (BL-20260906-88)
# ---------------------------------------------------------------------------

_OPINION_TEXT = (
    "The defendant was sentenced under C.R.S. § 18-3-102(1)(a). "
    "The claim is time-barred under section 99-9-999, C.R.S. "
)


class _FakeOpinionClient:
    def __init__(self, opinions: dict[str, dict[str, Any]]) -> None:
        self._opinions = opinions
        self.fetched: list[str] = []

    async def __aenter__(self) -> _FakeOpinionClient:
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        return None

    async def fetch_opinion(self, opinion_id: int | str) -> dict[str, Any]:
        self.fetched.append(str(opinion_id))
        try:
            return self._opinions[str(opinion_id)]
        except KeyError as exc:
            raise RuntimeError(f"404 for {opinion_id}") from exc


def _run_refetch(
    *args: str,
    opinions: dict[str, dict[str, Any]] | None = None,
    recall_pages: list[list[dict[str, Any]]] | None = None,
) -> tuple[str, Any, _FakeOpinionClient]:
    session = _FakeSession([[]])
    session.recall_pages = list(
        recall_pages
        if recall_pages is not None
        else [[{"case_id": "case-old", "source": "courtlistener"}], []]
    )
    client = _FakeOpinionClient(
        opinions
        if opinions is not None
        else {"case-old": {"plain_text": _OPINION_TEXT}}
    )
    out = StringIO()
    with (
        patch.object(cmd, "get_neo4j_driver", return_value=_FakeDriver(session)),
        patch(
            "law_ai.ingestionapp.services.courtlistener.CourtListenerClient",
            lambda *a, **k: client,
        ),
    ):
        call_command(_COMMAND, "--refetch", *args, stdout=out)
    return out.getvalue(), session, client


def test_refetch_recovers_a_cite_the_offline_pass_cannot_see() -> None:
    output, session, client = _run_refetch("--commit")
    assert client.fetched == ["case-old"]
    assert "refetched=1" in output
    assert "recovered=1" in output

    merges = [p for c, p in session.calls if c is queries.MERGE_CITES_STATUTE_CYPHER]
    assert [m["section_id"] for m in merges] == ["us-co/crs/18-3-102"]
    # Re-fetched edges are distinguishable from offline-backfilled ones.
    assert merges[0]["source"] == cmd.REFETCH_SOURCE
    assert merges[0]["case_id"] == "case-old"


def test_refetch_dry_run_writes_nothing() -> None:
    output, session, _ = _run_refetch("--verbose-pairs")
    assert "recovered=0" in output
    assert "re-fetched)" in output
    assert not [c for c, _ in session.calls if c is queries.MERGE_CITES_STATUTE_CYPHER]


def test_refetch_scan_is_scoped_to_refetchable_sources() -> None:
    _, session, _ = _run_refetch()
    _, params = next(
        (c, p)
        for c, p in session.calls
        if c is queries.LIST_CASES_WITHOUT_STATUTE_CITATIONS_CYPHER
    )
    assert params["sources"] == list(cmd.REFETCHABLE_SOURCES)
    assert params["reporters"] == list(cmd.STATUTE_REPORTERS)


def test_a_failed_refetch_is_counted_not_fatal() -> None:
    output, _, _ = _run_refetch("--commit", opinions={})
    assert "refetch_failed=1" in output
    assert "recovered=0" in output


def test_the_caveat_now_names_the_refetch_remedy() -> None:
    output, _, _ = _run_refetch()
    assert "--refetch" in cmd.RECALL_CAVEAT
    assert "Recall limit" in output


def test_without_refetch_no_opinion_is_fetched() -> None:
    session = _FakeSession(list(_ONE_PAGE))
    out = StringIO()
    with (
        patch.object(cmd, "get_neo4j_driver", return_value=_FakeDriver(session)),
        patch(
            "law_ai.ingestionapp.services.courtlistener.CourtListenerClient"
        ) as client,
    ):
        call_command(_COMMAND, stdout=out)
    client.assert_not_called()
    assert not [
        c
        for c, _ in session.calls
        if c is queries.LIST_CASES_WITHOUT_STATUTE_CITATIONS_CYPHER
    ]
