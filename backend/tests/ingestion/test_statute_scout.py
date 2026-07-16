"""Unit tests for ``StatuteScout`` (spec 016 T-003, AC-2)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from law_ai.core.schemas.statute_extraction import StatuteExtraction
from law_ai.ingestionapp.quarantine_kinds import KIND_STATUTE_SECTION
from law_ai.ingestionapp.services.statute_scout import StatuteScout

FIXTURE = (
    Path(__file__).parent / "fixtures" / "co" / "title_18_article_3.html"
).read_text(encoding="utf-8")


def _payload() -> dict[str, str]:
    return {
        "title_id": "us-co/crs/title-18",
        "html": FIXTURE,
        "source_url": "https://example.test/title-18/",
    }


def test_extract_returns_typed_extraction() -> None:
    scout = StatuteScout()
    extraction = scout.extract(_payload())
    assert isinstance(extraction, StatuteExtraction)
    assert extraction.statute_id == "us-co/crs/title-18"
    assert extraction.agent_version == StatuteScout.agent_version
    assert len(extraction.sections) == 6


def test_extract_rejects_missing_payload_keys() -> None:
    scout = StatuteScout()
    with pytest.raises(ValueError):
        scout.extract({"title_id": "us-co/crs/title-18"})  # missing html
    with pytest.raises(ValueError):
        scout.extract({"html": "<html></html>"})  # missing title_id


@pytest.mark.asyncio
async def test_run_and_commit_writes_high_confidence_and_quarantines_low(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """High-confidence sections MERGE; the malformed § 18-3-106 quarantines."""
    fake_session = AsyncMock()
    fake_driver = MagicMock()
    fake_driver.session.return_value.__aenter__.return_value = fake_session
    fake_driver.session.return_value.__aexit__.return_value = None
    monkeypatch.setattr(
        "law_ai.ingestionapp.services.statute_scout.get_neo4j_driver",
        lambda: fake_driver,
    )

    delay = MagicMock()
    monkeypatch.setattr(
        "law_ai.ingestionapp.tasks.quarantine_extraction.delay",
        delay,
    )

    scout = StatuteScout()
    summary = await scout.run_and_commit(_payload())

    assert summary["title_id"] == "us-co/crs/title-18"
    assert summary["committed"] == 5  # 18-3-101..105
    assert summary["pending"] == 1  # 18-3-106 (malformed fixture)
    assert summary["sections_total"] == 6
    assert summary["edges"] > 0

    # Exactly one quarantine dispatch, with kind=statute_section.
    assert delay.call_count == 1
    quarantined_payload = delay.call_args[0][0]
    assert quarantined_payload["kind"] == KIND_STATUTE_SECTION
    assert quarantined_payload["id"] == "us-co/crs/18-3-106"
    assert quarantined_payload["source"] == "colorado_statutes"


@pytest.mark.asyncio
async def test_run_and_commit_is_idempotent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """NFR-IDEMPOTENT-1: a second run produces the same MERGE call signature."""
    fake_session = AsyncMock()
    fake_driver = MagicMock()
    fake_driver.session.return_value.__aenter__.return_value = fake_session
    fake_driver.session.return_value.__aexit__.return_value = None
    monkeypatch.setattr(
        "law_ai.ingestionapp.services.statute_scout.get_neo4j_driver",
        lambda: fake_driver,
    )
    monkeypatch.setattr(
        "law_ai.ingestionapp.tasks.quarantine_extraction.delay",
        MagicMock(),
    )

    scout = StatuteScout()
    first = await scout.run_and_commit(_payload())
    first_calls = [c.args[0] for c in fake_session.run.await_args_list]
    fake_session.run.reset_mock()

    second = await scout.run_and_commit(_payload())
    second_calls = [c.args[0] for c in fake_session.run.await_args_list]

    assert first == second
    assert first_calls == second_calls
    # Each MERGE statement is idempotent; identical call signatures means
    # re-running the ingestion is a graph no-op (NFR-IDEMPOTENT-1).
    assert all("MERGE" in q for q in first_calls)


@pytest.mark.asyncio
async def test_run_and_commit_falls_back_to_jsonl_on_celery_failure(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """When Celery dispatch raises, the scout writes JSONL instead of crashing."""
    fake_session = AsyncMock()
    fake_driver = MagicMock()
    fake_driver.session.return_value.__aenter__.return_value = fake_session
    fake_driver.session.return_value.__aexit__.return_value = None
    monkeypatch.setattr(
        "law_ai.ingestionapp.services.statute_scout.get_neo4j_driver",
        lambda: fake_driver,
    )
    monkeypatch.setattr(
        "law_ai.ingestionapp.services.statute_scout.PENDING_REVIEW_DIR",
        tmp_path,
    )

    def boom(_payload: dict) -> None:
        raise RuntimeError("broker unreachable")

    monkeypatch.setattr(
        "law_ai.ingestionapp.tasks.quarantine_extraction.delay",
        boom,
    )

    scout = StatuteScout()
    summary = await scout.run_and_commit(_payload())
    assert summary["pending"] == 1
    jsonl_files = list(tmp_path.glob("*.jsonl"))
    assert len(jsonl_files) == 1
    assert "statute_section" in jsonl_files[0].read_text()
