"""Denver Revised Municipal Code client + parser (BL-20260509-05, "spec 016.b").

Spec 016 shipped the Colorado statute tree and explicitly deferred municipal
ordinances. This module is the deferred half: it turns one chapter of the
Denver Revised Municipal Code into an
:class:`~law_ai.core.schemas.ordinance_extraction.OrdinanceExtraction` that
:class:`~law_ai.ingestionapp.services.ordinance_scout.OrdinanceScout` can route
to the graph or to the HITL queue.

Structure mirrors
:mod:`law_ai.ingestionapp.services.colorado_statutes` deliberately — async
httpx + tenacity client, a deterministic lxml parser, all markup hooks in one
constant block so an upstream redesign surfaces as a single failing test.

Licence + access posture
------------------------
The DRMC text is a municipal government work and is not itself copyrightable,
but the *hosting* is not open: library.municode.com serves the code through a
JavaScript client under terms of use that prohibit systematic downloading, and
the pages a browser renders are not the pages an HTTP client receives. So:

* **v1 is offline.** The parser is the product; the client exists, is pointed
  at a configurable base URL (``DENVER_MUNICIPAL_CODE_BASE_URL``), and is
  never exercised by the test suite. Every test runs against a checked-in
  fixture, and the CLI's ``--chapter-dir`` reads local HTML.
* **Every fetched document is quarantined.** The adapter sets
  ``requires_human_approval = True``, so nothing from this source can reach
  the graph without a person (constitution §5), regardless of the parser's
  confidence score.

See [docs/data-sources.md](../../../../docs/data-sources.md) for the full entry.
"""

from __future__ import annotations

import logging
import os
import re
from collections.abc import AsyncIterator, Iterable
from datetime import date
from statistics import mean

import httpx
from lxml import html as lxml_html
from lxml.html import HtmlElement
from tenacity import (
    AsyncRetrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from law_ai.core.provenance import provenance
from law_ai.core.schemas.ordinance_extraction import (
    OrdinanceExtraction,
    OrdinanceSectionPayload,
)

logger = logging.getLogger("law_ai.ingestion.denver_municipal_code")

DEFAULT_BASE_URL = "https://library.municode.com/co/denver/codes/code_of_ordinances"
DEFAULT_TIMEOUT = 30.0
USER_AGENT = (
    "law-ai/0.1 (Denver municipal code ingestion; " "+https://github.com/bamr87/law-ai)"
)

JURISDICTION_CODE = "us-co-denver"
JURISDICTION_NAME = "Denver, Colorado"
CODE_TITLE = "Denver Revised Municipal Code"
#: Prefix every id shares; the chapter or section number completes it.
ID_PREFIX = "us-co-denver/dmc"
CITATION_PREFIX = "D.R.M.C."

#: Municode "chunk" markup hooks. If Municode redesigns, this is the only
#: block that needs updating (the same contract spec 016 made for Justia).
SECTION_CLASS = "chunk-section"
SECTION_DESIGNATOR_CLASS = "chunk-title-designator"
SECTION_HEADING_CLASS = "chunk-title-text"
SECTION_CONTENT_CLASS = "chunk-content"
HISTORY_NOTE_CLASS = "history-note"
CHAPTER_TITLE_CLASS = "chunk-title-chapter"

#: "Sec. 38-31." / "§ 38-31" / "38-31." — the designator a municipal code
#: prints ahead of a section heading. The number is chapter-section, and may
#: carry a decimal or letter suffix (``38-31.5``, ``38-31a``).
_SECTION_NUMBER_RE = re.compile(
    r"(?:sec\.?|section|§)?\s*(\d{1,3}-\d{1,4}(?:\.\d+)?[A-Za-z]?)\b",
    re.IGNORECASE,
)
_CHAPTER_NUMBER_RE = re.compile(r"chapter\s+(\d{1,3})", re.IGNORECASE)

#: Municipal history notes date their amendments as "5-31-05" or "5-31-2005".
_HISTORY_DATE_RE = re.compile(r"\b(\d{1,2})-(\d{1,2})-(\d{2}|\d{4})\b")


class DenverMunicipalCodeError(RuntimeError):
    """Raised on non-retryable upstream failures."""


def _is_retryable(exc: BaseException) -> bool:
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code in (429, 500, 502, 503, 504)
    return isinstance(exc, (httpx.TransportError, httpx.TimeoutException))


class DenverMunicipalCodeClient:
    """Async fetcher for DRMC chapter documents.

    Present for parity with the other source clients and for operators who
    point ``DENVER_MUNICIPAL_CODE_BASE_URL`` at a mirror they are permitted to
    crawl. **Not exercised by the test suite** — see the module docstring.
    """

    def __init__(
        self,
        *,
        base_url: str | None = None,
        timeout: float = DEFAULT_TIMEOUT,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._base_url = (
            base_url
            or os.environ.get("DENVER_MUNICIPAL_CODE_BASE_URL")
            or DEFAULT_BASE_URL
        ).rstrip("/")
        self._timeout = timeout
        self._owns_client = client is None
        headers = {"Accept": "text/html", "User-Agent": USER_AGENT}
        self._client = client or httpx.AsyncClient(
            base_url=self._base_url, timeout=self._timeout, headers=headers
        )

    async def __aenter__(self) -> DenverMunicipalCodeClient:
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    def url_for_chapter(self, chapter: str) -> str:
        """Canonical URL for one chapter of the code."""
        return f"{self._base_url}/chapter-{chapter}/"

    async def _get(self, path: str) -> str:
        async for attempt in AsyncRetrying(
            stop=stop_after_attempt(3),
            wait=wait_exponential(multiplier=0.5, min=0.5, max=8.0),
            retry=retry_if_exception_type((httpx.HTTPError,)),
            reraise=True,
        ):
            with attempt:
                response = await self._client.get(path)
                if response.status_code >= 400:
                    if not _is_retryable(
                        httpx.HTTPStatusError(
                            "non-retryable",
                            request=response.request,
                            response=response,
                        )
                    ):
                        raise DenverMunicipalCodeError(
                            f"denver_municipal_code {response.status_code} for "
                            f"{path}: {response.text[:200]}"
                        )
                    response.raise_for_status()
                provenance.log_graph_query(
                    cypher=f"GET {path}",
                    params={},
                    result_count=1,
                    latency_ms=response.elapsed.total_seconds() * 1000,
                )
                return response.text
        # AsyncRetrying with reraise=True always exits through the loop body
        # or by re-raising, so this is only here to satisfy the type checker.
        raise DenverMunicipalCodeError(  # pragma: no cover
            f"denver_municipal_code exhausted retries for {path}"
        )

    async def fetch_chapter(self, chapter: str) -> str:
        """Fetch the raw HTML for one DRMC chapter."""
        return await self._get(f"/chapter-{chapter}/")

    async def iter_chapters(
        self, chapters: Iterable[str]
    ) -> AsyncIterator[tuple[str, str]]:
        """Yield ``(chapter, html)`` pairs for each requested chapter."""
        for chapter in chapters:
            yield chapter, await self.fetch_chapter(chapter)


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------


def _strip_noise(tree: HtmlElement) -> None:
    """Drop ``<script>``/``<style>`` so they cannot leak into section text.

    NFR-SEC-1: parsed text is later rendered in the Analysis Studio, so no
    executable markup is carried downstream.
    """
    for tag in tree.xpath("//script | //style"):
        parent = tag.getparent()
        if parent is not None:
            parent.remove(tag)


def _first_class(parent: HtmlElement, class_name: str) -> HtmlElement | None:
    for el in parent.find_class(class_name):
        return el
    return None


def _text(el: HtmlElement | None, *, sep: str = " ") -> str:
    """Whitespace-collapsed text of an element, or ``""`` when missing."""
    if el is None:
        return ""
    raw = el.text_content()
    if sep == "\n":
        lines = [re.sub(r"\s+", " ", line).strip() for line in raw.splitlines()]
        return "\n".join(line for line in lines if line)
    return re.sub(r"\s+", " ", raw).strip()


def section_number(designator: str) -> str | None:
    """Pull the ``38-31``-shaped section number out of a designator string."""
    match = _SECTION_NUMBER_RE.search(designator or "")
    return match.group(1) if match else None


def parse_history_date(note: str | None) -> date | None:
    """Latest amendment date printed in a history note, or ``None``.

    Municipal history notes carry the enactment trail — ``(Ord. No. 342-05,
    § 1, 5-31-05; Ord. No. 20-11, § 2, 1-18-11)`` — and the *last* date is the
    one the current text took effect on. Two-digit years are read as 20xx for
    00-69 and 19xx above, which is the only reading that makes sense for a
    code whose oldest notes are 1950s ordinances.
    """
    if not note:
        return None
    latest: date | None = None
    for month, day, year in _HISTORY_DATE_RE.findall(note):
        y = int(year)
        if len(year) == 2:
            y += 2000 if y < 70 else 1900
        try:
            parsed = date(y, int(month), int(day))
        except ValueError:
            continue
        if latest is None or parsed > latest:
            latest = parsed
    return latest


def score_section(*, text: str, number: str | None, heading: str) -> float:
    """Rule-based per-section confidence in ``[0, 1]``.

    Same conservative shape as the CRS scorer: a section needs a parseable
    number, a real heading, and substantive body text. Municipal codes are
    full of one-line "Reserved." and "Editor's note" stubs, and those must
    score below the HITL threshold rather than entering the graph as law.
    """
    score = 0.5
    if number:
        score += 0.2
    stripped_heading = heading.strip(" .§")
    if stripped_heading and len(stripped_heading) > 4:
        score += 0.15
    body = text.strip()
    if len(body) >= 80:
        score += 0.15
    elif len(body) < 20:
        score -= 0.4
    # "Reserved." / "Repealed." carry no law; they exist to keep the
    # numbering contiguous. Never commit one as an ordinance section.
    if re.match(r"^\(?(reserved|repealed)\b", body, re.IGNORECASE):
        score = min(score, 0.3)
    return max(0.0, min(1.0, score))


def section_id(number: str) -> str:
    """Build the spec-015 ``OrdinanceSection.id`` for a DRMC section."""
    return f"{ID_PREFIX}/{number}"


def ordinance_id(chapter: str) -> str:
    """Build the spec-015 ``Ordinance.id`` for a DRMC chapter."""
    return f"{ID_PREFIX}/chapter-{chapter.removeprefix('chapter-')}"


def parse_chapter_html(
    chapter: str, html: str, *, source_url: str | None = None
) -> OrdinanceExtraction:
    """Parse one DRMC chapter page into an :class:`OrdinanceExtraction`.

    Parameters
    ----------
    chapter:
        The chapter number as it appears in the code, e.g. ``"38"``.
    html:
        Raw page HTML — from :meth:`DenverMunicipalCodeClient.fetch_chapter`
        or, in every test and in the CLI's offline mode, a local fixture.
    source_url:
        Canonical URL for provenance.

    A chapter with no recognisable sections yields an extraction with an
    empty ``sections`` list and ``confidence == 0.0``: an honest "nothing
    parsed", never a fabricated section.
    """
    tree = lxml_html.fromstring(html)
    _strip_noise(tree)

    heading_el = _first_class(tree, CHAPTER_TITLE_CLASS)
    chapter_title = _text(heading_el) or f"Chapter {chapter}"
    chapter_match = _CHAPTER_NUMBER_RE.search(chapter_title)
    chapter_number = chapter_match.group(1) if chapter_match else str(chapter)

    sections: list[OrdinanceSectionPayload] = []
    seen: set[str] = set()
    for el in tree.find_class(SECTION_CLASS):
        designator = _text(_first_class(el, SECTION_DESIGNATOR_CLASS))
        heading = _text(_first_class(el, SECTION_HEADING_CLASS))
        number = section_number(designator) or section_number(heading)
        if not number:
            # An `id` attribute is Municode's other carrier of the number.
            number = section_number(el.get("id") or "")
        if not number or number in seen:
            continue
        seen.add(number)

        content_el = _first_class(el, SECTION_CONTENT_CLASS)
        note = _text(_first_class(el, HISTORY_NOTE_CLASS))
        body = _text(content_el, sep="\n")
        sections.append(
            OrdinanceSectionPayload(
                id=section_id(number),
                citation=f"{CITATION_PREFIX} § {number}",
                heading=heading or designator,
                text=body,
                effective_from=parse_history_date(note),
                history_note=note,
                confidence=round(
                    score_section(text=body, number=number, heading=heading), 4
                ),
            )
        )

    aggregate = round(mean(s.confidence for s in sections), 4) if sections else 0.0
    return OrdinanceExtraction(
        jurisdiction_code=JURISDICTION_CODE,
        jurisdiction_name=JURISDICTION_NAME,
        jurisdiction_level="municipal",
        ordinance_id=ordinance_id(chapter_number),
        ordinance_title=chapter_title,
        ordinance_citation=f"{CITATION_PREFIX} ch. {chapter_number}",
        sections=sections,
        confidence=aggregate,
        source="denver_municipal_code",
        source_url=source_url,
    )
