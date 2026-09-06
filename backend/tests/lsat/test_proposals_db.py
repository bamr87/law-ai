"""Postgres mirror of the JSONL proposal store (BL-20260527-05).

The JSONL log stays the audit trail; ``LsatProposal`` is the indexed mirror
that answers reads once an operator has backfilled it. These tests pin the
two properties that make that safe: writes keep the mirror current, and every
read degrades to the replay when the mirror is off, empty, or unreachable.
"""

from __future__ import annotations

from io import StringIO
from pathlib import Path
from typing import Any

import pytest

from django.conf import settings
from django.core.management import call_command


@pytest.fixture(autouse=True)
def _isolate_state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Any:
    monkeypatch.setattr(settings, "AUDIT_PATH", str(tmp_path / "audit.jsonl"))
    monkeypatch.setattr(
        settings, "LSAT_PROPOSALS_DIR", str(tmp_path / "lsat_proposals"), raising=False
    )
    from law_ai.lsat.services import bank as bank_mod

    real = bank_mod.DATA_DIR
    sandbox = tmp_path / "lsat_data"
    sandbox.mkdir()
    for name in ("lr_bank.json", "rc_bank.json", "lg_bank.json", "concepts.json"):
        src = real / name
        if src.is_file():
            (sandbox / name).write_text(src.read_text(encoding="utf-8"))
    monkeypatch.setattr(bank_mod, "DATA_DIR", sandbox)
    bank_mod.reset_caches()
    yield
    bank_mod.reset_caches()


def _draft(section: str = "LR") -> dict[str, Any]:
    return {
        "section": section,
        "difficulty": "med",
        "stem": "Mirrored stem.",
        "choices": [{"label": label, "text": label} for label in "ABCDE"],
        "correct": "C",
        "explanation": "Because C.",
        "concepts": ["parallel-reasoning"],
        "confidence": 0.8,
    }


def _record() -> str:
    from law_ai.lsat.services import proposals

    return proposals.record_proposal(
        _draft(), agent_trace_id="trace-1", model="m", confidence=0.8
    )


class TestMirrorWrites:
    def test_recording_a_proposal_mirrors_it(self) -> None:
        from law_ai.lsat.models import LsatProposal

        pid = _record()
        row = LsatProposal.objects.get(id=pid)
        assert row.status == "pending"
        assert row.proposal_kind == "question"
        assert row.section == "LR"
        assert row.model == "m"
        assert row.confidence == pytest.approx(0.8)
        # The payload is the replayed row verbatim, so the API shape does not
        # depend on which store answered.
        assert row.payload["draft"]["stem"] == "Mirrored stem."
        assert row.created_at is not None
        # Nothing has happened to it yet: no invented decision timestamp.
        assert row.updated_at is None

    def test_a_decision_updates_the_mirror(self) -> None:
        from law_ai.lsat.models import LsatProposal
        from law_ai.lsat.services import proposals

        pid = _record()
        proposals.set_status(pid, "rejected", reviewer="alice", note="off-key")
        row = LsatProposal.objects.get(id=pid)
        assert row.status == "rejected"
        assert row.reviewer == "alice"
        assert row.note == "off-key"
        assert row.updated_at is not None
        assert row.payload["status"] == "rejected"

    def test_promotion_mirrors_the_assigned_question_id(self) -> None:
        from law_ai.lsat.models import LsatProposal
        from law_ai.lsat.services import proposals

        pid = _record()
        promoted = proposals.promote_to_bank(pid, reviewer="alice")
        row = LsatProposal.objects.get(id=pid)
        assert row.status == "approved"
        assert row.question_id == promoted["question_id"]

    def test_a_mirror_failure_never_blocks_a_write(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The JSONL log is the source of truth; the table is best-effort."""
        from law_ai.lsat.services import proposals

        def boom() -> Any:
            raise RuntimeError("database is gone")

        monkeypatch.setattr(proposals, "_proposal_model", boom)
        pid = _record()
        assert proposals.get_proposal(pid) is not None


class TestReadPath:
    def test_reads_use_the_jsonl_replay_by_default(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from law_ai.lsat.models import LsatProposal
        from law_ai.lsat.services import proposals

        pid = _record()
        # Corrupt the mirror: the default read path must not notice.
        LsatProposal.objects.filter(id=pid).update(
            payload={"id": pid, "status": "gone"}
        )
        assert proposals.get_proposal(pid)["status"] == "pending"
        assert [r["id"] for r in proposals.list_proposals("pending")] == [pid]

    def test_reads_use_the_mirror_when_enabled(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from law_ai.lsat.services import proposals

        pid = _record()
        monkeypatch.setattr(settings, "LSAT_PROPOSALS_DB_READS", True, raising=False)
        # Delete the log entirely: only the mirror can answer now.
        proposals._proposals_path().unlink()
        row = proposals.get_proposal(pid)
        assert row is not None and row["id"] == pid
        assert [r["id"] for r in proposals.list_proposals("pending")] == [pid]

    def test_status_filter_and_limit_match_the_replay(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from law_ai.lsat.services import proposals

        keep = _record()
        closed = _record()
        proposals.set_status(closed, "rejected", reviewer="alice")

        jsonl_pending = [r["id"] for r in proposals.list_proposals("pending")]
        jsonl_all = [r["id"] for r in proposals.list_proposals("all")]
        monkeypatch.setattr(settings, "LSAT_PROPOSALS_DB_READS", True, raising=False)
        assert [r["id"] for r in proposals.list_proposals("pending")] == jsonl_pending
        assert sorted(r["id"] for r in proposals.list_proposals("all")) == sorted(
            jsonl_all
        )
        assert keep in jsonl_pending and closed not in jsonl_pending
        assert len(proposals.list_proposals("all", limit=1)) == 1

    def test_an_empty_mirror_falls_back_instead_of_hiding_the_queue(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Flipping the flag before the backfill must not empty the queue."""
        from law_ai.lsat.models import LsatProposal
        from law_ai.lsat.services import proposals

        pid = _record()
        LsatProposal.objects.all().delete()  # as if recorded before the table
        monkeypatch.setattr(settings, "LSAT_PROPOSALS_DB_READS", True, raising=False)
        assert [r["id"] for r in proposals.list_proposals("pending")] == [pid]
        assert proposals.get_proposal(pid) is not None

    def test_an_async_caller_never_touches_the_orm(self) -> None:
        from law_ai.lsat.services import proposals

        async def _inside_loop() -> Any:
            return proposals._proposal_model()

        import asyncio

        assert asyncio.run(_inside_loop()) is None


class TestBackfillCommand:
    def test_dry_run_reports_without_writing(self) -> None:
        from law_ai.lsat.models import LsatProposal

        _record()
        LsatProposal.objects.all().delete()
        out = StringIO()
        call_command("lsat_proposals_backfill", "--dry-run", stdout=out)
        assert "would mirror 1 proposal" in out.getvalue()
        assert LsatProposal.objects.count() == 0

    def test_backfill_writes_every_replayed_proposal(self) -> None:
        from law_ai.lsat.models import LsatProposal

        first, second = _record(), _record()
        LsatProposal.objects.all().delete()
        out = StringIO()
        call_command("lsat_proposals_backfill", stdout=out)
        assert "Mirrored 2 proposal(s)" in out.getvalue()
        assert set(LsatProposal.objects.values_list("id", flat=True)) == {first, second}
