"""Doctrine gap → study plan (BL-20260817-04).

The curated map is data, so the first thing worth testing is that the data is
*valid*: every concept it names exists in the catalog. After that, the two
behaviours that make the plan useful — a matter's tags choose the concepts,
and the learner's own gaps choose the order.
"""

from __future__ import annotations

import json
from typing import Any

import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from law_ai.lsat.services import doctrine_map as dm
from law_ai.lsat.services.doctrine_map import (
    DoctrineMapError,
    concepts_for_tags,
    load_doctrine_map,
    normalise_tag,
    recommend_for_tags,
)

pytestmark = [pytest.mark.unit]


class TestTheMapItself:
    def test_every_mapped_concept_exists_in_the_catalog(self) -> None:
        from law_ai.lsat.services.bank import load_concepts

        known = set(load_concepts())
        mapping = load_doctrine_map()
        assert mapping, "the curated map must not be empty"
        for tag, entry in mapping.items():
            assert entry["concepts"], tag
            assert set(entry["concepts"]) <= known, tag

    def test_every_entry_explains_itself(self) -> None:
        for tag, entry in load_doctrine_map().items():
            assert entry["why"], f"{tag} has no rationale"
            assert entry["label"], f"{tag} has no label"

    def test_an_unknown_concept_id_fails_loudly(
        self, tmp_path: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        broken = tmp_path / "broken.json"
        broken.write_text(
            json.dumps({"map": {"negligence": {"concepts": ["not-a-concept"]}}}),
            encoding="utf-8",
        )
        monkeypatch.setattr(dm, "DATA_PATH", broken)
        load_doctrine_map.cache_clear()
        try:
            with pytest.raises(DoctrineMapError, match="unknown concept"):
                load_doctrine_map()
        finally:
            load_doctrine_map.cache_clear()

    def test_tags_normalise_case_and_separators(self) -> None:
        assert normalise_tag("  Landlord_Tenant ") == "landlord-tenant"


class TestSelection:
    def test_tags_choose_concepts_and_record_why(self) -> None:
        refs, unmapped = concepts_for_tags(["negligence"])
        ids = {r["concept_id"] for r in refs}
        assert "causation-vs-correlation" in ids
        assert unmapped == []
        assert all(r["from_tags"] == ["negligence"] for r in refs)

    def test_a_concept_two_issues_need_records_both_tags(self) -> None:
        refs, _ = concepts_for_tags(["negligence", "causation"])
        shared = next(r for r in refs if r["concept_id"] == "causation-vs-correlation")
        assert sorted(shared["from_tags"]) == ["causation", "negligence"]

    def test_an_uncovered_tag_is_reported_not_silently_dropped(self) -> None:
        _, unmapped = concepts_for_tags(["negligence", "admiralty-salvage"])
        assert unmapped == ["admiralty-salvage"]

    def test_no_tags_means_no_recommendations(self) -> None:
        plan = recommend_for_tags([])
        assert plan["concepts"] == []
        assert plan["unmapped_tags"] == []


@pytest.mark.django_db
class TestRanking:
    @pytest.fixture
    def learner(self):
        return get_user_model().objects.create_user(
            username="lee", password="pw-12345678"
        )

    def test_unpractised_concepts_come_first(self, learner) -> None:
        from law_ai.lsat.services.attempts import record_attempt

        # Practised, and always right → should not lead the plan.
        for _ in range(4):
            record_attempt(
                learner,
                question_id="q1",
                section="LR",
                correct=True,
                concepts=["causation-vs-correlation"],
            )
        plan = recommend_for_tags(["negligence"], user=learner)
        assert plan["concepts"][0]["status"] == "unpractised"
        practised = next(
            c for c in plan["concepts"] if c["concept_id"] == "causation-vs-correlation"
        )
        assert practised["status"] == "solid"
        assert practised["accuracy"] == 1.0

    def test_a_weak_concept_outranks_a_solid_one(self, learner) -> None:
        from law_ai.lsat.services.attempts import record_attempt

        for concept, correct in (
            ("causation-vs-correlation", False),
            ("alternative-cause", True),
        ):
            for _ in range(3):
                record_attempt(
                    learner,
                    question_id=f"q-{concept}",
                    section="LR",
                    correct=correct,
                    concepts=[concept],
                )
        ranked = [
            c["concept_id"]
            for c in recommend_for_tags(["causation"], user=learner)["concepts"]
            if c["attempts"]
        ]
        assert ranked.index("causation-vs-correlation") < ranked.index(
            "alternative-cause"
        )

    def test_a_plan_points_at_library_articles_and_drills(self, learner) -> None:
        plan = recommend_for_tags(["legal-writing"], user=learner)
        assert plan["concepts"]
        entry = plan["concepts"][0]
        assert "articles" in entry and "drills" in entry
        assert isinstance(entry["articles"], list)


@pytest.mark.django_db
class TestStudyPlanEndpoint:
    def test_a_matters_plan_comes_from_its_issue_tags(self) -> None:
        user = get_user_model().objects.create_user(
            username="ada", password="pw-12345678"
        )
        client = APIClient()
        client.force_authenticate(user=user)
        created = client.post(
            "/api/matters",
            {"name": "Slip and fall", "issue_tags": ["negligence", "quantum-meruit"]},
            format="json",
        ).json()
        body = client.get(f"/api/matters/{created['slug']}/study-plan").json()
        assert body["matter"]["slug"] == created["slug"]
        assert body["unmapped_tags"] == ["quantum-meruit"]
        assert {c["concept_id"] for c in body["concepts"]} >= {
            "causation-vs-correlation"
        }

    def test_the_plan_is_owner_scoped(self) -> None:
        from law_ai.matters.models import Matter

        other = get_user_model().objects.create_user(
            username="mallory", password="pw-12345678"
        )
        Matter.objects.create(owner=other, slug="theirs", name="Theirs")
        client = APIClient()
        client.force_authenticate(
            user=get_user_model().objects.create_user(
                username="ada", password="pw-12345678"
            )
        )
        assert client.get("/api/matters/theirs/study-plan").status_code == 404
