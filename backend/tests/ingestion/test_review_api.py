"""Quarantine review queue REST API (BL-20260811-01).

Spec 029's HITL loop had only operator surfaces (Django admin, `manage.py
review_queue`), so a domain reviewer without a shell could not work the queue.
These tests lock the web half: listing by state, the detail payload, and
approve/reject going through the *audited* approval service rather than
touching Neo4j.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import Client

from law_ai.ingestionapp.models import PendingReview
from law_ai.ingestionapp.services import approval as approval_mod

pytestmark = [pytest.mark.django_db, pytest.mark.unit]

_DOC = {
    "id": "case-1",
    "case_name": "Doe v. Roe",
    "plain_text": "The judgment below is affirmed. " * 30,
    "cluster": {"court": "Supreme Court of Colorado"},
}


@pytest.fixture(autouse=True)
def _isolate_audit(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "AUDIT_PATH", str(tmp_path / "audit.jsonl"))


def _make(review_id: str = "case-1", **overrides: Any) -> PendingReview:
    defaults: dict[str, Any] = {
        "id": review_id,
        "source": "courtlistener",
        "kind": "case",
        "confidence": 0.42,
        "reason": "low_confidence",
        "payload": {
            "id": review_id,
            "source": "courtlistener",
            "confidence": 0.42,
            "reason": "low_confidence",
            "payload": dict(_DOC, id=review_id),
        },
    }
    defaults.update(overrides)
    return PendingReview.objects.create(**defaults)


def _post(client: Client, url: str, body: dict[str, Any]) -> Any:
    return client.post(url, data=json.dumps(body), content_type="application/json")


# ---------------------------------------------------------------------------
# Listing
# ---------------------------------------------------------------------------
class TestList:
    def test_pending_is_the_default_and_omits_payloads(self, client: Client) -> None:
        _make("case-1")
        _make("case-2", approved=True, reviewed_at=datetime.now(UTC))
        res = client.get("/api/ingestion/reviews")
        assert res.status_code == 200
        body = res.json()
        assert body["status"] == "pending"
        assert [r["id"] for r in body["reviews"]] == ["case-1"]
        # NFR: a quarantined opinion carries the whole document body.
        assert "payload" not in body["reviews"][0]

    def test_row_carries_the_fields_a_reviewer_needs(self, client: Client) -> None:
        _make("case-1", reason="low_confidence", confidence=0.42)
        row = client.get("/api/ingestion/reviews").json()["reviews"][0]
        assert row["reason"] == "low_confidence"
        assert row["confidence"] == 0.42
        assert row["kind"] == "case"
        assert row["source"] == "courtlistener"
        assert row["approved"] is None
        assert row["commit_error"] == ""

    @pytest.mark.parametrize(
        ("state", "expected"),
        [
            ("pending", ["pending-1"]),
            ("approved", ["approved-1", "failed-1"]),
            ("rejected", ["rejected-1"]),
            ("committed", ["approved-1"]),
            ("failed", ["failed-1"]),
        ],
    )
    def test_status_filters(
        self, client: Client, state: str, expected: list[str]
    ) -> None:
        _make("pending-1")
        _make(
            "approved-1",
            approved=True,
            reviewed_at=datetime.now(UTC),
            committed_at=datetime.now(UTC),
        )
        _make("rejected-1", approved=False, reviewed_at=datetime.now(UTC))
        _make(
            "failed-1",
            approved=True,
            reviewed_at=datetime.now(UTC),
            commit_error="ApprovalError: unsupported quarantine kind",
        )
        body = client.get(f"/api/ingestion/reviews?status={state}").json()
        assert sorted(r["id"] for r in body["reviews"]) == sorted(expected)

    def test_counts_let_the_ui_render_tabs_without_five_requests(
        self, client: Client
    ) -> None:
        _make("pending-1")
        _make("rejected-1", approved=False, reviewed_at=datetime.now(UTC))
        counts = client.get("/api/ingestion/reviews").json()["counts"]
        assert counts["pending"] == 1
        assert counts["rejected"] == 1
        assert counts["failed"] == 0

    def test_unknown_status_is_a_422_naming_the_allowed_values(
        self, client: Client
    ) -> None:
        res = client.get("/api/ingestion/reviews?status=nope")
        assert res.status_code == 422
        assert "pending" in res.json()["allowed"]

    def test_kind_and_source_filters(self, client: Client) -> None:
        _make("case-1", kind="case", source="courtlistener")
        _make("sec-1", kind="statute_section", source="colorado_statutes")
        assert [
            r["id"]
            for r in client.get("/api/ingestion/reviews?kind=statute_section").json()[
                "reviews"
            ]
        ] == ["sec-1"]
        assert [
            r["id"]
            for r in client.get("/api/ingestion/reviews?source=courtlistener").json()[
                "reviews"
            ]
        ] == ["case-1"]


# ---------------------------------------------------------------------------
# Detail
# ---------------------------------------------------------------------------
class TestDetail:
    def test_detail_includes_the_payload(self, client: Client) -> None:
        _make("case-1")
        body = client.get("/api/ingestion/reviews/detail?id=case-1").json()
        assert body["id"] == "case-1"
        assert body["payload"]["payload"]["case_name"] == "Doe v. Roe"

    def test_detail_handles_a_url_shaped_id(self, client: Client) -> None:
        """`PendingReview.id` is routinely a source URL; hence a query param."""
        _make("https://www.courtlistener.com/opinion/1/doe-v-roe/")
        res = client.get(
            "/api/ingestion/reviews/detail",
            {"id": "https://www.courtlistener.com/opinion/1/doe-v-roe/"},
        )
        assert res.status_code == 200

    def test_missing_id_is_a_422_and_unknown_id_a_404(self, client: Client) -> None:
        assert client.get("/api/ingestion/reviews/detail").status_code == 422
        assert client.get("/api/ingestion/reviews/detail?id=nope").status_code == 404


# ---------------------------------------------------------------------------
# Decisions
# ---------------------------------------------------------------------------
class TestReject:
    def test_reject_records_the_decision_and_rationale(self, client: Client) -> None:
        _make("case-1")
        res = _post(
            client,
            "/api/ingestion/reviews/reject",
            {"id": "case-1", "reviewer": "alice", "note": "wrong jurisdiction"},
        )
        assert res.status_code == 200
        row = res.json()["review"]
        assert row["approved"] is False
        assert row["reviewer"] == "alice"
        assert row["review_note"] == "wrong jurisdiction"
        assert res.json()["committed"] is False

        review = PendingReview.objects.get(pk="case-1")
        assert review.approved is False
        assert review.reviewed_at is not None
        assert review.committed_at is None

    def test_reject_never_commits(self, client: Client) -> None:
        _make("case-1")
        with patch.object(approval_mod, "_commit_by_kind") as commit:
            _post(client, "/api/ingestion/reviews/reject", {"id": "case-1"})
        commit.assert_not_called()


class TestApprove:
    def test_approve_commits_through_the_audited_service(self, client: Client) -> None:
        _make("case-1")

        async def _fake_commit(kind: str, payload: dict[str, Any]) -> dict[str, Any]:
            return {"committed": True, "edges": 3}

        with patch.object(approval_mod, "_commit_by_kind", _fake_commit):
            res = _post(
                client,
                "/api/ingestion/reviews/approve",
                {"id": "case-1", "reviewer": "alice", "note": "verified"},
            )
        assert res.status_code == 200
        body = res.json()
        assert body["committed"] is True
        assert body["edges"] == 3
        assert body["commit_error"] == ""
        assert body["review"]["approved"] is True
        assert body["review"]["committed_at"] is not None

        review = PendingReview.objects.get(pk="case-1")
        assert review.committed_at is not None
        assert review.reviewer == "alice"
        assert review.review_note == "verified"

    def test_a_failed_commit_is_surfaced_not_hidden(self, client: Client) -> None:
        """A statute row hits this today; the UI must render the state."""
        _make("sec-1", kind="statute_section")

        async def _boom(kind: str, payload: dict[str, Any]) -> dict[str, Any]:
            raise approval_mod.ApprovalError(f"unsupported quarantine kind {kind!r}")

        with patch.object(approval_mod, "_commit_by_kind", _boom):
            res = _post(client, "/api/ingestion/reviews/approve", {"id": "sec-1"})
        assert res.status_code == 200
        body = res.json()
        assert body["committed"] is False
        assert "unsupported quarantine kind" in body["commit_error"]
        # The decision itself still stuck: a graph outage must not discard it.
        assert body["review"]["approved"] is True
        assert PendingReview.objects.get(pk="sec-1").approved is True

    def test_approve_is_idempotent_for_an_already_committed_row(
        self, client: Client
    ) -> None:
        _make("case-1", approved=True, committed_at=datetime.now(UTC))
        with patch.object(approval_mod, "_commit_by_kind") as commit:
            res = _post(client, "/api/ingestion/reviews/approve", {"id": "case-1"})
        assert res.status_code == 200
        commit.assert_not_called()

    def test_signed_in_account_wins_over_a_claimed_reviewer_string(
        self, client: Client
    ) -> None:
        user = get_user_model().objects.create_user(
            username="realuser", password="x" * 12
        )
        client.force_login(user)
        _make("case-1")

        async def _fake_commit(kind: str, payload: dict[str, Any]) -> dict[str, Any]:
            return {"committed": True, "edges": 0}

        with patch.object(approval_mod, "_commit_by_kind", _fake_commit):
            _post(
                client,
                "/api/ingestion/reviews/approve",
                {"id": "case-1", "reviewer": "impersonator"},
            )
        review = PendingReview.objects.get(pk="case-1")
        assert review.reviewer == "realuser"
        assert review.reviewer_user_id == user.pk

    def test_missing_id_is_a_422_and_unknown_id_a_404(self, client: Client) -> None:
        assert _post(client, "/api/ingestion/reviews/approve", {}).status_code == 422
        assert (
            _post(client, "/api/ingestion/reviews/approve", {"id": "nope"}).status_code
            == 404
        )


# ---------------------------------------------------------------------------
# Constitution §12 I1: this router never writes Neo4j itself.
# ---------------------------------------------------------------------------
def test_router_module_never_imports_the_neo4j_driver() -> None:
    from law_ai.ingestionapp import urls as ingestion_urls

    source = Path(ingestion_urls.__file__).read_text(encoding="utf-8")
    imports = [
        line
        for line in source.splitlines()
        if line.lstrip().startswith(("import ", "from "))
    ]
    assert not [line for line in imports if "neo4j" in line]
    assert "commit_approved_review" in source
