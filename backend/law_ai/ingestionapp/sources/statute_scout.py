"""StatuteScout adapter for SOURCE_REGISTRY (spec 018 T-006).

Delegates extraction to :class:`~law_ai.ingestionapp.services.statute_scout.StatuteScout`
but wraps the interface as a synchronous :class:`~law_ai.ingestionapp.sources.base.SourceAdapter`.

Since :class:`StatuteScout` already requires HTML as input (not a query string),
this adapter first fetches HTML via
:class:`~law_ai.ingestionapp.services.colorado_statutes.ColoradoStatutesClient`
and then calls ``extract`` to turn it into section payloads. The resulting
:class:`RawDoc` objects are fed into ``IngestionScout.run_and_commit`` by the
orchestrator — they are **not** committed here (constitution §12 invariant I1).
"""

from __future__ import annotations

import logging

from law_ai.ingestionapp.sources.base import RawDoc, SourceAdapter

logger = logging.getLogger("law_ai.sources.statute_scout")


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

    async def afetch(self, query: str, *, limit: int = 10) -> list[RawDoc]:
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
        from law_ai.ingestionapp.services.colorado_statutes import (
            ColoradoStatutesClient,
        )
        from law_ai.ingestionapp.services.statute_scout import StatuteScout

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
