"""Unit tests for the unified Ollama client (spec 024 AC-1..AC-4).

Fakes are injected via the ``async_client_factory`` / ``sync_client_factory``
seams so no network, Ollama daemon, or ``ollama`` import is required.
"""

from __future__ import annotations

from typing import Any

import pytest

from lawgraph.core.llm import (
    LLMClient,
    LLMClientAdapter,
    LLMError,
    LLMResponseError,
    LLMUnavailableError,
    get_llm_client,
    reset_llm_client,
)
from lawgraph.core.llm import client as client_module

# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class _FakeStatusError(Exception):
    """Mimics ``ollama.ResponseError`` (carries ``status_code``)."""

    def __init__(self, message: str, status_code: int) -> None:
        super().__init__(message)
        self.status_code = status_code


class _FakeAsyncOllama:
    """Scripted stand-in for ``ollama.AsyncClient``."""

    def __init__(
        self,
        *,
        responses: list[Any] | None = None,
        chunks: list[str] | None = None,
        embeddings: list[list[float]] | None = None,
    ) -> None:
        self._responses = list(responses or [])
        self._chunks = list(chunks or [])
        self._embeddings = embeddings or [[0.1, 0.2, 0.3]]
        self.generate_calls: list[dict[str, Any]] = []
        self.chat_calls: list[dict[str, Any]] = []

    async def generate(self, **kwargs: Any) -> Any:
        self.generate_calls.append(kwargs)
        if kwargs.get("stream"):
            return self._stream()
        result = self._responses.pop(0)
        if isinstance(result, Exception):
            raise result
        return {"response": result}

    async def _stream(self) -> Any:
        for chunk in self._chunks:
            yield {"response": chunk}

    async def chat(self, **kwargs: Any) -> Any:
        self.chat_calls.append(kwargs)
        result = self._responses.pop(0)
        if isinstance(result, Exception):
            raise result
        return {"message": {"content": result}}

    async def embed(self, **kwargs: Any) -> Any:
        return {"embeddings": self._embeddings}


class _FakeSyncOllama:
    """Scripted stand-in for ``ollama.Client``."""

    def __init__(self, responses: list[Any]) -> None:
        self._responses = list(responses)

    def generate(self, **kwargs: Any) -> Any:
        result = self._responses.pop(0)
        if isinstance(result, Exception):
            raise result
        return {"response": result}


def _client(fake: Any, **kwargs: Any) -> LLMClient:
    return LLMClient(
        host="http://fake:11434",
        model="fake-model",
        timeout_s=1.0,
        max_retries=kwargs.pop("max_retries", 2),
        backoff_base_s=0.001,
        async_client_factory=lambda: fake,
        sync_client_factory=lambda: fake,
        **kwargs,
    )


@pytest.fixture()
def audit_events(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    monkeypatch.setattr(client_module.audit_jsonl, "record", events.append)
    return events


# ---------------------------------------------------------------------------
# generate
# ---------------------------------------------------------------------------


class TestGenerate:
    async def test_returns_text_and_records_audit(
        self, audit_events: list[dict[str, Any]]
    ) -> None:
        fake = _FakeAsyncOllama(responses=["hello"])
        client = _client(fake)
        text = await client.generate("ping", caller="unit-test")
        assert text == "hello"
        assert len(audit_events) == 1
        event = audit_events[0]
        assert event["type"] == "llm_call"
        assert event["endpoint"] == "generate"
        assert event["model"] == "fake-model"
        assert event["caller"] == "unit-test"
        assert event["ok"] is True
        assert event["retries"] == 0
        assert event["prompt_hash"]
        assert event["response_hash"]

    async def test_json_format_and_temperature_forwarded(
        self, audit_events: list[dict[str, Any]]
    ) -> None:
        fake = _FakeAsyncOllama(responses=["{}"])
        client = _client(fake)
        await client.generate("p", temperature=0.4, json_format=True)
        call = fake.generate_calls[0]
        assert call["format"] == "json"
        assert call["options"] == {"temperature": 0.4}

    async def test_retries_transient_then_succeeds(
        self, audit_events: list[dict[str, Any]]
    ) -> None:
        fake = _FakeAsyncOllama(responses=[ConnectionError("refused"), "ok"])
        client = _client(fake)
        text = await client.generate("p")
        assert text == "ok"
        assert audit_events[0]["retries"] == 1

    async def test_does_not_retry_client_errors(
        self, audit_events: list[dict[str, Any]]
    ) -> None:
        fake = _FakeAsyncOllama(
            responses=[_FakeStatusError("no such model", 404), "never"]
        )
        client = _client(fake)
        with pytest.raises(LLMResponseError):
            await client.generate("p")
        # Only one transport attempt was made.
        assert len(fake.generate_calls) == 1
        assert audit_events[0]["ok"] is False

    async def test_raises_unavailable_after_retries_exhausted(
        self, audit_events: list[dict[str, Any]]
    ) -> None:
        fake = _FakeAsyncOllama(
            responses=[ConnectionError("a"), ConnectionError("b"), ConnectionError("c")]
        )
        client = _client(fake, max_retries=2)
        with pytest.raises(LLMUnavailableError):
            await client.generate("p")
        assert len(fake.generate_calls) == 3
        assert audit_events[0]["ok"] is False
        assert "error" in audit_events[0]


# ---------------------------------------------------------------------------
# streaming / chat / embed / sync
# ---------------------------------------------------------------------------


class TestOtherEndpoints:
    async def test_generate_stream_yields_chunks(
        self, audit_events: list[dict[str, Any]]
    ) -> None:
        fake = _FakeAsyncOllama(chunks=["Hel", "lo"])
        client = _client(fake)
        pieces = [c async for c in client.generate_stream("p", caller="stream-test")]
        assert pieces == ["Hel", "lo"]
        event = audit_events[0]
        assert event["endpoint"] == "generate_stream"
        assert event["response_hash"] == "chunks:2"

    async def test_chat_returns_message_content(
        self, audit_events: list[dict[str, Any]]
    ) -> None:
        fake = _FakeAsyncOllama(responses=["hi there"])
        client = _client(fake)
        text = await client.chat([{"role": "user", "content": "hi"}])
        assert text == "hi there"
        assert audit_events[0]["endpoint"] == "chat"

    async def test_embed_returns_vectors(
        self, audit_events: list[dict[str, Any]]
    ) -> None:
        fake = _FakeAsyncOllama(embeddings=[[1.0, 2.0], [3.0, 4.0]])
        client = _client(fake)
        vectors = await client.embed(["a", "b"])
        assert vectors == [[1.0, 2.0], [3.0, 4.0]]
        assert audit_events[0]["endpoint"] == "embed"
        assert audit_events[0]["response_hash"] == "vectors:2"

    def test_generate_sync_with_retry(self, audit_events: list[dict[str, Any]]) -> None:
        fake = _FakeSyncOllama([TimeoutError("slow"), "done"])
        client = _client(fake)
        assert client.generate_sync("p") == "done"
        assert audit_events[0]["retries"] == 1

    def test_generate_sync_raises_llm_error(
        self, audit_events: list[dict[str, Any]]
    ) -> None:
        fake = _FakeSyncOllama([ConnectionError("x")] * 3)
        client = _client(fake, max_retries=1)
        with pytest.raises(LLMError):
            client.generate_sync("p")


# ---------------------------------------------------------------------------
# adapter + module-level instance
# ---------------------------------------------------------------------------


class TestAdapterAndSingleton:
    async def test_adapter_satisfies_ainvoke_protocol(
        self, audit_events: list[dict[str, Any]]
    ) -> None:
        fake = _FakeAsyncOllama(responses=['{"queries": ["q"]}'])
        adapter = LLMClientAdapter(_client(fake), caller="legal_workflow")
        text = await adapter.ainvoke("draft queries")
        assert text == '{"queries": ["q"]}'
        assert audit_events[0]["caller"] == "legal_workflow"

    def test_get_llm_client_returns_shared_instance(self) -> None:
        reset_llm_client()
        try:
            first = get_llm_client()
            assert get_llm_client() is first
        finally:
            reset_llm_client()
