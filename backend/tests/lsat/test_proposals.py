"""Tests for the LSAT proposals service + API (spec 019 T-002, T-003)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from django.conf import settings


@pytest.fixture(autouse=True)
def _isolate_state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Point both audit + proposal stores at the test tmp dir."""
    monkeypatch.setattr(settings, "AUDIT_PATH", str(tmp_path / "audit.jsonl"))
    monkeypatch.setattr(
        settings, "LSAT_PROPOSALS_DIR", str(tmp_path / "lsat_proposals"), raising=False
    )
    # BL-20260527-06: approval blind-solves the new item; keep the verdict
    # cache out of the checked-in var/ directory too.
    monkeypatch.setattr(
        settings,
        "LSAT_RESPONSE_CACHE_DIR",
        str(tmp_path / "response_cache"),
        raising=False,
    )

    # Each test gets its own copy of the bank so promote_to_bank does not
    # mutate the checked-in fixture data.
    from law_ai.lsat.services import bank as bank_mod

    real_data_dir = bank_mod.DATA_DIR
    sandbox = tmp_path / "lsat_data"
    sandbox.mkdir()
    for name in (
        "lr_bank.json",
        "rc_bank.json",
        "lg_bank.json",
        "concepts.json",
        "passages.json",
        "sections.json",
        "guides.json",
    ):
        src = real_data_dir / name
        if src.is_file():
            (sandbox / name).write_text(
                src.read_text(encoding="utf-8"), encoding="utf-8"
            )
    monkeypatch.setattr(bank_mod, "DATA_DIR", sandbox)

    from law_ai.lsat.services import guides as guides_mod

    def _clear() -> None:
        bank_mod.load_bank.cache_clear()
        bank_mod.load_concepts.cache_clear()
        bank_mod.load_passages.cache_clear()
        bank_mod.load_sections.cache_clear()
        guides_mod.reset_guide_cache()

    _clear()
    yield
    _clear()


def _draft(section: str = "LR") -> dict[str, Any]:
    return {
        "section": section,
        "difficulty": "med",
        "stem": "Sample stem.",
        "choices": [
            {"label": "A", "text": "alpha"},
            {"label": "B", "text": "bravo"},
            {"label": "C", "text": "charlie"},
            {"label": "D", "text": "delta"},
            {"label": "E", "text": "echo"},
        ],
        "correct": "A",
        "explanation": "Because.",
        "concepts": ["parallel-reasoning"],
        "confidence": 0.8,
    }


class TestStoreRoundTrip:
    def test_record_and_list_pending(self) -> None:
        from law_ai.lsat.services import proposals

        pid = proposals.record_proposal(
            _draft(), agent_trace_id="t1", model="m", confidence=0.8
        )
        rows = proposals.list_proposals("pending")
        assert len(rows) == 1
        assert rows[0]["id"] == pid
        assert rows[0]["status"] == "pending"

    def test_reject_sets_status(self) -> None:
        from law_ai.lsat.services import proposals

        pid = proposals.record_proposal(
            _draft(), agent_trace_id="t1", model="m", confidence=0.8
        )
        proposals.set_status(pid, "rejected", reviewer="alice", note="off-topic")
        assert proposals.list_proposals("pending") == []
        rejected = proposals.list_proposals("rejected")
        assert len(rejected) == 1
        assert rejected[0]["status"] == "rejected"
        assert rejected[0]["reviewer"] == "alice"

    def test_promote_to_bank_appends_and_invalidates_cache(self) -> None:
        from law_ai.lsat.services import bank as bank_mod
        from law_ai.lsat.services import proposals

        pid = proposals.record_proposal(
            _draft("LR"), agent_trace_id="t1", model="m", confidence=0.9
        )
        before = len(bank_mod.load_bank())
        row = proposals.promote_to_bank(pid, reviewer="alice")
        after = bank_mod.load_bank()
        assert len(after) == before + 1
        assert row["status"] == "approved"
        assert row["question_id"] in after

    def test_promotion_keeps_the_bank_file_in_its_on_disk_format(self) -> None:
        """BL-20260905-48: append an item, do not reformat the whole file.

        The checked-in banks are 2-space JSON. A promotion that rewrote them
        at indent=4 would make the first production approval a whole-file
        diff, hiding the one line a reviewer needs to read.
        """
        from law_ai.lsat.services import bank as bank_mod
        from law_ai.lsat.services import proposals

        bank_path = bank_mod.DATA_DIR / "lr_bank.json"
        before = bank_path.read_text(encoding="utf-8")

        pid = proposals.record_proposal(
            _draft("LR"), agent_trace_id="t1", model="m", confidence=0.9
        )
        proposals.promote_to_bank(pid, reviewer="alice")

        after = bank_path.read_text(encoding="utf-8")
        # Same serialization convention as the file that was read in.
        assert (
            after == json.dumps(json.loads(after), indent=2, ensure_ascii=False) + "\n"
        )
        # And the existing items are untouched: every line of the old file up
        # to its final closing bracket survives verbatim.
        kept = before.rstrip().rsplit("\n", 2)[0]
        assert after.startswith(kept)

    def test_promotion_stamps_the_generating_archetype(self) -> None:
        """BL-20260905-54: the job knew the archetype; the item now says so."""
        from law_ai.lsat.services import bank as bank_mod
        from law_ai.lsat.services import proposals

        pid = proposals.record_proposal(
            _draft("LR"),
            agent_trace_id="t1",
            model="m",
            confidence=0.9,
            meta={"factory": {"archetype_id": "lr-weaken", "tier": "bulk"}},
        )
        row = proposals.promote_to_bank(pid, reviewer="alice")
        item = bank_mod.load_bank()[row["question_id"]]
        assert item.archetype == "lr-weaken"

    def test_a_hand_drafted_promotion_carries_no_archetype(self) -> None:
        from law_ai.lsat.services import bank as bank_mod
        from law_ai.lsat.services import proposals

        pid = proposals.record_proposal(
            _draft("LR"), agent_trace_id="t1", model="m", confidence=0.9
        )
        row = proposals.promote_to_bank(pid, reviewer="alice")
        # None, not a guess: the census falls back to the concept proxy.
        assert bank_mod.load_bank()[row["question_id"]].archetype is None

    def test_double_promote_raises(self) -> None:
        from law_ai.lsat.services import proposals

        pid = proposals.record_proposal(
            _draft(), agent_trace_id="t1", model="m", confidence=0.9
        )
        proposals.promote_to_bank(pid, reviewer="a")
        with pytest.raises(ValueError):
            proposals.promote_to_bank(pid, reviewer="a")


class TestLongLog:
    """BL-20260905-57 — a queue that outgrows the replay window.

    The reader used to replay only the last 5000 events, so once the log
    passed that, a proposal's ``create`` event dropped out and the row simply
    vanished from the queue — with no error and nothing in the UI to say so.
    """

    def test_a_proposal_survives_a_log_longer_than_the_old_window(self) -> None:
        import json as _json

        from law_ai.lsat.services import proposals

        pid = proposals.record_proposal(
            _draft(), agent_trace_id="t1", model="m", confidence=0.8
        )
        # Bury the create event under more events than the old tail kept.
        path = proposals._proposals_path()
        with path.open("a", encoding="utf-8") as fh:
            for i in range(5200):
                fh.write(
                    _json.dumps(
                        {
                            "type": "lsat_proposal.judge",
                            "id": f"prop-noise-{i}",
                            "timestamp": "2026-09-05T00:00:00+00:00",
                            "judge": {"verdict": "pass"},
                        }
                    )
                    + "\n"
                )

        rows = proposals.list_proposals("pending")
        assert [r["id"] for r in rows] == [pid]
        assert proposals.get_proposal(pid) is not None
        # …and it is still promotable: the draft came back whole, not a stub.
        assert proposals.get_proposal(pid)["draft"]["stem"] == "Sample stem."


class TestGapAnalysis:
    def test_empty_audit_yields_no_gaps(self) -> None:
        from law_ai.lsat.services import proposals

        assert proposals.gap_analysis() == []

    def test_ranks_lowest_accuracy_first(self) -> None:
        from law_ai.core import audit_jsonl as audit_store
        from law_ai.lsat.services import proposals

        # weak concept: 3 attempts, 0 correct (accuracy 0.0)
        for _ in range(3):
            audit_store.record(
                {
                    "type": "lsat_grade",
                    "section": "LR",
                    "concepts": ["weak"],
                    "correct": False,
                }
            )
        # strong concept: 3 attempts, 3 correct (accuracy 1.0)
        for _ in range(3):
            audit_store.record(
                {
                    "type": "lsat_grade",
                    "section": "LR",
                    "concepts": ["strong"],
                    "correct": True,
                }
            )
        gaps = proposals.gap_analysis()
        assert len(gaps) == 2
        assert gaps[0]["concept"] == "weak"
        assert gaps[0]["accuracy"] == 0.0
        assert gaps[1]["concept"] == "strong"


# ---------------------------------------------------------------------------
# API tests
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def client():
    from law_ai.asgi import application as app

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac


@pytest.mark.asyncio
async def test_generate_persists_and_lists(client: AsyncClient) -> None:
    from law_ai.agents_runtime.crews import lsat_content_author as mod

    payload = json.dumps(
        {
            "drafts": [
                {
                    "section": "LR",
                    "difficulty": "med",
                    "stem": "Sample stem from LLM.",
                    "choices": [
                        {"label": label, "text": label}
                        for label in ["A", "B", "C", "D", "E"]
                    ],
                    "correct": "B",
                    "explanation": "Because B.",
                    "concepts": ["parallel-reasoning"],
                    "confidence": 0.75,
                }
            ]
        }
    )
    from law_ai.core.llm.base import LLMResult

    result = LLMResult(
        text=payload, provider="claude_code", model="claude-opus-5-5", latency_ms=1.0
    )
    with patch.object(mod.llm, "agenerate", new=AsyncMock(return_value=result)):
        res = await client.post(
            "/api/lsat/proposals/generate",
            json={"section": "LR", "difficulty": "med", "count": 1},
        )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["count"] == 1
    pid = body["proposals"][0]["id"]

    listed = await client.get("/api/lsat/proposals", params={"status": "pending"})
    assert listed.status_code == 200
    assert listed.json()["proposals"][0]["id"] == pid


@pytest.mark.asyncio
async def test_approve_then_question_visible(client: AsyncClient) -> None:
    from law_ai.lsat.services import proposals

    pid = proposals.record_proposal(
        _draft("LR"), agent_trace_id="t1", model="m", confidence=0.9
    )
    res = await client.post(f"/api/lsat/proposals/{pid}/approve", json={})
    assert res.status_code == 200, res.text
    qid = res.json()["question_id"]

    fetched = await client.get(f"/api/lsat/questions/{qid}")
    assert fetched.status_code == 200
    assert fetched.json()["id"] == qid


@pytest.mark.asyncio
async def test_reject_marks_status(client: AsyncClient) -> None:
    from law_ai.lsat.services import proposals

    pid = proposals.record_proposal(
        _draft("LR"), agent_trace_id="t1", model="m", confidence=0.5
    )
    res = await client.post(f"/api/lsat/proposals/{pid}/reject", json={"note": "nope"})
    assert res.status_code == 200
    assert res.json()["status"] == "rejected"


@pytest.mark.asyncio
async def test_gaps_endpoint_returns_empty_initially(client: AsyncClient) -> None:
    res = await client.get("/api/lsat/gaps")
    assert res.status_code == 200
    body = res.json()
    assert body["gaps"] == []
    assert "limit" in body


# ---------------------------------------------------------------------------
# Spec 041 — guide drafts in the proposal queue (T-004, AC-6)
# ---------------------------------------------------------------------------


def _guide_draft(question_id: str) -> dict[str, Any]:
    from law_ai.lsat.services.bank import load_bank

    bank = load_bank()
    correct = bank[question_id].correct if question_id in bank else "B"
    return {
        "question_id": question_id,
        "method": "test walkthrough",
        "steps": [
            {"kind": "orient", "title": "Read", "text": "Read the stem."},
            {"kind": "symbolize", "title": "Notate", "text": "Symbolize the rule."},
            {"kind": "infer", "title": "Chain", "text": "Chain the inference."},
            {
                "kind": "answer",
                "title": "Answer",
                "text": f"Pick {correct}.",
                "spoiler": True,
            },
        ],
    }


class TestGuideProposals:
    def _guideless_qid(self) -> str:
        from law_ai.lsat.services.bank import load_bank
        from law_ai.lsat.services.guides import load_guides

        guides = load_guides()
        return next(q for q in load_bank() if q not in guides)

    def test_record_and_replay_carries_kind(self) -> None:
        from law_ai.lsat.services import proposals

        pid = proposals.record_proposal(
            _guide_draft(self._guideless_qid()),
            agent_trace_id="t-g",
            model="m",
            confidence=0.7,
            proposal_kind="guide",
        )
        row = proposals.get_proposal(pid)
        assert row is not None and row["proposal_kind"] == "guide"

        # Legacy question drafts backfill as kind "question".
        qpid = proposals.record_proposal(
            _draft("LR"), agent_trace_id="t-q", model="m", confidence=0.7
        )
        qrow = proposals.get_proposal(qpid)
        assert qrow is not None and qrow["proposal_kind"] == "question"

    def test_question_promotion_rejects_guide_drafts(self) -> None:
        from law_ai.lsat.services import proposals

        pid = proposals.record_proposal(
            _guide_draft(self._guideless_qid()),
            agent_trace_id="t-g",
            model="m",
            confidence=0.7,
            proposal_kind="guide",
        )
        with pytest.raises(ValueError, match="promote_guide_to_bank"):
            proposals.promote_to_bank(pid)

    def test_guide_promotion_rejects_question_drafts(self) -> None:
        from law_ai.lsat.services import proposals

        pid = proposals.record_proposal(
            _draft("LR"), agent_trace_id="t-q", model="m", confidence=0.7
        )
        with pytest.raises(ValueError, match="promote_to_bank"):
            proposals.promote_guide_to_bank(pid)

    def test_promote_guide_serves_via_loader(self) -> None:
        from law_ai.lsat.services import proposals
        from law_ai.lsat.services.guides import load_guides

        qid = self._guideless_qid()
        pid = proposals.record_proposal(
            _guide_draft(qid),
            agent_trace_id="t-g",
            model="m",
            confidence=0.7,
            proposal_kind="guide",
        )
        row = proposals.promote_guide_to_bank(pid, reviewer="rev", note="ok")
        assert row["status"] == "approved"
        assert row["question_id"] == qid

        guides = load_guides()
        assert qid in guides
        assert guides[qid].source.startswith("LSATSolveGuideAuthor (approved")

    def test_promote_guide_rejects_duplicate_question(self) -> None:
        from law_ai.lsat.services import proposals
        from law_ai.lsat.services.guides import load_guides

        existing_qid = next(iter(load_guides()))
        pid = proposals.record_proposal(
            _guide_draft(existing_qid),
            agent_trace_id="t-g",
            model="m",
            confidence=0.7,
            proposal_kind="guide",
        )
        with pytest.raises(ValueError, match="already has a solve guide"):
            proposals.promote_guide_to_bank(pid)

    def test_promote_guide_rejects_invalid_draft(self) -> None:
        from law_ai.lsat.services import proposals

        bad = _guide_draft(self._guideless_qid())
        bad["steps"] = []
        pid = proposals.record_proposal(
            bad,
            agent_trace_id="t-g",
            model="m",
            confidence=0.7,
            proposal_kind="guide",
        )
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            proposals.promote_guide_to_bank(pid)


# ---------------------------------------------------------------------------
# Library promotion (spec 048 T-042: FR-16, AC-10)
# ---------------------------------------------------------------------------

_SANDBOX_ARTICLE = """---
id: sandbox-note
title: Sandbox Note
kind: technique
level: core
sections: [LR]
summary: A promoted sandbox article.
concepts: []
prerequisites: []
related: []
tags: []
status: draft
last_reviewed: 2026-09-03
revision: 1
references: []
---

## One

Body text.

## Two

More body.

> [!example] Worked example
> An instance.

## Key takeaways

- a takeaway
"""


class TestPromoteLibraryArticle:
    """`promote_library_article` is the only path that writes to the library.

    Rides on the module's autouse sandbox, which already redirects
    ``bank.DATA_DIR`` at a tmp copy — this only adds the ``library/``
    subdirectory and drops the library caches around each test.
    """

    @pytest.fixture(autouse=True)
    def _library_dir(self, monkeypatch: pytest.MonkeyPatch) -> Any:
        from law_ai.lsat.services import bank as bank_mod
        from law_ai.lsat.services import library as lib

        directory = bank_mod.DATA_DIR / "library"
        directory.mkdir(parents=True, exist_ok=True)
        lib.reset_library_caches()
        yield directory
        lib.reset_library_caches()

    def _proposal(self, markdown: str, article_id: str = "sandbox-note") -> str:
        from law_ai.lsat.services import proposals

        return proposals.record_proposal(
            {"article_id": article_id, "markdown": markdown},
            agent_trace_id="trace-1",
            model="test/model",
            confidence=0.6,
            proposal_kind="library_article",
        )

    def test_promotion_writes_the_article_and_it_loads(
        self, _library_dir: Path
    ) -> None:
        from law_ai.lsat.services import proposals
        from law_ai.lsat.services.library import load_library

        pid = self._proposal(_SANDBOX_ARTICLE)
        row = proposals.promote_library_article(pid, reviewer="tester")
        assert row["status"] == "approved"
        assert (_library_dir / "sandbox-note.md").is_file()
        assert "sandbox-note" in load_library()

    def test_an_invalid_draft_is_rejected_before_it_reaches_disk(
        self, _library_dir: Path
    ) -> None:
        from law_ai.lsat.services import proposals

        pid = self._proposal(
            _SANDBOX_ARTICLE.replace("## Key takeaways", "## Wrapping up")
        )
        with pytest.raises(ValueError, match="failed library validation"):
            proposals.promote_library_article(pid)
        assert list(_library_dir.glob("*.md")) == []

    def test_a_draft_that_breaks_the_library_is_rolled_back(
        self, _library_dir: Path
    ) -> None:
        """Per-file parsing cannot see a dangling cross-reference; the reload can."""
        from law_ai.lsat.services import proposals

        pid = self._proposal(
            _SANDBOX_ARTICLE.replace("Body text.", "See [[article:nowhere]].")
        )
        with pytest.raises(ValueError, match="rolled back"):
            proposals.promote_library_article(pid)
        assert list(_library_dir.glob("*.md")) == []

    def test_a_question_draft_cannot_be_promoted_here(self, _library_dir: Path) -> None:
        from law_ai.lsat.services import proposals

        pid = proposals.record_proposal(
            {"section": "LR"},
            agent_trace_id="t",
            model="m",
            confidence=0.5,
            proposal_kind="question",
        )
        with pytest.raises(ValueError, match="only 'library_article' drafts"):
            proposals.promote_library_article(pid)

    def test_a_review_finding_is_never_promoted(self, _library_dir: Path) -> None:
        """`library_finding` rows are read and closed by a human, not written."""
        from law_ai.lsat.services import proposals

        pid = proposals.record_proposal(
            {"article_id": "sandbox-note", "findings": []},
            agent_trace_id="t",
            model="m",
            confidence=0.5,
            proposal_kind="library_finding",
        )
        with pytest.raises(ValueError, match="only 'library_article' drafts"):
            proposals.promote_library_article(pid)

    def test_unknown_proposal_raises(self, _library_dir: Path) -> None:
        from law_ai.lsat.services import proposals

        with pytest.raises(KeyError):
            proposals.promote_library_article("prop-doesnotexist")


# ---------------------------------------------------------------------------
# BL-20260810-08 — every HITL decision is attributed + audited
# ---------------------------------------------------------------------------


class TestDecisionAudit:
    """Approve *and* reject land in ``AuditEvent`` with reviewer + rationale."""

    def _rows(self) -> list[Any]:
        from law_ai.audit.models import AuditEvent
        from law_ai.lsat.services.proposals import DECISION_EVENT

        return list(AuditEvent.objects.filter(kind=DECISION_EVENT).order_by("pk"))

    def test_approve_writes_attributed_audit_event(self) -> None:
        from law_ai.lsat.services import proposals

        pid = proposals.record_proposal(
            _draft("LR"), agent_trace_id="trace-approve", model="m", confidence=0.9
        )
        assert self._rows() == []
        row = proposals.promote_to_bank(pid, reviewer="alice", note="looks right")
        events = self._rows()
        assert len(events) == 1
        payload = events[0].payload
        assert payload["proposal_id"] == pid
        assert payload["status"] == "approved"
        assert payload["reviewer"] == "alice"
        assert payload["note"] == "looks right"
        assert payload["question_id"] == row["question_id"]
        assert payload["section"] == "LR"
        assert payload["proposal_kind"] == "question"
        assert events[0].trace_id == "trace-approve"

    def test_reject_writes_attributed_audit_event(self) -> None:
        from law_ai.lsat.services import proposals

        pid = proposals.record_proposal(
            _draft("LR"), agent_trace_id="trace-reject", model="m", confidence=0.4
        )
        proposals.set_status(pid, "rejected", reviewer="bob", note="off-topic")
        events = self._rows()
        assert len(events) == 1
        payload = events[0].payload
        assert payload["proposal_id"] == pid
        assert payload["status"] == "rejected"
        assert payload["reviewer"] == "bob"
        assert payload["note"] == "off-topic"
        assert events[0].trace_id == "trace-reject"

    def test_anonymous_reviewer_is_logged_as_unattributed(self) -> None:
        from law_ai.lsat.services import proposals

        pid = proposals.record_proposal(
            _draft("LR"), agent_trace_id="t", model="m", confidence=0.4
        )
        proposals.set_status(pid, "rejected")
        (event,) = self._rows()
        assert event.payload["reviewer"] == "(unattributed)"
        assert event.payload["note"] == ""

    def test_decision_also_tees_to_jsonl_audit_store(self) -> None:
        from law_ai.core import audit_jsonl as audit_store
        from law_ai.lsat.services import proposals
        from law_ai.lsat.services.proposals import DECISION_EVENT

        pid = proposals.record_proposal(
            _draft("LR"), agent_trace_id="t", model="m", confidence=0.4
        )
        proposals.set_status(pid, "rejected", reviewer="carol", note="dup")
        kinds = [ev.get("type") for ev in audit_store.tail(20)]
        assert DECISION_EVENT in kinds


@pytest.mark.asyncio
async def test_reject_endpoint_records_reviewer_and_note(client: AsyncClient) -> None:
    from asgiref.sync import sync_to_async

    from law_ai.lsat.services import proposals

    pid = proposals.record_proposal(
        _draft("LR"), agent_trace_id="t-api", model="m", confidence=0.5
    )
    res = await client.post(
        f"/api/lsat/proposals/{pid}/reject",
        json={"reviewer": "dana", "note": "distractor B is also correct"},
    )
    assert res.status_code == 200, res.text
    assert res.json()["reviewer"] == "dana"

    def _fetch() -> list[dict[str, Any]]:
        from law_ai.audit.models import AuditEvent
        from law_ai.lsat.services.proposals import DECISION_EVENT

        return [
            e.payload
            for e in AuditEvent.objects.filter(kind=DECISION_EVENT, trace_id="t-api")
        ]

    payloads = await sync_to_async(_fetch)()
    assert len(payloads) == 1
    assert payloads[0]["status"] == "rejected"
    assert payloads[0]["reviewer"] == "dana"
    assert payloads[0]["note"] == "distractor B is also correct"


# ---------------------------------------------------------------------------
# BL-20260527-06 — approval pins a tutor-grade cross-check verdict
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_approve_endpoint_returns_cross_check_verdict(
    client: AsyncClient,
) -> None:
    from law_ai.core.llm.base import LLMResult
    from law_ai.lsat.services import crosscheck as cc_mod
    from law_ai.lsat.services import proposals

    pid = proposals.record_proposal(
        _draft("LR"), agent_trace_id="t1", model="m", confidence=0.9
    )
    verdict = LLMResult(
        text=json.dumps({"choice": "A", "rationale": "Because A."}),
        provider="claude_code",
        model="claude-opus-5-5",
        latency_ms=1.0,
    )
    with patch.object(cc_mod.llm, "agenerate", new=AsyncMock(return_value=verdict)):
        res = await client.post(f"/api/lsat/proposals/{pid}/approve", json={})
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["status"] == "approved"
    assert body["cross_check"]["question_id"] == body["question_id"]
    assert body["cross_check"]["agree"] is True
    assert body["cross_check"]["used_llm"] is True

    listed = await client.get("/api/lsat/proposals", params={"status": "approved"})
    row = next(r for r in listed.json()["proposals"] if r["id"] == pid)
    assert row["cross_check"]["agree"] is True


@pytest.mark.asyncio
async def test_approve_endpoint_cross_check_can_be_disabled(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from law_ai.lsat.services import crosscheck as cc_mod
    from law_ai.lsat.services import proposals

    monkeypatch.setattr(settings, "LSAT_CROSS_CHECK_ON_APPROVE", False, raising=False)
    pid = proposals.record_proposal(
        _draft("LR"), agent_trace_id="t1", model="m", confidence=0.9
    )
    mock = AsyncMock()
    with patch.object(cc_mod.llm, "agenerate", new=mock):
        res = await client.post(f"/api/lsat/proposals/{pid}/approve", json={})
    assert res.status_code == 200, res.text
    assert "cross_check" not in res.json()
    assert mock.await_count == 0


@pytest.mark.asyncio
async def test_generate_flags_answer_key_skew_onto_the_queue(
    client: AsyncClient,
) -> None:
    """BL-20260606-02: a skewed batch reaches HITL carrying the flag."""
    from law_ai.agents_runtime.crews import lsat_content_author as mod
    from law_ai.core.llm.base import LLMResult

    payload = json.dumps(
        {
            "drafts": [
                {
                    "section": "LR",
                    "difficulty": "med",
                    "stem": f"Skewed stem #{i}.",
                    "choices": [
                        {"label": label, "text": label}
                        for label in ["A", "B", "C", "D", "E"]
                    ],
                    "correct": "E",
                    "explanation": "Because E.",
                    "concepts": ["parallel-reasoning"],
                    "confidence": 0.75,
                }
                for i in range(3)
            ]
        }
    )
    result = LLMResult(
        text=payload, provider="claude_code", model="claude-opus-5-5", latency_ms=1.0
    )
    with patch.object(mod.llm, "agenerate", new=AsyncMock(return_value=result)):
        res = await client.post(
            "/api/lsat/proposals/generate",
            json={"section": "LR", "difficulty": "med", "count": 3},
        )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["count"] == 3, "flagged, not rejected"
    assert body["balance_flag"] and "'E'" in body["balance_flag"]
    for row in body["proposals"]:
        assert row["meta"]["balance_flag"] == body["balance_flag"]


@pytest.mark.asyncio
async def test_generate_leaves_no_flag_on_a_spread_batch(client: AsyncClient) -> None:
    from law_ai.agents_runtime.crews import lsat_content_author as mod
    from law_ai.core.llm.base import LLMResult

    payload = json.dumps(
        {
            "drafts": [
                {
                    "section": "LR",
                    "difficulty": "med",
                    "stem": f"Spread stem #{i}.",
                    "choices": [
                        {"label": label, "text": label}
                        for label in ["A", "B", "C", "D", "E"]
                    ],
                    "correct": key,
                    "explanation": f"Because {key}.",
                    "concepts": ["parallel-reasoning"],
                    "confidence": 0.75,
                }
                for i, key in enumerate(["A", "C", "E"])
            ]
        }
    )
    result = LLMResult(
        text=payload, provider="claude_code", model="claude-opus-5-5", latency_ms=1.0
    )
    with patch.object(mod.llm, "agenerate", new=AsyncMock(return_value=result)):
        res = await client.post(
            "/api/lsat/proposals/generate",
            json={"section": "LR", "difficulty": "med", "count": 3},
        )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["balance_flag"] is None
    for row in body["proposals"]:
        assert "balance_flag" not in (row.get("meta") or {})


@pytest_asyncio.fixture
async def parked_passage(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Any:
    """A passage_set job's parked context plus one draft written against it."""
    from law_ai.lsat.services import proposals

    monkeypatch.setattr(
        settings, "LSAT_FACTORY_DIR", str(tmp_path / "factory"), raising=False
    )
    park_dir = proposals.pending_passages_dir()
    path = park_dir / "mfst-api-job01.passage.json"
    path.write_text(
        json.dumps(
            {
                "section": "RC",
                "title": "Coastal erosion",
                "passage": "A study of coastal erosion across three decades.",
            }
        ),
        encoding="utf-8",
    )
    draft = _draft("RC")
    pid = proposals.record_proposal(
        draft,
        agent_trace_id="t-passage",
        model="m",
        confidence=0.8,
        meta={"factory": {"mode": "passage_set", "pending_passage_path": str(path)}},
    )
    return {"path": str(path), "proposal_id": pid}


@pytest.mark.asyncio
async def test_passage_approve_endpoint_promotes_and_links(
    client: AsyncClient, parked_passage: dict[str, str]
) -> None:
    """BL-20260702-07: the parked context becomes a passage the drafts link to."""
    from law_ai.lsat.services.bank import load_passages

    res = await client.post(
        "/api/lsat/proposals/passages/approve",
        json={
            "pending_passage_path": parked_passage["path"],
            "reviewer": "alice",
            "note": "checked the text",
        },
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["passage_id"].startswith("rc-passage-")
    assert body["linked_proposals"] == [parked_passage["proposal_id"]]
    assert body["passage_id"] in load_passages()

    fetched = await client.get(f"/api/lsat/passages/{body['passage_id']}")
    assert fetched.status_code == 200
    assert fetched.json()["passage"]["title"] == "Coastal erosion"

    approved = await client.post(
        f"/api/lsat/proposals/{parked_passage['proposal_id']}/approve",
        json={"reviewer": "alice"},
    )
    assert approved.status_code == 200, approved.text
    question = await client.get(f"/api/lsat/questions/{approved.json()['question_id']}")
    assert question.json()["passage_id"] == body["passage_id"]


@pytest.mark.asyncio
async def test_passage_approve_endpoint_accepts_a_job_id(
    client: AsyncClient, parked_passage: dict[str, str]
) -> None:
    res = await client.post(
        "/api/lsat/proposals/passages/approve",
        json={"job_id": "mfst-api-job01", "reviewer": "alice"},
    )
    assert res.status_code == 200, res.text
    assert res.json()["linked_proposals"] == [parked_passage["proposal_id"]]


@pytest.mark.asyncio
async def test_passage_approve_endpoint_rejects_a_second_promotion(
    client: AsyncClient, parked_passage: dict[str, str]
) -> None:
    first = await client.post(
        "/api/lsat/proposals/passages/approve",
        json={"pending_passage_path": parked_passage["path"]},
    )
    assert first.status_code == 200
    again = await client.post(
        "/api/lsat/proposals/passages/approve",
        json={"pending_passage_path": parked_passage["path"]},
    )
    assert again.status_code == 409
    assert "already promoted" in again.json()["detail"]


@pytest.mark.asyncio
async def test_passage_approve_endpoint_requires_a_target(
    client: AsyncClient, parked_passage: dict[str, str]
) -> None:
    res = await client.post("/api/lsat/proposals/passages/approve", json={})
    assert res.status_code == 422


@pytest.mark.asyncio
async def test_approving_a_passage_set_draft_first_is_refused(
    client: AsyncClient, parked_passage: dict[str, str]
) -> None:
    """Ordering: a question with no context would ship unusable."""
    res = await client.post(
        f"/api/lsat/proposals/{parked_passage['proposal_id']}/approve",
        json={"reviewer": "alice"},
    )
    assert res.status_code == 409
    assert "not promoted yet" in res.json()["detail"]


@pytest.mark.asyncio
async def test_approve_endpoint_closes_a_crosscheck_without_touching_the_bank(
    client: AsyncClient,
) -> None:
    """BL-20260831-21: approving a disagreement means "the key is right"."""
    from law_ai.lsat.services import proposals
    from law_ai.lsat.services.bank import load_bank

    pid = proposals.record_proposal(
        {
            "question_id": "lr-001",
            "bank_choice": "A",
            "model_choice": "B",
            "rationale": "The chain preferred B.",
        },
        agent_trace_id="",
        model="claude_code/claude-opus-5-5",
        confidence=0.0,
        proposal_kind="crosscheck",
    )
    before = set(load_bank())
    res = await client.post(
        f"/api/lsat/proposals/{pid}/approve",
        json={"reviewer": "alice", "note": "key re-verified"},
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["status"] == "approved"
    assert body["proposal_kind"] == "crosscheck"
    assert "cross_check" not in body, "no blind solve is run for a report row"
    assert set(load_bank()) == before


@pytest.mark.asyncio
async def test_reject_endpoint_closes_a_crosscheck_row(client: AsyncClient) -> None:
    """Rejecting means the key is wrong; the fix is a human question edit."""
    from law_ai.lsat.services import proposals

    pid = proposals.record_proposal(
        {"question_id": "lr-001", "bank_choice": "A", "model_choice": "B"},
        agent_trace_id="",
        model="m",
        confidence=0.0,
        proposal_kind="crosscheck",
    )
    res = await client.post(
        f"/api/lsat/proposals/{pid}/reject",
        json={"reviewer": "alice", "note": "key is wrong, editing lr-001"},
    )
    assert res.status_code == 200, res.text
    assert res.json()["status"] == "rejected"
