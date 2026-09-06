"""The privileged-data guarantee: `LLM_PROVIDER_CHAIN=ollama` leaves the box alone.

Constitution §1 (as amended 2026-08-11 and 2026-09-04) makes Claude the default
runtime and adds xAI as tier 3, and keeps local-first available by pinning the
chain to Ollama — a pin that is **required** for data under a confidentiality
obligation forbidding third-party processing. Until now nothing proved it: the
suite blanks every hosted credential (``settings/test.py``), so "no outbound
Anthropic call" held vacuously, for want of a key rather than because of the
pin (BL-20260811-24).

These tests deliberately configure *live-looking* Claude and xAI credentials
and then assert that a pinned chain still makes zero outbound requests to
either vendor — across the router, the LangChain adapter, and two real HTTP
surfaces (``POST /api/lsat/tutor`` and ``POST /api/analysis``). Outbound
traffic is intercepted at the httpcore layer by respx; the ASGI client talks to
the app through ``ASGITransport``, which never reaches httpcore, so the app
runs for real while every socket it would open is observed.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import patch

import httpx
import pytest
import pytest_asyncio
import respx
from django.conf import settings as django_settings
from httpx import ASGITransport, AsyncClient

from law_ai.agents_runtime import llm as llm_runtime
from law_ai.asgi import application as asgi_app
from law_ai.core import llm

pytestmark = pytest.mark.unit

_OLLAMA = "http://ollama.test:11434"
_OLLAMA_TAGS = f"{_OLLAMA}/api/tags"
_OLLAMA_GENERATE = f"{_OLLAMA}/api/generate"
_ANTHROPIC = "https://api.anthropic.com/v1/messages"
_XAI = "https://api.x.ai/v1/chat/completions"

#: A schema-shaped IRAC payload so the analyst path parses a real answer
#: instead of degrading before it can prove anything.
_IRAC_JSON = json.dumps(
    {
        "issue": "Whether the contract was breached.",
        "rule": "A material failure to perform is a breach.",
        "application": "The facts describe a failure to perform.",
        "conclusion": "Likely a breach.",
        "confidence": 0.6,
        "sources": [],
    }
)


@pytest.fixture(autouse=True)
def _isolate_audit(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep provenance writes in the test's own directory."""
    monkeypatch.setattr(django_settings, "AUDIT_PATH", str(tmp_path / "audit.jsonl"))


@pytest.fixture
def local_only(settings: Any, tmp_path: Path) -> Any:
    """A chain pinned to Ollama *with* hosted credentials sitting right there.

    The credentials are the point: they make the assertion about the pin, not
    about a missing key.
    """
    settings.LLM_PROVIDER_CHAIN = "ollama"
    settings.CLAUDE_CODE_OAUTH_TOKEN = "sk-ant-oat01-not-a-real-token"
    settings.ANTHROPIC_API_KEY = "sk-ant-api03-not-a-real-key"
    settings.ANTHROPIC_BASE_URL = "https://api.anthropic.com"
    settings.XAI_ACCESS_TOKEN = "xai-not-a-real-token"
    settings.XAI_REFRESH_TOKEN = "xai-not-a-real-refresh"
    settings.XAI_CREDENTIALS_PATH = str(tmp_path / "xai-credentials.json")
    settings.XAI_BASE_URL = "https://api.x.ai/v1"
    settings.OLLAMA_BASE_URL = _OLLAMA
    settings.OLLAMA_DEFAULT_MODEL = "mistral:7b-instruct-q4_K_M"
    settings.OLLAMA_MAX_RETRIES = 1
    # The tutor caches its walkthroughs on disk; a warm cache would answer
    # without calling anything and prove nothing.
    settings.LSAT_RESPONSE_CACHE_DIR = str(tmp_path / "response_cache")
    # The reachability verdict is TTL-cached in-process and shared through the
    # Django cache; a stale "down" would skip the mocked /api/tags entirely.
    llm_runtime.reset_probe_cache()
    llm.reset_permanent_failures()
    yield settings
    llm_runtime.reset_probe_cache()


@pytest_asyncio.fixture
async def api() -> Any:
    async with AsyncClient(
        transport=ASGITransport(app=asgi_app), base_url="http://test"
    ) as client:
        yield client


def _hosted_routes() -> tuple[Any, Any]:
    """Register the vendor endpoints so a leak is *observed*, not just refused."""
    anthropic = respx.post(_ANTHROPIC).mock(
        return_value=httpx.Response(
            200, json={"content": [{"type": "text", "text": "LEAKED"}]}
        )
    )
    xai = respx.post(_XAI).mock(
        return_value=httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "finish_reason": "stop",
                        "message": {"role": "assistant", "content": "LEAKED"},
                    }
                ]
            },
        )
    )
    return anthropic, xai


def _ollama_routes(text: str = "local answer") -> tuple[Any, Any]:
    tags = respx.get(_OLLAMA_TAGS).mock(
        return_value=httpx.Response(200, json={"models": []})
    )
    generate = respx.post(_OLLAMA_GENERATE).mock(
        return_value=httpx.Response(200, json={"response": text, "done": True})
    )
    return tags, generate


class _EventSink:
    """Records provenance events while letting the real logger run."""

    def __init__(self) -> None:
        self.events: list[tuple[str, dict[str, Any]]] = []

    def __call__(self, event_type: str, payload: dict[str, Any]) -> str:
        self.events.append((event_type, payload))
        return "test-trace"

    @property
    def llm_calls(self) -> list[dict[str, Any]]:
        return [p for kind, p in self.events if kind == "llm_call"]


def _sink() -> Any:
    sink = _EventSink()
    return sink, patch(
        "law_ai.core.provenance.ProvenanceLogger.log_event", side_effect=sink
    )


class TestPinnedChainNeverLeaves:
    """No hosted request escapes, on any surface, while the pin is in place."""

    @respx.mock
    async def test_router_call_stays_local(self, local_only) -> None:
        anthropic, xai = _hosted_routes()
        _tags, generate = _ollama_routes()
        sink, provenance = _sink()

        with provenance:
            result = await llm.agenerate("privileged client facts", agent="test")

        assert result.provider == "ollama"
        assert result.text == "local answer"
        assert anthropic.called is False
        assert xai.called is False
        assert generate.called is True
        assert [c["provider"] for c in sink.llm_calls] == ["ollama"]
        assert sink.llm_calls[0]["chain"] == ["ollama"]

    @respx.mock
    async def test_langchain_adapter_stays_local(self, local_only) -> None:
        """LangGraph nodes go through ChatProviderChain, not the router directly."""
        anthropic, xai = _hosted_routes()
        _tags, generate = _ollama_routes()

        reply = await llm.ChatProviderChain(agent="legal_workflow").ainvoke(
            "privileged client facts"
        )

        assert reply.content == "local answer"
        assert reply.response_metadata["provider"] == "ollama"
        assert anthropic.called is False
        assert xai.called is False
        assert generate.called is True

    @respx.mock
    async def test_lsat_tutor_endpoint_stays_local(self, local_only, api) -> None:
        from law_ai.lsat.services.bank import load_bank

        anthropic, xai = _hosted_routes()
        _tags, generate = _ollama_routes(
            json.dumps(
                {"coaching": "Look at the conclusion.", "next_steps": ["Re-read"]}
            )
        )
        qid, question = next(iter(load_bank().items()))

        res = await api.post(
            "/api/lsat/tutor",
            json={"question_id": qid, "user_choice": question.correct},
        )

        assert res.status_code == 200
        assert anthropic.called is False
        assert xai.called is False
        assert generate.called is True

    @respx.mock
    async def test_analysis_endpoint_stays_local(self, local_only, api) -> None:
        anthropic, xai = _hosted_routes()
        _tags, generate = _ollama_routes(_IRAC_JSON)
        sink, provenance = _sink()

        with provenance:
            res = await api.post(
                "/api/analysis",
                json={
                    "text": "Privileged: our client admits the late delivery.",
                    "jurisdiction": "US",
                    "use_langgraph": False,
                },
            )

        assert res.status_code == 200
        assert anthropic.called is False
        assert xai.called is False
        assert generate.called is True
        assert sink.llm_calls, "the analyst never reached the provider chain"
        assert {c["provider"] for c in sink.llm_calls} == {"ollama"}

    @respx.mock
    async def test_a_stray_hosted_request_would_fail_the_suite(
        self, local_only
    ) -> None:
        """Only Ollama is mocked here, so any other socket raises immediately.

        This is the assertion that keeps working when a future provider is
        added: it does not need to know the new vendor's hostname.
        """
        _tags, generate = _ollama_routes()

        result = await llm.agenerate("privileged client facts")

        assert result.provider == "ollama"
        assert generate.called is True

    @respx.mock
    async def test_the_pin_is_what_protects_the_data(self, local_only) -> None:
        """Control: unpin the chain and the very same call reaches Anthropic.

        Without this, every assertion above could pass for the wrong reason —
        a broken credential, a dead default — rather than because of the pin.
        """
        local_only.LLM_PROVIDER_CHAIN = "claude_code,ollama"
        anthropic, _xai = _hosted_routes()
        _ollama_routes()

        result = await llm.agenerate("privileged client facts")

        assert anthropic.called is True
        assert result.provider == "claude_code"


class TestNoTransportBypass:
    """The guarantee only holds if features route through ``core.llm``."""

    #: The only modules outside ``core/llm`` allowed to touch a transport.
    #: ``validate_xai`` is an operator diagnostic whose whole job is to prove
    #: this deployment can talk to xAI, so routing it through the chain would
    #: defeat the check. The factory's Claude executor is listed because it
    #: historically called the transport directly for reproducibility; it now
    #: pins the tier through ``providers=("claude_code",)`` instead, and the
    #: subset assertion below lets that stay fixed. Anything *new* here is a
    #: bypass of the chain, and therefore of the pin and of provenance.
    ALLOWED = {
        Path("core/management/commands/validate_xai.py"),
        Path("lsat/factory/executors.py"),
    }

    def test_only_sanctioned_modules_call_a_transport_directly(self) -> None:
        import law_ai

        root = Path(law_ai.__file__).resolve().parent
        offenders: set[Path] = set()
        for path in root.rglob("*.py"):
            relative = path.relative_to(root)
            if relative.parts[:2] == ("core", "llm") or relative.parts[0] == "tests":
                continue
            source = path.read_text(encoding="utf-8")
            # Match the attribute, not a call: ``async_to_sync(xai.generate)``
            # is just as much a bypass as calling it directly.
            if "claude_code.generate" in source or "xai.generate" in source:
                offenders.add(relative)

        assert offenders <= self.ALLOWED, (
            "a new module calls an LLM transport directly, bypassing "
            "law_ai.core.llm (and with it the chain pin and provenance): "
            f"{sorted(str(p) for p in offenders - self.ALLOWED)}"
        )
