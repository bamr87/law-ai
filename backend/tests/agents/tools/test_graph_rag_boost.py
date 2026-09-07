"""Matter-scoped retrieval memory (BL-20260817-05).

Research inside a matter used to start from zero every round: authorities a
human had already checked and approved were re-ranked against everything else
as if they had never been seen. These lock in the boost — and, just as
importantly, that the boost is *declared* in the coverage envelope, because an
undeclared thumb on the scale would read as a fresh relevance judgement.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any

import pytest
from django.contrib.auth import get_user_model

from law_ai.agents_runtime.tools.graph_rag import (
    GraphRAGRetriever,
    RetrievalCoverage,
)

pytestmark = [pytest.mark.unit]


class _FakeResult:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self._rows = rows

    def __aiter__(self):
        async def gen():
            for row in self._rows:
                yield row

        return gen()


class _FakeSession:
    def __init__(self, routes: dict[str, Any]) -> None:
        self.routes = routes

    async def run(self, cypher: str, params: dict[str, Any]) -> _FakeResult:
        for marker, rows in self.routes.items():
            if marker in cypher:
                return _FakeResult(rows)
        return _FakeResult([])


def _factory(session: _FakeSession) -> Any:
    @asynccontextmanager
    async def make() -> Any:
        yield session

    return make


def _case(node_id: str, score: float) -> dict[str, Any]:
    return {
        "id": node_id,
        "title": node_id,
        "holding_summary": "…",
        "court": "us-supreme",
        "decided_at": "1900-01-01",
        "source": "courtlistener",
        "source_url": f"https://example.test/{node_id}",
        "confidence": 0.9,
        "score": score,
    }


def _retriever(**kwargs: Any) -> GraphRAGRetriever:
    session = _FakeSession(
        {
            "db.index.fulltext.queryNodes": [
                _case("case:a", 3.0),
                _case("case:b", 2.0),
                _case("case:c", 1.0),
            ]
        }
    )
    return GraphRAGRetriever(
        session_factory=_factory(session), include_statutes=False, **kwargs
    )


class TestBoostOrdering:
    async def test_no_boost_leaves_the_corpus_order_alone(self) -> None:
        retriever = _retriever()
        passages = await retriever({"queries": ["judicial review"]})
        assert [p["id"] for p in passages] == ["case:a", "case:b", "case:c"]
        assert retriever.last_coverage.boosted_count == 0
        assert all("boosted" not in p for p in passages)

    async def test_a_verified_authority_is_promoted_and_labelled(self) -> None:
        retriever = _retriever(boost_ids={"case:c"}, boost_source="matter:lease")
        passages = await retriever({"queries": ["judicial review"]})
        assert [p["id"] for p in passages] == ["case:c", "case:a", "case:b"]
        assert passages[0]["boosted"] is True
        assert passages[0]["boost_source"] == "matter:lease"
        assert retriever.last_coverage.boosted_count == 1
        assert retriever.last_coverage.boost_source == "matter:lease"

    async def test_the_boost_is_stable_within_each_group(self) -> None:
        retriever = _retriever(boost_ids={"case:c", "case:b"})
        ids = [p["id"] for p in await retriever({"queries": ["q"]})]
        # b before c (their corpus order), both before the unboosted a.
        assert ids == ["case:b", "case:c", "case:a"]

    async def test_a_boost_id_the_corpus_never_returned_adds_nothing(self) -> None:
        retriever = _retriever(boost_ids={"case:zzz"})
        passages = await retriever({"queries": ["q"]})
        assert [p["id"] for p in passages] == ["case:a", "case:b", "case:c"]
        assert retriever.last_coverage.boosted_count == 0
        # No boost happened, so nothing claims one did.
        assert retriever.last_coverage.boost_source == ""

    async def test_state_may_carry_the_boost_set(self) -> None:
        retriever = _retriever()
        passages = await retriever({"queries": ["q"], "boost_case_ids": ["case:b"]})
        assert passages[0]["id"] == "case:b"
        assert retriever.last_coverage.boost_source == "explicit"


class TestCoverageEnvelope:
    def test_the_caveat_names_the_bias(self) -> None:
        coverage = RetrievalCoverage(
            result_count=3, boosted_count=2, boost_source="matter:lease"
        )
        note = coverage.note()
        assert "ranked first" in note
        assert "matter:lease" in note
        assert "deliberate bias" in note

    def test_no_boost_no_claim(self) -> None:
        assert "ranked first" not in RetrievalCoverage(result_count=3).note()


@pytest.mark.django_db
class TestMatterBoostSet:
    def test_only_verified_authorities_boost(self) -> None:
        from law_ai.matters.models import Matter, MatterAuthority
        from law_ai.matters.services.authorities import (
            boost_set_for_matter,
            verified_authority_ids,
        )

        owner = get_user_model().objects.create_user(
            username="ada", password="pw-12345678"
        )
        matter = Matter.objects.create(owner=owner, slug="lease", name="Lease")
        MatterAuthority.objects.create(
            matter=matter, node_id="case:verified", verified_at="2026-09-01T00:00:00Z"
        )
        MatterAuthority.objects.create(matter=matter, node_id="case:candidate")

        assert verified_authority_ids(matter) == {"case:verified"}
        ids, label = boost_set_for_matter(matter.pk)
        assert ids == {"case:verified"}
        assert label == "matter:lease"

    def test_an_archived_matter_boosts_nothing(self) -> None:
        from django.utils import timezone

        from law_ai.matters.models import Matter, MatterAuthority
        from law_ai.matters.services.authorities import boost_set_for_matter

        owner = get_user_model().objects.create_user(
            username="ada", password="pw-12345678"
        )
        matter = Matter.objects.create(
            owner=owner, slug="old", name="Old", archived_at=timezone.now()
        )
        MatterAuthority.objects.create(
            matter=matter, node_id="case:x", verified_at=timezone.now()
        )
        assert boost_set_for_matter(matter.pk) == (set(), "")

    def test_no_matter_id_means_no_boost(self) -> None:
        from law_ai.matters.services.authorities import boost_set_for_matter

        assert boost_set_for_matter(None) == (set(), "")

    def test_the_retriever_resolves_a_matter_id_from_state(self) -> None:
        """A ``matter_id`` in the workflow state becomes the run's boost set."""
        from django.utils import timezone

        from law_ai.matters.models import Matter, MatterAuthority

        owner = get_user_model().objects.create_user(
            username="ada", password="pw-12345678"
        )
        matter = Matter.objects.create(owner=owner, slug="lease", name="Lease")
        MatterAuthority.objects.create(
            matter=matter, node_id="case:c", verified_at=timezone.now()
        )
        MatterAuthority.objects.create(matter=matter, node_id="case:a")

        ids, source = _retriever()._resolve_boost({"matter_id": matter.pk})
        assert ids == {"case:c"}
        assert source == "matter:lease"

    def test_an_unresolvable_matter_id_never_breaks_retrieval(self) -> None:
        assert _retriever()._resolve_boost({"matter_id": 999_999}) == (set(), "")
