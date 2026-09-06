"""CLI smoke test for ``--source courtlistener`` (BL-20260429-06, specs/001 T-004).

Locks the ``scripts/ingest_sample.py --source courtlistener --dry-run --limit N``
contract against a ``respx``-mocked CourtListener API: no network, no Neo4j.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx

from law_ai.ingestionapp.services.courtlistener import BASE_URL

# Make scripts/ importable (mirrors test_ingest_cli_colorado.py).
SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import ingest_sample  # type: ignore[import-not-found]  # noqa: E402

# Long enough to clear the >500-char body rule in ``scout._score``.
_BODY = (
    "The district court's judgment is affirmed. As we explained in "
    "Marbury v. Madison, 5 U.S. 137 (1803), the province of the court is "
    "to say what the law is. Petitioner urges a contrary reading, relying "
    "on Brown v. Board of Education, 347 U.S. 483 (1954), but that case "
    "concerned a materially different record. See also Roe v. Wade, 410 "
    "U.S. 113 (1973). The remaining assignments of error are without "
    "merit and warrant no extended discussion. Because the findings below "
    "are supported by substantial evidence in the record, and because the "
    "legal conclusions drawn from those findings are sound, we decline to "
    "disturb them on appeal. Affirmed."
)


def _opinion(opinion_id: int, *, case_name: str, text: str) -> dict[str, Any]:
    return {
        "id": opinion_id,
        "case_name": case_name,
        "plain_text": text,
        "absolute_url": f"/opinion/{opinion_id}/{case_name.lower()}/",
        "cluster": {
            "case_name": case_name,
            "court": "Supreme Court of the United States",
            "judges": "Roberts, Kagan",
            "date_filed": "2020-01-15",
        },
    }


RESULTS = [
    _opinion(101, case_name="Alpha v. Beta", text=_BODY),
    _opinion(102, case_name="Gamma v. Delta", text=_BODY),
    # Short body, no citation → low confidence → counted as pending.
    _opinion(103, case_name="Epsilon v. Zeta", text="Per curiam. Affirmed."),
]


@pytest.fixture
def mock_courtlistener() -> respx.Router:
    router = respx.mock(assert_all_called=False)
    router.get(f"{BASE_URL}/opinions/").mock(
        return_value=httpx.Response(200, json={"results": RESULTS, "next": None})
    )
    return router


def _summary(out: str) -> dict[str, int]:
    return {
        key: int(value)
        for key, value in re.findall(
            r"(committed|pending|skipped|elapsed_s)=(\d+)", out
        )
    }


def test_cli_dry_run_extracts_three_opinions(
    mock_courtlistener: respx.Router, capsys: pytest.CaptureFixture[str]
) -> None:
    """``--dry-run --limit 3`` extracts every opinion and commits nothing."""
    with mock_courtlistener:
        rc = ingest_sample.main(
            ["--source", "courtlistener", "--limit", "3", "--dry-run"]
        )

    assert rc == 0
    out = capsys.readouterr().out
    assert "source=courtlistener" in out
    summary = _summary(out)
    assert summary["committed"] + summary["pending"] == 3
    assert summary["skipped"] == 0
    # Two long, well-cited opinions clear the 0.7 threshold; the stub does not.
    assert summary["committed"] == 2
    assert summary["pending"] == 1


def test_cli_dry_run_honours_limit(
    mock_courtlistener: respx.Router, capsys: pytest.CaptureFixture[str]
) -> None:
    """``--limit 1`` stops after the first result even though three are served."""
    with mock_courtlistener:
        rc = ingest_sample.main(
            ["--source", "courtlistener", "--limit", "1", "--dry-run"]
        )

    assert rc == 0
    summary = _summary(capsys.readouterr().out)
    assert summary["committed"] + summary["pending"] == 1
    assert summary["skipped"] == 0


def test_cli_dry_run_never_touches_neo4j(
    mock_courtlistener: respx.Router,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The dry-run path must not open a Neo4j driver (spec 001 T-004)."""

    def _boom() -> None:
        raise AssertionError("--dry-run must not open a Neo4j driver")

    monkeypatch.setattr("law_ai.ingestionapp.services.scout.get_neo4j_driver", _boom)
    with mock_courtlistener:
        rc = ingest_sample.main(
            ["--source", "courtlistener", "--limit", "3", "--dry-run"]
        )
    assert rc == 0
    assert "source=courtlistener" in capsys.readouterr().out
