"""The LegalBench pin watcher (BL-20260906-30).

``backend/law_ai/eval/fetch.py`` pins two upstream commits by hand and nothing
watched them, so the benchmark could age by neglect rather than by decision.
``scripts/check_legalbench_revisions.py`` is the watcher; these are its rules.

No network here: the fetch is injected, because a test that reaches Hugging
Face is a test that fails when Hugging Face is having a day.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any

import pytest

pytestmark = pytest.mark.specs

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "check_legalbench_revisions.py"

PINNED_DATA = "a" * 40
PINNED_PROMPT = "b" * 40
SOURCE = f"""
DATA_REVISION = "{PINNED_DATA}"
PROMPT_REVISION = "{PINNED_PROMPT}"
"""


@pytest.fixture(scope="module")
def checker() -> Any:
    assert SCRIPT.is_file(), f"missing {SCRIPT}"
    spec = importlib.util.spec_from_file_location("_legalbench_revisions", SCRIPT)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules["_legalbench_revisions"] = mod
    spec.loader.exec_module(mod)
    return mod


def test_it_reads_the_pins_out_of_the_real_source(checker: Any) -> None:
    """The pins are read from fetch.py, so they cannot be stale copies here."""
    source = (REPO_ROOT / "backend" / "law_ai" / "eval" / "fetch.py").read_text(
        encoding="utf-8"
    )
    for name in ("DATA_REVISION", "PROMPT_REVISION"):
        assert len(checker.read_pin(source, name)) == 40


def test_an_unchanged_upstream_is_not_drift(
    checker: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        checker,
        "fetch_head",
        lambda url, key: (PINNED_DATA if "huggingface" in url else PINNED_PROMPT, None),
    )
    pins = checker.collect(SOURCE)

    assert [p.drifted for p in pins] == [False, False]
    assert "DRIFTED" not in checker.report(pins)


def test_a_moved_upstream_is_reported_with_the_follow_through(
    checker: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(checker, "fetch_head", lambda url, key: ("c" * 40, None))
    pins = checker.collect(SOURCE)
    text = checker.report(pins)

    assert all(p.drifted for p in pins)
    assert text.count("DRIFTED") == 2
    # A report that says "it moved" and stops leaves the reader to rediscover
    # what to do about it.
    assert "MANIFEST=update make legalbench-cache" in text


def test_an_unreachable_upstream_is_not_reported_as_drift(
    checker: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An outage must not read as "the benchmark moved"."""
    monkeypatch.setattr(checker, "fetch_head", lambda url, key: (None, "timed out"))
    pins = checker.collect(SOURCE)

    assert not any(p.drifted for p in pins)
    assert "could not check" in checker.report(pins)


def test_strict_is_opt_in(checker: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    """Reporting drift is the default; failing on it is a choice."""
    monkeypatch.setattr(checker, "fetch_head", lambda url, key: ("c" * 40, None))
    monkeypatch.setattr(checker.Path, "read_text", lambda self, encoding=None: SOURCE)

    assert checker.main([]) == 0
    assert checker.main(["--strict"]) == 1


def test_a_workflow_actually_runs_the_check() -> None:
    """A watcher nobody schedules is a watcher that watches nothing."""
    workflows = REPO_ROOT / ".github" / "workflows"
    runners = [
        path.name
        for path in sorted(workflows.glob("*.yml"))
        if "scripts/check_legalbench_revisions.py" in path.read_text(encoding="utf-8")
    ]
    assert runners, (
        "no workflow runs scripts/check_legalbench_revisions.py — the pins "
        "would be watchable but never watched"
    )
