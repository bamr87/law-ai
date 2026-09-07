"""The matter spine: ownership, artifacts, authorities (spec 036, BL-2026081x).

The load-bearing property under test is not CRUD, it is **ownership**: a slug
is only ever resolved inside the caller's own rows, so another user's matter
is indistinguishable from one that never existed.
"""

from __future__ import annotations

from typing import Any

import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from law_ai.matters.models import Matter, MatterArtifact, MatterAuthority

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


@pytest.fixture
def owner():
    return get_user_model().objects.create_user(username="ada", password="pw-12345678")


@pytest.fixture
def intruder():
    return get_user_model().objects.create_user(
        username="mallory", password="pw-12345678"
    )


@pytest.fixture
def in_graph():
    """Pretend the corpus holds whatever node the test records.

    BL-20260906-16 made recording an authority check ``node_id`` against
    Neo4j, so a test that records one has to say whether the graph has it —
    otherwise the result depends on whatever the local graph happens to hold.
    """
    from unittest.mock import patch

    with patch(
        "law_ai.matters.services.authorities.graph_labels_for", return_value=["Case"]
    ) as stub:
        yield stub


@pytest.fixture
def client(owner) -> APIClient:
    api = APIClient()
    api.force_authenticate(user=owner)
    return api


def _make(client: APIClient, **body: Any) -> dict[str, Any]:
    payload = {"name": "Smith lease dispute", "issue_tags": ["landlord-tenant"]}
    payload.update(body)
    res = client.post("/api/matters", payload, format="json")
    assert res.status_code == 201, res.json()
    return res.json()


class TestOwnership:
    def test_anonymous_callers_get_401(self) -> None:
        assert APIClient().get("/api/matters").status_code == 401

    def test_create_then_list_returns_only_mine(
        self, client: APIClient, owner, intruder
    ) -> None:
        _make(client)
        Matter.objects.create(owner=intruder, slug="theirs", name="Theirs")
        body = client.get("/api/matters").json()
        assert body["count"] == 1
        assert body["matters"][0]["slug"] == "smith-lease-dispute"

    def test_another_users_slug_is_a_plain_404(
        self, client: APIClient, intruder
    ) -> None:
        Matter.objects.create(owner=intruder, slug="secret-merger", name="Secret")
        res = client.get("/api/matters/secret-merger")
        assert res.status_code == 404
        # Same shape as a slug nobody has, so probing learns nothing.
        assert client.get("/api/matters/never-existed").status_code == 404

    def test_two_users_may_hold_the_same_slug(self, client: APIClient, intruder):
        _make(client, slug="lease")
        Matter.objects.create(owner=intruder, slug="lease", name="Their lease")
        assert Matter.objects.filter(slug="lease").count() == 2

    def test_a_duplicate_slug_for_one_owner_is_a_conflict(self, client: APIClient):
        _make(client, slug="lease")
        res = client.post(
            "/api/matters", {"name": "Again", "slug": "lease"}, format="json"
        )
        assert res.status_code == 409

    def test_a_bad_slug_is_rejected(self, client: APIClient) -> None:
        res = client.post(
            "/api/matters", {"name": "x", "slug": "../etc/passwd"}, format="json"
        )
        assert res.status_code == 422


class TestLifecycle:
    def test_patch_updates_tags_and_stage(self, client: APIClient) -> None:
        matter = _make(client)
        res = client.patch(
            f"/api/matters/{matter['slug']}",
            {"stage": "research", "issue_tags": ["negligence", "damages"]},
            format="json",
        )
        assert res.status_code == 200
        assert res.json()["stage"] == "research"
        assert res.json()["issue_tags"] == ["negligence", "damages"]

    def test_an_unknown_stage_is_rejected(self, client: APIClient) -> None:
        matter = _make(client)
        res = client.patch(
            f"/api/matters/{matter['slug']}", {"stage": "vibes"}, format="json"
        )
        assert res.status_code == 422

    def test_archiving_soft_deletes(self, client: APIClient, owner) -> None:
        matter = _make(client)
        assert (
            client.patch(
                f"/api/matters/{matter['slug']}", {"archived": True}, format="json"
            ).status_code
            == 200
        )
        assert client.get(f"/api/matters/{matter['slug']}").status_code == 404
        # §5: the row is still there.
        assert Matter.objects.filter(owner=owner, slug=matter["slug"]).exists()


class TestArtifactsAndAuthorities:
    def test_artifact_carries_its_provenance_trace(self, client: APIClient) -> None:
        matter = _make(client)
        res = client.post(
            f"/api/matters/{matter['slug']}/artifacts",
            {
                "kind": "analysis",
                "title": "IRAC on habitability",
                "trace_id": "tr-1",
                "analysis_id": "an-1",
            },
            format="json",
        )
        assert res.status_code == 201
        assert res.json()["trace_id"] == "tr-1"
        detail = client.get(f"/api/matters/{matter['slug']}").json()
        assert [a["title"] for a in detail["artifacts"]] == ["IRAC on habitability"]

    def test_unknown_artifact_kind_is_rejected(self, client: APIClient) -> None:
        matter = _make(client)
        res = client.post(
            f"/api/matters/{matter['slug']}/artifacts",
            {"kind": "wishes"},
            format="json",
        )
        assert res.status_code == 422

    def test_recording_an_authority_twice_updates_rather_than_duplicates(
        self, client: APIClient, in_graph
    ) -> None:
        matter = _make(client)
        first = client.post(
            f"/api/matters/{matter['slug']}/authorities",
            {"node_id": "case-1", "citation": "1 U.S. 1"},
            format="json",
        )
        assert first.status_code == 201
        assert first.json()["verified"] is False
        second = client.post(
            f"/api/matters/{matter['slug']}/authorities",
            {"node_id": "case-1", "citation": "1 U.S. 1", "verified": True},
            format="json",
        )
        assert second.status_code == 200
        assert second.json()["verified"] is True
        assert MatterAuthority.objects.filter(matter__slug=matter["slug"]).count() == 1

    def test_an_authority_that_is_not_in_the_graph_is_refused(
        self, client: APIClient
    ) -> None:
        """BL-20260906-16: node_id is a claim about the corpus, so check it."""
        from unittest.mock import patch

        matter = _make(client)
        with patch(
            "law_ai.matters.services.authorities.graph_labels_for", return_value=[]
        ):
            res = client.post(
                f"/api/matters/{matter['slug']}/authorities",
                {"node_id": "case-ghost"},
                format="json",
            )
        assert res.status_code == 422
        assert "case-ghost" in res.json()["detail"]
        assert not MatterAuthority.objects.filter(node_id="case-ghost").exists()

    def test_a_verified_node_records_its_graph_labels(self, client: APIClient) -> None:
        from unittest.mock import patch

        matter = _make(client)
        with patch(
            "law_ai.matters.services.authorities.graph_labels_for",
            return_value=["Case"],
        ):
            res = client.post(
                f"/api/matters/{matter['slug']}/authorities",
                {"node_id": "case-real"},
                format="json",
            )
        assert res.status_code == 201
        assert res.json()["graph_labels"] == ["Case"]

    def test_an_unreachable_graph_does_not_block_recording(
        self, client: APIClient
    ) -> None:
        """A Neo4j outage degrades the check; it never blocks a reviewer."""
        from unittest.mock import patch

        matter = _make(client)
        with patch(
            "law_ai.matters.services.authorities.graph_labels_for", return_value=None
        ):
            res = client.post(
                f"/api/matters/{matter['slug']}/authorities",
                {"node_id": "case-unchecked"},
                format="json",
            )
        assert res.status_code == 201
        assert res.json()["graph_labels"] is None
        assert MatterAuthority.objects.filter(node_id="case-unchecked").exists()

    def test_verification_records_the_account_that_did_it(
        self, client: APIClient, owner, in_graph
    ) -> None:
        matter = _make(client)
        client.post(
            f"/api/matters/{matter['slug']}/authorities",
            {"node_id": "case-9", "verified": True},
            format="json",
        )
        row = MatterAuthority.objects.get(node_id="case-9")
        assert row.verified_by_id == owner.pk
        assert row.verified_at is not None

    def test_artifacts_of_another_users_matter_are_unreachable(
        self, client: APIClient, intruder
    ) -> None:
        theirs = Matter.objects.create(owner=intruder, slug="theirs", name="Theirs")
        MatterArtifact.objects.create(matter=theirs, kind="note", title="private")
        assert client.get("/api/matters/theirs/artifacts").status_code == 404


# ---------------------------------------------------------------------------
# Graph validation of a recorded authority (BL-20260906-16)
# ---------------------------------------------------------------------------


class TestAuthorityGraphLookup:
    def test_labels_come_back_for_a_node_that_exists(self) -> None:
        from law_ai.core.neo4j import queries

        assert "n.archived_at IS NULL" in queries.AUTHORITY_NODE_EXISTS_CYPHER
        # MATCH-only: the check must never create the node it is looking for.
        assert "MERGE" not in queries.AUTHORITY_NODE_EXISTS_CYPHER
        assert "CREATE" not in queries.AUTHORITY_NODE_EXISTS_CYPHER

    def test_an_unreachable_driver_is_reported_as_unknown(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from law_ai.matters.services import authorities

        def boom() -> None:
            raise RuntimeError("neo4j down")

        monkeypatch.setattr("law_ai.core.neo4j.driver.get_neo4j_driver", boom)
        assert authorities.graph_labels_for("case-1") is None
