"""The ocrmd plug-in — scanned pages in, on two doors, and the scanner itself as a library.

`ocrmd <https://github.com/bamr87/ocrmd>`_ reads a photographed page twice — local OCR
engines and a vision model — and reconciles the readings, marking every disagreement
instead of silently choosing. It talks to other systems through one small contract
(``ocrmd/sinks.py`` over there): a receiver answers ``GET`` with a *descriptor* of the
options it takes and takes ``POST`` with an *envelope* — the page's reconciled text, its
provenance, the book's catalogue entry and the operator's options. Law AI is a receiver
twice over:

* ``POST /api/lsat/intake/ocr`` (:mod:`law_ai.lsat.services.ocr_intake`) turns a page
  into pending LSAT question drafts;
* ``POST /api/matters/<slug>/intake/ocrmd`` (:mod:`law_ai.matters.services.scanned`) files
  a page as a source document on a matter.

This module holds what both share — the envelope model, the descriptor shape — and, when
the ``ocrmd`` extra is installed and ``ENABLE_OCRMD`` is on, the scanner itself as a
library (``ocrmd.api.Library``), so an upload can be OCR'd *here* without a scanner rig
(``POST /api/ingestion/ocrmd/scan``, ``manage.py ocrmd_scan``).

**Provider policy.** The embedded library runs with ``provider=None``: OCR only, every
byte on this host. ocrmd's own vision pass would call Anthropic from inside a dependency,
bypassing ``law_ai.core.llm`` — the constitution §4 choke point — and the chain has no
image path yet (BL-20260907-13). Pages read here therefore arrive with *one* reading and
say so in their provenance (``llm_model`` empty, ``status`` ``unverified``); the
cross-checked path is a scanner rig posting to the doors above.
"""

from __future__ import annotations

import importlib
import importlib.util
import logging
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from django.conf import settings
from pydantic import BaseModel, ConfigDict, Field

from law_ai.core.provenance import provenance

logger = logging.getLogger("law_ai.ingestion.ocrmd")

TOOL = "ocrmd"
#: The version of the sink contract this module speaks (``ocrmd_sink`` in descriptors,
#: ``ocrmd`` in envelopes).
SINK_CONTRACT = 1
IMAGE_SUFFIXES = (".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".webp", ".pdf")


class Provenance(BaseModel):
    """Where a page came from, as the scanner reported it (the envelope's ``provenance``).

    Every field is optional because the caller is an external tool and a missing field
    must degrade the audit trail, not reject the page. ``page_id`` is the sha256 of the
    processed image — the scanner's own identity for the page, stable across re-runs and
    the way back to the exact photograph. ``agreement``/``overlap`` are the scanner's
    two-reading cross-check, carried through so a reviewer can see how much the OCR and
    the vision model disagreed before this text was made.
    """

    model_config = ConfigDict(extra="ignore")

    tool: str = TOOL
    tool_version: str = ""
    document: str = ""
    page: int | None = None
    page_id: str = ""
    page_label: str = ""
    captured_at: str = ""
    ocr_engine: str = ""
    llm_model: str = ""
    agreement: float | None = None
    overlap: float | None = None
    flagged_spans: int | None = None
    unresolved: int | None = None
    status: str = ""
    #: Region of the page, in page fractions, when the operator boxed one item.
    bbox: list[float] | None = None
    image_url: str = ""
    page_url: str = ""

    def is_traceable(self) -> bool:
        return bool(self.document and (self.page is not None or self.page_id))

    def caveats(self) -> list[str]:
        """What a reviewer should know about this reading, in the scanner's own terms."""
        out: list[str] = []
        if not self.llm_model:
            out.append(
                "one reading only: the scanner did not cross-check this page "
                "against a model"
            )
        if self.status in ("suspect", "illegible", "blank"):
            out.append(f"the scanner marked this page {self.status}")
        if self.unresolved:
            out.append(
                f"{self.unresolved} unresolved disagreement(s) between the two "
                "readings travel with the text"
            )
        return out


class DocumentMeta(BaseModel):
    """The scanner's catalogue entry for the book (its ``document.yaml``)."""

    model_config = ConfigDict(extra="ignore")

    slug: str = ""
    title: str | None = None
    author: list[str] | str | None = None
    kind: str | None = None
    year: int | str | None = None
    isbn: str | None = None
    citation_key: str | None = None
    tags: list[str] | None = None
    project: str | None = None

    def author_line(self) -> str:
        if isinstance(self.author, list):
            return ", ".join(str(a) for a in self.author)
        return str(self.author or "")


class Envelope(BaseModel):
    """What ocrmd POSTs to a receiver (``ocrmd.sinks.envelope``)."""

    model_config = ConfigDict(extra="ignore")

    ocrmd: int = SINK_CONTRACT
    kind: Literal["page", "region"] = "page"
    text: str = Field(min_length=1)
    provenance: Provenance = Field(default_factory=Provenance)
    document: DocumentMeta = Field(default_factory=DocumentMeta)
    options: dict[str, Any] = Field(default_factory=dict)

    def default_title(self) -> str:
        head = self.document.title or self.provenance.document or "scanned page"
        if self.provenance.page_label:
            return f"{head}, p. {self.provenance.page_label}"
        if self.provenance.page is not None:
            return f"{head}, page {self.provenance.page}"
        return head


def is_envelope(data: Mapping[str, Any]) -> bool:
    """Whether a request body is an ocrmd envelope rather than a door's own legacy shape."""
    return "text" in data and ("ocrmd" in data or "provenance" in data)


def option(
    key: str,
    type_: str,
    *,
    label: str | None = None,
    choices: Sequence[str] | None = None,
    default: Any = None,
    help_: str = "",
) -> dict[str, Any]:
    """One option in a descriptor: the scanner draws an input of ``type_`` for it."""
    out: dict[str, Any] = {"key": key, "type": type_, "label": label or key}
    if choices is not None:
        out["choices"] = list(choices)
    if default is not None:
        out["default"] = default
    if help_:
        out["help"] = help_
    return out


def descriptor(
    name: str,
    description: str,
    options: Sequence[dict[str, Any]],
    *,
    accepts: Sequence[str] = ("page", "region"),
) -> dict[str, Any]:
    """The document a door answers ``GET`` with: what it is and what it takes."""
    return {
        "ocrmd_sink": SINK_CONTRACT,
        "name": name,
        "description": description,
        "accepts": list(accepts),
        "options": list(options),
    }


# ---------------------------------------------------------------------------
# The scanner as a library
# ---------------------------------------------------------------------------


class OcrmdUnavailable(RuntimeError):
    """The embedded scanner cannot be used: disabled, or the extra is not installed."""


def enabled() -> bool:
    return bool(getattr(settings, "ENABLE_OCRMD", False))


def installed() -> bool:
    try:
        return importlib.util.find_spec("ocrmd.api") is not None
    except (ImportError, ValueError):
        return False


def version() -> str | None:
    if not installed():
        return None
    try:
        mod = importlib.import_module("ocrmd")
        return str(getattr(mod, "__version__", "") or "") or None
    except Exception:  # pragma: no cover - a broken install reads as absent
        return None


def root() -> Path:
    """Where the embedded scanner keeps its store. Relative paths hang off BASE_DIR
    (``/app`` in the container, ``./backend`` on the host), like ``var/autonomy``."""
    raw = Path(str(getattr(settings, "OCRMD_ROOT", "var/ocrmd") or "var/ocrmd"))
    if raw.is_absolute():
        return raw
    return Path(settings.BASE_DIR) / raw


def status() -> dict[str, Any]:
    """Doctor-as-data for the plug-in: what a UI or an operator needs to know first."""
    out: dict[str, Any] = {
        "enabled": enabled(),
        "installed": installed(),
        "version": version(),
        "root": str(root()),
        "max_pages": int(getattr(settings, "OCRMD_MAX_PAGES", 5)),
        "llm": "none — the embedded scanner runs OCR only (see ocrmd_plugin.py)",
        "engines": [],
        "doors": {
            "lsat": "/api/lsat/intake/ocr",
            "matter": "/api/matters/<slug>/intake/ocrmd",
            "scan": "/api/ingestion/ocrmd/scan",
        },
    }
    if out["installed"]:
        try:
            ocr = importlib.import_module("ocrmd.ocr")
            out["engines"] = [str(e) for e in ocr.available_engines()]
        except Exception as exc:  # pragma: no cover - engine probing is best effort
            out["engines_error"] = f"{type(exc).__name__}: {exc}"
    return out


def library() -> Any:
    """An ``ocrmd.api.Library`` over :func:`root`, OCR-only. Close it when done."""
    if not enabled():
        raise OcrmdUnavailable("the ocrmd plug-in is off (ENABLE_OCRMD=false)")
    if not installed():
        raise OcrmdUnavailable(
            "the ocrmd package is not installed — build the backend image with "
            "INSTALL_OCRMD=1 (the `ocrmd` extra in backend/pyproject.toml)"
        )
    api = importlib.import_module("ocrmd.api")
    return api.Library(root=root(), provider=None)


@dataclass
class ScanResult:
    """What became of one uploaded file: an envelope per page, and what did not become one."""

    document: str
    pages: list[dict[str, Any]] = field(default_factory=list)
    duplicates: int = 0
    rejected: int = 0
    unreadable: list[str] = field(default_factory=list)
    engine: str = ""

    def summary(self) -> str:
        text = f"{len(self.pages)} page(s) read into {self.document!r}"
        if self.duplicates:
            text += f", {self.duplicates} duplicate(s) skipped"
        if self.unreadable:
            text += f", {len(self.unreadable)} unreadable file(s)"
        if self.engine:
            text += f" ({self.engine}, OCR only)"
        return text


def scan_file(path: Path, doc: str, *, max_pages: int | None = None) -> ScanResult:
    """Read one image or PDF with the embedded scanner and return one envelope per page.

    OCR only (see the module docstring); every page's ``provenance`` says so. The
    envelopes carry no ``image_url``/``page_url`` — no scanner UI serves them here — but
    ``page_id`` and ``store_root`` are the way back to the processed image on disk.
    """
    lib = library()
    try:
        report = lib.ingest([path], doc, llm=False)
        out = ScanResult(
            document=doc,
            duplicates=int(report.duplicates),
            rejected=int(report.rejected),
            unreadable=[str(x) for x in report.unreadable],
        )
        pages = list(report.pages)
        if max_pages is not None:
            pages = pages[: max(0, max_pages)]
        for page in pages:
            env: dict[str, Any] = dict(lib.envelope(doc, int(page.sequence)))
            prov: dict[str, Any] = dict(env.get("provenance") or {})
            prov["image_url"] = ""
            prov["page_url"] = ""
            prov["store_root"] = str(root())
            env["provenance"] = prov
            out.pages.append(env)
        if pages:
            ocr_block = dict(pages[0].frontmatter.get("ocr") or {})
            out.engine = str(ocr_block.get("engine") or "")
    finally:
        lib.close()
    provenance.log_event(
        "ocrmd_scan",
        {
            "file": path.name,
            "document": doc,
            "pages": len(out.pages),
            "duplicates": out.duplicates,
            "rejected": out.rejected,
            "unreadable": len(out.unreadable),
            "engine": out.engine,
            "llm": "none",
        },
    )
    return out
