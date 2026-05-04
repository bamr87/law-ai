"""Tests for app.core.audit_store (spec 003)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from lexgraph.core import audit_jsonl as audit_store
from django.conf import settings


@pytest.fixture()
def audit_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    target = tmp_path / "provenance.jsonl"
    monkeypatch.setattr(settings, "AUDIT_PATH", str(target))
    return target


def test_record_creates_file_and_appends(audit_path: Path) -> None:
    audit_store.record({"agent": "A", "i": 1})
    audit_store.record({"agent": "B", "i": 2})
    lines = audit_path.read_text().strip().splitlines()
    assert [json.loads(line)["i"] for line in lines] == [1, 2]


def test_tail_returns_newest_first(audit_path: Path) -> None:
    for i in range(5):
        audit_store.record({"i": i})
    out = audit_store.tail(3)
    assert [event["i"] for event in out] == [4, 3, 2]


def test_tail_zero_or_missing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    target = tmp_path / "missing.jsonl"
    monkeypatch.setattr(settings, "AUDIT_PATH", str(target))
    assert audit_store.tail(50) == []
    assert audit_store.tail(0) == []


def test_tail_skips_corrupt_lines(audit_path: Path) -> None:
    audit_path.parent.mkdir(parents=True, exist_ok=True)
    audit_path.write_text('{"good": 1}\nnot-json\n{"good": 2}\n')
    out = audit_store.tail(50)
    assert [event["good"] for event in out] == [2, 1]


def test_record_failure_is_swallowed(monkeypatch: pytest.MonkeyPatch) -> None:
    # NFR-AUDIT-1 / AC-5 — bad path must not raise.
    monkeypatch.setattr(settings, "AUDIT_PATH", "/proc/definitely-not-writable/x.jsonl")
    audit_store.record({"agent": "X"})  # must not raise


def test_rotation_truncates_to_keep(
    audit_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # AC-7 — exceeding MAX triggers truncation to KEEP, preserving the most recent.
    monkeypatch.setattr(settings, "MAX_AUDIT_LINES", 5)
    monkeypatch.setattr(settings, "KEEP_AUDIT_LINES", 2)
    for i in range(6):
        audit_store.record({"i": i})
    lines = audit_path.read_text().strip().splitlines()
    assert [json.loads(line)["i"] for line in lines] == [4, 5]
