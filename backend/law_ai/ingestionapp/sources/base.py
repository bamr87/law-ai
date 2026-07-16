"""Abstract base for all Law AI source adapters (spec 018 T-006).

Every adapter in SOURCE_REGISTRY must subclass :class:`SourceAdapter` and
implement :meth:`fetch`. The returned :class:`RawDoc` objects carry enough
provenance that downstream ``IngestionScout.run_and_commit`` can attribute
each document correctly (constitution §4).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import datetime, UTC
from typing import Any


@dataclass(frozen=True, slots=True)
class RawDoc:
    """Minimal carrier returned by every :class:`SourceAdapter`.

    Fields are intentionally flat so adapters don't need the full
    Pydantic schema that ``IngestionScout`` builds later.
    """

    source_name: str
    """Registry key of the adapter that produced this document."""

    source_url: str
    """Canonical URL for provenance + deduplication."""

    title: str
    """Human-readable title or section number."""

    text: str
    """Full plain text (or HTML) ready for extraction."""

    fetched_at: datetime = field(
        default_factory=lambda: datetime.now(UTC), compare=False
    )

    metadata: dict[str, Any] = field(default_factory=dict, compare=False)
    """Adapter-specific fields (e.g. ``jurisdiction``, ``court``)."""


class SourceAdapter(ABC):
    """Abstract base for all Law AI ingest source adapters.

    Subclasses must set class attributes ``name``, ``jurisdiction``,
    ``license``, ``requires_human_approval``, and ``rate_limit_rps``,
    and implement :meth:`fetch`.

    Adapters MUST NOT write to Neo4j directly; they return
    :class:`RawDoc` objects that are fed into
    ``IngestionScout.run_and_commit`` by the orchestrator.
    This preserves constitution §12 invariant I1 (no direct Neo4j writes
    outside the scout).
    """

    # ------------------------------------------------------------------ class-level metadata (set by subclasses)
    name: str
    """Unique registry key — appears in ``AUTONOMY_ALLOWED_SOURCES``."""

    jurisdiction: str
    """CLDR-style jurisdiction tag, e.g. ``'us'``, ``'us-co'``, ``'*'``."""

    license: str
    """SPDX expression or prose description of the upstream data licence."""

    requires_human_approval: bool = False
    """When True, every batch must clear an explicit HITL gate before
    ``IngestionScout.run_and_commit`` is called."""

    rate_limit_rps: float = 1.0
    """Recommended maximum request rate in requests-per-second."""

    @abstractmethod
    def fetch(self, query: str, *, limit: int = 10) -> Iterable[RawDoc]:
        """Yield up to *limit* :class:`RawDoc` objects matching *query*.

        Implementations MUST be synchronous (the autonomy runner calls
        them from a normal thread). Async adapters should use
        ``asyncio.run`` internally or provide a companion ``afetch``
        coroutine.

        Parameters
        ----------
        query:
            Free-text search term or identifier (e.g. a citation string,
            a statute title-number, a case name).
        limit:
            Maximum number of documents to return in a single call.
        """

    def __repr__(self) -> str:
        return (
            f"<{self.__class__.__name__} name={self.name!r}"
            f" jurisdiction={self.jurisdiction!r}>"
        )
