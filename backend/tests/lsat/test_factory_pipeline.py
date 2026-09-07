"""Pipeline e2e tests (spec 024 T-007: FR-8 backing functions, AC-1, AC-2)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from law_ai.lsat.factory.config import FactoryConfig
from law_ai.lsat.factory.executors import ExecutionError, RawBatch
from law_ai.lsat.factory.manifest import GenerationJob
from law_ai.lsat.factory.pipeline import (
    compile_plan,
    execute_manifest,
    ingest_drafts_file,
    load_manifest,
    plan,
    status,
)
from law_ai.lsat.services import proposals

_STEM_BANK = (
    "Museum attendance doubled after free-admission Fridays began; the "
    "director credits the policy. Which finding most weakens that claim?",
    "A firm's revenue grew each quarter it advertised on podcasts; the CMO "
    "concludes the ads caused the growth. What most undermines this?",
    "Students using flashcards outscored peers; the tutor infers flashcards "
    "work. Which alternative most challenges the inference?",
)


def _draft_for(job: GenerationJob, i: int) -> dict[str, Any]:
    return {
        "section": job.target.section,
        "difficulty": job.target.difficulty,
        "stem": f"{_STEM_BANK[i % len(_STEM_BANK)]} (variant {job.job_id}-{i})",
        "choices": [
            {"label": label, "text": f"option {label} #{i}"}
            for label in ("A", "B", "C", "D", "E")
        ],
        "correct": ("A", "B", "C", "D", "E")[i % 5],
        "explanation": "Key holds; each other choice fails distinctly.",
        "concepts": list(job.target.concepts[:2]),
        "confidence": 0.7,
    }


class TestOfflineLifecycle:
    def test_plan_compile_status(self, factory_env: FactoryConfig) -> None:
        # AC-1: fully offline plan → compile → status.
        targets = plan(factory_env)
        assert targets
        _manifest, path = compile_plan(factory_env, targets)
        assert path.is_file()
        snapshot = status(factory_env)
        assert snapshot["bank_total"] > 0
        assert snapshot["latest_manifest"] == str(path)
        assert snapshot["cells_with_deficit"] > 0

    @pytest.mark.asyncio
    async def test_external_drafts_roundtrip(
        self, factory_env: FactoryConfig, tmp_path: Path
    ) -> None:
        # AC-2: compile → external drafts JSONL → ingest → pending proposals.
        manifest, _ = compile_plan(factory_env)
        jobs = [j for j in manifest.jobs if j.target.mode == "items"][:2]
        assert jobs, "expected at least one items-mode job"
        drafts_path = tmp_path / "external_drafts.jsonl"
        with drafts_path.open("w", encoding="utf-8") as fh:
            for j, job in enumerate(jobs):
                record = {
                    "job_id": job.job_id,
                    "model": f"external/test-{job.tier}",
                    "drafts": [
                        _draft_for(job, j * 3 + i) for i in range(job.target.count)
                    ],
                }
                fh.write(json.dumps(record) + "\n")

        results = await ingest_drafts_file(manifest, drafts_path, factory_env)
        assert len(results) == len(jobs)
        accepted = [pid for r in results for pid in r.accepted]
        assert accepted
        rows = proposals.list_proposals(status="pending")
        assert len(rows) == len(accepted)
        metas = {r["meta"]["factory"]["manifest_id"] for r in rows}
        assert metas == {manifest.manifest_id}
        snapshot = status(factory_env)
        assert snapshot["pending_from_factory"] == len(accepted)

    @pytest.mark.asyncio
    async def test_failed_job_reported_not_fatal(
        self, factory_env: FactoryConfig
    ) -> None:
        manifest, _ = compile_plan(factory_env)

        class _Boom:
            name = "boom"

            async def execute(self, job: GenerationJob) -> RawBatch:
                raise ExecutionError(f"job {job.job_id}: nope")

        results = await execute_manifest(
            manifest, _Boom(), factory_env, job_ids=[manifest.jobs[0].job_id]
        )
        assert len(results) == 1
        assert results[0].accepted == []
        assert results[0].model_label == "boom/failed"
        # Operators must see WHY the job failed, not just that it did.
        assert results[0].error is not None and "nope" in results[0].error

    def test_load_manifest_requires_artifacts(self, factory_env: FactoryConfig) -> None:
        with pytest.raises(FileNotFoundError):
            load_manifest(None, factory_env)


# --------------------------------------------------------------------------
# BL-20260702-02 — the judge tier reviews accepted drafts before the queue.
# --------------------------------------------------------------------------


class _Executor:
    """Fulfils every job from the local draft fixtures (no network)."""

    name = "stub"

    async def execute(self, job: GenerationJob) -> RawBatch:
        return RawBatch(
            job_id=job.job_id,
            payload={"drafts": [_draft_for(job, 0)]},
            model_label="stub/model",
        )


def _verdict_output(verdict: str = "flag", *, degraded: bool = False) -> Any:
    from law_ai.agents_runtime.crews.lsat_draft_judge import (
        JudgeDraftOutput,
        JudgeVerdict,
    )

    return JudgeDraftOutput(
        verdict=JudgeVerdict(
            verdict=verdict,  # type: ignore[arg-type]
            single_best_answer=verdict == "pass",
            solved_key="B",
            ambiguity=0.2,
            issues=[] if verdict == "pass" else ["Choice (D) is also defensible."],
            confidence=0.0 if degraded else 0.7,
            rationale="stub",
            model="stub/judge",
            degraded=degraded,
        ),
        model="stub/judge",
        degraded=degraded,
        trace_id="trace-judge-1",
    )


class TestJudgeTier:
    @pytest.mark.asyncio
    async def test_verdict_lands_on_the_proposal_meta(
        self, factory_env: FactoryConfig, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from law_ai.agents_runtime.crews import lsat_draft_judge as judge_mod

        cfg = factory_env.model_copy(update={"judge_enabled": True})
        manifest, _ = compile_plan(cfg)
        job = next(j for j in manifest.jobs if j.target.mode == "items")

        seen: list[dict[str, Any]] = []

        async def _run(_self: Any, payload: dict[str, Any]) -> Any:
            seen.append(payload)
            return _verdict_output("flag")

        monkeypatch.setattr(judge_mod.LSATDraftJudge, "run", _run)
        results = await execute_manifest(
            manifest, _Executor(), cfg, job_ids=[job.job_id]
        )

        assert len(results) == 1 and results[0].accepted
        proposal_id = results[0].accepted[0]
        assert results[0].judge == {proposal_id: "flag"}
        assert seen and seen[0]["proposal_id"] == proposal_id

        row = proposals.get_proposal(proposal_id)
        assert row is not None
        verdict = row["meta"]["factory"]["judge"]
        assert verdict["verdict"] == "flag"
        assert verdict["issues"] == ["Choice (D) is also defensible."]
        assert verdict["trace_id"] == "trace-judge-1"
        # Advisory only: the proposal is still waiting for a human.
        assert row["status"] == "pending"

    @pytest.mark.asyncio
    async def test_judge_is_off_by_default(
        self, factory_env: FactoryConfig, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from law_ai.agents_runtime.crews import lsat_draft_judge as judge_mod

        called = False

        async def _run(_self: Any, payload: dict[str, Any]) -> Any:
            nonlocal called
            called = True
            return _verdict_output()

        monkeypatch.setattr(judge_mod.LSATDraftJudge, "run", _run)
        manifest, _ = compile_plan(factory_env)
        job = next(j for j in manifest.jobs if j.target.mode == "items")
        results = await execute_manifest(
            manifest, _Executor(), factory_env, job_ids=[job.job_id]
        )

        assert results[0].accepted and not called
        assert results[0].judge == {}
        row = proposals.get_proposal(results[0].accepted[0])
        assert row is not None and "judge" not in row["meta"]["factory"]

    @pytest.mark.asyncio
    async def test_degraded_judge_does_not_fail_the_run(
        self, factory_env: FactoryConfig, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from law_ai.agents_runtime.crews import lsat_draft_judge as judge_mod

        async def _run(_self: Any, payload: dict[str, Any]) -> Any:
            return _verdict_output("flag", degraded=True)

        monkeypatch.setattr(judge_mod.LSATDraftJudge, "run", _run)
        cfg = factory_env.model_copy(update={"judge_enabled": True})
        manifest, _ = compile_plan(cfg)
        job = next(j for j in manifest.jobs if j.target.mode == "items")
        results = await execute_manifest(
            manifest, _Executor(), cfg, job_ids=[job.job_id]
        )

        assert results[0].accepted
        assert any("judge degraded" in w for w in results[0].warnings)
        row = proposals.get_proposal(results[0].accepted[0])
        assert row is not None
        assert row["meta"]["factory"]["judge"]["degraded"] is True

    @pytest.mark.asyncio
    async def test_a_raising_judge_is_reported_not_fatal(
        self, factory_env: FactoryConfig, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from law_ai.agents_runtime.crews import lsat_draft_judge as judge_mod

        async def _run(_self: Any, payload: dict[str, Any]) -> Any:
            raise RuntimeError("judge exploded")

        monkeypatch.setattr(judge_mod.LSATDraftJudge, "run", _run)
        cfg = factory_env.model_copy(update={"judge_enabled": True})
        manifest, _ = compile_plan(cfg)
        job = next(j for j in manifest.jobs if j.target.mode == "items")
        results = await execute_manifest(
            manifest, _Executor(), cfg, job_ids=[job.job_id]
        )

        assert results[0].accepted and results[0].judge == {}
        assert any("judge exploded" in w for w in results[0].warnings)


# --------------------------------------------------------------------------
# BL-20260901-04 — a solve guide is drafted with the item, not swept for later.
# --------------------------------------------------------------------------


def _guide_output(*, degraded: bool = False) -> Any:
    from law_ai.agents_runtime.crews.lsat_solve_guide_author import GenerateGuideOutput
    from law_ai.lsat.services.guides import SolveGuide, SolveStep

    return GenerateGuideOutput(
        guide=SolveGuide(
            question_id="overwritten-by-the-agent",
            method="Find the causal gap, then break it",
            steps=[
                SolveStep(kind="orient", title="Read", text="Name the conclusion."),
                SolveStep(
                    kind="answer",
                    title="Answer",
                    text="The key severs the causal link.",
                    spoiler=True,
                ),
            ],
        ),
        model="stub/guide",
        confidence=0.0 if degraded else 0.7,
        degraded=degraded,
        trace_id="trace-guide-1",
    )


class TestGuideAtAuthoring:
    @staticmethod
    def _stub_author(monkeypatch: pytest.MonkeyPatch, *, degraded: bool = False) -> Any:
        from law_ai.agents_runtime.crews import lsat_solve_guide_author as guide_mod

        seen: list[dict[str, Any]] = []

        async def _run(_self: Any, payload: dict[str, Any]) -> Any:
            seen.append(payload)
            return _guide_output(degraded=degraded)

        monkeypatch.setattr(guide_mod.LSATSolveGuideAuthor, "run", _run)
        return seen

    @pytest.mark.asyncio
    async def test_each_accepted_draft_gets_a_linked_guide_proposal(
        self, factory_env: FactoryConfig, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        seen = self._stub_author(monkeypatch)
        manifest, _ = compile_plan(factory_env)
        job = next(j for j in manifest.jobs if j.target.mode == "items")
        results = await execute_manifest(
            manifest, _Executor(), factory_env, job_ids=[job.job_id]
        )

        proposal_id = results[0].accepted[0]
        guide_id = results[0].guides[proposal_id]
        # The draft itself is handed to the author: it is not in the bank yet.
        assert seen[0]["question_id"] == proposal_id
        assert seen[0]["question"]["stem"]

        guide_row = proposals.get_proposal(guide_id)
        assert guide_row is not None
        assert guide_row["proposal_kind"] == "guide"
        assert guide_row["status"] == "pending"
        assert guide_row["meta"]["guide_for_proposal"] == proposal_id
        # Factory lineage rides along so the queue can group the pair.
        assert guide_row["meta"]["factory"]["job_id"] == job.job_id

    @pytest.mark.asyncio
    async def test_degraded_guides_are_not_queued(
        self, factory_env: FactoryConfig, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        self._stub_author(monkeypatch, degraded=True)
        manifest, _ = compile_plan(factory_env)
        job = next(j for j in manifest.jobs if j.target.mode == "items")
        results = await execute_manifest(
            manifest, _Executor(), factory_env, job_ids=[job.job_id]
        )

        assert results[0].accepted and results[0].guides == {}
        assert not [
            r
            for r in proposals.list_proposals("pending")
            if r.get("proposal_kind") == "guide"
        ]
        assert any("guide skipped" in w for w in results[0].warnings)

    @pytest.mark.asyncio
    async def test_guides_can_be_switched_off(
        self, factory_env: FactoryConfig, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        seen = self._stub_author(monkeypatch)
        cfg = factory_env.model_copy(update={"guides_enabled": False})
        manifest, _ = compile_plan(cfg)
        job = next(j for j in manifest.jobs if j.target.mode == "items")
        results = await execute_manifest(
            manifest, _Executor(), cfg, job_ids=[job.job_id]
        )

        assert results[0].accepted and results[0].guides == {}
        assert seen == []

    @pytest.mark.asyncio
    async def test_promotion_relinks_the_guide_to_the_new_question_id(
        self, factory_env: FactoryConfig, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        self._stub_author(monkeypatch)
        manifest, _ = compile_plan(factory_env)
        job = next(j for j in manifest.jobs if j.target.mode == "items")
        results = await execute_manifest(
            manifest, _Executor(), factory_env, job_ids=[job.job_id]
        )
        proposal_id = results[0].accepted[0]
        guide_id = results[0].guides[proposal_id]

        promoted = proposals.promote_to_bank(proposal_id, reviewer="tester")
        question_id = promoted["question_id"]
        assert promoted["linked_guide_proposals"] == [guide_id]

        guide_row = proposals.get_proposal(guide_id)
        assert guide_row is not None
        assert guide_row["draft"]["question_id"] == question_id
        # The guide is still HITL-gated in its own right.
        assert guide_row["status"] == "pending"

    @pytest.mark.asyncio
    async def test_a_second_run_does_not_double_queue_a_guide(
        self, factory_env: FactoryConfig, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        self._stub_author(monkeypatch)
        manifest, _ = compile_plan(factory_env)
        job = next(j for j in manifest.jobs if j.target.mode == "items")
        results = await execute_manifest(
            manifest, _Executor(), factory_env, job_ids=[job.job_id]
        )
        first = results[0]
        # Re-running guide drafting over the same result is a no-op.
        from law_ai.lsat.factory.guides import draft_guides

        first.guides.clear()
        await draft_guides(first, config=factory_env)
        assert first.guides == {}
        guides = [
            r
            for r in proposals.list_proposals("pending")
            if r.get("proposal_kind") == "guide"
        ]
        assert len(guides) == 1
