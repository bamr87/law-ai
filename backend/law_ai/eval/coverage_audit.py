"""Coverage XML parser for the autonomy audit pipeline (spec 018 T-003).

Parses a ``coverage.xml`` (Cobertura format) produced by ``pytest-cov`` and
returns a ranked list of module-level coverage records — lowest coverage
first — for use by ``scripts/evolve_audit.py`` and the nightly autonomy loop.

Usage::

    from law_ai.eval.coverage_audit import load_coverage_report, CoverageRecord

    records = load_coverage_report()          # uses default path
    below_threshold = [r for r in records if r.pct < 75.0]

The module intentionally has **zero Django / ORM dependencies** so it can be
imported by ``scripts/evolve_audit.py`` (stdlib-only execution context) without
calling ``django.setup()``.
"""

from __future__ import annotations

import contextlib
import logging
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger("law_ai.eval.coverage_audit")

# Default location produced by ``make test-coverage`` (bind-mounted to host).
_DEFAULT_XML = Path(__file__).resolve().parents[2] / "coverage.xml"

# Constitution gate: warn (not fail) when below 75%; error when below 65%.
COVERAGE_WARN_THRESHOLD = 75.0
COVERAGE_ERROR_THRESHOLD = 65.0


@dataclass(frozen=True, order=True)
class CoverageRecord:
    """Per-module coverage record, sortable by ascending ``pct``."""

    pct: float
    module: str
    missing_lines: list[int] = field(compare=False, default_factory=list)

    @property
    def severity(self) -> str:
        """Return ``"high"``, ``"med"``, or ``"ok"`` based on constitution thresholds."""
        if self.pct < COVERAGE_ERROR_THRESHOLD:
            return "high"
        if self.pct < COVERAGE_WARN_THRESHOLD:
            return "med"
        return "ok"


def load_coverage_report(
    xml_path: Path | None = None,
    *,
    min_statements: int = 5,
) -> list[CoverageRecord]:
    """Parse a Cobertura ``coverage.xml`` and return records sorted ascending by pct.

    Args:
        xml_path: Path to ``coverage.xml``. Defaults to
            ``backend/coverage.xml`` relative to the repo root.
        min_statements: Skip modules with fewer than this many statements
            (avoids noise from tiny ``__init__.py`` files).

    Returns:
        Sorted list of :class:`CoverageRecord` (lowest coverage first).
        Returns an empty list when the file does not exist or cannot be parsed.
    """
    path = xml_path if xml_path is not None else _DEFAULT_XML
    if not path.exists():
        logger.debug("coverage.xml not found at %s — skipping coverage audit", path)
        return []

    try:
        tree = ET.parse(str(path))  # known-safe: local CI artifact
    except ET.ParseError as exc:
        logger.warning("Failed to parse %s: %s", path, exc)
        return []

    records: list[CoverageRecord] = []
    root = tree.getroot()

    for cls_el in root.iter("class"):
        name = cls_el.get("name") or cls_el.get("filename") or "<unknown>"
        # ``statements`` attribute is present in coverage.py ≥ 7.x output; fall
        # back to counting ``<line>`` child elements for older / third-party formats.
        stmts_attr = cls_el.get("statements")
        if stmts_attr is not None:
            stmts = int(stmts_attr or "0")
        else:
            stmts = sum(1 for _ in cls_el.iter("line"))
        if stmts < min_statements:
            continue

        raw_rate = cls_el.get("line-rate", "0")
        try:
            rate = float(raw_rate)
        except ValueError:
            logger.debug("Unparseable line-rate %r for %s", raw_rate, name)
            continue

        pct = round(rate * 100, 1)

        # Collect missing line numbers (lines where hits == 0).
        missing: list[int] = []
        for line_el in cls_el.iter("line"):
            if line_el.get("hits", "1") == "0":
                with contextlib.suppress(ValueError):
                    missing.append(int(line_el.get("number", "0") or "0"))

        records.append(CoverageRecord(pct=pct, module=name, missing_lines=missing))

    records.sort()  # ascending by pct (lowest first)
    return records


def overall_coverage(xml_path: Path | None = None) -> float | None:
    """Return the overall (total) line-rate from the ``<coverage>`` root element.

    Returns:
        Percentage (0-100) as a float, or ``None`` when the file is absent or
        the attribute is missing.
    """
    path = xml_path if xml_path is not None else _DEFAULT_XML
    if not path.exists():
        return None
    try:
        tree = ET.parse(str(path))
    except ET.ParseError:
        return None
    root = tree.getroot()
    raw = root.get("line-rate")
    if raw is None:
        return None
    try:
        return round(float(raw) * 100, 1)
    except ValueError:
        return None
