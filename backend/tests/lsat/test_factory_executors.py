"""Executor tests (spec 024 T-005: FR-6, NFR-SEC-1, AC-5)."""

from __future__ import annotations

import json
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest

from law_ai.core import claude_code, llm, xai_oauth
from law_ai.core.llm.base import LLMUnavailableError
from law_ai.lsat.factory.config import FactoryConfig
from law_ai.lsat.factory.coverage import GenerationTarget
from law_ai.lsat.factory.executors import (
    ClaudeCodeExecutor,
    DraftFileExecutor,
    ExecutionError,
    ExecutorUnavailable,
    XaiExecutor,
    _parse_payload,
)
from law_ai.lsat.factory.manifest import GenerationJob


def _job(job_id: str = "mfst-x-job01", mode: str = "items") -> GenerationJob:
    return GenerationJob(
        job_id=job_id,
        target=GenerationTarget(
            section="LR",
            archetype_id="lr-weaken",
            difficulty="med",
            count=1,
            concepts=["weaken"],
            mode=mode,  # type: ignore[arg-type]
            passage_id=None,
            tier="standard",
            priority=1.0,
            rationale="test",
        ),
        tier="standard",
        model_hint="claude-sonnet-5",
        template_version="lsat_factory_item/1",
        prompt="PROMPT",
    )


_DRAFT: dict[str, Any] = {
    "section": "LR",
    "difficulty": "med",
    "stem": "A stem.",
    "choices": [
        {"label": label, "text": f"choice {label}"}
        for label in ("A", "B", "C", "D", "E")
    ],
    "correct": "B",
    "explanation": "Because.",
    "concepts": ["weaken"],
    "confidence": 0.8,
}


class TestParsePayload:
    def test_rejects_non_json(self) -> None:
        with pytest.raises(ExecutionError, match="not JSON"):
            _parse_payload("no json here", "j1")

    def test_rejects_missing_drafts(self) -> None:
        with pytest.raises(ExecutionError, match="missing 'drafts'"):
            _parse_payload('{"nope": 1}', "j1")

    def test_tolerates_fences(self) -> None:
        raw = '```json\n{"drafts": []}\n```'
        assert _parse_payload(raw, "j1") == {"drafts": []}


class TestClaudeCodeExecutor:
    def test_refuses_without_any_claude_credential(self, settings) -> None:
        settings.CLAUDE_CODE_OAUTH_TOKEN = ""
        settings.ANTHROPIC_API_KEY = ""
        with pytest.raises(ExecutorUnavailable, match="no Claude credential"):
            ClaudeCodeExecutor(FactoryConfig())

    def test_falls_back_to_api_key_when_no_oauth_token(self, settings) -> None:
        settings.CLAUDE_CODE_OAUTH_TOKEN = ""
        settings.ANTHROPIC_API_KEY = "sk-ant-api03-test"
        assert ClaudeCodeExecutor(FactoryConfig())._auth == "api_key"

    @pytest.mark.asyncio
    async def test_tier_routes_model_id(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(claude_code, "oauth_token", lambda: "tok")
        fake = AsyncMock(return_value=json.dumps({"drafts": [_DRAFT]}))
        monkeypatch.setattr(claude_code, "generate", fake)
        executor = ClaudeCodeExecutor(FactoryConfig())
        batch = await executor.execute(_job())
        assert batch.model_label == "claude_code/claude-sonnet-5"
        assert fake.await_args is not None
        assert fake.await_args.kwargs["model_id"] == "claude-sonnet-5"
        # Items mode pins the response with the structured-output schema.
        assert fake.await_args.kwargs["response_schema"] is not None
        assert batch.payload["drafts"][0]["correct"] == "B"

    @pytest.mark.asyncio
    async def test_passage_mode_skips_schema(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(claude_code, "oauth_token", lambda: "tok")
        fake = AsyncMock(
            return_value=json.dumps({"drafts": [_DRAFT], "passage": {"title": "x"}})
        )
        monkeypatch.setattr(claude_code, "generate", fake)
        executor = ClaudeCodeExecutor(FactoryConfig())
        batch = await executor.execute(_job(mode="passage_set"))
        assert fake.await_args is not None
        assert fake.await_args.kwargs["response_schema"] is None
        assert "passage" in batch.payload


class TestXaiExecutor:
    """Spec 050: the factory can generate on the xAI tier.

    The Claude executor calls its transport directly; this one goes through
    ``law_ai.core.llm`` with the chain pinned to a single provider, which keeps
    the run just as attributable while staying inside the constitution §4
    choke point.
    """

    def test_refuses_without_a_credential(self, tmp_path, settings) -> None:
        settings.XAI_CREDENTIALS_PATH = str(tmp_path / "missing.json")
        settings.XAI_ACCESS_TOKEN = ""
        settings.XAI_REFRESH_TOKEN = ""
        with pytest.raises(ExecutorUnavailable, match=r"xai-login|XAI_REFRESH_TOKEN"):
            XaiExecutor(FactoryConfig())

    @pytest.mark.asyncio
    async def test_pins_the_chain_to_xai_only(
        self, tmp_path, settings, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A silent fall-through to Claude would make the bank unattributable."""
        settings.XAI_CREDENTIALS_PATH = str(tmp_path / "creds.json")
        xai_oauth.save_credentials(
            xai_oauth.Credentials(access="a", refresh="r", expires_at=time.time() + 999)
        )
        captured: dict[str, Any] = {}

        async def fake_aroute(request):
            captured["providers"] = request.providers
            captured["schema"] = request.response_schema
            return SimpleNamespace(
                text=json.dumps({"drafts": [_DRAFT]}),
                model_label="xai/grok-4.6",
                provider="xai",
            )

        monkeypatch.setattr(llm, "aroute", fake_aroute)
        batch = await XaiExecutor(FactoryConfig()).execute(_job())

        assert captured["providers"] == ("xai",)
        assert captured["schema"] is not None  # items mode pins the schema
        assert batch.model_label == "xai/grok-4.6"
        assert batch.payload["drafts"][0]["correct"] == "B"

    @pytest.mark.asyncio
    async def test_chain_failure_becomes_an_execution_error(
        self, tmp_path, settings, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """One dead job must not abort the whole manifest run."""
        settings.XAI_CREDENTIALS_PATH = str(tmp_path / "creds.json")
        xai_oauth.save_credentials(
            xai_oauth.Credentials(access="a", refresh="r", expires_at=time.time() + 999)
        )

        async def boom(request):
            raise LLMUnavailableError("xai is down")

        monkeypatch.setattr(llm, "aroute", boom)
        with pytest.raises(ExecutionError, match="xAI unavailable"):
            await XaiExecutor(FactoryConfig()).execute(_job())


class TestDraftFileExecutor:
    def test_missing_file(self, tmp_path: Path) -> None:
        with pytest.raises(ExecutorUnavailable, match="not found"):
            DraftFileExecutor(tmp_path / "nope.jsonl")

    def test_malformed_line(self, tmp_path: Path) -> None:
        path = tmp_path / "drafts.jsonl"
        path.write_text("{broken\n", encoding="utf-8")
        with pytest.raises(ExecutorUnavailable, match="malformed"):
            DraftFileExecutor(path)

    @pytest.mark.asyncio
    async def test_fulfills_known_jobs(self, tmp_path: Path) -> None:
        path = tmp_path / "drafts.jsonl"
        record = {
            "job_id": "mfst-x-job01",
            "drafts": [_DRAFT],
            "passage": {"title": "new game"},
            "model": "claude_code/claude-haiku-4-5-20251001",
        }
        path.write_text(json.dumps(record) + "\n", encoding="utf-8")
        executor = DraftFileExecutor(path)
        assert executor.fulfilled_job_ids() == {"mfst-x-job01"}
        batch = await executor.execute(_job())
        assert batch.model_label == "claude_code/claude-haiku-4-5-20251001"
        assert batch.payload["passage"] == {"title": "new game"}
        with pytest.raises(ExecutionError, match="no record"):
            await executor.execute(_job(job_id="mfst-x-job99"))
