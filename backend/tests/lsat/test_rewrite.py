"""Judge-driven rewrites of bank items (spec 054 FR-11, AC-10, AC-11)."""

from __future__ import annotations

import json
from io import StringIO
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
from django.conf import settings
from django.core.management import call_command

from law_ai.lsat.services.bank import load_bank
from law_ai.lsat.services.rewrite import (
    judge_objects,
    review_question,
    validate_rewrite,
)

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


def _edit(qid: str = "lr-002", **over: Any) -> dict[str, Any]:
    q = load_bank()[qid]
    d = {
        "question_id": qid,
        "section": q.section,
        "difficulty": q.difficulty,
        "stem": q.stem,
        "choices": [c.model_dump() for c in q.choices],
        "correct": q.correct,
        "explanation": q.explanation + " Tightened.",
        "concepts": list(q.concepts),
        "passage_id": q.passage_id,
        "change_summary": "Tightened the explanation to address the objection.",
        "confidence": 0.8,
    }
    d.update(over)
    return d


def _verdict(
    verdict: str, *issues: str, key_agrees: bool | None = True, **over: Any
) -> dict[str, Any]:
    v = {
        "verdict": verdict,
        "issues": list(issues),
        "key_agrees": key_agrees,
        "degraded": False,
        "model": "m",
    }
    v.update(over)
    return v


class TestGates:
    def test_clean_edit_passes_and_type_must_stay(self) -> None:
        src = load_bank()["lr-002"]
        assert validate_rewrite(_edit(), src) == []
        bad = _edit(stem=src.stem.replace("most weakens", "most strengthens"))
        assert any("reads as lr-strengthen" in i for i in validate_rewrite(bad, src))

    def test_shared_stimulus_is_locked(self) -> None:
        src = load_bank()["lr-002"]  # root of a contrast set
        changed = _edit(
            stem="City planner: a different argument.\n\n" + src.stem.split("\n\n")[-1]
        )
        assert any("shares its stimulus" in i for i in validate_rewrite(changed, src))
        lone = load_bank()["lr-001"]
        alone = _edit(
            "lr-001", stem="Other stimulus.\n\n" + lone.stem.split("\n\n")[-1]
        )
        assert not any("shares" in i for i in validate_rewrite(alone, lone))

    def test_metadata_gates(self) -> None:
        src = load_bank()["lr-002"]
        issues = validate_rewrite(
            _edit(change_summary="x", concepts=["nope"], explanation=""), src
        )
        assert any("change_summary" in i for i in issues)
        assert any("unknown concept" in i for i in issues)
        assert any("explanation" in i for i in issues)
        assert validate_rewrite({}, src) == ["stem is missing"]

    def test_judge_objects(self) -> None:
        assert not judge_objects(_verdict("pass"))
        assert not judge_objects(_verdict("flag"))
        assert judge_objects(_verdict("flag", "Choice B also works."))
        assert judge_objects(_verdict("fail"))
        assert judge_objects(_verdict("flag", key_agrees=False, solved_key="B"))
        assert not judge_objects(_verdict("fail", degraded=True))


def _patch_crews(
    verdicts: list[dict[str, Any]],
    edits: list[dict[str, Any] | None],
    final: dict[str, Any] | None = None,
):
    from law_ai.agents_runtime.crews import lsat_draft_judge as judge_mod
    from law_ai.agents_runtime.crews import lsat_question_editor as editor_mod
    from law_ai.agents_runtime.crews.lsat_draft_judge import (
        JudgeDraftOutput,
        JudgeVerdict,
    )
    from law_ai.agents_runtime.crews.lsat_question_editor import EditOutput, EditedDraft

    it = iter(verdicts)

    async def judge_run(_self: Any, payload: dict[str, Any]) -> JudgeDraftOutput:
        v = final if payload.get("model_override") and final is not None else next(it)
        return JudgeDraftOutput(
            verdict=JudgeVerdict.model_validate(
                {k: x for k, x in v.items() if k != "role"}
            ),
            model="m",
        )

    eit = iter(edits)

    async def editor_run(_self: Any, payload: dict[str, Any]) -> EditOutput:
        e = next(eit)
        if e is None:
            return EditOutput(draft=None, degraded=True)
        return EditOutput(draft=EditedDraft.model_validate(e), model="editor/m")

    return (
        patch.object(judge_mod.LSATDraftJudge, "run", new=judge_run),
        patch.object(editor_mod.LSATQuestionEditor, "run", new=editor_run),
    )


class TestReviewQuestion:
    @pytest.mark.asyncio
    async def test_clean_item_files_nothing_and_is_cached(self) -> None:
        from law_ai.lsat.services import proposals as proposals_store

        p1, p2 = _patch_crews([_verdict("pass")], [])
        with p1, p2:
            r = await review_question("lr-002")
            again = await review_question("lr-002")
        assert r.clean and r.proposal_id is None and not r.cached
        assert again.clean and again.cached
        assert proposals_store.list_proposals("pending") == []

    @pytest.mark.asyncio
    async def test_objection_is_rewritten_reviewed_and_filed_then_promoted_in_place(
        self,
    ) -> None:
        from law_ai.lsat.services import proposals as proposals_store

        p1, p2 = _patch_crews(
            [_verdict("flag", "Choice A is vague."), _verdict("pass")],
            [_edit()],
            final=_verdict("flag", "one reservation", role="final_review"),
        )
        with p1, p2:
            r = await review_question("lr-002")
        assert not r.clean and r.accepted and r.rounds == 1 and r.proposal_id
        assert r.final_verdict == "flag" and r.issues == ["Choice A is vague."]
        row = proposals_store.get_proposal(r.proposal_id)
        assert row is not None and row["proposal_kind"] == "rewrite"
        assert row["meta"]["rewrite_of"] == "lr-002"
        assert row["meta"]["original_judge"]["issues"] == ["Choice A is vague."]
        assert row["meta"]["final_review"]["role"] == "final_review"
        assert row["meta"]["revisions"]["accepted"] is True
        promoted = proposals_store.promote_rewrite(r.proposal_id, reviewer="tester")
        assert promoted["question_id"] == "lr-002"
        item = load_bank()["lr-002"]
        assert item.explanation.endswith("Tightened.")
        assert item.archetype == "lr-weaken" and item.id == "lr-002"
        assert item.review is not None and item.review.method == "editorial"
        assert "rewrite approved" in (item.review.note or "")
        raw = json.loads(
            (
                __import__("law_ai.lsat.services.bank", fromlist=["DATA_DIR"]).DATA_DIR
                / "lr_bank.json"
            ).read_text()
        )
        assert sum(1 for i in raw["items"] if i["id"] == "lr-002") == 1
        with pytest.raises(ValueError):
            proposals_store.promote_rewrite(r.proposal_id)

    @pytest.mark.asyncio
    async def test_final_review_fail_files_unaccepted(self) -> None:
        from law_ai.lsat.services import proposals as proposals_store

        p1, p2 = _patch_crews(
            [_verdict("fail", "Key is wrong."), _verdict("pass")],
            [_edit()],
            final=_verdict("fail", "still wrong", key_agrees=False, solved_key="B"),
        )
        with p1, p2:
            r = await review_question("lr-002")
        assert r.proposal_id and not r.accepted and r.final_verdict == "fail"
        row = proposals_store.get_proposal(r.proposal_id)
        assert row is not None and row["meta"]["revisions"]["accepted"] is False

    @pytest.mark.asyncio
    async def test_degraded_editor_files_nothing(self) -> None:
        from law_ai.lsat.services import proposals as proposals_store

        p1, p2 = _patch_crews([_verdict("fail", "bad")], [None])
        with p1, p2:
            r = await review_question("lr-002", use_final_review=False)
        assert r.degraded and r.proposal_id is None
        assert proposals_store.list_proposals("pending") == []


class TestSweep:
    def test_sweep_files_rewrites_and_skips_judged_and_pending(self) -> None:
        from law_ai.lsat.services import proposals as proposals_store

        p1, p2 = _patch_crews(
            [
                _verdict("pass"),
                _verdict("flag", "Choice A is vague."),
                _verdict("pass"),
            ],
            [_edit()],
            final=_verdict("pass"),
        )
        out = StringIO()
        with p1, p2:
            call_command(
                "lsat_question_review_sweep",
                "--section",
                "LR",
                "--limit",
                "2",
                stdout=out,
            )
        text = out.getvalue()
        assert "lr-001: pass — clean" in text
        assert "lr-002: flag (1 issue(s)) → rewrite" in text and "final pass" in text
        assert "1 rewrites queued" in text
        assert len(proposals_store.list_proposals("pending")) == 1
        out = StringIO()
        call_command(
            "lsat_question_review_sweep",
            "--section",
            "LR",
            "--limit",
            "1",
            "--dry-run",
            stdout=out,
        )
        assert "would review: lr-003" in out.getvalue()
