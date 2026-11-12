"""Shared fixtures for the lawmode tests (spec 057).

No provider is ever reached: a test either patches ``llm.agenerate`` or runs
the real router against :class:`StubProvider`, which is how the tests prove a
review goes through the chain rather than around it.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from django.conf import settings

from law_ai.core import llm
from law_ai.core.llm.base import LLMRequest


@pytest.fixture(autouse=True)
def _isolate_audit(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep provenance writes in the test's own directory."""
    monkeypatch.setattr(settings, "AUDIT_PATH", str(tmp_path / "audit.jsonl"))


@pytest.fixture(autouse=True)
def _shipped_lawmode_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    """Run every test on the shipped lawmode defaults.

    Compose feeds the developer's ``.env`` to the test container, so a
    ``LAWMODE_MODELS`` or ``LAWMODE_JURISDICTIONS`` set there would otherwise
    decide whether these tests pass. Tests that want another value set it.
    """
    monkeypatch.setattr(settings, "LAWMODE_MODELS", "")
    monkeypatch.setattr(settings, "LAWMODE_JURISDICTIONS", ["US", "EU", "UK"])


@pytest.fixture(autouse=True)
def _forget_provider_failures() -> Iterator[None]:
    """A tier another test left marked as failing must not be skipped here."""
    llm.reset_permanent_failures()
    yield
    llm.reset_permanent_failures()


class StubProvider:
    """A provider double honouring the ``LLMProvider`` protocol.

    It records every request it is handed, so a test can read back exactly
    what the chain sent: the prompt, the system instruction, the model
    override, the prompt id.
    """

    def __init__(
        self,
        name: str = "claude_code",
        *,
        text: str = "{}",
        configured: bool = True,
        error: Exception | None = None,
    ) -> None:
        self.name = name
        self._text = text
        self._configured = configured
        self._error = error
        self.requests: list[LLMRequest] = []

    def configured(self) -> bool:
        return self._configured

    def unconfigured_reason(self) -> str | None:
        return None if self._configured else f"{self.name} not configured"

    def model_for(self, request: LLMRequest) -> str:
        return request.model_for(self.name) or f"{self.name}-default-model"

    async def agenerate(self, request: LLMRequest) -> str:
        self.requests.append(request)
        if self._error is not None:
            raise self._error
        return self._text

    async def probe(self) -> dict[str, Any]:
        return {"reachable": self._error is None}


def chain(*providers: StubProvider) -> Any:
    """Run the real router against the given stubs, in order."""
    return patch("law_ai.core.llm.router.build_chain", return_value=providers)


def finding(**overrides: Any) -> dict[str, Any]:
    """One finding as a model would return it."""
    body: dict[str, Any] = {
        "severity": "High",
        "title": "Personal data sent without encryption",
        "law": "GDPR Art. 32",
        "jurisdiction": "EU",
        "citation": "https://eur-lex.europa.eu/eli/reg/2016/679/oj",
        "description": "The email field is posted over plain HTTP.",
        "mitigation": "Send it over TLS.",
        "line_start": 12,
        "line_end": 14,
    }
    body.update(overrides)
    return body


def reply(*findings: dict[str, Any], **top: Any) -> str:
    """A whole model reply as JSON text."""
    payload: dict[str, Any] = {"jurisdictions": ["EU"], "risks": list(findings)}
    payload.update(top)
    return json.dumps(payload)


def audit_events(kind: str) -> list[dict[str, Any]]:
    """Events of one type from the test's audit log, oldest first."""
    from law_ai.core import audit_jsonl

    return [e for e in reversed(audit_jsonl.tail(200)) if e.get("type") == kind]
