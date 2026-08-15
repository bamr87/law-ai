"""Provider-agnostic contracts for the Law AI LLM chain (spec 034).

Every model call in the product now flows through one ordered chain of
providers — Claude OAuth first, the Anthropic API key second, local Ollama
last (constitution §1, as amended 2026-08-11). This module holds the shapes
those providers agree on; :mod:`law_ai.core.llm.router` does the routing and
:mod:`law_ai.core.llm.providers` implements the transports.

The request object is deliberately provider-neutral. Model ids are *not*
interchangeable across providers (``claude-opus-4-8`` means nothing to Ollama),
so a caller that needs to pin one passes a per-provider mapping::

    LLMRequest(prompt=p, models={"ollama": "mistral:7b-instruct-q4_K_M"})

and a caller that must not leave a given provider restricts the chain::

    LLMRequest(prompt=p, providers=("ollama",))   # eval harness: local only
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable


class LLMUnavailableError(RuntimeError):
    """No provider in the configured chain could serve the request.

    Carries the per-provider failure reasons so callers can degrade with an
    honest explanation instead of a fabricated answer (constitution §13).
    """

    def __init__(self, message: str, attempts: Sequence[LLMAttempt] = ()) -> None:
        super().__init__(message)
        self.attempts: tuple[LLMAttempt, ...] = tuple(attempts)


@dataclass(frozen=True, slots=True)
class LLMRequest:
    """One provider-neutral generation request.

    Args:
        prompt: the user-turn text.
        system: optional system instruction.
        response_schema: JSON Schema pinning the reply to schema-valid JSON
            (Anthropic structured outputs). Providers that cannot enforce a
            schema fall back to JSON mode.
        max_tokens: output cap; provider default when ``None``.
        temperature: sampling temperature.
        json_mode: request JSON output without a full schema.
        models: per-provider model id overrides, keyed by provider name.
        providers: restrict the chain to these provider names, in this order.
            ``None`` uses the configured chain.
    """

    prompt: str
    system: str | None = None
    response_schema: dict[str, Any] | None = None
    max_tokens: int | None = None
    temperature: float = 0.0
    json_mode: bool = False
    models: Mapping[str, str] = field(default_factory=dict)
    providers: Sequence[str] | None = None

    def wants_json(self) -> bool:
        """True when the caller expects a JSON payload back."""
        return self.json_mode or self.response_schema is not None

    def model_for(self, provider: str) -> str | None:
        """The caller's model override for *provider*, if any."""
        return self.models.get(provider)


@dataclass(frozen=True, slots=True)
class LLMAttempt:
    """One provider's outcome within a single routed request."""

    provider: str
    ok: bool
    error: str | None = None
    skipped_reason: str | None = None


@dataclass(frozen=True, slots=True)
class LLMResult:
    """A successful generation plus the route that produced it."""

    text: str
    provider: str
    model: str
    latency_ms: float
    attempts: tuple[LLMAttempt, ...] = ()

    @property
    def model_label(self) -> str:
        """Audit-friendly ``provider/model`` identifier."""
        return f"{self.provider}/{self.model}"

    @property
    def fell_back(self) -> bool:
        """True when an earlier provider in the chain failed or was skipped."""
        return any(a.provider != self.provider for a in self.attempts)


@runtime_checkable
class LLMProvider(Protocol):
    """The contract every transport in the chain implements."""

    name: str

    def configured(self) -> bool:
        """True iff this provider has the credentials/config to be tried."""
        ...

    def unconfigured_reason(self) -> str | None:
        """Why :meth:`configured` is ``False`` (for logs and the health probe)."""
        ...

    def model_for(self, request: LLMRequest) -> str:
        """The model id this provider would use for *request*."""
        ...

    async def agenerate(self, request: LLMRequest) -> str:
        """Generate text, raising on transport/provider failure."""
        ...

    async def probe(self) -> dict[str, Any]:
        """Never-raising reachability report for the health endpoint."""
        ...


__all__ = [
    "LLMAttempt",
    "LLMProvider",
    "LLMRequest",
    "LLMResult",
    "LLMUnavailableError",
]
