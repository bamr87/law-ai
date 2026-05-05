"""Unit tests for IngestionScout extraction + HITL routing (T-003)."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from lawgraph.ingestionapp.services import scout as scout_module
from lawgraph.ingestionapp.services.scout import IngestionScout

HIGH_CONF_OPINION = {
    "id": 12345,
    "case_name": "Roe v. Wade",
    "absolute_url": "/opinion/12345/roe-v-wade/",
    "plain_text": (
        "The Supreme Court held in Roe v. Wade, 410 U.S. 113 (1973), "
        "that the Due Process Clause of the Fourteenth Amendment provides "
        "a fundamental right to privacy that protects a pregnant woman's "
        "liberty to choose. See also Griswold v. Connecticut, 381 U.S. 479 (1965); "
        "Eisenstadt v. Baird, 405 U.S. 438 (1972); "
        "Doe v. Bolton, 410 U.S. 179 (1973); "
        "Planned Parenthood v. Casey, 505 U.S. 833 (1992). "
        "The court's reasoning rests on substantive due process doctrine. "
    )
    * 2,
    "cluster": {
        "case_name": "Roe v. Wade",
        "court": "Supreme Court",
        "date_filed": "1973-01-22",
        "judges": "Blackmun, Burger, Douglas",
    },
}

LOW_CONF_OPINION = {
    "id": 999,
    "case_name": "Untitled opinion",
    "plain_text": "",
    "cluster": {},
}


def test_extract_high_confidence_returns_citations_and_provenance() -> None:
    scout = IngestionScout()
    result = scout.extract(HIGH_CONF_OPINION)
    assert result.case_id == "12345"
    assert result.title == "Roe v. Wade"
    assert result.court == "Supreme Court"
    assert result.confidence >= 0.7
    assert any("u.s." in c.normalized for c in result.citations)
    assert result.source == "courtlistener"
    assert result.source_url and result.source_url.startswith("https://")


def test_extract_low_confidence_below_threshold() -> None:
    scout = IngestionScout()
    result = scout.extract(LOW_CONF_OPINION)
    assert not result.is_high_confidence()


@pytest.mark.asyncio
async def test_low_confidence_routes_to_pending_jsonl(tmp_path, monkeypatch) -> None:
    """AC-2 / AC-5: when the Celery dispatch fails, the JSONL fallback fires."""
    quarantine_dir = tmp_path / "pending_review"
    monkeypatch.setattr(scout_module, "PENDING_REVIEW_DIR", quarantine_dir)

    scout = IngestionScout()
    # Force the canonical path to fail so we exercise the JSONL fallback.
    monkeypatch.setattr(
        scout,
        "_quarantine_via_celery",
        MagicMock(side_effect=RuntimeError("no broker")),
    )

    summary = await scout.run_and_commit(LOW_CONF_OPINION)
    assert summary["committed"] is False
    assert summary["pending"] is True
    assert summary["edges"] == 0

    written = list(quarantine_dir.glob("*.jsonl"))
    assert len(written) == 1
    line = written[0].read_text(encoding="utf-8").strip()
    record = json.loads(line)
    assert record["id"] == "999"
    assert record["reason"] == "low_confidence"


@pytest.mark.asyncio
async def test_low_confidence_routes_to_postgres_when_available(
    tmp_path, monkeypatch
) -> None:
    """AC-1: a successful Celery dispatch must NOT also produce a JSONL file."""
    quarantine_dir = tmp_path / "pending_review"
    monkeypatch.setattr(scout_module, "PENDING_REVIEW_DIR", quarantine_dir)

    scout = IngestionScout()
    celery_mock = MagicMock(return_value=None)
    monkeypatch.setattr(scout, "_quarantine_via_celery", celery_mock)

    summary = await scout.run_and_commit(LOW_CONF_OPINION)

    assert summary == {
        "case_id": "999",
        "committed": False,
        "pending": True,
        "confidence": pytest.approx(summary["confidence"]),
        "edges": 0,
    }
    celery_mock.assert_called_once()
    assert not quarantine_dir.exists() or not list(quarantine_dir.glob("*.jsonl"))


@pytest.mark.asyncio
async def test_quarantine_via_celery_dispatches_with_expected_payload(
    monkeypatch,
) -> None:
    """BL-20260503-20: the canonical path delegates to ``quarantine_extraction``.

    Asserts the dispatched payload contains the scout-derived metadata
    (id/source/confidence/reason) plus the original opinion under ``payload``
    so the ORM task can persist them to ``PendingReview``.
    """
    from lawgraph.ingestionapp import tasks as tasks_module

    delay_mock = MagicMock(return_value=None)
    monkeypatch.setattr(tasks_module.quarantine_extraction, "delay", delay_mock)

    scout = IngestionScout()
    result = scout.extract(LOW_CONF_OPINION)
    scout._quarantine_via_celery(result, LOW_CONF_OPINION)

    delay_mock.assert_called_once()
    (dispatched_payload,) = delay_mock.call_args.args
    assert dispatched_payload["id"] == "999"
    assert dispatched_payload["source"] == "courtlistener"
    assert dispatched_payload["reason"] == "low_confidence"
    assert dispatched_payload["payload"]["id"] == 999


def test_scout_no_longer_uses_inline_asyncpg() -> None:
    """BL-20260503-20: the inline asyncpg path must be gone.

    Quarantine writes are now owned by ``ingestionapp.tasks.quarantine_extraction``.
    """
    source = Path(scout_module.__file__).read_text(encoding="utf-8")
    assert "import asyncpg" not in source
    assert "asyncpg.connect" not in source
    assert "INSERT INTO pending_review" not in source


def test_no_asyncio_run_in_quarantine_path() -> None:
    """AC-4: the refactor must not reintroduce the sync-over-async hack."""
    source = Path(scout_module.__file__).read_text(encoding="utf-8")
    assert "asyncio.run(" not in source
    assert "get_running_loop" not in source


def test_extract_raises_on_missing_id() -> None:
    scout = IngestionScout()
    with pytest.raises(ValueError):
        scout.extract({"case_name": "x"})
