"""CLI smoke test for ``--source colorado_statutes`` (spec 016 T-006, AC-4)."""

from __future__ import annotations

import sys
from pathlib import Path

import httpx
import pytest
import respx

# Make scripts/ importable.
SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import ingest_sample  # type: ignore[import-not-found]  # noqa: E402

FIXTURE = (
    Path(__file__).parent / "fixtures" / "co" / "title_18_article_3.html"
).read_text(encoding="utf-8")


@pytest.fixture
def mock_justia() -> respx.Router:
    router = respx.mock(assert_all_called=False)
    router.get(url__regex=r".*/title-18/").mock(
        return_value=httpx.Response(200, text=FIXTURE)
    )
    return router


def test_cli_dry_run_reports_committed_count(
    mock_justia: respx.Router, capsys: pytest.CaptureFixture[str]
) -> None:
    with mock_justia:
        rc = ingest_sample.main(
            [
                "--source",
                "colorado_statutes",
                "--titles",
                "18",
                "--dry-run",
            ]
        )
    assert rc == 0
    out = capsys.readouterr().out
    assert "source=colorado_statutes" in out
    # 5 high-confidence sections in the fixture.
    assert "committed=5" in out
    assert "pending=1" in out


def test_cli_requires_titles(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as excinfo:
        ingest_sample.main(["--source", "colorado_statutes", "--dry-run"])
    assert "--titles" in str(excinfo.value)
