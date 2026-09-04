"""Tests for /api/lsat/library/* (spec 048 T-020: FR-12, AC-3, AC-4, AC-8)."""

from __future__ import annotations

from pathlib import Path

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from django.conf import settings
from law_ai.asgi import application as app
from law_ai.lsat.services.library import load_library, load_tracks


@pytest.fixture(autouse=True)
def _isolate_audit(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "AUDIT_PATH", str(tmp_path / "audit.jsonl"))


@pytest_asyncio.fixture
async def client():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac


def _any_article_id() -> str:
    return sorted(load_library())[0]


class TestIndex:
    async def test_index_returns_rows_without_bodies(self, client) -> None:
        r = await client.get("/api/lsat/library")
        assert r.status_code == 200
        body = r.json()
        assert body["count"] == len(load_library())
        row = body["articles"][0]
        assert "blocks" not in row  # NFR-PERF-1
        assert {"id", "title", "kind", "reading_minutes"} <= set(row)

    async def test_section_filter(self, client) -> None:
        r = await client.get("/api/lsat/library?section=RC")
        assert r.status_code == 200
        rows = r.json()["articles"]
        assert rows
        assert all("RC" in row["sections"] for row in rows)

    async def test_kind_filter(self, client) -> None:
        r = await client.get("/api/lsat/library?kind=section-guide")
        assert all(row["kind"] == "section-guide" for row in r.json()["articles"])

    async def test_concept_filter_uses_the_inverse_index(self, client) -> None:
        r = await client.get("/api/lsat/library?concept=weaken")
        rows = r.json()["articles"]
        assert rows, "no article is linked to the 'weaken' concept"

    async def test_track_filter_preserves_curriculum_order(self, client) -> None:
        track = next(iter(load_tracks().values()))
        r = await client.get(f"/api/lsat/library?track={track.id}")
        assert [row["id"] for row in r.json()["articles"]] == track.article_ids

    async def test_unknown_track_is_404(self, client) -> None:
        r = await client.get("/api/lsat/library?track=no-such-track")
        assert r.status_code == 404


class TestDetail:
    async def test_detail_returns_blocks_and_resolved_cross_references(
        self, client
    ) -> None:
        article_id = _any_article_id()
        r = await client.get(f"/api/lsat/library/{article_id}")
        assert r.status_code == 200
        body = r.json()
        assert body["article"]["id"] == article_id
        assert body["article"]["blocks"]
        assert body["article"]["outline"]
        for key in ("concepts", "prerequisites", "related", "tracks"):
            assert isinstance(body[key], list)
        assert isinstance(body["drill_question_count"], int)

    async def test_resolved_concepts_are_full_objects(self, client) -> None:
        article = next(a for a in load_library().values() if a.concepts)
        r = await client.get(f"/api/lsat/library/{article.id}")
        concepts = r.json()["concepts"]
        assert {c["id"] for c in concepts} == set(article.concepts)
        assert all(c.get("name") for c in concepts)

    async def test_unknown_article_is_404(self, client) -> None:
        r = await client.get("/api/lsat/library/no-such-article")
        assert r.status_code == 404

    async def test_static_routes_are_not_read_as_article_ids(self, client) -> None:
        """`/library/tracks` must never resolve to an article called "tracks"."""
        r = await client.get("/api/lsat/library/tracks")
        assert r.status_code == 200
        assert "tracks" in r.json()


class TestTracks:
    async def test_tracks_carry_computed_durations(self, client) -> None:
        r = await client.get("/api/lsat/library/tracks")
        assert r.status_code == 200
        body = r.json()
        assert body["count"] == len(load_tracks())
        for track in body["tracks"]:
            assert track["article_count"] == len(track["article_ids"])
            assert track["estimated_minutes"] > 0


class TestSearch:
    async def test_ranked_hits_with_snippets(self, client) -> None:
        r = await client.get("/api/lsat/library/search?q=negation")
        assert r.status_code == 200
        body = r.json()
        assert body["count"] > 0
        hit = body["results"][0]
        assert hit["snippet"]
        assert hit["matched_in"]
        scores = [h["score"] for h in body["results"]]
        assert scores == sorted(scores, reverse=True)

    @pytest.mark.parametrize("q", ["", "a"])
    async def test_short_query_is_422(self, client, q: str) -> None:
        r = await client.get(f"/api/lsat/library/search?q={q}")
        assert r.status_code == 422

    async def test_overlong_query_is_422(self, client) -> None:
        r = await client.get("/api/lsat/library/search?q=" + "x" * 101)
        assert r.status_code == 422

    async def test_no_match_is_an_empty_result_not_an_error(self, client) -> None:
        r = await client.get("/api/lsat/library/search?q=zzzzqqqqxxxx")
        assert r.status_code == 200
        assert r.json()["count"] == 0


class TestHealth:
    async def test_health_reports_every_audit_category(self, client) -> None:
        r = await client.get("/api/lsat/library/health")
        assert r.status_code == 200
        body = r.json()
        assert set(body) >= {"counts", "words", "coverage", "freshness", "graph"}
        assert body["counts"]["articles"] == len(load_library())


class TestConceptLinkage:
    async def test_concept_detail_lists_the_articles_that_teach_it(
        self, client
    ) -> None:
        """Spec 048 FR-7: the inverse of `Article.concepts`."""
        article = next(a for a in load_library().values() if a.concepts)
        concept_id = article.concepts[0]
        r = await client.get(f"/api/lsat/concepts/{concept_id}")
        assert r.status_code == 200
        assert article.id in r.json()["taught_in"]
