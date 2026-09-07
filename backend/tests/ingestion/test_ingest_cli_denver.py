"""CLI smoke test for ``--source denver_municipal_code`` (BL-20260509-05).

Runs entirely offline through ``--chapter-dir``, which is the documented
workflow for this source: library.municode.com's terms prohibit systematic
downloading, so the shipped path reads local HTML rather than fetching.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

# Make scripts/ importable.
SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import ingest_sample  # type: ignore[import-not-found]  # noqa: E402

CHAPTER_DIR = Path(__file__).parent / "fixtures" / "denver"


def test_cli_dry_run_reports_the_parse(capsys: pytest.CaptureFixture[str]) -> None:
    rc = ingest_sample.main(
        [
            "--source",
            "denver_municipal_code",
            "--chapters",
            "38",
            "--chapter-dir",
            str(CHAPTER_DIR),
            "--dry-run",
        ]
    )
    assert rc == 0
    out = capsys.readouterr().out
    assert "source=denver_municipal_code" in out
    # Three substantive sections; the "Reserved." stub stays under threshold.
    assert "committed=3" in out
    assert "pending=1" in out
    assert "skipped=0" in out


def test_cli_limit_caps_sections_per_chapter(
    capsys: pytest.CaptureFixture[str],
) -> None:
    rc = ingest_sample.main(
        [
            "--source",
            "denver_municipal_code",
            "--chapters",
            "38",
            "--chapter-dir",
            str(CHAPTER_DIR),
            "--limit",
            "2",
            "--dry-run",
        ]
    )
    assert rc == 0
    out = capsys.readouterr().out
    assert "committed=2" in out
    assert "pending=0" in out


def test_cli_requires_chapters() -> None:
    with pytest.raises(SystemExit, match="requires --chapters"):
        ingest_sample.main(["--source", "denver_municipal_code", "--dry-run"])


def test_cli_counts_a_missing_chapter_as_skipped(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    rc = ingest_sample.main(
        [
            "--source",
            "denver_municipal_code",
            "--chapters",
            "99",
            "--chapter-dir",
            str(tmp_path),
            "--dry-run",
        ]
    )
    assert rc == 0
    assert "skipped=1" in capsys.readouterr().out


def test_chapters_all_reads_the_chapter_dir_offline(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """BL-20260906-06: `--chapters all` must not need a hand-typed list."""
    with patch.object(ingest_sample, "DenverMunicipalCodeClient") as client:
        rc = ingest_sample.main(
            [
                "--source",
                "denver_municipal_code",
                "--chapters",
                "all",
                "--chapter-dir",
                str(CHAPTER_DIR),
                "--dry-run",
            ]
        )
    assert rc == 0
    # Offline discovery stays offline.
    client.assert_not_called()
    out = capsys.readouterr().out
    assert "committed=3" in out
    assert "skipped=0" in out


def test_chapters_all_asks_the_code_for_its_chapters(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Online discovery reads the table of contents instead of a typed list."""
    seen: dict[str, Any] = {}

    class _FakeClient:
        async def __aenter__(self) -> _FakeClient:
            return self

        async def __aexit__(self, *exc: object) -> None:
            return None

        async def list_chapters(self) -> list[str]:
            seen["listed"] = True
            return ["38"]

        def url_for_chapter(self, chapter: str) -> str:
            return f"https://example.test/chapter-{chapter}/"

        async def iter_chapters(self, chapters: Any) -> Any:
            seen["chapters"] = list(chapters)
            for chapter in seen["chapters"]:
                yield chapter, (CHAPTER_DIR / f"chapter-{chapter}.html").read_text(
                    encoding="utf-8"
                )

    with patch.object(ingest_sample, "DenverMunicipalCodeClient", _FakeClient):
        rc = ingest_sample.main(
            [
                "--source",
                "denver_municipal_code",
                "--chapters",
                "all",
                "--dry-run",
            ]
        )
    assert rc == 0
    assert seen == {"listed": True, "chapters": ["38"]}
    assert "committed=3" in capsys.readouterr().out


def test_offline_mode_opens_no_client(capsys: pytest.CaptureFixture[str]) -> None:
    """`--chapter-dir` must not reach the network, even to construct a client."""
    with patch.object(ingest_sample, "DenverMunicipalCodeClient") as client:
        ingest_sample.main(
            [
                "--source",
                "denver_municipal_code",
                "--chapters",
                "38",
                "--chapter-dir",
                str(CHAPTER_DIR),
                "--dry-run",
            ]
        )
    client.assert_not_called()


def test_commit_mode_quarantines_every_section(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The source requires human approval, so nothing auto-commits (§5)."""
    quarantined: list[Any] = []

    async def _fake_quarantine(_self: Any, extraction: Any, section: Any) -> None:
        quarantined.append(section.id)

    from law_ai.ingestionapp.services.ordinance_scout import OrdinanceScout

    with patch.object(OrdinanceScout, "_quarantine", _fake_quarantine):
        rc = ingest_sample.main(
            [
                "--source",
                "denver_municipal_code",
                "--chapters",
                "38",
                "--chapter-dir",
                str(CHAPTER_DIR),
            ]
        )
    assert rc == 0
    out = capsys.readouterr().out
    assert "committed=0" in out
    assert "pending=4" in out
    assert len(quarantined) == 4
