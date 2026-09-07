"""Unit tests for the ``densify_backfill`` management command (BL-20260429-11).

Hermetic: a hand-rolled fake Neo4j session (same shape as the one in
``tests/db/test_citation_resolver.py``) stands in for the driver, so no Docker
Neo4j is required. The live-graph proof is covered by the integration suite's
existing citation-resolver tests plus a manual ``--commit`` run.
"""

from __future__ import annotations

import re
from typing import Any

import pytest
from django.core.management import call_command  # type: ignore[import-untyped]
from django.core.management.base import CommandError  # type: ignore[import-untyped]

from law_ai.core.neo4j.queries import (
    LIST_CASES_WITH_UNLINKED_CITATIONS_CYPHER,
    list_cases_with_unlinked_citations,
)

MODULE = "law_ai.ingestionapp.management.commands.densify_backfill"


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


class FakeSession:
    """Answers the three Cypher statements the backfill issues."""

    def __init__(
        self,
        *,
        pages: list[list[dict[str, Any]]],
        aliases: dict[str, str],
        missing_targets: set[str] | None = None,
    ) -> None:
        self._pages = list(pages)
        self._aliases = aliases
        self._missing = missing_targets or set()
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.merged: list[dict[str, Any]] = []

    async def run(self, cypher: str, params: dict[str, Any]) -> _FakeResult:
        self.calls.append((cypher, params))
        if "HAS_CITATION" in cypher and "$after" in cypher:
            page = self._pages.pop(0) if self._pages else []
            return _FakeResult(page)
        if "UNWIND $normalized" in cypher:
            return _FakeResult(
                [
                    {"normalized": n, "case_id": self._aliases.get(n)}
                    for n in params["normalized"]
                ]
            )
        if "MERGE (src)-[r:CITES]->(dst)" in cypher:
            if params["dst_id"] in self._missing:
                return _FakeResult([])
            self.merged.append(params)
            return _FakeResult([{"r": "rel"}])
        raise AssertionError(f"unexpected cypher: {cypher}")  # pragma: no cover

    async def __aenter__(self) -> FakeSession:
        return self

    async def __aexit__(self, *exc: object) -> None:
        return None


class FakeDriver:
    def __init__(self, session: FakeSession) -> None:
        self._session = session

    def session(self) -> FakeSession:
        return self._session


def _page(case_id: str, pending: list[tuple[str, float]]) -> dict[str, Any]:
    return {
        "case_id": case_id,
        "pending": [{"normalized": n, "confidence": c} for n, c in pending],
    }


@pytest.fixture
def install_driver(monkeypatch):
    def _install(session: FakeSession) -> FakeSession:
        monkeypatch.setattr(MODULE + ".get_neo4j_driver", lambda: FakeDriver(session))
        return session

    return _install


# ---------------------------------------------------------------------------
# The read query
# ---------------------------------------------------------------------------


def test_query_is_keyset_paginated_and_skips_archived() -> None:
    """SKIP would step over rows that a committing run removes; a cursor won't."""
    cypher = LIST_CASES_WITH_UNLINKED_CITATIONS_CYPHER
    assert "SKIP" not in cypher
    assert "c.id > $after" in cypher
    assert "c.archived_at IS NULL" in cypher
    assert re.search(r"ORDER BY case_id\s+LIMIT \$limit", cypher)


@pytest.mark.asyncio
async def test_list_cases_with_unlinked_citations_shapes_rows() -> None:
    session = FakeSession(
        pages=[[_page("a", [("410 u.s. 113", 0.8)]), {"case_id": "b", "pending": []}]],
        aliases={},
    )
    rows = await list_cases_with_unlinked_citations(session, after="", limit=10)
    assert rows == [
        {
            "case_id": "a",
            "pending": [{"normalized": "410 u.s. 113", "confidence": 0.8}],
        },
        {"case_id": "b", "pending": []},
    ]
    assert session.calls[0][1] == {"after": "", "limit": 10}


# ---------------------------------------------------------------------------
# Dry run (the default)
# ---------------------------------------------------------------------------


def test_dry_run_is_the_default_and_writes_nothing(install_driver, capsys) -> None:
    session = install_driver(
        FakeSession(
            pages=[[_page("src-a", [("410 u.s. 113", 0.8), ("999 zz 9", 0.5)])], []],
            aliases={"410 u.s. 113": "roe"},
        )
    )
    call_command("densify_backfill", "--verbose-pairs")
    out = capsys.readouterr().out

    assert session.merged == []
    assert not any("MERGE (src)-[r:CITES]" in c for c, _ in session.calls)
    assert "dry run" in out
    assert "scanned=2 resolved=1 edges_created=0" in out
    assert "410 u.s. 113 -> roe (would merge)" in out
    assert "Re-run with --commit" in out


def test_explicit_dry_run_flag_matches_the_default(install_driver, capsys) -> None:
    install_driver(
        FakeSession(
            pages=[[_page("src-a", [("410 u.s. 113", 0.8)])], []],
            aliases={"410 u.s. 113": "roe"},
        )
    )
    call_command("densify_backfill", "--dry-run")
    assert "scanned=1 resolved=1 edges_created=0" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# Commit mode
# ---------------------------------------------------------------------------


def test_commit_merges_edges_with_the_has_citation_confidence(
    install_driver, capsys
) -> None:
    session = install_driver(
        FakeSession(
            pages=[[_page("src-a", [("410 u.s. 113", 0.77), ("999 zz 9", 0.5)])], []],
            aliases={"410 u.s. 113": "roe"},
        )
    )
    call_command("densify_backfill", "--commit")
    out = capsys.readouterr().out

    assert len(session.merged) == 1
    merged = session.merged[0]
    assert merged["src_id"] == "src-a"
    assert merged["dst_id"] == "roe"
    assert merged["confidence"] == pytest.approx(0.77)
    assert merged["ingest_timestamp"]
    assert "scanned=2 resolved=1 edges_created=1" in out
    assert "Re-run with --commit" not in out


def test_commit_never_touches_case_properties(install_driver) -> None:
    """MERGE-only, edges-only: no :Case write statement may be issued."""
    session = install_driver(
        FakeSession(
            pages=[[_page("src-a", [("410 u.s. 113", 0.9)])], []],
            aliases={"410 u.s. 113": "roe"},
        )
    )
    call_command("densify_backfill", "--commit")
    for cypher, _ in session.calls:
        assert "MERGE (c:Case" not in cypher
        assert "SET c." not in cypher
        assert "DELETE" not in cypher


def test_commit_is_idempotent_across_runs(install_driver) -> None:
    session = install_driver(
        FakeSession(
            pages=[[_page("src-a", [("410 u.s. 113", 0.9)])], [], []],
            aliases={"410 u.s. 113": "roe"},
        )
    )
    call_command("densify_backfill", "--commit")
    first = list(session.merged)
    # Second run: the fixed row has dropped out of the predicate, so nothing
    # more is merged.
    call_command("densify_backfill", "--commit")
    assert session.merged == first


def test_self_citation_is_skipped(install_driver, capsys) -> None:
    session = install_driver(
        FakeSession(
            pages=[[_page("roe", [("410 u.s. 113", 0.9)])], []],
            aliases={"410 u.s. 113": "roe"},
        )
    )
    call_command("densify_backfill", "--commit", "--verbose-pairs")
    out = capsys.readouterr().out
    assert session.merged == []
    assert "self, skipped" in out
    assert "self_citations=1" in out


def test_missing_target_case_does_not_count_as_an_edge(install_driver, capsys) -> None:
    install_driver(
        FakeSession(
            pages=[[_page("src-a", [("410 u.s. 113", 0.9)])], []],
            aliases={"410 u.s. 113": "roe"},
            missing_targets={"roe"},
        )
    )
    call_command("densify_backfill", "--commit", "--verbose-pairs")
    out = capsys.readouterr().out
    assert "target missing" in out
    assert "edges_created=0" in out


# ---------------------------------------------------------------------------
# Batching + limits
# ---------------------------------------------------------------------------


def test_pages_with_the_keyset_cursor_until_exhausted(install_driver) -> None:
    session = install_driver(
        FakeSession(
            pages=[
                [_page("a", [("c1", 0.5)]), _page("b", [("c2", 0.5)])],
                [_page("c", [("c3", 0.5)])],
                [],
            ],
            aliases={"c1": "t1", "c2": "t2", "c3": "t3"},
        )
    )
    call_command("densify_backfill", "--batch-size", "2")
    reads = [p for c, p in session.calls if "$after" in c]
    assert [r["after"] for r in reads] == ["", "b", "c"]
    assert all(r["limit"] == 2 for r in reads)


def test_limit_caps_the_number_of_cases(install_driver, capsys) -> None:
    session = install_driver(
        FakeSession(
            pages=[[_page("a", [("c1", 0.5)]), _page("b", [("c2", 0.5)])]],
            aliases={"c1": "t1", "c2": "t2"},
        )
    )
    call_command("densify_backfill", "--limit", "2", "--batch-size", "50")
    reads = [p for c, p in session.calls if "$after" in c]
    # One read of at most 2 cases, then the budget is spent — no second read.
    assert len(reads) == 1
    assert reads[0]["limit"] == 2
    assert "scanned=2" in capsys.readouterr().out


def test_provenance_logged_per_batch(install_driver, monkeypatch) -> None:
    logged: list[dict[str, Any]] = []
    from law_ai.core.provenance import provenance

    monkeypatch.setattr(
        provenance,
        "log_graph_query",
        lambda **kw: logged.append(kw),
    )
    install_driver(
        FakeSession(
            pages=[[_page("a", [("c1", 0.5)])], [_page("b", [("c2", 0.5)])], []],
            aliases={"c1": "t1", "c2": "t2"},
        )
    )
    call_command("densify_backfill", "--batch-size", "1")
    batch_events = [e for e in logged if e["cypher"] == "densify_backfill.batch"]
    assert len(batch_events) == 2
    assert batch_events[0]["params"]["commit"] is False
    assert batch_events[0]["params"]["cases"] == 1


# ---------------------------------------------------------------------------
# Argument validation
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "argv",
    [
        ["--commit", "--dry-run"],
        ["--batch-size", "0"],
        ["--limit", "0"],
    ],
)
def test_invalid_arguments_raise(install_driver, argv) -> None:
    install_driver(FakeSession(pages=[[]], aliases={}))
    with pytest.raises(CommandError):
        call_command("densify_backfill", *argv)
