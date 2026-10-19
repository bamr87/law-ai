"""Executor tests (spec 024 T-005: FR-6, NFR-SEC-1, AC-5)."""

from __future__ import annotations

import json
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

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
    OllamaExecutor,
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
        model_hint="claude-sonnet-5-5",
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

    def test_api_key_path_pins_the_anthropic_api_provider(self, settings) -> None:
        settings.CLAUDE_CODE_OAUTH_TOKEN = ""
        settings.ANTHROPIC_API_KEY = "sk-ant-api03-test"
        assert ClaudeCodeExecutor(FactoryConfig())._provider == llm.ANTHROPIC_API

    @pytest.mark.asyncio
    async def test_tier_routes_model_id_through_a_pinned_chain(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """BL-20260905-13: the same pin as the xAI executor, plus provenance."""
        monkeypatch.setattr(claude_code, "oauth_token", lambda: "tok")
        captured: dict[str, Any] = {}

        async def fake_aroute(request, *, agent=None):
            captured["providers"] = request.providers
            captured["models"] = request.models
            captured["schema"] = request.response_schema
            captured["agent"] = agent
            return SimpleNamespace(
                text=json.dumps({"drafts": [_DRAFT]}),
                model_label="claude_code/claude-sonnet-5-5",
                provider="claude_code",
            )

        monkeypatch.setattr(llm, "aroute", fake_aroute)
        batch = await ClaudeCodeExecutor(FactoryConfig()).execute(_job())

        # One provider only: a fall-through would make the bank unattributable.
        assert captured["providers"] == ("claude_code",)
        assert captured["models"] == {"claude_code": "claude-sonnet-5-5"}
        # Items mode pins the response with the structured-output schema.
        assert captured["schema"] is not None
        assert captured["agent"] == "lsat_factory"
        assert batch.model_label == "claude_code/claude-sonnet-5-5"
        assert batch.payload["drafts"][0]["correct"] == "B"

    @pytest.mark.asyncio
    async def test_passage_mode_skips_schema(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(claude_code, "oauth_token", lambda: "tok")
        captured: dict[str, Any] = {}

        async def fake_aroute(request, *, agent=None):
            captured["schema"] = request.response_schema
            return SimpleNamespace(
                text=json.dumps({"drafts": [_DRAFT], "passage": {"title": "x"}}),
                model_label="claude_code/claude-sonnet-5-5",
                provider="claude_code",
            )

        monkeypatch.setattr(llm, "aroute", fake_aroute)
        batch = await ClaudeCodeExecutor(FactoryConfig()).execute(
            _job(mode="passage_set")
        )
        assert captured["schema"] is None
        assert "passage" in batch.payload

    @pytest.mark.asyncio
    async def test_chain_failure_becomes_an_execution_error(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(claude_code, "oauth_token", lambda: "tok")

        async def boom(request, *, agent=None):
            raise LLMUnavailableError("claude is down")

        monkeypatch.setattr(llm, "aroute", boom)
        with pytest.raises(ExecutionError, match="Claude unavailable"):
            await ClaudeCodeExecutor(FactoryConfig()).execute(_job())

    @pytest.mark.asyncio
    async def test_batch_writes_an_llm_call_provenance_event(
        self, settings, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The whole point of the port: the batch is in the audit trail.

        Nothing patches the router here — the real chain runs, pinned to the
        Claude tier, with only the transport stubbed.
        """
        from law_ai.core.llm import providers as provider_mod

        settings.CLAUDE_CODE_OAUTH_TOKEN = "tok"

        async def fake_generate(self: Any, request: Any) -> str:
            return json.dumps({"drafts": [_DRAFT]})

        monkeypatch.setattr(
            provider_mod.ClaudeOAuthProvider, "agenerate", fake_generate
        )

        with patch("law_ai.core.provenance.ProvenanceLogger.log_event") as log:
            batch = await ClaudeCodeExecutor(FactoryConfig()).execute(_job())

        payloads = [
            call[0][1] for call in log.call_args_list if call[0][0] == "llm_call"
        ]
        assert payloads, "the Claude executor wrote no llm_call event"
        assert payloads[-1]["provider"] == "claude_code"
        assert payloads[-1]["agent"] == "lsat_factory"
        assert payloads[-1]["ok"] is True
        assert batch.model_label.startswith("claude_code/")


class TestXaiExecutor:
    """Spec 050: the factory can generate on the xAI tier.

    Same shape as every other model-backed executor since BL-20260905-13:
    ``law_ai.core.llm`` with the chain pinned to a single provider, which
    keeps the run attributable while staying inside the constitution §4 choke
    point.
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

        async def fake_aroute(request, *, agent=None):
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

        async def boom(request, *, agent=None):
            raise LLMUnavailableError("xai is down")

        monkeypatch.setattr(llm, "aroute", boom)
        with pytest.raises(ExecutionError, match="xAI unavailable"):
            await XaiExecutor(FactoryConfig()).execute(_job())


class TestOllamaExecutor:
    """BL-20260810-05: the local executor rides the chain, pinned to Ollama.

    Before this it hand-rolled its own ``httpx`` post to ``/api/generate`` and
    wrote no ``llm_call`` provenance. Now it is the same shape as the xAI
    executor: one provider, no fall-through, transport/retry/timeout owned by
    ``OllamaProvider``.
    """

    @pytest.mark.asyncio
    async def test_pins_the_chain_to_ollama_only(
        self, settings, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        settings.OLLAMA_DEFAULT_MODEL = "mistral:7b-instruct-q4_K_M"
        captured: dict[str, Any] = {}

        async def fake_aroute(request, *, agent=None):
            captured["providers"] = request.providers
            captured["models"] = dict(request.models)
            captured["json_mode"] = request.json_mode
            captured["temperature"] = request.temperature
            captured["agent"] = agent
            return SimpleNamespace(
                text=json.dumps({"drafts": [_DRAFT]}),
                model_label="ollama/mistral:7b-instruct-q4_K_M",
                provider="ollama",
            )

        monkeypatch.setattr(llm, "aroute", fake_aroute)
        batch = await OllamaExecutor(FactoryConfig()).execute(_job())

        assert captured["providers"] == ("ollama",)
        assert captured["models"] == {"ollama": "mistral:7b-instruct-q4_K_M"}
        assert captured["json_mode"] is True
        assert captured["temperature"] == pytest.approx(0.4)
        assert captured["agent"] == "lsat_factory"
        assert batch.model_label == "ollama/mistral:7b-instruct-q4_K_M"
        assert batch.payload["drafts"][0]["correct"] == "B"

    @pytest.mark.asyncio
    async def test_chain_failure_becomes_an_execution_error(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        async def boom(request, *, agent=None):
            raise LLMUnavailableError("ollama: ConnectError: refused")

        monkeypatch.setattr(llm, "aroute", boom)
        with pytest.raises(ExecutionError, match="Ollama error"):
            await OllamaExecutor(FactoryConfig()).execute(_job())

    @pytest.mark.asyncio
    async def test_writes_llm_call_provenance(
        self, settings, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Constitution §4: a factory batch is an LLM call and is audited as one."""
        settings.OLLAMA_BASE_URL = "http://ollama.test:11434"

        class _Ollama:
            name = "ollama"

            def configured(self) -> bool:
                return True

            def unconfigured_reason(self) -> str | None:
                return None

            def model_for(self, request) -> str:
                return "mistral:7b-instruct-q4_K_M"

            async def agenerate(self, request) -> str:
                return json.dumps({"drafts": [_DRAFT]})

            async def probe(self) -> dict[str, Any]:
                return {"reachable": True}

        monkeypatch.setattr(
            "law_ai.core.llm.router.build_chain", lambda override=None: (_Ollama(),)
        )
        with patch("law_ai.core.provenance.ProvenanceLogger.log_event") as log:
            batch = await OllamaExecutor(FactoryConfig()).execute(_job())

        assert batch.model_label == "ollama/mistral:7b-instruct-q4_K_M"
        log.assert_called_once()
        event_type, payload = log.call_args[0]
        assert event_type == "llm_call"
        assert payload["agent"] == "lsat_factory"
        assert payload["provider"] == "ollama"
        assert payload["ok"] is True


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
            "model": "claude_code/claude-haiku-5-5",
        }
        path.write_text(json.dumps(record) + "\n", encoding="utf-8")
        executor = DraftFileExecutor(path)
        assert executor.fulfilled_job_ids() == {"mfst-x-job01"}
        batch = await executor.execute(_job())
        assert batch.model_label == "claude_code/claude-haiku-5-5"
        assert batch.payload["passage"] == {"title": "new game"}
        with pytest.raises(ExecutionError, match="no record"):
            await executor.execute(_job(job_id="mfst-x-job99"))
