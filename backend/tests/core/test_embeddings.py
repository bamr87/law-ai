"""Tests for the local embedding client + backfill (BL-20260810-17).

Hermetic: ``httpx.AsyncClient`` is replaced with a stub, so nothing reaches
Ollama. Test settings already point ``OLLAMA_BASE_URL`` at a closed port, which
is what makes the fail-open path the default in the rest of the suite.
"""

from __future__ import annotations

from typing import Any

import httpx
import pytest
from django.core.management import call_command  # type: ignore[import-untyped]
from django.core.management.base import CommandError  # type: ignore[import-untyped]

from law_ai.core.llm import embeddings as emb

BACKFILL = "law_ai.core.management.commands.backfill_embeddings"


class _Response:
    def __init__(self, payload: Any, *, status: int = 200) -> None:
        self._payload = payload
        self.status_code = status

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise httpx.HTTPStatusError(
                "boom", request=None, response=None  # type: ignore[arg-type]
            )

    def json(self) -> Any:
        return self._payload


class _Client:
    """Stub httpx.AsyncClient that answers /api/embeddings."""

    posted: list[dict[str, Any]] = []

    def __init__(self, *, payloads: list[Any] | None = None, raise_on_post=None):
        self._payloads = list(payloads or [])
        self._raise = raise_on_post

    async def __aenter__(self) -> _Client:
        return self

    async def __aexit__(self, *exc: object) -> None:
        return None

    async def post(self, url: str, json: dict[str, Any]) -> _Response:
        type(self).posted.append({"url": url, **json})
        if self._raise is not None:
            raise self._raise
        return _Response(self._payloads.pop(0) if self._payloads else {})


def _install(monkeypatch: pytest.MonkeyPatch, **kwargs: Any) -> None:
    _Client.posted = []
    monkeypatch.setattr(emb.httpx, "AsyncClient", lambda **_: _Client(**kwargs))


# ---------------------------------------------------------------------------
# Text builders
# ---------------------------------------------------------------------------


def test_case_embedding_text_joins_title_and_holding() -> None:
    assert emb.case_embedding_text("A v. B", "Held: x") == "A v. B\nHeld: x"
    assert emb.case_embedding_text("A v. B", None) == "A v. B"
    assert emb.case_embedding_text(None, "   ") == ""


def test_statute_embedding_text_joins_citation_heading_text() -> None:
    out = emb.statute_embedding_text("C.R.S. 1-2-3", "Scope", "The text.")
    assert out == "C.R.S. 1-2-3\nScope\nThe text."


def test_embedding_text_is_truncated() -> None:
    assert len(emb.case_embedding_text("x" * 20000, None)) == 8000


# ---------------------------------------------------------------------------
# The client
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_embed_text_returns_the_vector(monkeypatch: pytest.MonkeyPatch) -> None:
    _install(monkeypatch, payloads=[{"embedding": [0.5] * emb.EMBED_DIMENSIONS}])
    vector = await emb.embed_text("judicial review")
    assert vector == [0.5] * emb.EMBED_DIMENSIONS
    assert _Client.posted[0]["url"].endswith("/api/embeddings")
    assert _Client.posted[0]["model"] == emb.embedding_model()


@pytest.mark.asyncio
async def test_embed_text_fails_open_when_ollama_is_down(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Ingest must never block on the embedder."""
    _install(monkeypatch, raise_on_post=httpx.ConnectError("refused"))
    assert await emb.embed_text("anything") is None


@pytest.mark.asyncio
async def test_wrong_dimension_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    """A vector index rejects mismatched dims — catch it before Neo4j does."""
    _install(monkeypatch, payloads=[{"embedding": [0.1, 0.2, 0.3]}])
    assert await emb.embed_text("anything") is None


@pytest.mark.asyncio
async def test_embed_texts_preserves_order_and_skips_blanks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install(
        monkeypatch,
        payloads=[
            {"embedding": [0.1] * emb.EMBED_DIMENSIONS},
            {"embedding": [0.2] * emb.EMBED_DIMENSIONS},
        ],
    )
    out = await emb.embed_texts(["a", "   ", "b"])
    assert out[0] == [0.1] * emb.EMBED_DIMENSIONS
    assert out[1] is None
    assert out[2] == [0.2] * emb.EMBED_DIMENSIONS
    assert len(_Client.posted) == 2


@pytest.mark.asyncio
async def test_embed_texts_of_nothing_makes_no_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install(monkeypatch)
    assert await emb.embed_texts(["", "  "]) == [None, None]
    assert _Client.posted == []


@pytest.mark.asyncio
async def test_a_batch_writes_one_provenance_event(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Constitution §4: retrieval-side model calls are auditable too."""
    events: list[tuple[str, dict[str, Any]]] = []
    monkeypatch.setattr(
        emb.provenance,
        "log_event",
        lambda kind, payload: events.append((kind, payload)),
    )
    _install(monkeypatch, payloads=[{"embedding": [0.4] * emb.EMBED_DIMENSIONS}])
    await emb.embed_text("x", component="ingest_case")
    assert len(events) == 1
    kind, payload = events[0]
    assert kind == "embedding_batch"
    assert payload["component"] == "ingest_case"
    assert payload["dimensions"] == emb.EMBED_DIMENSIONS
    assert payload["computed"] == 1


@pytest.mark.asyncio
async def test_a_failed_batch_writes_no_provenance_event(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[Any] = []
    monkeypatch.setattr(emb.provenance, "log_event", lambda *a: events.append(a))
    _install(monkeypatch, raise_on_post=httpx.ConnectError("refused"))
    await emb.embed_text("x")
    assert events == []


def test_the_embedder_is_pinned_to_the_local_stack() -> None:
    """Constitution §1 / LegalBench comparability: never the provider chain."""
    source = __import__("pathlib").Path(emb.__file__).read_text()
    assert "OLLAMA_BASE_URL" in source
    assert "ANTHROPIC" not in source.upper()
    assert "law_ai.core.llm.router" not in source
    assert emb.DEFAULT_EMBED_MODEL == "nomic-embed-text"


def test_the_migration_declares_the_same_dimension() -> None:
    """A dimension mismatch makes every vector write fail at runtime."""
    from law_ai.core.neo4j import migrator

    path = next(
        p for p in migrator.discover() if migrator.migration_id(p).startswith("008")
    )
    text = path.read_text()
    assert f"`vector.dimensions`: {emb.EMBED_DIMENSIONS}" in text
    assert "'cosine'" in text
    assert emb.CASE_VECTOR_INDEX in text
    assert emb.STATUTE_VECTOR_INDEX in text


# ---------------------------------------------------------------------------
# backfill_embeddings
# ---------------------------------------------------------------------------


class _FakeResult:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self._rows = rows

    def __aiter__(self):
        async def gen():
            for row in self._rows:
                yield row

        return gen()


class FakeSession:
    def __init__(self, pages: dict[str, list[list[dict[str, Any]]]]) -> None:
        self._pages = {k: list(v) for k, v in pages.items()}
        self.writes: list[dict[str, Any]] = []
        self.calls: list[str] = []

    async def run(self, cypher: str, params: dict[str, Any]) -> _FakeResult:
        self.calls.append(cypher)
        if "MATCH (c:Case)" in cypher and "RETURN c.id" in cypher:
            pages = self._pages.get("Case", [])
            return _FakeResult(pages.pop(0) if pages else [])
        if "MATCH (s:StatuteSection)" in cypher and "RETURN s.id" in cypher:
            pages = self._pages.get("StatuteSection", [])
            return _FakeResult(pages.pop(0) if pages else [])
        if "SET n.embedding" in cypher:
            self.writes.append(params)
        return _FakeResult([])

    async def __aenter__(self) -> FakeSession:
        return self

    async def __aexit__(self, *exc: object) -> None:
        return None


class FakeDriver:
    def __init__(self, session: FakeSession) -> None:
        self._session = session

    def session(self) -> FakeSession:
        return self._session


@pytest.fixture
def backfill_env(monkeypatch: pytest.MonkeyPatch):
    def _setup(pages, vector=None):
        session = FakeSession(pages)
        monkeypatch.setattr(BACKFILL + ".get_neo4j_driver", lambda: FakeDriver(session))

        async def fake_embed_texts(texts, *, component="graph"):
            return [None if not t.strip() else vector for t in texts]

        monkeypatch.setattr(BACKFILL + ".embed_texts", fake_embed_texts)
        return session

    return _setup


def test_backfill_dry_run_writes_nothing(backfill_env, capsys) -> None:
    session = backfill_env(
        {"Case": [[{"id": "c1", "title": "A", "holding_summary": "H"}]]},
        vector=[0.1] * emb.EMBED_DIMENSIONS,
    )
    call_command("backfill_embeddings", "--label", "Case")
    out = capsys.readouterr().out
    assert session.writes == []
    assert "dry run" in out
    assert "Case: pending=1 embedded=0" in out


def test_backfill_commit_writes_vectors(backfill_env, capsys) -> None:
    session = backfill_env(
        {
            "Case": [
                [{"id": "c1", "title": "A", "holding_summary": "H"}],
                [],
            ]
        },
        vector=[0.1] * emb.EMBED_DIMENSIONS,
    )
    call_command("backfill_embeddings", "--commit", "--label", "Case")
    assert len(session.writes) == 1
    written = session.writes[0]
    assert written["model"] == emb.embedding_model()
    assert written["rows"] == [{"id": "c1", "embedding": [0.1] * emb.EMBED_DIMENSIONS}]
    assert "Case: pending=1 embedded=1" in capsys.readouterr().out


def test_backfill_stops_when_the_embedder_is_down(backfill_env, capsys) -> None:
    """No vectors → stop, do not spin on the same page."""
    session = backfill_env(
        {"Case": [[{"id": "c1", "title": "A", "holding_summary": "H"}]] * 5},
        vector=None,
    )
    call_command("backfill_embeddings", "--commit", "--label", "Case")
    assert session.writes == []
    assert "local embedder is unreachable" in capsys.readouterr().out


def test_backfill_counts_nodes_with_no_text(backfill_env, capsys) -> None:
    backfill_env(
        {"Case": [[{"id": "c1", "title": None, "holding_summary": None}], []]},
        vector=[0.2] * emb.EMBED_DIMENSIONS,
    )
    call_command("backfill_embeddings", "--commit", "--label", "Case")
    assert "no_text=1" in capsys.readouterr().out


def test_backfill_only_visits_nodes_missing_this_models_vector(
    backfill_env,
) -> None:
    session = backfill_env({"Case": [[]]}, vector=None)
    call_command("backfill_embeddings", "--label", "Case")
    read = next(c for c in session.calls if "RETURN c.id" in c)
    assert "c.embedding IS NULL" in read
    assert "coalesce(c.embedding_model, '') <> $model" in read
    assert "c.archived_at IS NULL" in read


def test_backfill_covers_both_labels_by_default(backfill_env, capsys) -> None:
    backfill_env({"Case": [[]], "StatuteSection": [[]]}, vector=None)
    call_command("backfill_embeddings")
    out = capsys.readouterr().out
    assert "Case: pending=0" in out
    assert "StatuteSection: pending=0" in out


@pytest.mark.parametrize("argv", [["--batch-size", "0"], ["--limit", "0"]])
def test_backfill_rejects_bad_arguments(backfill_env, argv) -> None:
    backfill_env({"Case": [[]]}, vector=None)
    with pytest.raises(CommandError):
        call_command("backfill_embeddings", *argv)
