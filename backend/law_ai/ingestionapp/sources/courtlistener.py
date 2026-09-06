"""CourtListener adapter for SOURCE_REGISTRY (spec 018 T-006).

Wraps :class:`~law_ai.ingestionapp.services.courtlistener.CourtListenerClient`
as a synchronous :class:`~law_ai.ingestionapp.sources.base.SourceAdapter` so
the autonomy orchestrator can call ``fetch()`` from a plain thread.
"""

from __future__ import annotations

import logging

from law_ai.ingestionapp.sources.base import RawDoc, SourceAdapter

logger = logging.getLogger("law_ai.sources.courtlistener")


class CourtListenerAdapter(SourceAdapter):
    """Synchronous wrapper around CourtListenerClient.list_opinions."""

    name = "courtlistener"
    jurisdiction = "us"
    license = "CC0/public domain (CourtListener API data)"
    requires_human_approval = False
    rate_limit_rps = 2.0

    async def afetch(self, query: str, *, limit: int = 10) -> list[RawDoc]:
        """Return up to *limit* opinions matching *query*.

        Network unavailability raises; callers should catch and quarantine.
        Synchronous callers use the inherited :meth:`SourceAdapter.fetch`.

        Example
        -------
        >>> adapter = CourtListenerAdapter()
        >>> docs = list(adapter.fetch("Brown v Board", limit=3))  # doctest: +SKIP
        >>> all(d.source_name == "courtlistener" for d in docs)
        True
        """
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
                                # BL-20260803-01: carry the cluster's own
                                # outcome text through so `IngestionScout`
                                # can map a disposition. Absent keys stay
                                # absent — never defaulted to a guess.
                                "disposition": (opinion.get("cluster") or {}).get(
                                    "disposition"
                                ),
                                "posture": (opinion.get("cluster") or {}).get(
                                    "posture"
                                ),
                            },
                        )
                    )
        except Exception:
            logger.exception("CourtListenerAdapter.fetch failed for query=%r", query)
            raise
        return docs
