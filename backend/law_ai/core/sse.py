"""Server-sent-events line parsing shared by the streaming transports.

Both hosted tiers stream over SSE — Anthropic's Messages API and xAI's
OpenAI-compatible completions — and both frame their payloads the same way: a
``data:`` line carrying one JSON object, with ``[DONE]`` and blank keep-alive
lines interleaved. This module holds that one shared grammar so the two
transports cannot drift apart on it (BL-20260811-20).

It deliberately imports nothing from ``law_ai``: :mod:`law_ai.core.claude_code`
and :mod:`law_ai.core.xai` are imported *by* the ``core.llm`` package, so a
helper they share has to sit outside it — the same reason
:mod:`law_ai.core.usage` lives where it does.
"""

from __future__ import annotations

import json
from typing import Any

__all__ = ["data_payload"]

_PREFIX = "data:"
_SENTINEL = "[DONE]"


def data_payload(line: str) -> dict[str, Any] | None:
    """The JSON object one SSE line carries, or ``None`` if it carries none.

    ``None`` covers every frame a client should skip rather than die on: an
    ``event:``/``id:`` line, a keep-alive blank, the terminal ``[DONE]``
    sentinel, a non-JSON body, or a JSON value that is not an object. A
    provider is free to add frame types, and a stream must not break on one the
    client does not model.
    """
    if not line.startswith(_PREFIX):
        return None
    raw = line[len(_PREFIX) :].strip()
    if not raw or raw == _SENTINEL:
        return None
    try:
        event = json.loads(raw)
    except json.JSONDecodeError:
        return None
    return event if isinstance(event, dict) else None
