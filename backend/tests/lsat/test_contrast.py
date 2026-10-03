"""Contrast variations: sets, gates, filing, promotion (spec 054 AC-1..AC-5)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from django.conf import settings

from law_ai.lsat.services.bank import load_bank
from law_ai.lsat.services.contrast import (
    contrast_set,
    draft_variation,
    pivot_targets,
    public_contrast_view,
    root_id_of,
    stimulus_of,
    validate_variation,
)
from law_ai.lsat.services.playbooks import classify

pytestmark = [pytest.mark.unit]


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


def _good_draft(source_id: str = "lr-002") -> dict[str, Any]:
    """A clean Strengthen variation of lr-002 (mirrors the seeded lr-097)."""
    seeded = load_bank()["lr-097"]
    return {
        "section": "LR",
        "difficulty": "med",
        "stem": seeded.stem,
        "choices": [c.model_dump() for c in seeded.choices],
        "correct": seeded.correct,
        "explanation": seeded.explanation,
        "concepts": list(seeded.concepts),
        "contrast_note": seeded.contrast_note,
        "distractor_traps": {"B": "out-of-scope", "E": "out-of-scope"},
        "confidence": 0.8,
        "variation_of": source_id,
        "target_archetype_id": "lr-strengthen",
    }


class TestShape:
    def test_stimulus_is_everything_before_the_question_sentence(self) -> None:
        assert stimulus_of("Arg.\n\nMore.\n\nWhich weakens?") == "Arg.\n\nMore."
        assert stimulus_of("Which weakens?") == ""

    def test_seeded_variations_share_their_roots_stimulus_and_type_correctly(
        self,
    ) -> None:
        # AC-1: every shipped variation is what it claims to be.
        bank = load_bank()
        variations = [q for q in bank.values() if q.variation_of]
        assert {q.id for q in variations} >= {"lr-097", "lr-098", "lr-099"}
        for q in variations:
            root = bank[q.variation_of or ""]
            assert stimulus_of(q.stem) == stimulus_of(root.stem), q.id
            assert q.archetype and q.archetype != root.archetype, q.id
            assert (
                classify(q.model_copy(update={"archetype": None})).archetype_id
                == q.archetype
            )
            assert q.contrast_note and len(q.contrast_note) >= 60
            assert (
                validate_variation(
                    {**q.model_dump(), "distractor_traps": {}}, root, q.archetype
                )
                == []
            )

    def test_contrast_set_is_root_first_from_any_member(self) -> None:
        ids = [q.id for q in contrast_set("lr-098")]
        assert ids[0] == "lr-002" and "lr-097" in ids and "lr-098" in ids
        assert [q.id for q in contrast_set("lr-002")] == ids
        assert root_id_of(load_bank()["lr-099"]) == "lr-007"
        assert [q.id for q in contrast_set("lr-001")] == ["lr-001"]

    def test_pivot_targets_prefer_confusables_and_skip_existing(self) -> None:
        targets = pivot_targets(load_bank()["lr-002"])
        assert (
            "lr-strengthen" not in targets and "lr-necessary-assumption" not in targets
        )
        assert "lr-weaken" not in targets
        assert targets[0] in {"lr-causal-flaw", "lr-evaluate-argument"}
        assert pivot_targets(load_bank()["rc-001"]) == []

    def test_public_view_withholds_notes_unless_asked(self) -> None:
        body = public_contrast_view("lr-097")
        assert body["root_id"] == "lr-002" and body["count"] == 3
        member = next(m for m in body["members"] if m["id"] == "lr-097")
        assert member["archetype_name"] == "Strengthen" and member["task"]
        assert "contrast_note" not in member and "correct" not in member
        spoiled = public_contrast_view("lr-097", include_spoilers=True)
        assert next(m for m in spoiled["members"] if m["id"] == "lr-097")[
            "contrast_note"
        ]
        with pytest.raises(KeyError):
            public_contrast_view("nope")


class TestGates:
    def test_clean_draft_passes(self) -> None:
        assert (
            validate_variation(_good_draft(), load_bank()["lr-002"], "lr-strengthen")
            == []
        )

    def test_altered_stimulus_is_rejected(self) -> None:
        d = _good_draft()
        d["stem"] = (
            "City planner: something else entirely.\n\n" + d["stem"].split("\n\n")[-1]
        )
        issues = validate_variation(d, load_bank()["lr-002"], "lr-strengthen")
        assert any("stimulus was altered" in i for i in issues)

    def test_stem_must_read_as_the_target(self) -> None:
        d = _good_draft()
        d["stem"] = d["stem"].replace("most strengthens", "most weakens")
        issues = validate_variation(d, load_bank()["lr-002"], "lr-strengthen")
        assert any("reads as lr-weaken" in i for i in issues)

    def test_recycled_key_and_same_question_are_rejected(self) -> None:
        src = load_bank()["lr-002"]
        d = _good_draft()
        key_text = next(c.text for c in src.choices if c.label == src.correct)
        d["choices"][0]["text"] = key_text
        d["stem"] = src.stem
        issues = validate_variation(d, src, "lr-strengthen")
        assert any("source's key verbatim" in i for i in issues)
        assert any("question sentence is unchanged" in i for i in issues)

    def test_metadata_gates(self) -> None:
        d = _good_draft()
        d["contrast_note"] = "short"
        d["concepts"] = ["weaken"]
        d["distractor_traps"] = {"A": "nope"}
        issues = validate_variation(d, load_bank()["lr-002"], "lr-strengthen")
        assert any("contrast_note" in i for i in issues)
        assert any("primary tag 'strengthen'" in i for i in issues)
        assert any("unknown trap" in i for i in issues)
        assert any("must not tag the key" in i for i in issues)

    def test_bad_targets(self) -> None:
        src = load_bank()["lr-002"]
        assert validate_variation(_good_draft(), src, "rc-main-point")[0].startswith(
            "target rc-main-point is a RC"
        )
        assert (
            "nothing to contrast"
            in validate_variation(_good_draft(), src, "lr-weaken")[0]
        )
        assert validate_variation({}, src, "lr-bogus") == [
            "unknown target archetype 'lr-bogus'"
        ]
        assert validate_variation({}, src, "lr-strengthen")[0] == "stem is missing"


class TestDraftAndFile:
    @pytest.mark.asyncio
    async def test_files_an_accepted_draft_with_lineage_and_history(self) -> None:
        # AC-3: author → gates → judge → proposal, all pending.
        from law_ai.agents_runtime.crews import lsat_contrast_author as author_mod
        from law_ai.agents_runtime.crews import lsat_draft_judge as judge_mod
        from law_ai.agents_runtime.crews.lsat_contrast_author import (
            ContrastDraft,
            ContrastOutput,
        )
        from law_ai.agents_runtime.crews.lsat_draft_judge import (
            JudgeDraftOutput,
            JudgeVerdict,
        )
        from law_ai.lsat.services import proposals as proposals_store

        draft = ContrastDraft.model_validate(_good_draft())
        verdict = JudgeVerdict(
            verdict="pass", solved_key="A", key_agrees=True, confidence=0.9
        )
        with (
            patch.object(
                author_mod.LSATContrastAuthor,
                "run",
                new=AsyncMock(
                    return_value=ContrastOutput(draft=draft, model="test/model")
                ),
            ),
            patch.object(
                judge_mod.LSATDraftJudge,
                "run",
                new=AsyncMock(
                    return_value=JudgeDraftOutput(verdict=verdict, model="test/judge")
                ),
            ),
        ):
            result = await draft_variation("lr-002", "lr-strengthen")
        assert result.accepted and result.rounds == 1 and result.proposal_id
        # The same (patched) judge served as the final reviewer.
        assert result.final_verdict == "pass"
        row = proposals_store.get_proposal(result.proposal_id)
        assert row is not None and row["status"] == "pending"
        assert row["proposal_kind"] == "question"
        assert row["meta"]["final_review"]["role"] == "final_review"
        assert row["meta"]["variation_of"] == "lr-002"
        assert row["meta"]["factory"]["archetype_id"] == "lr-strengthen"
        assert row["meta"]["factory"]["judge"]["verdict"] == "pass"
        assert row["meta"]["revisions"]["accepted"] is True
        assert row["draft"]["contrast_note"]
        # Promotion carries the lineage into the bank (AC-4).
        promoted = proposals_store.promote_to_bank(
            result.proposal_id, reviewer="tester"
        )
        item = load_bank()[promoted["question_id"]]
        assert item.variation_of == "lr-002" and item.archetype == "lr-strengthen"
        assert item.contrast_note and item.contrast_note.startswith("Same argument")
        assert promoted["question_id"] in [q.id for q in contrast_set("lr-002")]

    @pytest.mark.asyncio
    async def test_revises_on_gate_failure_and_flags_when_cap_is_hit(self) -> None:
        # AC-5: a bad draft is sent back with the objections; an unaccepted
        # draft is still filed for a human, flagged.
        from law_ai.agents_runtime.crews import lsat_contrast_author as author_mod
        from law_ai.agents_runtime.crews.lsat_contrast_author import (
            ContrastDraft,
            ContrastOutput,
        )
        from law_ai.lsat.services import proposals as proposals_store

        bad = _good_draft()
        bad["stem"] = bad["stem"].replace("most strengthens", "most weakens")
        seen: list[list[str]] = []

        async def _run(_self: Any, payload: dict[str, Any]) -> ContrastOutput:
            seen.append(list(payload["critique"]))
            return ContrastOutput(
                draft=ContrastDraft.model_validate(bad), model="test/model"
            )

        with patch.object(author_mod.LSATContrastAuthor, "run", new=_run):
            result = await draft_variation(
                "lr-002",
                "lr-strengthen",
                max_rounds=2,
                use_judge=False,
                use_final_review=False,
            )
        assert not result.accepted and result.rounds == 2 and result.proposal_id
        assert seen[0] == [] and any("reads as lr-weaken" in c for c in seen[1])
        row = proposals_store.get_proposal(result.proposal_id)
        assert row is not None and row["meta"]["revisions"]["accepted"] is False
        assert len(row["meta"]["revisions"]["rounds"]) == 2

    @pytest.mark.asyncio
    async def test_degraded_author_files_nothing(self) -> None:
        from law_ai.agents_runtime.crews import lsat_contrast_author as author_mod
        from law_ai.agents_runtime.crews.lsat_contrast_author import ContrastOutput
        from law_ai.lsat.services import proposals as proposals_store

        with patch.object(
            author_mod.LSATContrastAuthor,
            "run",
            new=AsyncMock(return_value=ContrastOutput(draft=None, degraded=True)),
        ):
            result = await draft_variation(
                "lr-002", "lr-strengthen", use_judge=False, use_final_review=False
            )
        assert result.degraded and result.proposal_id is None
        assert proposals_store.list_proposals("pending") == []


class TestTypecheckPromotion:
    def test_approving_a_typecheck_restamps_and_rejecting_keeps(self) -> None:
        from law_ai.lsat.services import proposals as proposals_store

        pid = proposals_store.record_proposal(
            {
                "question_id": "lr-002",
                "section": "LR",
                "stem": "x",
                "stamped_archetype": "lr-weaken",
                "model_archetype": "lr-causal-flaw",
                "rationale": "r",
                "confidence": 0.7,
                "model": "m",
            },
            agent_trace_id="",
            model="m",
            confidence=0.7,
            proposal_kind="typecheck",
        )
        row = proposals_store.promote_typecheck(pid, reviewer="tester")
        assert row["status"] == "approved" and row["question_id"] == "lr-002"
        assert load_bank()["lr-002"].archetype == "lr-causal-flaw"
        raw = json.loads(
            (
                load_bank
                and __import__(
                    "law_ai.lsat.services.bank", fromlist=["DATA_DIR"]
                ).DATA_DIR
                / "lr_bank.json"
            ).read_text()
        )
        assert (
            next(i for i in raw["items"] if i["id"] == "lr-002")["archetype"]
            == "lr-causal-flaw"
        )
        with pytest.raises(ValueError):
            proposals_store.promote_typecheck(pid)
        with pytest.raises(ValueError):
            proposals_store.promote_crosscheck(
                proposals_store.record_proposal(
                    {
                        "question_id": "lr-003",
                        "section": "LR",
                        "stem": "x",
                        "model_archetype": "lr-weaken",
                    },
                    agent_trace_id="",
                    model="m",
                    confidence=0.0,
                    proposal_kind="typecheck",
                )
            )
