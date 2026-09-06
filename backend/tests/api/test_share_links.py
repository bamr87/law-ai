"""Save & share (BL-20260429-26 / spec 036 T-007).

The interesting cases are all about what a slug must *not* do: outlive its
revocation, resolve to an archived or unshareable run, or be mintable by
someone who is not signed in.
"""

from __future__ import annotations

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APIClient

from law_ai.analysis.models import AnalysisRun, ShareLink

pytestmark = [pytest.mark.unit, pytest.mark.django_db]


@pytest.fixture
def client() -> APIClient:
    return APIClient()


@pytest.fixture
def user():
    return get_user_model().objects.create_user(username="ada", password="pw-123456")


@pytest.fixture
def other_user():
    return get_user_model().objects.create_user(username="bob", password="pw-123456")


@pytest.fixture
def run(user) -> AnalysisRun:
    return AnalysisRun.objects.create(
        analysis_id="an-share01",
        request={"text": "Did the seller breach?"},
        response={"id": "an-share01", "irac": {"conclusion": "Breach."}},
        trace_id="trace-parent",
        child_trace_ids=["trace-a", "trace-b"],
        engine=AnalysisRun.ENGINE_DIRECT,
        confidence=0.9,
        created_by=user,
    )


# --------------------------------------------------------------------------
# Minting
# --------------------------------------------------------------------------
def test_signed_in_owner_mints_a_slug_and_url(client: APIClient, user, run) -> None:
    client.force_login(user)
    res = client.post(f"/api/analysis/{run.analysis_id}/share", {}, format="json")
    assert res.status_code == 201
    body = res.json()
    assert body["analysis_id"] == run.analysis_id
    assert body["url"] == f"/shared/{body['slug']}"
    assert len(body["slug"]) >= 40  # 32 random bytes, url-safe base64
    assert body["revoked"] is False


def test_anonymous_callers_cannot_mint(client: APIClient, run) -> None:
    res = client.post(f"/api/analysis/{run.analysis_id}/share", {}, format="json")
    assert res.status_code == 403
    assert "sign in" in res.json()["detail"]
    assert ShareLink.objects.count() == 0


def test_a_chosen_slug_is_accepted_and_becomes_the_url(
    client: APIClient, user, run
) -> None:
    client.force_login(user)
    res = client.post(
        f"/api/analysis/{run.analysis_id}/share",
        {"slug": "wet-floor-memo", "label": "For the partner"},
        format="json",
    )
    assert res.status_code == 201
    assert res.json()["slug"] == "wet-floor-memo"
    assert res.json()["url"] == "/shared/wet-floor-memo"
    assert res.json()["label"] == "For the partner"


@pytest.mark.parametrize("bad", ["ab", "Has Capitals", "../etc", "x" * 65, "-lead"])
def test_a_malformed_slug_is_refused(client: APIClient, user, run, bad: str) -> None:
    client.force_login(user)
    res = client.post(
        f"/api/analysis/{run.analysis_id}/share", {"slug": bad}, format="json"
    )
    assert res.status_code == 422


def test_a_taken_slug_is_a_conflict_even_after_revocation(
    client: APIClient, user, run
) -> None:
    client.force_login(user)
    first = client.post(
        f"/api/analysis/{run.analysis_id}/share", {"slug": "memo-one"}, format="json"
    )
    assert first.status_code == 201
    client.delete(f"/api/analysis/{run.analysis_id}/share/memo-one")

    again = client.post(
        f"/api/analysis/{run.analysis_id}/share", {"slug": "memo-one"}, format="json"
    )
    assert again.status_code == 409


def test_another_user_cannot_share_someone_elses_run(
    client: APIClient, other_user, run
) -> None:
    client.force_login(other_user)
    res = client.post(f"/api/analysis/{run.analysis_id}/share", {}, format="json")
    assert res.status_code == 403
    assert "not your analysis" in res.json()["detail"]


def test_an_unshareable_run_can_never_be_shared(client: APIClient, user, run) -> None:
    run.shareable = False
    run.save()
    client.force_login(user)
    res = client.post(f"/api/analysis/{run.analysis_id}/share", {}, format="json")
    assert res.status_code == 403
    assert "not shareable" in res.json()["detail"]


def test_minting_against_an_unknown_run_is_404(client: APIClient, user) -> None:
    client.force_login(user)
    res = client.post("/api/analysis/an-nope/share", {}, format="json")
    assert res.status_code == 404


def test_share_links_are_listable(client: APIClient, user, run) -> None:
    client.force_login(user)
    client.post(
        f"/api/analysis/{run.analysis_id}/share", {"slug": "memo-two"}, format="json"
    )
    res = client.get(f"/api/analysis/{run.analysis_id}/share")
    assert res.status_code == 200
    assert [link["slug"] for link in res.json()["links"]] == ["memo-two"]


# --------------------------------------------------------------------------
# Resolving
# --------------------------------------------------------------------------
def test_the_shared_url_reads_without_any_credential(
    client: APIClient, user, run
) -> None:
    client.force_login(user)
    slug = client.post(
        f"/api/analysis/{run.analysis_id}/share", {}, format="json"
    ).json()["slug"]

    anon = APIClient()
    res = anon.get(f"/api/shared/{slug}")
    assert res.status_code == 200
    body = res.json()
    assert body["shared"] is True
    assert body["slug"] == slug
    assert body["irac"]["conclusion"] == "Breach."
    assert "Not legal advice" in body["disclaimer"]


def test_the_shared_url_works_even_when_an_env_key_gates_the_api(
    client: APIClient, user, run, settings
) -> None:
    client.force_login(user)
    slug = client.post(
        f"/api/analysis/{run.analysis_id}/share", {}, format="json"
    ).json()["slug"]

    settings.ANALYSIS_API_KEY = "env-secret"
    settings.AGENT_API_KEY = "env-secret"
    assert APIClient().get(f"/api/shared/{slug}").status_code == 200


def test_a_revoked_slug_is_404(client: APIClient, user, run) -> None:
    client.force_login(user)
    slug = client.post(
        f"/api/analysis/{run.analysis_id}/share", {}, format="json"
    ).json()["slug"]

    revoked = client.delete(f"/api/analysis/{run.analysis_id}/share/{slug}")
    assert revoked.status_code == 200
    assert revoked.json()["revoked"] is True
    assert APIClient().get(f"/api/shared/{slug}").status_code == 404
    # Never hard-deleted (constitution §5).
    assert ShareLink.objects.filter(slug=slug).exists()


def test_archiving_the_run_kills_every_link(client: APIClient, user, run) -> None:
    client.force_login(user)
    slug = client.post(
        f"/api/analysis/{run.analysis_id}/share", {}, format="json"
    ).json()["slug"]

    run.archived_at = timezone.now()
    run.save()
    assert APIClient().get(f"/api/shared/{slug}").status_code == 404


def test_marking_a_run_unshareable_kills_existing_links(
    client: APIClient, user, run
) -> None:
    client.force_login(user)
    slug = client.post(
        f"/api/analysis/{run.analysis_id}/share", {}, format="json"
    ).json()["slug"]

    run.shareable = False
    run.save()
    assert APIClient().get(f"/api/shared/{slug}").status_code == 404


def test_an_unknown_slug_is_404(client: APIClient) -> None:
    assert APIClient().get("/api/shared/never-minted").status_code == 404


# --------------------------------------------------------------------------
# Revoking
# --------------------------------------------------------------------------
def test_anonymous_callers_cannot_revoke(client: APIClient, user, run) -> None:
    client.force_login(user)
    slug = client.post(
        f"/api/analysis/{run.analysis_id}/share", {}, format="json"
    ).json()["slug"]

    assert (
        APIClient().delete(f"/api/analysis/{run.analysis_id}/share/{slug}").status_code
        == 403
    )
    assert ShareLink.objects.get(slug=slug).revoked_at is None


def test_another_user_cannot_revoke_your_link(
    client: APIClient, user, other_user, run
) -> None:
    client.force_login(user)
    slug = client.post(
        f"/api/analysis/{run.analysis_id}/share", {}, format="json"
    ).json()["slug"]

    thief = APIClient()
    thief.force_login(other_user)
    res = thief.delete(f"/api/analysis/{run.analysis_id}/share/{slug}")
    assert res.status_code == 403


def test_revoking_twice_is_404(client: APIClient, user, run) -> None:
    client.force_login(user)
    slug = client.post(
        f"/api/analysis/{run.analysis_id}/share", {}, format="json"
    ).json()["slug"]

    assert (
        client.delete(f"/api/analysis/{run.analysis_id}/share/{slug}").status_code
        == 200
    )
    assert (
        client.delete(f"/api/analysis/{run.analysis_id}/share/{slug}").status_code
        == 404
    )


def test_mint_and_revoke_are_provenance_logged(
    client: APIClient, user, run, monkeypatch: pytest.MonkeyPatch
) -> None:
    from law_ai.analysis import urls as analysis_api

    seen: list[tuple[str, dict]] = []
    monkeypatch.setattr(
        analysis_api.provenance,
        "log_event",
        lambda kind, payload: seen.append((kind, payload)),
    )
    client.force_login(user)
    slug = client.post(
        f"/api/analysis/{run.analysis_id}/share", {}, format="json"
    ).json()["slug"]
    client.delete(f"/api/analysis/{run.analysis_id}/share/{slug}")

    kinds = [kind for kind, _ in seen]
    assert "share_link.minted" in kinds
    assert "share_link.revoked" in kinds
    assert all(payload["analysis_id"] == run.analysis_id for _, payload in seen)


def test_listing_share_links_needs_a_session(client: APIClient, user, run) -> None:
    """A live slug is a credential — a scope key alone must not enumerate them."""
    client.force_login(user)
    client.post(
        f"/api/analysis/{run.analysis_id}/share", {"slug": "memo-three"}, format="json"
    )

    res = APIClient().get(f"/api/analysis/{run.analysis_id}/share")
    assert res.status_code == 403
    assert "sign in" in res.json()["detail"]
