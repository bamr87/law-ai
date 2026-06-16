"""CLI tests for the offline ``--source sample`` seed (graph empty-state CTA).

``make ingest-sample`` runs this path; it must populate Neo4j with a handful of
landmark cases + citations using **no network call or API token** (the
courtlistener/colorado paths both require one).
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest

# Make scripts/ importable.
SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import ingest_sample  # type: ignore[import-not-found]  # noqa: E402


def test_sample_dry_run_reports_five_committed(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Dry-run touches no driver and reports the seed size."""
    rc = ingest_sample.main(["--source", "sample", "--dry-run"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "source=sample" in out
    assert "committed=5" in out
    assert "skipped=0" in out


# ---------------------------------------------------------------------------
# Commit mode against a fake async driver (no live Neo4j needed).
# ---------------------------------------------------------------------------


class _FakeSession:
    def __init__(self, calls: list[tuple[str, dict[str, Any]]]) -> None:
        self._calls = calls

    async def run(self, cypher: str, params: dict[str, Any] | None = None) -> None:
        self._calls.append((cypher, params or {}))

    async def __aenter__(self) -> _FakeSession:
        return self

    async def __aexit__(self, *exc: object) -> bool:
        return False


class _FakeDriver:
    def __init__(self, calls: list[tuple[str, dict[str, Any]]]) -> None:
        self._calls = calls

    def session(self) -> _FakeSession:
        return _FakeSession(self._calls)


def test_sample_commit_writes_cases_citations_and_edges(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    calls: list[tuple[str, dict[str, Any]]] = []
    monkeypatch.setattr(
        "lawgraph.core.neo4j.driver.get_neo4j_driver",
        lambda: _FakeDriver(calls),
    )

    rc = ingest_sample.main(["--source", "sample"])
    assert rc == 0
    assert "source=sample" in capsys.readouterr().out

    # 5 cases × (case MERGE + citation MERGE) + 6 CITES edges = 16 writes.
    assert len(calls) == 16

    case_params = [p for c, p in calls if "MERGE (c:Case" in c]
    assert len(case_params) == 5
    # Every seeded case carries provenance fields (constitution §4).
    for p in case_params:
        assert p["source"] == "seed"
        assert p["confidence"] == 1.0
        assert p["court"] == "Supreme Court of the United States"
    ids = {p["id"] for p in case_params}
    assert "scotus-brown-1954" in ids and "scotus-marbury-1803" in ids

    cites_params = [p for c, p in calls if "MERGE (src)-[r:CITES]" in c]
    assert len(cites_params) == 6
    pairs = {(p["src_id"], p["dst_id"]) for p in cites_params}
    assert ("scotus-brown-1954", "scotus-plessy-1896") in pairs
    assert ("scotus-miranda-1966", "scotus-gideon-1963") in pairs
    # Four cases cite Marbury (the judicial-review hub).
    assert sum(1 for _, dst in pairs if dst == "scotus-marbury-1803") == 4
