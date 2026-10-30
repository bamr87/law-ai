"""Tests for the ``run_autonomy`` management command (spec 018 T-009)."""

from __future__ import annotations

from io import StringIO
from typing import Any
from unittest.mock import patch

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

# Beat entries that deliberately do NOT route through ``autonomy_cycle``: they
# are not autonomy decisions and must keep running on an instance with autonomy
# switched off. Each one's reason lives beside it in ``law_ai/celery.py``. The
# tests below assert the autonomy contract only over the other entries, and
# assert these separately — the point of naming them here is that adding one is
# a conscious edit rather than silent drift into the schedule.
NON_AUTONOMY_BEATS = {
    "matter-task-reminders": "law_ai.matters.sweep_task_reminders",
}


def _autonomy_beats(schedule: dict) -> dict:  # type: ignore[type-arg]
    """The beat entries that are autonomy cycles."""
    return {k: v for k, v in schedule.items() if k not in NON_AUTONOMY_BEATS}


@pytest.fixture()
def _autonomy_enabled(settings: object) -> None:  # type: ignore[type-arg]
    """Temporarily enable the autonomy kill-switch for a single test."""
    from django.conf import settings as dj

    dj.AUTONOMY_ENABLED = True
    dj.AUTONOMY_ALLOWED_SOURCES = ["courtlistener", "colorado_statutes"]
    yield
    dj.AUTONOMY_ENABLED = False
    dj.AUTONOMY_ALLOWED_SOURCES = []


class TestRunAutonomyBasic:
    def test_disabled_exits_0_with_warning(self, settings: object) -> None:  # type: ignore[type-arg]
        """When AUTONOMY_ENABLED=False the command should still exit 0."""
        from django.conf import settings as dj

        dj.AUTONOMY_ENABLED = False  # type: ignore[assignment]
        out = StringIO()
        # No exception = exit 0
        call_command("run_autonomy", "--kind", "digest", stdout=out)
        assert "disabled" in out.getvalue().lower()

    def test_dry_run_prints_payload(self) -> None:
        out = StringIO()
        call_command(
            "run_autonomy",
            "--kind",
            "corpus_growth",
            "--source",
            "courtlistener",
            "--budget",
            "5",
            "--dry-run",
            stdout=out,
        )
        body = out.getvalue()
        assert "corpus_growth" in body
        assert "courtlistener" in body

    def test_policy_violation_on_unknown_source(self) -> None:
        """Source not in allow-list → CommandError with returncode 1."""
        with pytest.raises(CommandError, match="not in AUTONOMY_ALLOWED_SOURCES"):
            call_command(
                "run_autonomy",
                "--kind",
                "corpus_growth",
                "--source",
                "totally_unknown_adapter",
            )

    @pytest.mark.usefixtures("_autonomy_enabled")
    def test_dry_run_shows_enabled_status(self) -> None:
        out = StringIO()
        call_command(
            "run_autonomy",
            "--kind",
            "digest",
            "--dry-run",
            stdout=out,
        )
        body = out.getvalue()
        assert "AUTONOMY_ENABLED=True" in body

    @pytest.mark.usefixtures("_autonomy_enabled")
    def test_run_cycle_called_with_correct_kind(self) -> None:
        """Happy path: run_cycle is invoked with the requested kind."""
        out = StringIO()
        fake_result = {
            "status": "ok",
            "cycle_id": "test-cycle-1",
            "result": {"digest_path": "var/autonomy/digest-2026-10-26.md"},
        }

        with patch(
            "law_ai.core.autonomy.run_cycle", return_value=fake_result
        ) as mock_run:
            call_command("run_autonomy", "--kind", "digest", stdout=out)

        mock_run.assert_called_once()
        call_args = mock_run.call_args
        assert call_args.args[0] == "digest"
        assert "digest" in out.getvalue().lower() or "cycle" in out.getvalue().lower()

    @pytest.mark.usefixtures("_autonomy_enabled")
    def test_run_cycle_corpus_growth_kind(self) -> None:
        out = StringIO()
        fake_result = {
            "status": "ok",
            "cycle_id": "test-cycle-2",
            "result": {"docs_queued": 0},
        }

        with patch(
            "law_ai.core.autonomy.run_cycle", return_value=fake_result
        ) as mock_run:
            call_command(
                "run_autonomy",
                "--kind",
                "corpus_growth",
                "--source",
                "courtlistener",
                "--budget",
                "10",
                stdout=out,
            )

        mock_run.assert_called_once()
        call_args = mock_run.call_args
        assert call_args.args[0] == "corpus_growth"

    @pytest.mark.usefixtures("_autonomy_enabled")
    def test_run_cycle_error_status_exits_2(self) -> None:
        """If run_cycle returns status=error the command should raise SystemExit(2)."""
        err = StringIO()
        fake_result = {
            "status": "error",
            "cycle_id": "test-cycle-3",
            "error": "something exploded",
        }

        with (
            patch("law_ai.core.autonomy.run_cycle", return_value=fake_result),
            pytest.raises(SystemExit) as exc_info,
        ):
            call_command("run_autonomy", "--kind", "digest", stderr=err)

        assert exc_info.value.code == 2


class TestCeleryAutonomyTask:
    """Smoke-tests for the ``autonomy_cycle`` Celery task (T-009 beat integration)."""

    def test_task_registered(self) -> None:
        from law_ai.celery import app
        import law_ai.core.tasks  # trigger autodiscovery for this module  # noqa: F401

        assert "law_ai.core.tasks.autonomy_cycle" in app.tasks

    def test_task_delegates_to_run_cycle_disabled(self) -> None:
        """When AUTONOMY_ENABLED=False the task returns status=disabled."""
        from law_ai.core.tasks import autonomy_cycle

        result = autonomy_cycle(kind="digest")
        assert result["status"] == "disabled"

    def test_beat_schedule_keys_present(self) -> None:
        from law_ai.celery import app

        schedule = app.conf.beat_schedule
        assert "autonomy-content-sweep" in schedule
        # The nightly test-synthesis entry was retired on 2026-10-26 (ADR 0008).
        assert "autonomy-nightly-tests" not in schedule
        assert "autonomy-daily-digest" in schedule

    def test_beat_tasks_point_at_autonomy_cycle(self) -> None:
        from law_ai.celery import app

        # BL-20260511-23: the digest entry runs the retrying variant; every
        # other autonomy entry still funnels through the generic cycle task.
        allowed = {
            "law_ai.core.tasks.autonomy_cycle",
            "law_ai.core.tasks.compose_digest_task",
        }
        for key, entry in app.conf.beat_schedule.items():
            if key in NON_AUTONOMY_BEATS:
                assert (
                    entry["task"] == NON_AUTONOMY_BEATS[key]
                ), f"Beat entry {key!r} points at wrong task"
                continue
            assert entry["task"] in allowed, f"Beat entry {key!r} points at wrong task"
        assert (
            app.conf.beat_schedule["autonomy-daily-digest"]["task"]
            == "law_ai.core.tasks.compose_digest_task"
        )


class TestSharedDispatchTable:
    """One ``{kind: runner}`` table, two entry points (BL-20260906-26).

    The CLI and the Celery task each carried their own if-chain, and they
    drifted: ``lsat_cross_check`` was dispatchable from ``manage.py
    run_autonomy`` while the beat entry pointing at ``autonomy_cycle`` raised
    ``Unknown kind``. These pin the table as the single definition.
    """

    def test_every_argparse_choice_has_a_runner(self) -> None:
        from law_ai.core.management.commands.run_autonomy import (
            AUTONOMY_RUNNERS,
            Command,
        )

        parser = Command().create_parser("manage.py", "run_autonomy")
        choices = next(a.choices for a in parser._actions if a.dest == "kind")
        assert set(choices) == set(AUTONOMY_RUNNERS)

    def test_every_beat_kind_has_a_runner(self) -> None:
        from law_ai.celery import app
        from law_ai.core.management.commands.run_autonomy import AUTONOMY_RUNNERS

        for key, entry in app.conf.beat_schedule.items():
            if key in NON_AUTONOMY_BEATS:
                continue
            kind = entry.get("kwargs", {}).get("kind")
            assert kind in AUTONOMY_RUNNERS, (
                f"beat entry {key!r} dispatches kind {kind!r}, which "
                "law_ai.core.tasks.autonomy_cycle cannot run"
            )

    def test_the_celery_task_dispatches_every_registered_kind(
        self, _autonomy_enabled: None, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The regression: the task used to raise for kinds the CLI knew."""
        from law_ai.core import autonomy
        from law_ai.core.management.commands.run_autonomy import AUTONOMY_RUNNERS
        from law_ai.core.tasks import autonomy_cycle

        seen: list[str] = []

        def fake_run_cycle(kind, runner, payload=None, **kw):  # type: ignore[no-untyped-def]
            seen.append(kind)
            # Prove the runner is callable and bound to the right sub-runner,
            # without executing a real pillar.
            assert callable(runner)
            return {"status": "ok", "kind": kind, "result": {}}

        monkeypatch.setattr(autonomy, "run_cycle", fake_run_cycle)
        for kind in AUTONOMY_RUNNERS:
            result = autonomy_cycle(kind=kind, source="courtlistener", budget=1)
            assert result["status"] == "ok"
        assert seen == list(AUTONOMY_RUNNERS)

    def test_an_unknown_kind_still_raises(self) -> None:
        from law_ai.core.management.commands.run_autonomy import build_runner

        with pytest.raises(ValueError, match="Unknown kind"):
            build_runner("not_a_pillar")

    def test_each_runner_is_handed_only_the_arguments_it_declares(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """`source` goes to corpus_growth, `window_to_now` to digest, nothing else."""
        import inspect

        import law_ai.core.management.commands.run_autonomy as cmd

        calls: dict[str, dict[str, Any]] = {}
        table = dict(cmd.AUTONOMY_RUNNERS)

        for name, real in list(table.items()):

            def _probe(context: dict[str, Any], _name: str = name, **kw: Any) -> dict:  # type: ignore[type-arg]
                calls[_name] = kw
                return {}

            # Keep the real signature: build_runner reads it to decide what
            # each sub-runner may be handed.
            _probe.__signature__ = inspect.signature(real)  # type: ignore[attr-defined]
            table[name] = _probe

        monkeypatch.setattr(cmd, "AUTONOMY_RUNNERS", table)
        for name in table:
            cmd.build_runner(
                name, source="courtlistener", budget=3, window_to_now=True
            )({})

        assert calls["corpus_growth"] == {"source": "courtlistener", "budget": 3}
        assert calls["digest"] == {"window_to_now": True}
        assert calls["commit_approved"] == {"budget": 3}


class TestLsatCrossCheckCycle:
    """The scheduled bank cross-check sweep (BL-20260905-58)."""

    def test_beat_entry_exists_and_is_budget_capped(self) -> None:
        from law_ai.celery import app

        entry = app.conf.beat_schedule["autonomy-lsat-cross-check"]
        assert entry["kwargs"]["kind"] == "lsat_cross_check"
        # Every question is a real provider call, so the cadence is weekly and
        # the budget small: an unattended sweep must cost a bounded amount.
        assert entry["kwargs"]["budget"] == 5
        assert entry["options"]["queue"] == "autonomy"

    def test_kind_is_dispatchable_from_the_command(self) -> None:
        out = StringIO()
        call_command(
            "run_autonomy", "--kind", "lsat_cross_check", "--dry-run", stdout=out
        )
        assert '"kind": "lsat_cross_check"' in out.getvalue()

    @staticmethod
    def _stub_cross_check(monkeypatch: pytest.MonkeyPatch, verdicts: dict) -> list[str]:  # type: ignore[type-arg]
        """Answer each question from *verdicts* without touching a provider."""
        from law_ai.core.management.commands import run_autonomy as cmd
        from law_ai.lsat.management.commands import lsat_cross_check_sweep as sweep
        from law_ai.lsat.services import crosscheck as cc

        asked: list[str] = []

        async def _stub(question, *, refresh: bool = False):  # type: ignore[no-untyped-def]
            asked.append(question.id)
            spec = verdicts.get(question.id, {})
            agree = spec.get("agree", True)
            # A disagreement has to name a *different* label, or the row a
            # reviewer opens would contradict itself.
            other = next(c for c in "ABCDE" if c != question.correct)
            return cc.CrossCheckResult(
                question_id=question.id,
                bank_choice=question.correct,
                model_choice=spec.get(
                    "model_choice", question.correct if agree else other
                ),
                agree=agree,
                rationale="stub",
                model="test/model",
                used_llm=spec.get("used_llm", True),
            )

        monkeypatch.setattr(cc, "cross_check", _stub)
        # The sweep command bound `cross_check` at import time, and the runner
        # imports that module lazily. Importing it here — inside the patched
        # window but named explicitly — would otherwise freeze this stub into
        # the command for the rest of the session, which is how a later test
        # of the sweep ends up solving every question with it.
        monkeypatch.setattr(sweep, "cross_check", _stub)
        assert cmd.CROSS_CHECK_MAX_PER_CYCLE >= 1
        return asked

    def test_runner_queues_only_disagreements(
        self, tmp_path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from django.conf import settings as dj

        from law_ai.core.management.commands.run_autonomy import _run_lsat_cross_check
        from law_ai.lsat.services import proposals as proposals_store
        from law_ai.lsat.services.bank import load_bank

        monkeypatch.setattr(dj, "AUDIT_PATH", str(tmp_path / "audit.jsonl"))
        monkeypatch.setattr(
            dj, "LSAT_PROPOSALS_DIR", str(tmp_path / "proposals"), raising=False
        )
        ids = sorted(load_bank())[:2]
        assert len(ids) == 2, "the bank must ship at least two questions"
        # First agrees, second disagrees: only the second is a reviewer's problem.
        asked = self._stub_cross_check(monkeypatch, {ids[1]: {"agree": False}})

        summary = _run_lsat_cross_check({}, budget=2)

        assert asked == ids
        assert summary["solved"] == 2
        assert summary["agreed"] == 1
        assert summary["filed"] == 1
        pending = proposals_store.list_proposals("pending")
        assert [p["proposal_kind"] for p in pending] == ["crosscheck"]
        assert pending[0]["draft"]["question_id"] == ids[1]

    def test_degraded_verdicts_are_never_filed(
        self, tmp_path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """An outage is not a disagreement."""
        from django.conf import settings as dj

        from law_ai.core.management.commands.run_autonomy import _run_lsat_cross_check
        from law_ai.lsat.services import proposals as proposals_store
        from law_ai.lsat.services.bank import load_bank

        monkeypatch.setattr(dj, "AUDIT_PATH", str(tmp_path / "audit.jsonl"))
        monkeypatch.setattr(
            dj, "LSAT_PROPOSALS_DIR", str(tmp_path / "proposals"), raising=False
        )
        qid = sorted(load_bank())[0]
        self._stub_cross_check(
            monkeypatch,
            {qid: {"agree": None, "model_choice": None, "used_llm": False}},
        )

        summary = _run_lsat_cross_check({}, budget=1)

        assert summary["degraded"] == 1 and summary["filed"] == 0
        assert proposals_store.list_proposals("pending") == []

    def test_budget_is_hard_capped(
        self, tmp_path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A beat that asks for a thousand solves still buys at most the cap."""
        from django.conf import settings as dj

        from law_ai.core.management.commands import run_autonomy as cmd

        monkeypatch.setattr(dj, "AUDIT_PATH", str(tmp_path / "audit.jsonl"))
        monkeypatch.setattr(
            dj, "LSAT_PROPOSALS_DIR", str(tmp_path / "proposals"), raising=False
        )
        asked = self._stub_cross_check(monkeypatch, {})

        summary = cmd._run_lsat_cross_check({}, budget=10_000)

        assert summary["limit"] == cmd.CROSS_CHECK_MAX_PER_CYCLE
        assert len(asked) <= cmd.CROSS_CHECK_MAX_PER_CYCLE


class TestLsatLibraryCycle:
    """The scheduled knowledge-library review pass (spec 048 FR-17, AC-10)."""

    def test_beat_entry_exists_and_reviews_only(self) -> None:
        from law_ai.celery import app

        entry = app.conf.beat_schedule["autonomy-lsat-library"]
        assert entry["kwargs"]["kind"] == "lsat_library"
        # Budget-capped: each review is a full-article model call.
        assert entry["kwargs"]["budget"] == 3
        assert entry["options"]["queue"] == "autonomy"

    def test_kind_is_dispatchable_from_the_command(self) -> None:
        out = StringIO()
        call_command("run_autonomy", "--kind", "lsat_library", "--dry-run", stdout=out)
        assert '"kind": "lsat_library"' in out.getvalue()

    def test_runner_files_proposals_and_writes_no_content(
        self, tmp_path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import json

        from django.conf import settings as dj

        from law_ai.core.management.commands.run_autonomy import _run_lsat_library
        from law_ai.core import llm
        from law_ai.lsat.services import library as lib
        from law_ai.lsat.services import proposals as proposals_store

        monkeypatch.setattr(dj, "AUDIT_PATH", str(tmp_path / "audit.jsonl"))
        monkeypatch.setattr(
            dj, "LSAT_PROPOSALS_DIR", str(tmp_path / "proposals"), raising=False
        )

        class _Result:
            text = json.dumps({"summary": "Looks sound.", "findings": []})
            model_label = "test/model"

        async def _agenerate(prompt, *, system=None, agent=None):
            return _Result()

        monkeypatch.setattr(llm, "agenerate", _agenerate)

        before = {
            p.name: p.read_text(encoding="utf-8")
            for p in sorted(lib._library_dir().glob("*.md"))
        }
        summary = _run_lsat_library({}, budget=1)
        after = {
            p.name: p.read_text(encoding="utf-8")
            for p in sorted(lib._library_dir().glob("*.md"))
        }

        assert before == after, "the scheduled cycle must not edit content"
        assert summary["reviews_filed"] == 1
        assert summary["degraded"] is False
        pending = proposals_store.list_proposals("pending")
        assert [p["proposal_kind"] for p in pending] == ["library_finding"]

    def test_degraded_runs_file_nothing(
        self, tmp_path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from django.conf import settings as dj

        from law_ai.core.management.commands.run_autonomy import _run_lsat_library
        from law_ai.core import llm
        from law_ai.lsat.services import proposals as proposals_store

        monkeypatch.setattr(dj, "AUDIT_PATH", str(tmp_path / "audit.jsonl"))
        monkeypatch.setattr(
            dj, "LSAT_PROPOSALS_DIR", str(tmp_path / "proposals"), raising=False
        )

        async def _agenerate(prompt, *, system=None, agent=None):
            raise llm.LLMUnavailableError("no provider")

        monkeypatch.setattr(llm, "agenerate", _agenerate)

        summary = _run_lsat_library({}, budget=1)
        assert summary["degraded"] is True
        assert summary["reviews_filed"] == 0
        # An offline fallback carries no review; filing it is only noise.
        assert proposals_store.list_proposals("pending") == []


class TestLsatContentCycle:
    """BL-20260606-02: the autonomy beat checks its batch for A-E spread."""

    def test_skewed_batch_carries_the_flag_into_the_queue(
        self, tmp_path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import json

        from django.conf import settings as dj

        from law_ai.core import llm
        from law_ai.core.management.commands.run_autonomy import _run_lsat_content
        from law_ai.lsat.services import proposals as proposals_store

        monkeypatch.setattr(dj, "AUDIT_PATH", str(tmp_path / "audit.jsonl"))
        monkeypatch.setattr(
            dj, "LSAT_PROPOSALS_DIR", str(tmp_path / "proposals"), raising=False
        )

        drafts = [
            {
                "section": "LR",
                "difficulty": "med",
                "stem": f"Autonomy stem #{i}.",
                "choices": [{"label": label, "text": label} for label in "ABCDE"],
                "correct": "B",
                "explanation": "Because B.",
                "concepts": [],
                "confidence": 0.7,
            }
            for i in range(3)
        ]

        class _Result:
            text = json.dumps({"drafts": drafts})
            model_label = "test/model"
            model = "test/model"
            provider = "test"

        async def _agenerate(prompt, **kwargs):
            return _Result()

        monkeypatch.setattr(llm, "agenerate", _agenerate)

        summary = _run_lsat_content({}, budget=3)
        assert summary["drafts_persisted"] == 3, "flagged, not rejected"
        assert summary["balance_flag"] and "'B'" in summary["balance_flag"]
        pending = proposals_store.list_proposals("pending")
        assert len(pending) == 3
        for row in pending:
            assert row["meta"]["balance_flag"] == summary["balance_flag"]


class TestLsatFactoryCycle:
    """BL-20260702-04: the nightly coverage-driven factory batch."""

    def test_beat_entry_is_local_only_and_budget_capped(self) -> None:
        from law_ai.celery import app

        entry = app.conf.beat_schedule["autonomy-lsat-factory"]
        assert entry["kwargs"]["kind"] == "lsat_factory"
        # Small cap: a nightly local run must finish on modest hardware.
        assert entry["kwargs"]["budget"] == 4
        assert entry["options"]["queue"] == "autonomy"
        assert entry["schedule"].hour == {3}

    def test_kind_is_dispatchable_from_the_command(self) -> None:
        out = StringIO()
        call_command("run_autonomy", "--kind", "lsat_factory", "--dry-run", stdout=out)
        assert '"kind": "lsat_factory"' in out.getvalue()

    def test_celery_dispatcher_knows_the_kind(self) -> None:
        from law_ai.core.management.commands.run_autonomy import _run_lsat_factory

        assert callable(_run_lsat_factory)

    @staticmethod
    def _stub_executor(monkeypatch: pytest.MonkeyPatch, calls: list[str]) -> None:
        """Replace the Ollama executor with an offline stand-in."""
        from law_ai.lsat.factory import executors as exec_mod

        class _StubOllama:
            name = "ollama"

            def __init__(self, config: object) -> None:
                self._config = config

            async def execute(self, job: object) -> object:
                calls.append(job.job_id)  # type: ignore[attr-defined]
                target = job.target  # type: ignore[attr-defined]
                return exec_mod.RawBatch(
                    job_id=job.job_id,  # type: ignore[attr-defined]
                    payload={
                        "drafts": [
                            {
                                "section": target.section,
                                "difficulty": target.difficulty,
                                "stem": "Nightly factory stem for "
                                f"{job.job_id}: a survey showed X, so Y. "  # type: ignore[attr-defined]
                                "Which one of the following most weakens it?",
                                "choices": [
                                    {"label": label, "text": f"choice {label}"}
                                    for label in "ABCDE"
                                ],
                                "correct": "C",
                                "explanation": "C breaks the link; others do not.",
                                "concepts": [],
                                "confidence": 0.6,
                            }
                        ]
                    },
                    model_label="ollama/mistral",
                )

        monkeypatch.setattr(exec_mod, "OllamaExecutor", _StubOllama)

    def test_runner_queues_pending_proposals_from_the_local_executor(
        self, tmp_path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from django.conf import settings as dj

        from law_ai.core.management.commands.run_autonomy import _run_lsat_factory
        from law_ai.lsat.services import proposals as proposals_store

        monkeypatch.setattr(dj, "AUDIT_PATH", str(tmp_path / "audit.jsonl"))
        monkeypatch.setattr(
            dj, "LSAT_PROPOSALS_DIR", str(tmp_path / "proposals"), raising=False
        )
        monkeypatch.setattr(
            dj, "LSAT_FACTORY_DIR", str(tmp_path / "factory"), raising=False
        )
        calls: list[str] = []
        self._stub_executor(monkeypatch, calls)

        summary = _run_lsat_factory({}, budget=2)

        # Budget caps the manifest, so the beat never runs the whole plan.
        assert summary["jobs"] <= 2 and calls
        assert summary["executor"] == "ollama"
        assert summary["accepted"] >= 1
        pending = proposals_store.list_proposals("pending")
        assert len(pending) == summary["accepted"]
        for row in pending:
            # Drafts only: a nightly cycle never promotes (constitution §5).
            assert row["status"] == "pending"
            assert row["meta"]["factory"]["executor"] == "ollama"

    def _judge_spy(self, monkeypatch: pytest.MonkeyPatch) -> list[bool]:
        """Record whether the pipeline asked for a judge pass, and call none."""
        from law_ai.lsat.factory import pipeline as pipeline_mod

        seen: list[bool] = []

        async def _stub(result, *, config, tier_model_hint=None):  # type: ignore[no-untyped-def]
            seen.append(bool(config.judge_enabled))
            return result

        monkeypatch.setattr(pipeline_mod, "judge_result", _stub)
        return seen

    def _factory_paths(self, tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
        from django.conf import settings as dj

        monkeypatch.setattr(dj, "AUDIT_PATH", str(tmp_path / "audit.jsonl"))
        monkeypatch.setattr(
            dj, "LSAT_PROPOSALS_DIR", str(tmp_path / "proposals"), raising=False
        )
        monkeypatch.setattr(
            dj, "LSAT_FACTORY_DIR", str(tmp_path / "factory"), raising=False
        )

    def test_judge_runs_when_the_chain_is_local_only(
        self, tmp_path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """BL-20260905-49: nightly drafts reach the queue judged, for free.

        Pinning the chain to Ollama makes the second model call per draft cost
        nothing, which is the only condition under which a beat may make it.
        """
        from django.conf import settings as dj

        from law_ai.core.management.commands.run_autonomy import _run_lsat_factory

        self._factory_paths(tmp_path, monkeypatch)
        monkeypatch.setattr(dj, "LLM_PROVIDER_CHAIN", "ollama")
        monkeypatch.setattr(dj, "LSAT_FACTORY_JUDGE", False, raising=False)
        seen = self._judge_spy(monkeypatch)
        self._stub_executor(monkeypatch, [])

        summary = _run_lsat_factory({}, budget=1)

        assert summary["judge_enabled"] is True
        assert seen and all(seen)

    def test_judge_stays_off_on_a_chain_that_would_bill(
        self, tmp_path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The default chain leads with a hosted tier; a beat never opts in."""
        from django.conf import settings as dj

        from law_ai.core.management.commands.run_autonomy import _run_lsat_factory

        self._factory_paths(tmp_path, monkeypatch)
        monkeypatch.setattr(dj, "LLM_PROVIDER_CHAIN", "claude_code,ollama")
        monkeypatch.setattr(dj, "LSAT_FACTORY_JUDGE", False, raising=False)
        seen = self._judge_spy(monkeypatch)
        self._stub_executor(monkeypatch, [])

        summary = _run_lsat_factory({}, budget=1)

        assert summary["judge_enabled"] is False
        assert seen and not any(seen)

    def test_kill_switch_stops_the_cycle_before_any_generation(
        self, tmp_path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from django.conf import settings as dj

        monkeypatch.setattr(dj, "AUDIT_PATH", str(tmp_path / "audit.jsonl"))
        monkeypatch.setattr(
            dj, "LSAT_FACTORY_DIR", str(tmp_path / "factory"), raising=False
        )
        monkeypatch.setattr(dj, "AUTONOMY_ENABLED", False)
        calls: list[str] = []
        self._stub_executor(monkeypatch, calls)

        out = StringIO()
        call_command("run_autonomy", "--kind", "lsat_factory", stdout=out)
        assert calls == []


@pytest.mark.integration
@pytest.mark.django_db
class TestBeatScheduleSmoke:
    """BL-20260511-11: drive every beat entry through Celery, not just the dict.

    ``TestCeleryAutonomyTask`` deliberately stays *unmarked* so it keeps running
    in ``make test-backend``; marking it ``integration`` would have moved it out
    of that suite, which is the opposite of what the backlog item wants. The
    "full beat-schedule smoke suite" lives here instead: it needs real Postgres
    and Redis (``make test-integration``) because a cycle writes an
    ``AuditEvent`` row on the way through, so it is marked ``integration``.

    The kill-switch stays *off* for the whole class: what is under test is task
    registration, the kwargs shape of each beat entry, and the
    ``AUTONOMY_ENABLED`` short-circuit reaching the caller through Celery's
    execution path — never a live cycle (no LLM calls, no ingestion).
    """

    @staticmethod
    def _disable(monkeypatch: pytest.MonkeyPatch) -> None:
        from django.conf import settings as dj

        monkeypatch.setattr(dj, "AUTONOMY_ENABLED", False)

    def test_every_beat_entry_executes_through_celery(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from law_ai.celery import app

        # Import the way a real worker does, rather than hand-listing modules:
        # a new beat entry then fails here if its task is unreachable, which is
        # exactly the production failure this test exists to catch.
        app.loader.import_default_modules()

        self._disable(monkeypatch)
        assert app.conf.beat_schedule, "beat schedule must not be empty"

        for name, entry in app.conf.beat_schedule.items():
            task = app.tasks.get(entry["task"])
            assert task is not None, f"beat entry {name!r} names an unregistered task"
            if name in NON_AUTONOMY_BEATS:
                continue  # not a cycle: no kill-switch, no cycle payload
            result = task.apply(kwargs=dict(entry.get("kwargs") or {}))
            payload = result.get()
            assert (
                payload["status"] == "disabled"
            ), f"beat entry {name!r} ran despite the kill-switch"
            assert payload["cycle_type"] == entry["kwargs"]["kind"]
            assert payload["cycle_id"]

    def test_every_beat_kind_is_dispatchable(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Each scheduled ``kind`` is one the CLI and the runner both know."""
        from law_ai.celery import app
        from law_ai.core.management.commands.run_autonomy import Command

        self._disable(monkeypatch)
        parser = Command().create_parser("manage.py", "run_autonomy")
        choices: list[str] = next(
            list(action.choices or [])
            for action in parser._actions
            if action.dest == "kind"
        )

        for name, entry in _autonomy_beats(app.conf.beat_schedule).items():
            kind = entry["kwargs"]["kind"]
            assert kind in choices, f"{name!r} schedules unknown kind {kind!r}"
            out = StringIO()
            call_command("run_autonomy", "--kind", kind, stdout=out)
            assert "disabled" in out.getvalue().lower()

    def test_audit_row_lands_for_each_disabled_cycle(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The kill-switch is audited, not silent (constitution §12 I3)."""
        from law_ai.audit.models import AuditEvent
        from law_ai.celery import app

        app.loader.import_default_modules()
        self._disable(monkeypatch)
        before = AuditEvent.objects.filter(kind="autonomy_disabled").count()

        entries = list(_autonomy_beats(app.conf.beat_schedule).values())
        for entry in entries:
            app.tasks[entry["task"]].apply(kwargs=dict(entry.get("kwargs") or {}))

        after = AuditEvent.objects.filter(kind="autonomy_disabled").count()
        assert after - before == len(entries)


class TestCycleIdIdempotency:
    """BL-20260511-29: ``--cycle-id`` replays a completed run, never re-runs it."""

    @pytest.mark.usefixtures("_autonomy_enabled")
    def test_cycle_id_reaches_run_cycle_in_the_payload(self) -> None:
        fake_result = {"status": "ok", "cycle_id": "cid-9", "result": {}}
        with patch(
            "law_ai.core.autonomy.run_cycle", return_value=fake_result
        ) as mock_run:
            call_command(
                "run_autonomy",
                "--kind",
                "digest",
                "--cycle-id",
                "cid-9",
                stdout=StringIO(),
            )

        assert mock_run.call_args.kwargs["payload"]["cycle_id"] == "cid-9"

    @pytest.mark.usefixtures("_autonomy_enabled")
    def test_replay_is_reported_as_such_on_stdout(self) -> None:
        """An operator reusing a key must not read 'complete' and assume it ran."""
        out = StringIO()
        fake_result = {
            "status": "ok",
            "cycle_id": "cid-9",
            "result": {"digest_path": "/app/var/autonomy/digest-2026-05-11.md"},
            "replayed": True,
        }
        with patch("law_ai.core.autonomy.run_cycle", return_value=fake_result):
            call_command(
                "run_autonomy", "--kind", "digest", "--cycle-id", "cid-9", stdout=out
            )

        body = out.getvalue()
        assert "replayed" in body.lower()
        assert "cid-9" in body

    @pytest.mark.usefixtures("_autonomy_enabled")
    def test_the_second_run_of_a_key_does_not_touch_the_runner(
        self, tmp_path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from django.conf import settings as dj

        monkeypatch.setattr(dj, "AUDIT_PATH", str(tmp_path / "audit.jsonl"))
        monkeypatch.setattr(dj, "AUTONOMY_DIGEST_DIR", str(tmp_path))
        monkeypatch.setattr(dj, "AUTONOMY_DIGEST_SLACK_WEBHOOK_URL", "")
        monkeypatch.setattr(dj, "AUTONOMY_DIGEST_EMAIL_TO", [])
        composed: list[int] = []

        from law_ai.core import autonomy

        real_compose = autonomy.compose_digest

        def _counting(**kwargs: object) -> object:
            composed.append(1)
            return real_compose(**kwargs)  # type: ignore[arg-type]

        monkeypatch.setattr(autonomy, "compose_digest", _counting)

        for _ in range(2):
            call_command(
                "run_autonomy",
                "--kind",
                "digest",
                "--cycle-id",
                "cid-cli-1",
                stdout=StringIO(),
            )

        assert composed == [1], "the second invocation must replay, not recompose"
