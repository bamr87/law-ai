"""StatuteScout adapter for SOURCE_REGISTRY (spec 018 T-006).

Delegates extraction to :class:`~lawgraph.ingestionapp.services.statute_scout.StatuteScout`
but wraps the interface as a synchronous :class:`~lawgraph.ingestionapp.sources.base.SourceAdapter`.

Since :class:`StatuteScout` already requires HTML as input (not a query string),
this adapter first fetches HTML via
:class:`~lawgraph.ingestionapp.services.colorado_statutes.ColoradoStatutesClient`
and then calls ``extract`` to turn it into section payloads. The resulting
:class:`RawDoc` objects are fed into ``IngestionScout.run_and_commit`` by the
orchestrator — they are **not** committed here (constitution §12 invariant I1).
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Iterable

from lawgraph.ingestionapp.sources.base import RawDoc, SourceAdapter

logger = logging.getLogger("lawgraph.sources.statute_scout")


class StatuteScoutAdapter(SourceAdapter):
    """Adapter that applies StatuteScout.extract to Colorado statute HTML."""

    name = "statute_scout"
    jurisdiction = "us-co"
    license = (
        "US Government work (CRS text is uncopyrightable); "
        "Justia commentary CC-BY — redistribution: false"
    )
    requires_human_approval = False
    rate_limit_rps = 0.5

    def fetch(self, query: str, *, limit: int = 10) -> Iterable[RawDoc]:
        """Fetch CRS title *query* and return extracted section RawDocs.

        Unlike :class:`ColoradoStatutesAdapter`, this adapter runs the
        StatuteScout extraction pipeline (provenance-logged) before
        returning documents, so confidence scores are pre-computed.

        Example
        -------
        >>> adapter = StatuteScoutAdapter()
        >>> docs = list(adapter.fetch("1", limit=3))  # doctest: +SKIP
        >>> all(d.source_name == "statute_scout" for d in docs)
        True
        """
        return list(asyncio.run(self._afetch(query, limit=limit)))

    async def _afetch(self, query: str, *, limit: int) -> list[RawDoc]:
        from lawgraph.ingestionapp.services.colorado_statutes import (
            ColoradoStatutesClient,
        )
        from lawgraph.ingestionapp.services.statute_scout import StatuteScout

        scout = StatuteScout()
        docs: list[RawDoc] = []
        try:
            async with ColoradoStatutesClient() as client:
                source_url = f"{client._base_url}/title-{query}/"
                html = await client.fetch_title(query)

            extraction = scout.extract(
                {"title_id": query, "html": html, "source_url": source_url}
            )
            for section in extraction.sections[:limit]:
                docs.append(
                    RawDoc(
                        source_name=self.name,
                        source_url=extraction.source_url or source_url,
                        title=section.citation,
                        text=section.text,
                        metadata={
                            "title_id": query,
                            "section_id": section.id,
                            "jurisdiction": self.jurisdiction,
                            "confidence": extraction.confidence,
                            "agent_version": extraction.agent_version,
                            "effective_from": (
                                section.effective_from.isoformat()
                                if section.effective_from
                                else None
                            ),
                        },
                    )
                )
        except Exception:
            logger.exception("StatuteScoutAdapter.fetch failed for query=%r", query)
            raise
        return docs
