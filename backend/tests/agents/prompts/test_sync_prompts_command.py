"""Spec 036 FR-4 + AC-4 — the ``sync_prompts`` management command."""

from __future__ import annotations

from io import StringIO
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx
from django.core.management import call_command
from django.core.management.base import CommandError

from law_ai.agents_runtime.prompts import phoenix as phoenix_sync
from law_ai.agents_runtime.prompts.registry import LocalPrompt

BASE = "http://phoenix.test"


@pytest.fixture()
def one_prompt(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> LocalPrompt:
    f = tmp_path / "alpha.v1.md"
    f.write_text("alpha prompt body\n", encoding="utf-8")
    prompt = LocalPrompt(name="alpha", family="runtime", path=f, version=1)
    monkeypatch.setattr(phoenix_sync, "iter_local_prompts", lambda: [prompt])
    monkeypatch.setattr(
        phoenix_sync.ProvenanceLogger, "log_event", staticmethod(lambda *a, **k: None)
    )
    return prompt


def test_unconfigured_phoenix_is_a_command_error(settings: Any) -> None:
    settings.PHOENIX_BASE_URL = None
    settings.PHOENIX_COLLECTOR_ENDPOINT = None
    with pytest.raises(CommandError, match="PHOENIX_BASE_URL"):
        call_command("sync_prompts")


@respx.mock
def test_sync_prints_outcomes_and_summary(one_prompt: LocalPrompt) -> None:
    respx.get(f"{BASE}/v1/prompts/alpha/tags/v1").mock(httpx.Response(404))
    respx.post(f"{BASE}/v1/prompts").mock(
        httpx.Response(200, json={"data": {"id": "pv-1"}})
    )
    respx.post(f"{BASE}/v1/prompt_versions/pv-1/tags").mock(httpx.Response(204))

    out = StringIO()
    call_command("sync_prompts", "--base-url", BASE, stdout=out)

    text = out.getvalue()
    assert "created  alpha v1" in text
    assert "1 created, 0 updated, 0 skipped, 0 error(s)" in text


@respx.mock
def test_dry_run_reports_without_posting(one_prompt: LocalPrompt) -> None:
    respx.get(f"{BASE}/v1/prompts/alpha/tags/v1").mock(httpx.Response(404))
    create = respx.post(f"{BASE}/v1/prompts").mock(httpx.Response(200))

    out = StringIO()
    call_command("sync_prompts", "--dry-run", "--base-url", BASE, stdout=out)

    assert not create.called
    assert "DRY RUN:" in out.getvalue()


@respx.mock
def test_any_error_outcome_exits_nonzero(one_prompt: LocalPrompt) -> None:
    respx.get(f"{BASE}/v1/prompts/alpha/tags/v1").mock(httpx.Response(500))

    err = StringIO()
    with pytest.raises(CommandError, match="1 error"):
        call_command("sync_prompts", "--base-url", BASE, stderr=err)
    assert "error" in err.getvalue()
