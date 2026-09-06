"""PDF fallback for CRS publications (BL-20260509-06, spec 016 NG1).

The parser is exercised through a faked page extractor so the suite does not
depend on a binary fixture; one extra test runs the real ``pypdf`` extractor
over a PDF built in-test, and is skipped when the optional dependency is not
installed in the image yet.
"""

from __future__ import annotations

import importlib.util
import tomllib
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx

from law_ai.ingestionapp.services import colorado_statutes as co
from law_ai.ingestionapp.services.colorado_statutes import (
    PDF_CONFIDENCE_PENALTY,
    ColoradoStatutesClient,
    ColoradoStatutesError,
    parse_title_html,
    parse_title_pdf,
)

HTML_FIXTURE = (
    Path(__file__).parent / "fixtures" / "co" / "title_18_article_3.html"
).read_text(encoding="utf-8")

_BODY = (
    "Any person who, after deliberation and with the intent to cause the "
    "death of a person other than himself, causes the death of that person "
    "or of another person commits the offense described in this section. "
    "Effective: July 1, 2021"
)

# Two pages, each carrying the running header/footer a CRS PDF stamps on
# every page, and together covering the same six sections as the HTML fixture.
PDF_PAGES = [
    "COLORADO REVISED STATUTES\n"
    "18-3-101. Homicide - definition of terms\n" + _BODY + "\n"
    "18-3-102. Murder in the first degree\n" + _BODY + "\n"
    "18-3-103. Murder in the second degree\n" + _BODY + "\n"
    "Page 1 of 2",
    "COLORADO REVISED STATUTES\n"
    "18-3-104. Manslaughter\n" + _BODY + "\n"
    "18-3-105. Criminally negligent homicide\n" + _BODY + "\n"
    "18-3-106. Vehicular homicide\n" + _BODY + "\n"
    "Page 2 of 2",
]


@pytest.fixture
def fake_pdf(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(co, "_pdf_page_texts", lambda data: list(PDF_PAGES))


# ---------------------------------------------------------------------------
# Parser parity with the HTML path
# ---------------------------------------------------------------------------


def test_pdf_sections_match_the_html_section_ids(fake_pdf: None) -> None:
    pdf = parse_title_pdf("us-co/crs/title-18", b"%PDF-fake")
    html = parse_title_html("us-co/crs/title-18", HTML_FIXTURE)
    assert [s.id for s in pdf.sections] == [s.id for s in html.sections]
    assert [s.citation for s in pdf.sections] == [s.citation for s in html.sections]


def test_pdf_extraction_envelope_matches_the_html_path(fake_pdf: None) -> None:
    extraction = parse_title_pdf(
        "us-co/crs/title-18", b"%PDF-fake", source_url="file:///title-18.pdf"
    )
    assert extraction.jurisdiction_code == co.JURISDICTION_CODE
    assert extraction.code_id == co.CODE_ID
    assert extraction.statute_id == "us-co/crs/title-18"
    assert extraction.statute_citation == "C.R.S. Title 18"
    assert extraction.source == "colorado_statutes"
    assert extraction.source_url == "file:///title-18.pdf"


def test_pdf_sections_carry_heading_body_and_effective_date(fake_pdf: None) -> None:
    section = parse_title_pdf("us-co/crs/title-18", b"%PDF-fake").sections[1]
    assert section.citation == "C.R.S. § 18-3-102"
    assert "Murder in the first degree" in section.heading
    assert "after deliberation" in section.text
    assert section.effective_from is not None
    assert section.effective_from.year == 2021


def test_running_headers_are_stripped_from_section_bodies(fake_pdf: None) -> None:
    extraction = parse_title_pdf("us-co/crs/title-18", b"%PDF-fake")
    for section in extraction.sections:
        assert "COLORADO REVISED STATUTES" not in section.text
        assert "Page 1 of 2" not in section.text


def test_pdf_confidence_is_penalised_below_the_hitl_threshold(fake_pdf: None) -> None:
    """Column-interleaved text must never auto-commit (spec 016 NG1)."""
    pdf = parse_title_pdf("us-co/crs/title-18", b"%PDF-fake")
    html = parse_title_html("us-co/crs/title-18", HTML_FIXTURE)
    assert PDF_CONFIDENCE_PENALTY > 0.3, "must keep the max PDF score under 0.7"
    assert all(s.confidence < 0.7 for s in pdf.sections)
    assert pdf.confidence < html.confidence


def test_pdf_with_no_recognisable_sections_yields_empty_extraction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(co, "_pdf_page_texts", lambda data: ["front matter only"])
    extraction = parse_title_pdf("us-co/crs/title-18", b"%PDF-fake")
    assert extraction.sections == []
    assert extraction.confidence == 0.0


# ---------------------------------------------------------------------------
# Client fallback
# ---------------------------------------------------------------------------


def test_pdf_url_is_none_without_configuration(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("COLORADO_STATUTES_PDF_BASE_URL", raising=False)
    assert ColoradoStatutesClient().pdf_url_for_title("18") is None


def test_pdf_url_supports_a_template(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(
        "COLORADO_STATUTES_PDF_BASE_URL", "https://pdf.test/crs-{title}.pdf"
    )
    assert (
        ColoradoStatutesClient().pdf_url_for_title("18")
        == "https://pdf.test/crs-18.pdf"
    )


@pytest.mark.asyncio
@respx.mock
async def test_fetch_title_document_falls_back_to_pdf(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("COLORADO_STATUTES_PDF_BASE_URL", "https://pdf.test/crs")
    respx.get(url__regex=r".*/title-18/").mock(return_value=httpx.Response(404))
    pdf_route = respx.get("https://pdf.test/crs/title-18.pdf").mock(
        return_value=httpx.Response(200, content=b"%PDF-1.4 fake")
    )
    async with ColoradoStatutesClient() as client:
        fmt, document = await client.fetch_title_document("18")
    assert fmt == "pdf"
    assert document == b"%PDF-1.4 fake"
    assert pdf_route.called


@pytest.mark.asyncio
@respx.mock
async def test_fetch_title_document_prefers_html(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("COLORADO_STATUTES_PDF_BASE_URL", "https://pdf.test/crs")
    respx.get(url__regex=r".*/title-18/").mock(
        return_value=httpx.Response(200, text=HTML_FIXTURE)
    )
    async with ColoradoStatutesClient() as client:
        fmt, document = await client.fetch_title_document("18")
    assert fmt == "html"
    assert "codes-section" in str(document)


@pytest.mark.asyncio
@respx.mock
async def test_html_failure_propagates_when_no_pdf_is_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A silent format switch would be worse than a loud failure."""
    monkeypatch.delenv("COLORADO_STATUTES_PDF_BASE_URL", raising=False)
    respx.get(url__regex=r".*/title-18/").mock(return_value=httpx.Response(404))
    async with ColoradoStatutesClient() as client:
        with pytest.raises(ColoradoStatutesError):
            await client.fetch_title_document("18")


@pytest.mark.asyncio
async def test_fetch_title_pdf_without_configuration_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("COLORADO_STATUTES_PDF_BASE_URL", raising=False)
    async with ColoradoStatutesClient() as client:
        with pytest.raises(ColoradoStatutesError, match="COLORADO_STATUTES_PDF"):
            await client.fetch_title_pdf("18")


# ---------------------------------------------------------------------------
# Dependency + real extractor
# ---------------------------------------------------------------------------


def test_pypdf_is_declared_as_a_dependency() -> None:
    """The item's premise ("pypdf already in stack") was false; fix it here."""
    pyproject = Path(__file__).resolve().parents[2] / "pyproject.toml"
    with pyproject.open("rb") as fh:
        data = tomllib.load(fh)
    assert any(
        dep.startswith("pypdf") for dep in data["project"]["dependencies"]
    ), "pypdf must be declared for the PDF fallback path"


def _minimal_pdf(lines: list[str]) -> bytes:
    """Build a one-page PDF with ``lines`` of Helvetica text, no dependencies."""
    text_ops = "BT /F1 12 Tf 40 750 Td 14 TL\n"
    for line in lines:
        escaped = line.replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)")
        text_ops += f"({escaped}) Tj T*\n"
    text_ops += "ET"
    stream = text_ops.encode("latin-1")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>",
        b"<< /Length "
        + str(len(stream)).encode()
        + b" >>\nstream\n"
        + stream
        + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for index, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{index} 0 obj\n".encode() + body + b"\nendobj\n"
    xref_at = len(out)
    out += f"xref\n0 {len(objects) + 1}\n".encode()
    out += b"0000000000 65535 f \n"
    for offset in offsets:
        out += f"{offset:010d} 00000 n \n".encode()
    out += (
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
        f"startxref\n{xref_at}\n%%EOF\n"
    ).encode()
    return bytes(out)


@pytest.mark.skipif(
    importlib.util.find_spec("pypdf") is None,
    reason="pypdf not installed in this image yet (declared in pyproject)",
)
def test_real_pypdf_extraction_finds_sections() -> None:
    pdf = _minimal_pdf(
        [
            "18-3-101. Homicide - definition of terms",
            "Any person who commits the offense described in this section.",
            "18-3-102. Murder in the first degree",
            "Any person who after deliberation causes the death of another.",
        ]
    )
    extraction = parse_title_pdf("us-co/crs/title-18", pdf)
    assert [s.id for s in extraction.sections] == [
        "us-co/crs/18-3-101",
        "us-co/crs/18-3-102",
    ]


def test_page_text_extractor_is_imported_lazily() -> None:
    """No module-level pypdf import: the fallback must not tax normal runs."""
    source = Path(co.__file__).read_text(encoding="utf-8")
    head = source.split("class ColoradoStatutesError", 1)[0]
    assert "pypdf" not in head
    assert "from pypdf import PdfReader" in source


def test_cli_exposes_a_pdf_dir_option() -> None:
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
    import ingest_sample  # type: ignore[import-not-found]

    parser_help = ingest_sample.main.__doc__ or ""
    assert parser_help is not None  # keeps the import meaningful
    with pytest.raises(SystemExit):
        ingest_sample.main(["--source", "colorado_statutes", "--pdf-dir"])


def test_cli_pdf_dir_parses_local_files(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: Any
) -> None:
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
    import ingest_sample  # type: ignore[import-not-found]

    monkeypatch.setattr(co, "_pdf_page_texts", lambda data: list(PDF_PAGES))
    (tmp_path / "title-18.pdf").write_bytes(b"%PDF-fake")
    rc = ingest_sample.main(
        [
            "--source",
            "colorado_statutes",
            "--titles",
            "18",
            "--pdf-dir",
            str(tmp_path),
            "--dry-run",
        ]
    )
    assert rc == 0
    out = capsys.readouterr().out
    # Every PDF section is penalised below the threshold → all pending.
    assert "committed=0" in out
    assert "pending=6" in out
    assert "skipped=0" in out
