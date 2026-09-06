"""Abstract base for all Law AI source adapters (spec 018 T-006).

Every adapter in SOURCE_REGISTRY must subclass :class:`SourceAdapter` and
implement the :meth:`SourceAdapter.afetch` coroutine; the base class supplies
the synchronous :meth:`SourceAdapter.fetch` shim. The returned
:class:`RawDoc` objects carry enough provenance that downstream
``IngestionScout.run_and_commit`` can attribute each document correctly
(constitution §4).
"""

from __future__ import annotations

import asyncio
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
    and implement :meth:`afetch`. :meth:`fetch` is inherited.

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

    extractor: type | None = None
    """Optional per-adapter extractor class (BL-20260602-07).

    ``TopicFrontier`` dispatch instantiates this instead of the default
    ``IngestionScout`` when an adapter declares it, so a source whose
    documents are not court opinions can be parsed by the right extractor.
    The class must expose ``run_and_commit(payload, *, force_quarantine)``.

    Left ``None`` by every shipped adapter today: all three currently emit
    opinion-shaped ``RawDoc``s, and the statute commit path is tracked
    separately (BL-20260811-03). ``source_name`` on the dispatch payload is
    what makes ``PendingReview.source`` truthful in the meantime.
    """

    @abstractmethod
    async def afetch(self, query: str, *, limit: int = 10) -> list[RawDoc]:
        """Return up to *limit* :class:`RawDoc` objects matching *query*.

        The **async** method is the one adapters implement (BL-20260511-08).
        Every adapter here is HTTP-backed, so the coroutine is the honest
        primitive; ``fetch`` is the thin sync shim on top of it.

        Parameters
        ----------
        query:
            Free-text search term or identifier (e.g. a citation string,
            a statute title-number, a case name).
        limit:
            Maximum number of documents to return in a single call.
        """

    def fetch(self, query: str, *, limit: int = 10) -> Iterable[RawDoc]:
        """Synchronous wrapper around :meth:`afetch`.

        Safe from a plain thread; **raises** from inside a running event
        loop rather than deadlocking or blowing up inside ``asyncio.run``.
        That was a live bug: ``TopicFrontier`` dispatch awaited a coroutine
        that called ``adapter.fetch`` → ``asyncio.run`` inside the already
        running autonomy loop, which raises ``RuntimeError``; the dispatch
        node swallowed it as "fetch failed", so every real ``corpus_growth``
        run silently fetched nothing. Async callers must await
        :meth:`afetch` instead.
        """
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return list(asyncio.run(self.afetch(query, limit=limit)))
        raise RuntimeError(
            f"{type(self).__name__}.fetch() called from a running event loop; "
            "await afetch() instead (BL-20260511-08)"
        )

    def __repr__(self) -> str:
        return (
            f"<{self.__class__.__name__} name={self.name!r}"
            f" jurisdiction={self.jurisdiction!r}>"
        )
