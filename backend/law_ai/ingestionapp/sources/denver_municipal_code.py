"""Denver Municipal Code adapter for SOURCE_REGISTRY (BL-20260509-05).

Wraps :class:`~law_ai.ingestionapp.services.denver_municipal_code.DenverMunicipalCodeClient`
and :func:`~law_ai.ingestionapp.services.denver_municipal_code.parse_chapter_html`
as a :class:`~law_ai.ingestionapp.sources.base.SourceAdapter`. ``query`` is a
DRMC chapter number (e.g. ``"38"``); jurisdiction is ``us-co-denver``.

``requires_human_approval = True`` is the point of this adapter's
configuration, not an afterthought: library.municode.com renders the code
through JavaScript under terms of use that prohibit systematic downloading, so
anything an HTTP client retrieves is both legally and structurally uncertain.
The orchestrator reads this flag and routes every document to the HITL queue
(`topic_frontier._dispatch`'s ``force_quarantine``), which means no municipal
ordinance can enter the graph without a person having read it.
"""

from __future__ import annotations

import logging

from law_ai.ingestionapp.sources.base import RawDoc, SourceAdapter

logger = logging.getLogger("law_ai.sources.denver_municipal_code")


class DenverMunicipalCodeAdapter(SourceAdapter):
    """Adapter for the Denver Revised Municipal Code."""

    name = "denver_municipal_code"
    jurisdiction = "us-co-denver"
    license = (
        "Municipal government work (DRMC text is uncopyrightable); "
        "Municode hosting terms prohibit systematic downloading — "
        "redistribution: false, HITL required"
    )
    #: See the module docstring. Every document goes to a human.
    requires_human_approval = True
    #: Deliberately slower than the Justia adapter: this host is not one we
    #: have permission to crawl at volume.
    rate_limit_rps = 0.25

    async def afetch(self, query: str, *, limit: int = 10) -> list[RawDoc]:
        """Return ordinance sections for DRMC chapter *query*.

        Example
        -------
        >>> adapter = DenverMunicipalCodeAdapter()
        >>> docs = list(adapter.fetch("38", limit=5))  # doctest: +SKIP
        >>> all(d.source_name == "denver_municipal_code" for d in docs)
        True
        """
        from law_ai.ingestionapp.services.denver_municipal_code import (
            DenverMunicipalCodeClient,
            parse_chapter_html,
        )

        docs: list[RawDoc] = []
        try:
            async with DenverMunicipalCodeClient() as client:
                html = await client.fetch_chapter(query)
                extraction = parse_chapter_html(
                    query, html, source_url=client.url_for_chapter(query)
                )
                for section in extraction.sections[:limit]:
                    docs.append(
                        RawDoc(
                            source_name=self.name,
                            source_url=extraction.source_url or "",
                            title=section.citation,
                            text=section.text,
                            metadata={
                                "chapter": query,
                                "ordinance_id": extraction.ordinance_id,
                                "section_id": section.id,
                                "jurisdiction": self.jurisdiction,
                                "history_note": section.history_note,
                                "effective_from": (
                                    section.effective_from.isoformat()
                                    if section.effective_from
                                    else None
                                ),
                            },
                        )
                    )
        except Exception:
            logger.exception(
                "DenverMunicipalCodeAdapter.fetch failed for query=%r", query
            )
            raise
        return docs
