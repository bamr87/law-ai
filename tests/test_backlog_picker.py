"""Unit tests for scripts/pick_backlog_item.py (the /evolve work picker)."""

from __future__ import annotations

import importlib.util
from pathlib import Path

_SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "pick_backlog_item.py"


def _load():
    spec = importlib.util.spec_from_file_location("pick_backlog_item", _SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_severity_then_debt_then_oldest():
    m = _load()
    text = (
        "## Open\n"
        "- **BL-20260101-02** — *feature, high* — newer high feature\n"
        "- **BL-20260101-01** — *tech-debt, high* — older high debt\n"
        "- **BL-20260101-03** — *feature, low* — low feature\n"
        "- **BL-20251231-09** — *feature, med* — med feature\n"
        "## Done\n"
    )
    # high beats med/low; within high, tech-debt beats feature.
    assert m.pick(text)["id"] == "BL-20260101-01"


def test_oldest_first_within_same_severity_and_kind():
    m = _load()
    text = (
        "## Open\n"
        "- **BL-20260201-01** — *feature, med* — newer\n"
        "- **BL-20260115-01** — *feature, med* — older\n"
        "## Done\n"
    )
    assert m.pick(text)["id"] == "BL-20260115-01"


def test_skips_resolved_items_left_in_open():
    m = _load()
    text = (
        "## Open\n"
        "- **BL-20260101-01** — *test-gap, high* — ~~done thing~~ **(resolved 2026-01-02)**: shipped\n"
        "- **BL-20260101-02** — *feature, med* — real open work\n"
        "## Done\n"
    )
    picked = m.pick(text)
    assert picked is not None
    assert picked["id"] == "BL-20260101-02"  # the resolved high item is skipped


def test_no_open_items_returns_none():
    m = _load()
    assert m.pick("## Open\n\n## Claimed\n## Done\n") is None


def test_only_reads_the_open_section():
    m = _load()
    text = (
        "## Open\n"
        "- **BL-20260101-01** — *feature, low* — open one\n"
        "## Done\n"
        "- **BL-20259999-99** — *feature, high* — a done item, must be ignored\n"
    )
    assert m.pick(text)["id"] == "BL-20260101-01"
