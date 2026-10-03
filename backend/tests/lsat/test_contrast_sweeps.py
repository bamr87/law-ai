"""The two spec 054 sweeps: contrast drafting and type review."""

from __future__ import annotations

import json
from io import StringIO
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from django.conf import settings
from django.core.management import call_command
from django.core.management.base import CommandError

pytestmark = [pytest.mark.unit]


@pytest.fixture(autouse=True)
def _isolate_state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Any:
    monkeypatch.setattr(settings, "AUDIT_PATH", str(tmp_path / "audit.jsonl"))
    monkeypatch.setattr(
        settings, "LSAT_PROPOSALS_DIR", str(tmp_path / "lsat_proposals"), raising=False
    )
    monkeypatch.setattr(
        settings,
        "LSAT_RESPONSE_CACHE_DIR",
        str(tmp_path / "response_cache"),
        raising=False,
    )
    from law_ai.lsat.services import bank as bank_mod

    real = bank_mod.DATA_DIR
    sandbox = tmp_path / "lsat_data"
    sandbox.mkdir()
    for name in (
        "lr_bank.json",
        "rc_bank.json",
        "lg_bank.json",
        "concepts.json",
        "passages.json",
        "sections.json",
    ):
        (sandbox / name).write_text((real / name).read_text(encoding="utf-8"))
    monkeypatch.setattr(bank_mod, "DATA_DIR", sandbox)
    bank_mod.reset_caches()
    yield
    bank_mod.reset_caches()


def _run(cmd: str, *args: str) -> str:
    out = StringIO()
    call_command(cmd, *args, stdout=out)
    return out.getvalue()


class TestContrastSweep:
    def test_dry_run_plans_confusable_pairs_and_skips_existing(self) -> None:
        out = _run("lsat_contrast_sweep", "--source", "lr-002", "--dry-run")
        assert "would draft: lr-002 → " in out
        assert "lr-strengthen" not in out and "lr-necessary-assumption" not in out
        out = _run("lsat_contrast_sweep", "--limit", "2", "--dry-run")
        assert out.count("would draft:") == 2

    def test_bad_arguments(self) -> None:
        with pytest.raises(CommandError):
            _run("lsat_contrast_sweep", "--target", "lr-bogus")
        with pytest.raises(CommandError):
            _run("lsat_contrast_sweep", "--section", "RC")
        with pytest.raises(CommandError):
            _run("lsat_contrast_sweep", "--source", "nope-1")

    def test_files_through_the_loop_and_skips_pending_pairs(self) -> None:
        from law_ai.lsat.services import proposals as proposals_store
        from law_ai.lsat.services.contrast import VariationResult

        calls: list[tuple[str, str]] = []

        async def fake(src: str, tgt: str, **kw: Any) -> VariationResult:
            calls.append((src, tgt))
            pid = proposals_store.record_proposal(
                {"section": "LR", "stem": "x"},
                agent_trace_id="",
                model="m",
                confidence=0.5,
                meta={"variation_of": src, "factory": {"archetype_id": tgt}},
            )
            return VariationResult(
                source_id=src,
                target_archetype_id=tgt,
                proposal_id=pid,
                accepted=True,
                rounds=1,
            )

        with patch(
            "law_ai.lsat.management.commands.lsat_contrast_sweep.draft_variation",
            new=fake,
        ):
            out = _run(
                "lsat_contrast_sweep",
                "--source",
                "lr-002",
                "--target",
                "lr-evaluate-argument",
            )
            assert "1 filed" in out and calls == [("lr-002", "lr-evaluate-argument")]
            out = _run(
                "lsat_contrast_sweep",
                "--source",
                "lr-002",
                "--target",
                "lr-evaluate-argument",
                "--dry-run",
            )
            assert "0 variation(s)" in out


class TestTypeReviewSweep:
    def _review(self, archetype: str) -> Any:
        from law_ai.core.llm.base import LLMResult

        return LLMResult(
            text=json.dumps(
                {"archetype_id": archetype, "rationale": "r", "confidence": 0.8}
            ),
            provider="claude_code",
            model="m",
            latency_ms=1.0,
        )

    def test_disagreement_is_queued_and_agreement_is_not(self) -> None:
        from law_ai.agents_runtime.crews import lsat_type_reviewer as mod
        from law_ai.lsat.services import proposals as proposals_store

        with patch.object(
            mod.llm, "agenerate", new=AsyncMock(return_value=self._review("lr-weaken"))
        ):
            out = _run("lsat_type_review_sweep", "--section", "LR", "--limit", "1")
        assert "lr-001: DISAGREES" in out  # lr-001 is parallel reasoning
        rows = proposals_store.list_proposals("pending")
        assert len(rows) == 1 and rows[0]["proposal_kind"] == "typecheck"
        assert rows[0]["draft"]["model_archetype"] == "lr-weaken"
        assert rows[0]["draft"]["stamped_archetype"] == "lr-parallel-reasoning"
        # The pending row and the cached read both keep lr-001 out of the next run.
        out = _run(
            "lsat_type_review_sweep", "--section", "LR", "--limit", "1", "--dry-run"
        )
        assert "would read: lr-002" in out
        with patch.object(
            mod.llm, "agenerate", new=AsyncMock(return_value=self._review("lr-weaken"))
        ):
            out = _run("lsat_type_review_sweep", "--section", "LR", "--limit", "1")
        assert (
            "lr-002: agrees" in out
            and len(proposals_store.list_proposals("pending")) == 1
        )

    def test_degraded_is_never_filed(self) -> None:
        from law_ai.agents_runtime.crews import lsat_type_reviewer as mod
        from law_ai.lsat.services import proposals as proposals_store

        with patch.object(
            mod.llm,
            "agenerate",
            new=AsyncMock(side_effect=mod.llm.LLMUnavailableError("down")),
        ):
            out = _run("lsat_type_review_sweep", "--limit", "2")
        assert (
            "2 degraded skipped" in out
            and proposals_store.list_proposals("pending") == []
        )
        with pytest.raises(CommandError):
            _run("lsat_type_review_sweep", "--section", "WS")
