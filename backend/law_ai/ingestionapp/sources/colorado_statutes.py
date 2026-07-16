"""Colorado Revised Statutes adapter for SOURCE_REGISTRY (spec 018 T-006).

Wraps :class:`~law_ai.ingestionapp.services.colorado_statutes.ColoradoStatutesClient`
and :func:`~law_ai.ingestionapp.services.colorado_statutes.parse_title_html`
as a synchronous :class:`~law_ai.ingestionapp.sources.base.SourceAdapter`.

The ``query`` argument to ``fetch`` is interpreted as a CRS title number
(e.g. ``"1"`` or ``"24"``). Jurisdiction is ``us-co`` (Colorado).
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Iterable

from law_ai.ingestionapp.sources.base import RawDoc, SourceAdapter

logger = logging.getLogger("law_ai.sources.colorado_statutes")


class ColoradoStatutesAdapter(SourceAdapter):
    """Synchronous adapter for the Colorado Revised Statutes Justia mirror."""

    name = "colorado_statutes"
    jurisdiction = "us-co"
    license = (
        "US Government work (CRS text is uncopyrightable); "
        "Justia commentary CC-BY — redistribution: false"
    )
    requires_human_approval = False
    rate_limit_rps = 0.5  # Respect Justia robots.txt / crawl-delay

    def fetch(self, query: str, *, limit: int = 10) -> Iterable[RawDoc]:
        """Yield statute sections for CRS title *query*.

        ``query`` is treated as a CRS title id (e.g. ``"1"``). For
        title-scanning callers may pass ``"all"`` to iterate every
        title, but that makes hundreds of HTTP requests — not suitable
        for interactive use; prefer explicit title ids in production.

        Example
        -------
        >>> adapter = ColoradoStatutesAdapter()
        >>> docs = list(adapter.fetch("1", limit=5))  # doctest: +SKIP
        >>> all(d.source_name == "colorado_statutes" for d in docs)
        True
        """
        return list(asyncio.run(self._afetch(query, limit=limit)))

    async def _afetch(self, query: str, *, limit: int) -> list[RawDoc]:
        from law_ai.ingestionapp.services.colorado_statutes import (
            ColoradoStatutesClient,
            parse_title_html,
        )

        docs: list[RawDoc] = []
        try:
            async with ColoradoStatutesClient() as client:
                html = await client.fetch_title(query)
                extraction = parse_title_html(query, html)
                for section in extraction.sections[:limit]:
                    docs.append(
                        RawDoc(
                            source_name=self.name,
                            source_url=extraction.source_url or "",
                            title=section.citation,
                            text=section.text,
                            metadata={
                                "title_id": query,
                                "section_id": section.id,
                                "jurisdiction": self.jurisdiction,
                                "effective_from": (
                                    section.effective_from.isoformat()
                                    if section.effective_from
                                    else None
                                ),
                            },
                        )
                    )
        except Exception:
            logger.exception("ColoradoStatutesAdapter.fetch failed for query=%r", query)
            raise
        return docs
