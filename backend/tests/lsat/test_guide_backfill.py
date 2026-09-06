"""Tests for the ``lsat_guide_backfill`` management command (BL-20260830-11)."""

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
    from law_ai.lsat.services import guides as guides_mod

    real = bank_mod.DATA_DIR
    sandbox = tmp_path / "lsat_data"
    sandbox.mkdir()
    for name in ("lr_bank.json", "rc_bank.json", "lg_bank.json", "guides.json"):
        src = real / name
        if src.is_file():
            (sandbox / name).write_text(src.read_text(encoding="utf-8"))
    monkeypatch.setattr(bank_mod, "DATA_DIR", sandbox)

    def _clear() -> None:
        bank_mod.load_bank.cache_clear()
        guides_mod.reset_guide_cache()

    _clear()
    yield
    _clear()


def _fake_output(question_id: str, *, degraded: bool = False) -> Any:
    from law_ai.agents_runtime.crews.lsat_solve_guide_author import (
        GenerateGuideOutput,
        _fallback_guide,
    )
    from law_ai.lsat.services.bank import load_bank
    from law_ai.lsat.services.guides import SolveGuide

    q = load_bank()[question_id]
    if degraded:
        guide = _fallback_guide(q)
    else:
        guide = SolveGuide.model_validate(
            {
                "question_id": q.id,
                "method": "batch-drafted walkthrough",
                "steps": [
                    {"kind": "orient", "title": "Read", "text": "Read the stem."},
                    {"kind": "infer", "title": "Chain", "text": "Chain it."},
                    {
                        "kind": "answer",
                        "title": "Answer",
                        "text": f"It is {q.correct}.",
                        "spoiler": True,
                    },
                ],
            }
        )
    return GenerateGuideOutput(
        guide=guide,
        model="fallback/offline" if degraded else "claude_code/claude-opus-5",
        confidence=0.0 if degraded else 0.7,
        degraded=degraded,
        trace_id="t-backfill",
    )


def _patch_agent(monkeypatch: pytest.MonkeyPatch, *, degraded: bool = False) -> None:
    from law_ai.agents_runtime.crews import lsat_solve_guide_author as mod

    async def fake_run(self: Any, input_data: dict[str, Any]) -> Any:
        return _fake_output(input_data["question_id"], degraded=degraded)

    monkeypatch.setattr(mod.LSATSolveGuideAuthor, "run", fake_run)


def test_dry_run_lists_guideless_questions() -> None:
    out = StringIO()
    call_command("lsat_guide_backfill", "--dry-run", "--limit", "3", stdout=out)
    text = out.getvalue()
    assert "would draft:" in text
    assert text.count("would draft:") == 3


def test_backfill_queues_pending_guide_proposals(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from law_ai.lsat.services import proposals

    _patch_agent(monkeypatch)
    out = StringIO()
    call_command("lsat_guide_backfill", "--section", "LR", "--limit", "2", stdout=out)
    rows = [
        r
        for r in proposals.list_proposals("pending", limit=100)
        if r.get("proposal_kind") == "guide"
    ]
    assert len(rows) == 2
    for r in rows:
        assert r["status"] == "pending"
        assert r["draft"]["method"] == "batch-drafted walkthrough"
    assert "2 queued for review" in out.getvalue()


def test_backfill_skips_already_pending_questions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from law_ai.lsat.services import proposals

    _patch_agent(monkeypatch)
    call_command(
        "lsat_guide_backfill", "--section", "LR", "--limit", "2", stdout=StringIO()
    )
    first = {
        r["draft"]["question_id"]
        for r in proposals.list_proposals("pending", limit=100)
        if r.get("proposal_kind") == "guide"
    }
    call_command(
        "lsat_guide_backfill", "--section", "LR", "--limit", "2", stdout=StringIO()
    )
    second = {
        r["draft"]["question_id"]
        for r in proposals.list_proposals("pending", limit=100)
        if r.get("proposal_kind") == "guide"
    }
    # Second run drafted two NEW questions rather than re-drafting the first.
    assert len(second) == 4
    assert first < second


def test_backfill_skips_degraded_by_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from law_ai.lsat.services import proposals

    _patch_agent(monkeypatch, degraded=True)
    out = StringIO()
    call_command("lsat_guide_backfill", "--limit", "2", stdout=out)
    rows = [
        r
        for r in proposals.list_proposals("pending", limit=100)
        if r.get("proposal_kind") == "guide"
    ]
    assert rows == []
    assert "degraded" in out.getvalue()

    call_command(
        "lsat_guide_backfill", "--limit", "1", "--include-degraded", stdout=StringIO()
    )
    rows = [
        r
        for r in proposals.list_proposals("pending", limit=100)
        if r.get("proposal_kind") == "guide"
    ]
    assert len(rows) == 1
    assert rows[0]["confidence"] == 0.0


def test_rejects_bad_section() -> None:
    from django.core.management import CommandError

    with pytest.raises(CommandError):
        call_command("lsat_guide_backfill", "--section", "XX", stdout=StringIO())


def test_backfill_closes_the_gap_end_to_end(monkeypatch: pytest.MonkeyPatch) -> None:
    """BL-20260831-23 — draft, approve, serve, and never draft it twice.

    The operator's whole loop against a stubbed provider: the command queues a
    guide, a reviewer promotes it, the guide store serves it, and the next run
    no longer offers that question as a target.
    """
    from law_ai.lsat.services import proposals
    from law_ai.lsat.services.guides import load_guides, validate_guide_quality
    from law_ai.lsat.services.bank import load_bank

    _patch_agent(monkeypatch)
    before = set(load_guides())

    call_command(
        "lsat_guide_backfill", "--section", "LR", "--limit", "1", stdout=StringIO()
    )
    pending = [
        r
        for r in proposals.list_proposals("pending", limit=100)
        if r.get("proposal_kind") == "guide"
    ]
    assert len(pending) == 1
    question_id = pending[0]["draft"]["question_id"]
    assert question_id not in before, "the command must target a guide-less question"

    row = proposals.promote_guide_to_bank(pending[0]["id"], reviewer="editor")
    assert row["status"] == "approved"

    guides = load_guides()
    assert question_id in guides, "an approved guide must serve immediately"
    assert not validate_guide_quality(guides[question_id], load_bank()[question_id])
    assert "approved" in guides[question_id].source

    # The gap closed by one, and the next run picks a different question.
    out = StringIO()
    call_command(
        "lsat_guide_backfill",
        "--section",
        "LR",
        "--dry-run",
        "--limit",
        "3",
        stdout=out,
    )
    assert question_id not in out.getvalue()
