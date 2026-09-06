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

A **PDF fallback** (BL-20260509-06) covers the case where the HTML source is
unavailable — an upstream outage, or a title only published as a LexisNexis
CRS PDF. :func:`parse_title_pdf` emits the same
:class:`~law_ai.core.schemas.statute_extraction.StatuteExtraction` as
:func:`parse_title_html`, with deliberately lower per-section confidence:
CRS PDFs are column-laid-out and naive text extraction interleaves columns,
so every PDF-derived section stays under the HITL threshold and is reviewed
by a human before it reaches the graph.
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

# PDF fallback (BL-20260509-06). CRS PDFs print section starts as
# "18-3-102. Murder in the first degree." (the § is often dropped), one per
# line, so a line-anchored match is the reliable split point.
_PDF_SECTION_RE = re.compile(
    r"(?m)^[ \t]*(?:§[ \t]*)?(\d+[A-Z]?(?:-\d+)+(?:\.\d+)?)\.[ \t]*(.*)$"
)

#: Every PDF-derived section is penalised by this much so column-interleaved
#: text can never clear ``CONFIDENCE_THRESHOLD`` (0.7) on its own — spec 016
#: NG1 wanted PDFs behind HITL, not silently trusted. ``_score_section`` tops
#: out at 1.0, so the penalty must exceed 0.3 for that guarantee to hold.
PDF_CONFIDENCE_PENALTY = 0.35

#: How many lines at the top and bottom of a page count as "the edge", where
#: running headers and footers live.
_EDGE_LINES = 2

#: Running page numbers ("Page 3 of 41") vary per page, so the
#: repeated-line filter cannot catch them.
_PAGE_NUMBER_RE = re.compile(r"^\s*(?:Page\s+)?\d+(?:\s+of\s+\d+)?\s*$", re.I)


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

    # -- PDF fallback (BL-20260509-06) ---------------------------------

    def pdf_url_for_title(self, title: str) -> str | None:
        """Canonical PDF URL for a title, or ``None`` when none is configured.

        Set ``COLORADO_STATUTES_PDF_BASE_URL`` to the directory holding the
        LexisNexis CRS title PDFs; ``{title}`` in the value is substituted,
        otherwise ``title-<N>.pdf`` is appended.
        """
        base = os.environ.get("COLORADO_STATUTES_PDF_BASE_URL", "").strip()
        if not base:
            return None
        if "{title}" in base:
            return base.replace("{title}", title)
        return f"{base.rstrip('/')}/title-{title}.pdf"

    async def fetch_title_pdf(self, title: str) -> bytes:
        """Fetch the PDF publication for one CRS title."""
        url = self.pdf_url_for_title(title)
        if not url:
            raise ColoradoStatutesError(
                "no PDF source configured — set COLORADO_STATUTES_PDF_BASE_URL"
            )
        response = await self._client.get(url, headers={"Accept": "application/pdf"})
        if response.status_code >= 400:
            raise ColoradoStatutesError(
                f"colorado_statutes PDF {response.status_code} for {url}"
            )
        provenance.log_graph_query(
            cypher=f"GET {url}",
            params={"format": "pdf"},
            result_count=1,
            latency_ms=response.elapsed.total_seconds() * 1000,
        )
        return bytes(response.content)

    async def fetch_title_document(self, title: str) -> tuple[str, str | bytes]:
        """Fetch a title as ``("html", text)``, falling back to ``("pdf", bytes)``.

        The fallback only fires when the HTML fetch fails *and* a PDF source
        is configured (BL-20260509-06); otherwise the original HTML error
        propagates, because a silent format switch would be worse than a
        loud failure.
        """
        try:
            return "html", await self.fetch_title(title)
        except Exception as exc:
            if not self.pdf_url_for_title(title):
                raise
            logger.warning(
                "colorado_statutes HTML fetch failed for title %s (%s); "
                "falling back to the PDF publication",
                title,
                type(exc).__name__,
            )
            return "pdf", await self.fetch_title_pdf(title)


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


# ---------------------------------------------------------------------------
# PDF fallback parser (BL-20260509-06)
# ---------------------------------------------------------------------------


def _pdf_page_texts(pdf_bytes: bytes) -> list[str]:
    """Extract per-page text with ``pypdf`` (imported lazily).

    Lazy because the vast majority of runs never see a PDF, and because the
    import is only needed by the fallback path.
    """
    import io

    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(pdf_bytes))
    return [(page.extract_text() or "") for page in reader.pages]


def _strip_running_headers(pages: list[str]) -> str:
    """Join pages, dropping the repeated header/footer lines at page edges.

    CRS PDFs stamp the code name and a page number on every page; left in
    place they land inside the previous section's body text. Only the first
    and last few lines of each page are considered, so a sentence that
    legitimately repeats in the body is never discarded.
    """
    if len(pages) < 2:
        return "\n".join(pages)
    edge_counts: dict[str, int] = {}
    for page in pages:
        lines = [ln.strip() for ln in page.splitlines() if ln.strip()]
        for line in set(lines[:_EDGE_LINES] + lines[-_EDGE_LINES:]):
            edge_counts[line] = edge_counts.get(line, 0) + 1
    threshold = max(2, (len(pages) + 1) // 2)
    repeated = {line for line, n in edge_counts.items() if n >= threshold}

    kept: list[str] = []
    for page in pages:
        lines = page.splitlines()
        last = len(lines) - _EDGE_LINES
        for index, line in enumerate(lines):
            stripped = line.strip()
            at_edge = index < _EDGE_LINES or index >= last
            if at_edge and (stripped in repeated or _PAGE_NUMBER_RE.match(stripped)):
                continue
            kept.append(line)
    return "\n".join(kept)


def _collapse(raw: str) -> str:
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in raw.splitlines()]
    return "\n".join(line for line in lines if line)


def parse_title_pdf(
    title_id: str,
    pdf_bytes: bytes,
    *,
    source_url: str | None = None,
    statute_title: str | None = None,
) -> StatuteExtraction:
    """Parse one CRS title PDF into the same shape as :func:`parse_title_html`.

    Fallback for when the HTML source is unavailable (BL-20260509-06, spec
    016 NG1). Section ids, citations and the extraction envelope are
    identical to the HTML path — only ``confidence`` differs: every section
    is penalised by :data:`PDF_CONFIDENCE_PENALTY` so column-interleaved text
    is always reviewed by a human before it reaches the graph.
    """
    body = _strip_running_headers(_pdf_page_texts(pdf_bytes))
    matches = list(_PDF_SECTION_RE.finditer(body))

    sections: list[StatuteSectionPayload] = []
    for index, match in enumerate(matches):
        number = match.group(1)
        heading_text = _collapse(match.group(2) or "").strip()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(body)
        text_block = _collapse(body[match.end() : end])
        heading = f"§ {number}. {heading_text}".strip().rstrip(".")
        confidence = _score_section(text=text_block, number=number, heading=heading)
        sections.append(
            StatuteSectionPayload(
                id=_section_id(title_id, number),
                citation=f"C.R.S. § {number}",
                heading=heading,
                text=text_block,
                effective_from=_parse_effective_date(text_block),
                confidence=round(max(0.0, confidence - PDF_CONFIDENCE_PENALTY), 4),
            )
        )

    title_number_match = _TITLE_NUMBER_RE.search(statute_title or "") or re.search(
        r"title-(\d+[A-Z]?)", title_id
    )
    resolved_title = statute_title or f"CRS {title_id.removeprefix('us-co/crs/')}"
    aggregate = round(mean(s.confidence for s in sections), 4) if sections else 0.0
    return StatuteExtraction(
        jurisdiction_code=JURISDICTION_CODE,
        jurisdiction_name=JURISDICTION_NAME,
        jurisdiction_level="state",
        code_id=CODE_ID,
        code_title=CODE_TITLE,
        statute_id=title_id,
        statute_title=resolved_title,
        statute_citation=(
            f"C.R.S. Title {title_number_match.group(1)}"
            if title_number_match
            else None
        ),
        sections=sections,
        confidence=aggregate,
        source="colorado_statutes",
        source_url=source_url,
    )
