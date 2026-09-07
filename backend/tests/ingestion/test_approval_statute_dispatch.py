"""Statute/ordinance approval commit path (BL-20260811-03).

``commit_approved_review`` routed every ``kind`` through ``IngestionScout``,
a ``:Case`` extractor, so approving a ``kind="statute_section"`` row could
never reach the graph — and the row's stored payload did not even carry the
jurisdiction/code metadata needed to rebuild a ``StatuteExtraction``. Both
halves are fixed here; these tests pin them.
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from law_ai.core.schemas.statute_extraction import (
    StatuteExtraction,
    StatuteSectionPayload,
)
from law_ai.ingestionapp.models import PendingReview
from law_ai.ingestionapp.quarantine_kinds import KIND_STATUTE_SECTION
from law_ai.ingestionapp.services import approval as approval_mod
from law_ai.ingestionapp.services.approval import commit_approved_review
from law_ai.ingestionapp.services.statute_scout import (
    REQUIRED_COMMIT_METADATA,
    StatuteScout,
    _section_envelope,
)

SECTION = StatuteSectionPayload(
    id="us-co/crs/18-3-102",
    citation="C.R.S. § 18-3-102",
    heading="Murder in the first degree",
    text="Any person who, after deliberation, causes the death of another...",
    confidence=0.55,  # below the 0.7 gate — this is why it was quarantined
)

EXTRACTION = StatuteExtraction(
    jurisdiction_code="us-co",
    jurisdiction_name="Colorado",
    jurisdiction_level="state",
    code_id="us-co/crs",
    code_title="Colorado Revised Statutes",
    statute_id="us-co/crs/title-18",
    statute_title="Title 18 — Criminal Code",
    statute_citation="C.R.S. Title 18",
    sections=[SECTION],
    confidence=0.55,
    source="colorado_statutes",
    source_url="https://law.justia.com/codes/colorado/2024/title-18/",
)


def _statute_review(payload: dict[str, Any] | None = None) -> PendingReview:
    envelope = (
        payload if payload is not None else _section_envelope(EXTRACTION, SECTION)
    )
    return PendingReview.objects.create(
        id=SECTION.id,
        source="colorado_statutes",
        kind=KIND_STATUTE_SECTION,
        confidence=SECTION.confidence,
        reason="low_confidence",
        payload={
            "id": SECTION.id,
            "source": "colorado_statutes",
            "kind": KIND_STATUTE_SECTION,
            "confidence": SECTION.confidence,
            "reason": "low_confidence",
            "payload": envelope,
        },
        approved=True,
    )


# ---------------------------------------------------------------------------
# The quarantine row is self-describing
# ---------------------------------------------------------------------------


def test_quarantine_envelope_carries_the_admin_metadata() -> None:
    envelope = _section_envelope(EXTRACTION, SECTION)
    for key in REQUIRED_COMMIT_METADATA:
        assert envelope.get(key), f"{key} missing from the quarantine envelope"
    assert envelope["section"]["id"] == SECTION.id
    assert envelope["source_url"] == EXTRACTION.source_url


def test_celery_dispatch_stores_the_enriched_envelope(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import law_ai.ingestionapp.tasks as tasks_module

    sent: list[dict[str, Any]] = []

    def _capture(payload: dict[str, Any]) -> None:
        sent.append(payload)

    monkeypatch.setattr(tasks_module.quarantine_extraction, "delay", _capture)
    StatuteScout()._quarantine_via_celery(EXTRACTION, SECTION)

    assert sent[0]["kind"] == KIND_STATUTE_SECTION
    assert sent[0]["payload"]["jurisdiction_code"] == "us-co"
    assert json.loads(json.dumps(sent[0]))  # JSON-serialisable for the task


# ---------------------------------------------------------------------------
# StatuteScout.commit_section
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_commit_section_forces_the_confidence_gate_open() -> None:
    """The human approval IS the gate: a 0.55 section must still commit."""
    captured: dict[str, Any] = {}

    async def _fake_commit(session: Any, extraction: Any, *, threshold: float) -> int:
        captured["threshold"] = threshold
        captured["extraction"] = extraction
        return 2

    session = MagicMock()
    driver = MagicMock()
    driver.session.return_value.__aenter__ = AsyncMock(return_value=session)
    driver.session.return_value.__aexit__ = AsyncMock(return_value=False)

    with (
        patch(
            "law_ai.ingestionapp.services.statute_scout.get_neo4j_driver",
            return_value=driver,
        ),
        patch(
            "law_ai.ingestionapp.services.statute_scout.commit_statute_extraction",
            _fake_commit,
        ),
    ):
        result = await StatuteScout().commit_section(
            _section_envelope(EXTRACTION, SECTION)
        )

    assert captured["threshold"] == 0.0
    assert captured["extraction"].statute_id == "us-co/crs/title-18"
    assert [s.id for s in captured["extraction"].sections] == [SECTION.id]
    assert result["committed"] is True
    assert result["edges"] == 2


@pytest.mark.asyncio
async def test_commit_section_rejects_a_row_without_metadata() -> None:
    """Rows written before the enrichment fail loudly, not silently."""
    legacy = {
        "section": json.loads(SECTION.model_dump_json()),
        "statute_id": "us-co/crs/title-18",
        "source_url": EXTRACTION.source_url,
    }
    with pytest.raises(ValueError, match="re-ingest"):
        await StatuteScout().commit_section(legacy)


@pytest.mark.asyncio
async def test_commit_section_rejects_a_payload_without_a_section() -> None:
    with pytest.raises(ValueError, match="no 'section'"):
        await StatuteScout().commit_section({"statute_id": "x"})


# ---------------------------------------------------------------------------
# Approval-time dispatch by kind
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestApprovalDispatch:
    def test_statute_row_routes_to_the_statute_scout(self) -> None:
        review = _statute_review()
        commit = AsyncMock(
            return_value={"committed": True, "edges": 3, "section_id": SECTION.id}
        )
        with (
            patch.object(approval_mod.provenance, "log_event", lambda t, p: None),
            patch(
                "law_ai.ingestionapp.services.statute_scout.StatuteScout.commit_section",
                commit,
            ),
            patch(
                "law_ai.ingestionapp.services.scout.IngestionScout.run_and_commit",
                AsyncMock(side_effect=AssertionError("case path must not run")),
            ),
        ):
            from asgiref.sync import async_to_sync

            outcome = async_to_sync(commit_approved_review)(review)

        review.refresh_from_db()
        assert outcome["committed"] is True
        assert outcome["edges"] == 3
        assert review.committed_at is not None
        assert review.commit_error == ""
        assert commit.await_args.kwargs["force_commit"] is True

    def test_case_row_still_routes_to_the_ingestion_scout(self) -> None:
        review = PendingReview.objects.create(
            id="case-9",
            source="courtlistener",
            kind="case",
            confidence=0.4,
            reason="low_confidence",
            payload={"payload": {"id": "case-9", "case_name": "Doe v. Roe"}},
            approved=True,
        )
        run = AsyncMock(return_value={"committed": True, "edges": 1})
        with (
            patch.object(approval_mod.provenance, "log_event", lambda t, p: None),
            patch(
                "law_ai.ingestionapp.services.scout.IngestionScout.run_and_commit", run
            ),
        ):
            from asgiref.sync import async_to_sync

            outcome = async_to_sync(commit_approved_review)(review)

        assert outcome["committed"] is True
        assert run.await_args.kwargs["force_commit"] is True

    def test_unsupported_kind_records_an_audited_commit_error(self) -> None:
        # `ordinance_section` used to be the example here; it gained a commit
        # path in BL-20260509-05, so the still-unimplemented `regulation` kind
        # now carries the test. The invariant is unchanged: an approved row
        # whose kind has no writer fails loudly and audibly rather than
        # looking like a successful approval.
        review = PendingReview.objects.create(
            id="regulation-1",
            source="ecfr",
            kind="regulation",
            confidence=0.3,
            reason="low_confidence",
            payload={"payload": {"section": {}}},
            approved=True,
        )
        events: list[tuple[str, dict[str, Any]]] = []
        with patch.object(
            approval_mod.provenance, "log_event", lambda t, p: events.append((t, p))
        ):
            from asgiref.sync import async_to_sync

            outcome = async_to_sync(commit_approved_review)(review)

        review.refresh_from_db()
        assert outcome["committed"] is False
        assert "unsupported quarantine kind" in outcome["error"]
        assert "regulation" in review.commit_error
        assert review.committed_at is None
        assert [t for t, _ in events] == ["quarantine_commit_failed"]

    def test_legacy_statute_row_fails_with_a_reingest_hint(self) -> None:
        review = _statute_review(
            payload={
                "section": json.loads(SECTION.model_dump_json()),
                "statute_id": "us-co/crs/title-18",
                "source_url": EXTRACTION.source_url,
            }
        )
        with patch.object(approval_mod.provenance, "log_event", lambda t, p: None):
            from asgiref.sync import async_to_sync

            outcome = async_to_sync(commit_approved_review)(review)

        review.refresh_from_db()
        assert outcome["committed"] is False
        assert "re-ingest" in review.commit_error
        assert review.committed_at is None
