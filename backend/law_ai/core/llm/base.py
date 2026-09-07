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

from collections.abc import AsyncIterator, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from law_ai.core.usage import LLMUsage, ProviderReply, usage_of


class LLMUnavailableError(RuntimeError):
    """No provider in the configured chain could serve the request.

    Carries the per-provider failure reasons so callers can degrade with an
    honest explanation instead of a fabricated answer (constitution §13).
    """

    def __init__(self, message: str, attempts: Sequence[LLMAttempt] = ()) -> None:
        super().__init__(message)
        self.attempts: tuple[LLMAttempt, ...] = tuple(attempts)


class LLMPermanentError(LLMUnavailableError):
    """A failure retrying cannot fix — bad credentials, a rejected request.

    The chain still falls through to the next tier by default (the
    constitution wants an answer), but the router remembers a *credential*
    permanent failure for ``LLM_PERMANENT_FAILURE_TTL_S`` so every later
    request skips that tier instead of re-earning the same 401. Deployments
    that would rather fail loudly than quietly answer from the local model set
    ``LLM_FAIL_FAST_ON_PERMANENT=true``, and this is what they get.
    """


class LLMStreamInterrupted(LLMUnavailableError):
    """A stream failed *after* the caller already saw tokens (BL-20260811-20).

    The chain deliberately does **not** fall through here. Once a delta has
    been handed to a caller — and, in the WebSocket path, rendered in front of
    a human — restarting on the next tier would silently splice two different
    answers into one. The partial text is carried on :attr:`partial` so the
    caller can decide: discard it, or keep it clearly marked as truncated.
    """

    def __init__(
        self,
        message: str,
        attempts: Sequence[LLMAttempt] = (),
        *,
        partial: str = "",
    ) -> None:
        super().__init__(message, attempts)
        self.partial = partial


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
        prompt_id: name of the versioned prompt this call renders, if any.
        prompt_version: that prompt's version string.
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
    #: Which versioned prompt produced this call, e.g.
    #: ``("lsat_tutor", "lsat_tutor/1")``. Recorded on the ``llm_call`` event
    #: so prompt drift is attributable to the calls it changed
    #: (BL-20260503-01). Optional: a caller that builds its prompt inline
    #: simply has nothing to declare.
    prompt_id: str | None = None
    prompt_version: str | None = None

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
    #: ``"permanent"`` or ``"transient"`` for a failed attempt, ``None``
    #: otherwise — so an audit reader can tell a misconfigured key from an
    #: overloaded vendor without parsing the error string (BL-20260811-23).
    kind: str | None = None


@dataclass(frozen=True, slots=True)
class LLMResult:
    """A successful generation plus the route that produced it."""

    text: str
    provider: str
    model: str
    latency_ms: float
    attempts: tuple[LLMAttempt, ...] = ()
    #: Token counts the serving transport reported, when it reported any.
    #: ``None`` for a provider that returns no usage block — the audit event
    #: then records nulls rather than inventing counts (BL-20260811-21).
    usage: LLMUsage | None = None
    #: True when the text was assembled from a token stream rather than one
    #: buffered response (BL-20260811-20). Recorded on the ``llm_call`` event
    #: so an auditor can tell the two paths apart.
    streamed: bool = False

    @property
    def model_label(self) -> str:
        """Audit-friendly ``provider/model`` identifier."""
        return f"{self.provider}/{self.model}"

    @property
    def fell_back(self) -> bool:
        """True when an earlier provider in the chain failed or was skipped."""
        return any(a.provider != self.provider for a in self.attempts)


@dataclass(frozen=True, slots=True)
class LLMChunk:
    """One delta of a streamed generation, tagged with its route.

    Every chunk carries the serving provider/model because the router picks a
    tier lazily: a caller rendering tokens can only label them honestly if the
    label arrives with the first delta rather than at the end.
    """

    text: str
    provider: str
    model: str
    #: True on the first delta of a stream — the point after which the chain
    #: can no longer fall back to another provider.
    first: bool = False

    @property
    def model_label(self) -> str:
        """Audit-friendly ``provider/model`` identifier."""
        return f"{self.provider}/{self.model}"


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
        """Generate text, raising on transport/provider failure.

        Returning a :class:`~law_ai.core.usage.ProviderReply` (a ``str``
        subclass) instead of a bare string additionally hands the router the
        provider's token usage; plain strings stay valid.
        """
        ...

    def astream(self, request: LLMRequest) -> AsyncIterator[str]:
        """Yield text deltas as the provider produces them (BL-20260811-20).

        Optional: a transport that cannot stream simply omits it, and
        :func:`law_ai.core.llm.router.astream` degrades to one buffered
        :meth:`agenerate` call yielded as a single delta, so every tier is
        streamable from the caller's point of view.

        A transport that knows its token usage yields it on the final delta as
        a :class:`~law_ai.core.usage.ProviderReply` (a ``str`` subclass,
        usually empty text) — the same trick :meth:`agenerate` uses, so no new
        return type enters the contract.
        """
        ...

    async def probe(self) -> dict[str, Any]:
        """Never-raising reachability report for the health endpoint."""
        ...


__all__ = [
    "LLMAttempt",
    "LLMChunk",
    "LLMPermanentError",
    "LLMProvider",
    "LLMRequest",
    "LLMResult",
    "LLMStreamInterrupted",
    "LLMUnavailableError",
    "LLMUsage",
    "ProviderReply",
    "usage_of",
]
