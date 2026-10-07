"""A scanned page filed on a matter — the matter door of the ocrmd plug-in (spec 055).

Ownership is the load-bearing property, as everywhere under ``/api/matters``: the door
is signed-in only, a stranger's matter is a 404, and a page already filed answers with
the artifact it made rather than a second copy.
"""

from __future__ import annotations

import copy
from typing import Any

import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from law_ai.matters.models import MatterArtifact

pytestmark = [pytest.mark.unit, pytest.mark.django_db]

ENVELOPE: dict[str, Any] = {
    "ocrmd": 1,
    "kind": "page",
    "text": "4. The tenant shall keep the premises in good repair, ordinary wear excepted.",
    "provenance": {
        "tool": "ocrmd",
        "document": "lease-file",
        "page": 3,
        "page_id": "abc123",
        "page_label": "3",
        "ocr_engine": "apple_vision@26.5",
        "llm_model": "claude-opus-5",
        "agreement": 0.97,
        "overlap": 0.99,
        "flagged_spans": 0,
        "unresolved": 0,
        "status": "verified",
    },
    "document": {"slug": "lease-file", "title": "Smith lease"},
    "options": {},
}


@pytest.fixture
def owner() -> Any:
    return get_user_model().objects.create_user(username="ada", password="pw-12345678")


@pytest.fixture
def intruder() -> Any:
    return get_user_model().objects.create_user(
        username="mallory", password="pw-12345678"
    )


@pytest.fixture
def client(owner: Any) -> APIClient:
    api = APIClient()
    api.force_authenticate(user=owner)
    return api


@pytest.fixture
def slug(client: APIClient) -> str:
    res = client.post(
        "/api/matters",
        {"name": "Smith lease dispute", "issue_tags": ["landlord-tenant"]},
        format="json",
    )
    assert res.status_code == 201, res.json()
    return str(res.json()["slug"])


def _url(slug: str) -> str:
    return f"/api/matters/{slug}/intake/ocrmd"


class TestDescriptor:
    def test_get_answers_with_the_sink_descriptor(
        self, client: APIClient, slug: str
    ) -> None:
        res = client.get(_url(slug))
        assert res.status_code == 200, res.content
        body = res.json()
        assert body["ocrmd_sink"] == 1 and "Smith lease dispute" in body["name"]
        assert [o["key"] for o in body["options"]] == ["title", "note"]

    def test_anonymous_and_strangers_learn_nothing(
        self, client: APIClient, slug: str, intruder: Any
    ) -> None:
        assert APIClient().get(_url(slug)).status_code == 401
        other = APIClient()
        other.force_authenticate(user=intruder)
        assert other.get(_url(slug)).status_code == 404
        assert other.post(_url(slug), ENVELOPE, format="json").status_code == 404


class TestFiling:
    def test_a_page_becomes_a_document_artifact(
        self, client: APIClient, slug: str
    ) -> None:
        res = client.post(_url(slug), ENVELOPE, format="json")
        assert res.status_code == 201, res.content
        body = res.json()
        assert body["summary"].startswith("filed as document #")
        assert body["items"][0]["status"] == "filed" and body["created"] is True
        assert body["warnings"] == []
        artifact = MatterArtifact.objects.get(pk=body["artifact"]["id"])
        assert artifact.kind == "document" and artifact.source == "ocrmd"
        assert artifact.confidence == 0.97
        assert artifact.title == "Smith lease, p. 3"
        assert artifact.body["provenance"]["page_id"] == "abc123"
        assert artifact.body["text"].startswith("4. The tenant")
        assert artifact.body["document"]["title"] == "Smith lease"
        detail = client.get(f"/api/matters/{slug}").json()
        assert [a["id"] for a in detail["artifacts"]] == [artifact.pk]

    def test_sending_twice_is_safe(self, client: APIClient, slug: str) -> None:
        first = client.post(_url(slug), ENVELOPE, format="json").json()
        res = client.post(_url(slug), ENVELOPE, format="json")
        assert res.status_code == 200, res.content
        body = res.json()
        assert body["summary"].startswith("already filed as document #")
        assert body["created"] is False
        assert body["artifact"]["id"] == first["artifact"]["id"]
        assert MatterArtifact.objects.filter(source="ocrmd").count() == 1

    def test_a_region_of_the_same_page_is_its_own_filing(
        self, client: APIClient, slug: str
    ) -> None:
        client.post(_url(slug), ENVELOPE, format="json")
        region = copy.deepcopy(ENVELOPE)
        region["kind"] = "region"
        region["text"] = "ordinary wear excepted"
        region["provenance"]["bbox"] = [0.1, 0.5, 0.8, 0.05]
        res = client.post(_url(slug), region, format="json")
        assert res.status_code == 201
        assert MatterArtifact.objects.filter(source="ocrmd").count() == 2

    def test_the_operators_title_wins(self, client: APIClient, slug: str) -> None:
        env = copy.deepcopy(ENVELOPE)
        env["options"] = {"title": "Clause 4 — repair", "note": "the repair covenant"}
        res = client.post(_url(slug), env, format="json")
        assert res.status_code == 201
        assert res.json()["artifact"]["title"] == "Clause 4 — repair"
        assert res.json()["artifact"]["body"]["note"] == "the repair covenant"

    def test_a_single_reading_is_named_as_such(
        self, client: APIClient, slug: str
    ) -> None:
        """A page the scanner did not cross-check says so to whoever files it."""
        env = copy.deepcopy(ENVELOPE)
        env["provenance"]["llm_model"] = ""
        env["provenance"]["status"] = "unverified"
        env["provenance"]["unresolved"] = 2
        res = client.post(_url(slug), env, format="json")
        assert res.status_code == 201
        warnings = res.json()["warnings"]
        assert any("one reading only" in w for w in warnings)
        assert any("2 unresolved" in w for w in warnings)

    def test_an_empty_page_is_422(self, client: APIClient, slug: str) -> None:
        env = copy.deepcopy(ENVELOPE)
        env["text"] = ""
        assert client.post(_url(slug), env, format="json").status_code == 422
