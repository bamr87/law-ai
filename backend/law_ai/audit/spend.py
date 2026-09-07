"""Read the token/cost accounting back out of the audit log (BL-20260905-69).

``law_ai.core.llm.router`` writes ``input_tokens``, ``output_tokens``,
``total_tokens`` and ``cost_usd`` onto every ``llm_call`` :class:`AuditEvent`
(BL-20260811-21), but until now nothing read them: the accounting was
write-only, so "what did the hosted tiers cost this week" had no answer short
of a shell and a hand-rolled query.

This module is the read side. It is deliberately a pure function over event
payloads plus a thin ORM query, so the rollup can be tested without a model
call and reused by anything that wants the numbers (a command today, an
endpoint later).

Two rules the numbers obey, because a spend report that quietly rounds either
one is worse than no report:

* **Unpriced is not free.** ``estimate_cost_usd`` returns ``None`` — never
  zero — for a tier with no entry in the price table, and that ``None`` is
  carried through as ``unpriced_calls`` rather than summed as ``0.0``. A local
  Ollama call is genuinely free; an unpriced hosted model is unknown, and the
  report says which is which.
* **Failures still count.** A call that fell all the way through the chain has
  ``ok: False`` and no usage, but it happened. It is counted in ``calls`` and
  reported as ``failed_calls``, so a burst of retries is visible rather than
  invisible.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from django.utils import timezone

#: The provenance event kind the router writes for every model call.
LLM_CALL_KIND = "llm_call"

#: What a caller gets when a payload names no agent. The router records
#: ``agent: None`` for calls made outside an agent (a bare ``route()``), and
#: bucketing those under a visible label beats dropping them.
UNATTRIBUTED = "(unattributed)"


def _as_int(value: Any) -> int | None:
    """Coerce a payload token count, or ``None`` when it is not a number."""
    if isinstance(value, bool) or value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _as_float(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


@dataclass
class SpendBucket:
    """Accumulated spend for one grouping key."""

    key: str
    calls: int = 0
    failed_calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    #: Calls whose model has no price-table entry. Their cost is unknown, not
    #: zero, so ``cost_usd`` under-reports by exactly this many calls.
    unpriced_calls: int = 0

    def add(self, payload: Mapping[str, Any]) -> None:
        self.calls += 1
        if not payload.get("ok", True):
            self.failed_calls += 1
        for name in ("input_tokens", "output_tokens"):
            tokens = _as_int(payload.get(name))
            if tokens is not None:
                setattr(self, name, getattr(self, name) + tokens)
        cost = _as_float(payload.get("cost_usd"))
        if cost is None:
            # A failed call has no usage at all; only a *successful* call with
            # no price is a gap in the price table worth flagging.
            if payload.get("ok", True):
                self.unpriced_calls += 1
        else:
            self.cost_usd += cost

    def as_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "calls": self.calls,
            "failed_calls": self.failed_calls,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "total_tokens": self.input_tokens + self.output_tokens,
            "cost_usd": round(self.cost_usd, 6),
            "unpriced_calls": self.unpriced_calls,
        }


@dataclass
class SpendReport:
    """Per-agent and per-tier rollups plus the totals they sum to."""

    since: datetime | None = None
    total: SpendBucket = field(default_factory=lambda: SpendBucket(key="total"))
    by_agent: list[SpendBucket] = field(default_factory=list)
    by_tier: list[SpendBucket] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "since": self.since.isoformat() if self.since else None,
            "total": self.total.as_dict(),
            "by_agent": [b.as_dict() for b in self.by_agent],
            "by_tier": [b.as_dict() for b in self.by_tier],
        }


def _tier_key(payload: Mapping[str, Any]) -> str:
    """``provider/model`` for a served call, or the chain that failed."""
    provider = str(payload.get("provider") or "").strip()
    model = str(payload.get("model") or "").strip()
    if provider and model:
        return f"{provider}/{model}"
    if provider:
        return provider
    chain = payload.get("chain")
    if isinstance(chain, list) and chain:
        return "(failed: " + ",".join(str(c) for c in chain) + ")"
    return "(unknown)"


def _sorted(buckets: dict[str, SpendBucket]) -> list[SpendBucket]:
    """Most expensive first, then most-called, then by key for determinism."""
    return sorted(buckets.values(), key=lambda b: (-b.cost_usd, -b.calls, b.key))


def rollup(payloads: Iterable[Mapping[str, Any]]) -> SpendReport:
    """Aggregate ``llm_call`` payloads by agent and by provider/model tier."""
    report = SpendReport()
    agents: dict[str, SpendBucket] = {}
    tiers: dict[str, SpendBucket] = {}
    for payload in payloads:
        if not isinstance(payload, Mapping):
            continue
        agent = str(payload.get("agent") or "").strip() or UNATTRIBUTED
        agents.setdefault(agent, SpendBucket(key=agent)).add(payload)
        tier = _tier_key(payload)
        tiers.setdefault(tier, SpendBucket(key=tier)).add(payload)
        report.total.add(payload)
    report.by_agent = _sorted(agents)
    report.by_tier = _sorted(tiers)
    return report


def spend_report(*, days: int | None = 30) -> SpendReport:
    """Roll up every ``llm_call`` event in the trailing *days* window.

    ``days=None`` means the whole audit table. The payload column is pulled
    with ``values_list`` so a long window costs one column, not whole model
    instances.
    """
    from law_ai.audit.models import AuditEvent

    rows = AuditEvent.objects.filter(kind=LLM_CALL_KIND)
    since: datetime | None = None
    if days is not None:
        since = timezone.now() - timedelta(days=days)
        rows = rows.filter(timestamp__gte=since)
    report = rollup(rows.values_list("payload", flat=True))
    report.since = since
    return report


__all__ = [
    "LLM_CALL_KIND",
    "UNATTRIBUTED",
    "SpendBucket",
    "SpendReport",
    "rollup",
    "spend_report",
]
