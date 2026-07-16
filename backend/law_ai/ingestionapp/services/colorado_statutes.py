"""Colorado Revised Statutes (CRS) HTML client + parser (spec 016 T-002).

Source: clean public HTML at ``law.justia.com/codes/colorado/<year>/title-N/...``.
The underlying CRS text is uncopyrightable government work; Justia commentary
is CC-BY. We store provenance (`source_url`) on every persisted node and
mark cached HTML as ``redistribution: false`` in the operator's downstream
export pipeline (see [docs/data-sources.md](../../../../docs/data-sources.md)).

Design: mirror :class:`law_ai.ingestionapp.services.courtlistener.CourtListenerClient`
(async httpx + tenacity + provenance logging). The parser is deterministic
and unit-tested against a checked-in fixture so changes to Justia HTML
surface as a single failing test.
"""

from __future__ import annotations

import logging
import os
import re
from collections.abc import AsyncIterator, Iterable
from datetime import date, datetime
from statistics import mean

import httpx
from lxml import html as lxml_html
from lxml.html import HtmlElement
from tenacity import (
    AsyncRetrying,
    RetryError,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from law_ai.core.provenance import provenance
from law_ai.core.schemas.statute_extraction import (
    StatuteExtraction,
    StatuteSectionPayload,
)

logger = logging.getLogger("law_ai.ingestion.colorado_statutes")

DEFAULT_BASE_URL = "https://law.justia.com/codes/colorado/2024"
DEFAULT_TIMEOUT = 30.0
USER_AGENT = (
    "law-ai/0.1 (Colorado statutes ingestion; +https://github.com/bamr87/law-ai)"
)

JURISDICTION_CODE = "us-co"
JURISDICTION_NAME = "Colorado"
CODE_ID = "us-co/crs"
CODE_TITLE = "Colorado Revised Statutes"

# Justia CSS hooks. If Justia changes their markup, this is the only block
# that needs updating (R-1 in spec.md).
SECTION_SELECTOR = "article.codes-section"
SECTION_HEADING_SELECTOR = "h3.section-heading"
SECTION_NUMBER_SELECTOR = "span.section-number"
SECTION_TEXT_SELECTOR = "div.section-text"
EFFECTIVE_DATE_SELECTOR = "p.effective-date"
TITLE_HEADING_SELECTOR = "h1.codes-title"

_SECTION_NUMBER_RE = re.compile(r"§\s*([\d\-]+(?:\.\d+)?)")
_TITLE_NUMBER_RE = re.compile(r"Title\s+(\d+[A-Z]?)", re.IGNORECASE)
_EFFECTIVE_DATE_RE = re.compile(
    r"Effective:\s*([A-Za-z]+\s+\d{1,2},\s+\d{4})", re.IGNORECASE
)


class ColoradoStatutesError(RuntimeError):
    """Raised on non-retryable upstream failures."""


def _is_retryable(exc: BaseException) -> bool:
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code in (429, 500, 502, 503, 504)
    return isinstance(exc, (httpx.TransportError, httpx.TimeoutException))


class ColoradoStatutesClient:
    """Async fetcher for CRS title pages.

    Parameters
    ----------
    base_url:
        Override via ``COLORADO_STATUTES_BASE_URL`` env var (useful for
        local mirror testing).
    """

    def __init__(
        self,
        *,
        base_url: str | None = None,
        timeout: float = DEFAULT_TIMEOUT,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._base_url = (
            base_url or os.environ.get("COLORADO_STATUTES_BASE_URL") or DEFAULT_BASE_URL
        ).rstrip("/")
        self._timeout = timeout
        self._owns_client = client is None
        headers = {"Accept": "text/html", "User-Agent": USER_AGENT}
        self._client = client or httpx.AsyncClient(
            base_url=self._base_url, timeout=self._timeout, headers=headers
        )

    async def __aenter__(self) -> ColoradoStatutesClient:
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    def url_for_title(self, title: str) -> str:
        """Return the canonical URL for a CRS title page."""
        return f"{self._base_url}/title-{title}/"

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
                        raise ColoradoStatutesError(
                            f"colorado_statutes {response.status_code} for {path}: "
                            f"{response.text[:200]}"
                        )
                    response.raise_for_status()
                provenance.log_graph_query(
                    cypher=f"GET {path}",
                    params={},
                    result_count=1,
                    latency_ms=response.elapsed.total_seconds() * 1000,
                )
                return response.text
        raise RetryError("unreachable")  # pragma: no cover

    async def fetch_title(self, title: str) -> str:
        """Fetch the raw HTML for one CRS title."""
        return await self._get(f"/title-{title}/")

    async def iter_titles(
        self, titles: Iterable[str]
    ) -> AsyncIterator[tuple[str, str]]:
        """Yield ``(title_id, html)`` pairs for each requested title."""
        for title in titles:
            html = await self.fetch_title(title)
            yield title, html


# ---------------------------------------------------------------------------
# Parser (pure, deterministic — unit-tested on fixture HTML)
# ---------------------------------------------------------------------------


def _strip_noise(tree: HtmlElement) -> None:
    """Remove ``<script>`` and ``<style>`` so they cannot leak into ``text``.

    NFR-SEC-1: parsed text is later rendered in the Analysis Studio; we
    refuse to carry any executable markup downstream.
    """
    for tag in tree.xpath("//script | //style"):
        parent = tag.getparent()
        if parent is not None:
            parent.remove(tag)


def _first_class(
    parent: HtmlElement, class_name: str, tag: str | None = None
) -> HtmlElement | None:
    """Return the first descendant with ``class_name`` (optionally constrained to ``tag``)."""
    for el in parent.find_class(class_name):
        if tag is None or el.tag == tag:
            return el
    return None


def _text(el: HtmlElement | None, *, sep: str = " ") -> str:
    """Whitespace-collapsed text content of an element, or ``""`` if missing."""
    if el is None:
        return ""
    raw = el.text_content()
    if sep == "\n":
        # Preserve paragraph breaks, collapse intra-line whitespace.
        lines = [re.sub(r"\s+", " ", line).strip() for line in raw.splitlines()]
        return "\n".join(line for line in lines if line)
    return re.sub(r"\s+", " ", raw).strip()


def _parse_effective_date(text: str | None) -> date | None:
    if not text:
        return None
    match = _EFFECTIVE_DATE_RE.search(text)
    if not match:
        return None
    try:
        return datetime.strptime(match.group(1), "%B %d, %Y").date()
    except ValueError:
        return None


def _section_number(heading: str) -> str | None:
    match = _SECTION_NUMBER_RE.search(heading)
    return match.group(1) if match else None


def _score_section(*, text: str, number: str | None, heading: str) -> float:
    """Rule-based per-section confidence in ``[0, 1]``.

    Conservative: a section needs (a) a parseable section number, (b) a
    heading beyond the bare ``§`` marker, (c) substantive body text
    (>= 80 chars). Anything weaker quarantines.
    """
    score = 0.5
    if number:
        score += 0.2
    if heading.strip(" .§") and not heading.strip().endswith("§") and len(heading) > 6:
        score += 0.15
    body_len = len(text.strip())
    if body_len >= 80:
        score += 0.15
    elif body_len < 20:
        score -= 0.4
    return max(0.0, min(1.0, score))


def _section_id(title_id: str, number: str) -> str:
    """Build the spec-015 ``StatuteSection.id`` from title + section number."""
    title_num = title_id.removeprefix("us-co/crs/title-")
    if number.startswith(f"{title_num}-"):
        return f"us-co/crs/{number}"
    return f"us-co/crs/{title_num}-{number.lstrip('-')}"


def parse_title_html(
    title_id: str, html: str, *, source_url: str | None = None
) -> StatuteExtraction:
    """Parse one CRS title HTML page into a :class:`StatuteExtraction`.

    Parameters
    ----------
    title_id:
        The spec-015 ``Statute.id``, e.g. ``"us-co/crs/title-18"``.
    html:
        Raw page HTML (from :meth:`ColoradoStatutesClient.fetch_title` or
        a checked-in fixture).
    source_url:
        Canonical URL for provenance. Defaults to ``None`` (caller may
        fill in afterwards).
    """
    tree = lxml_html.fromstring(html)
    _strip_noise(tree)

    title_heading = _first_class(tree, "codes-title", tag="h1")
    statute_title = (
        _text(title_heading)
        if title_heading is not None
        else f"CRS {title_id.removeprefix('us-co/crs/')}"
    )
    title_number_match = _TITLE_NUMBER_RE.search(statute_title)
    statute_citation = (
        f"C.R.S. Title {title_number_match.group(1)}" if title_number_match else None
    )

    sections: list[StatuteSectionPayload] = []
    articles = [el for el in tree.find_class("codes-section") if el.tag == "article"]
    for article in articles:
        heading_el = _first_class(article, "section-heading", tag="h3")
        text_el = _first_class(article, "section-text", tag="div")
        eff_el = _first_class(article, "effective-date", tag="p")

        heading = _text(heading_el)
        number = _section_number(heading)
        if number is None:
            # Fallback to the article id attribute (Justia uses it).
            number = (article.get("id") or "").strip() or None
        if not number:
            continue

        text_block = _text(text_el, sep="\n")
        confidence = _score_section(text=text_block, number=number, heading=heading)
        sec_id = _section_id(title_id, number)
        citation = f"C.R.S. § {number}"

        sections.append(
            StatuteSectionPayload(
                id=sec_id,
                citation=citation,
                heading=heading,
                text=text_block,
                effective_from=_parse_effective_date(_text(eff_el) or None),
                confidence=round(confidence, 4),
            )
        )

    aggregate = round(mean(s.confidence for s in sections), 4) if sections else 0.0
    return StatuteExtraction(
        jurisdiction_code=JURISDICTION_CODE,
        jurisdiction_name=JURISDICTION_NAME,
        jurisdiction_level="state",
        code_id=CODE_ID,
        code_title=CODE_TITLE,
        statute_id=title_id,
        statute_title=statute_title,
        statute_citation=statute_citation,
        sections=sections,
        confidence=aggregate,
        source="colorado_statutes",
        source_url=source_url,
    )
