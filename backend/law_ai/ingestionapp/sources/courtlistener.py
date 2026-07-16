"""CourtListener adapter for SOURCE_REGISTRY (spec 018 T-006).

Wraps :class:`~law_ai.ingestionapp.services.courtlistener.CourtListenerClient`
as a synchronous :class:`~law_ai.ingestionapp.sources.base.SourceAdapter` so
the autonomy orchestrator can call ``fetch()`` from a plain thread.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Iterable

from law_ai.ingestionapp.sources.base import RawDoc, SourceAdapter

logger = logging.getLogger("law_ai.sources.courtlistener")


class CourtListenerAdapter(SourceAdapter):
    """Synchronous wrapper around CourtListenerClient.list_opinions."""

    name = "courtlistener"
    jurisdiction = "us"
    license = "CC0/public domain (CourtListener API data)"
    requires_human_approval = False
    rate_limit_rps = 2.0

    def fetch(self, query: str, *, limit: int = 10) -> Iterable[RawDoc]:
        """Yield up to *limit* opinions matching *query* (sync wrapper).

        Uses ``asyncio.run`` so it works from any synchronous context.
        Network unavailability raises; callers should catch and quarantine.

        Example
        -------
        >>> adapter = CourtListenerAdapter()
        >>> docs = list(adapter.fetch("Brown v Board", limit=3))
        >>> all(d.source_name == "courtlistener" for d in docs)
        True
        """
        return list(asyncio.run(self._afetch(query, limit=limit)))

    async def _afetch(self, query: str, *, limit: int) -> list[RawDoc]:
        from law_ai.ingestionapp.services.courtlistener import CourtListenerClient

        docs: list[RawDoc] = []
        try:
            async with CourtListenerClient() as client:
                async for opinion in client.list_opinions(
                    case_name__icontains=query, limit=limit
                ):
                    source_url = opinion.get("absolute_url", "")
                    if source_url and source_url.startswith("/"):
                        source_url = f"https://www.courtlistener.com{source_url}"
                    case_name = (
                        opinion.get("case_name")
                        or (opinion.get("cluster") or {}).get("case_name")
                        or "Untitled"
                    )
                    text = (
                        opinion.get("plain_text")
                        or opinion.get("html_with_citations")
                        or ""
                    )
                    docs.append(
                        RawDoc(
                            source_name=self.name,
                            source_url=source_url,
                            title=case_name,
                            text=text,
                            metadata={
                                "opinion_id": opinion.get("id"),
                                "court": (opinion.get("cluster") or {}).get("court"),
                            },
                        )
                    )
        except Exception:
            logger.exception("CourtListenerAdapter.fetch failed for query=%r", query)
            raise
        return docs
