"""Token-usage value objects shared by every LLM transport (BL-20260811-21).

Hosted tiers bill per token, so the ``llm_call`` provenance event has to carry
token counts — latency and provider alone cannot attribute spend to an agent.
The counts are produced at the transport boundary (Anthropic's ``usage``
object, xAI's ``usage``, Ollama's ``prompt_eval_count``/``eval_count``) and
have to survive the trip up to :mod:`law_ai.core.llm.router`.

This module deliberately lives *outside* :mod:`law_ai.core.llm` and imports
nothing from ``law_ai``: :mod:`law_ai.core.claude_code` and
:mod:`law_ai.core.xai` are imported *by* the ``core.llm`` package, so a shape
defined in ``core.llm.base`` could not be imported back into them without a
circular import.

:class:`ProviderReply` is a ``str`` subclass on purpose. The provider contract
(``LLMProvider.agenerate() -> str``) is left exactly as it was so that every
existing caller — and the streaming work landing on top of it — keeps working
unchanged, while the router can read ``reply.usage`` when a transport supplied
counts. Providers that report nothing simply return a plain string.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

__all__ = [
    "LLMUsage",
    "ProviderReply",
    "usage_of",
]


@dataclass(frozen=True, slots=True)
class LLMUsage:
    """Token counts a provider reported for one generation.

    Both fields are optional: a transport that reports only one half (or a
    future provider that reports neither) still yields a usable record, and
    the audit event says ``null`` rather than guessing a number.
    """

    input_tokens: int | None = None
    output_tokens: int | None = None

    @property
    def total_tokens(self) -> int | None:
        """Sum of the two counts, or ``None`` when neither is known."""
        known = [t for t in (self.input_tokens, self.output_tokens) if t is not None]
        return sum(known) if known else None

    def as_dict(self) -> dict[str, int | None]:
        """JSON-friendly mapping for provenance payloads."""
        return {
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "total_tokens": self.total_tokens,
        }

    @classmethod
    def from_counts(cls, input_tokens: Any, output_tokens: Any) -> LLMUsage | None:
        """Build usage from two raw provider values, or ``None`` if both are absent.

        Non-numeric or negative values are dropped rather than raising: a
        malformed ``usage`` block from a provider must never fail a request
        that otherwise succeeded.
        """
        inp = _coerce_count(input_tokens)
        out = _coerce_count(output_tokens)
        if inp is None and out is None:
            return None
        return cls(input_tokens=inp, output_tokens=out)

    @classmethod
    def from_payload(
        cls,
        payload: Any,
        *,
        input_key: str,
        output_key: str,
    ) -> LLMUsage | None:
        """Read the two counts out of a provider's ``usage``-shaped mapping."""
        if not isinstance(payload, Mapping):
            return None
        return cls.from_counts(payload.get(input_key), payload.get(output_key))


def _coerce_count(value: Any) -> int | None:
    """Best-effort non-negative int, or ``None`` for anything unusable."""
    if value is None or isinstance(value, bool):
        return None
    try:
        count = int(value)
    except (TypeError, ValueError):
        return None
    return count if count >= 0 else None


class ProviderReply(str):
    """Generated text that also carries the provider's token usage.

    A ``str`` subclass so the transport contract is unchanged — every caller
    that treats the reply as text (``json.loads``, ``strip_code_fence``, the
    factory executors) keeps working, and no provider is forced to adopt a new
    return type. Only the router looks at :attr:`usage`, via :func:`usage_of`.
    """

    __slots__ = ("usage",)

    usage: LLMUsage | None

    def __new__(cls, text: str, usage: LLMUsage | None = None) -> ProviderReply:
        reply = str.__new__(cls, text)
        reply.usage = usage
        return reply


def usage_of(value: object) -> LLMUsage | None:
    """The usage attached to a reply, or ``None`` for a plain string."""
    usage = getattr(value, "usage", None)
    return usage if isinstance(usage, LLMUsage) else None
