"""Spec 036 FR-3/FR-5 + AC-1..AC-5 — idempotent Phoenix sync, no live server.

Phoenix HTTP is respx-mocked; the registry is monkeypatched to two tmp-file
prompts (one versioned, one unversioned) so assertions stay exact.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import httpx
import pytest
import respx

from law_ai.agents_runtime.prompts import phoenix as phoenix_sync
from law_ai.agents_runtime.prompts.registry import LocalPrompt

BASE = "http://phoenix.test"


@pytest.fixture()
def two_prompts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[LocalPrompt, LocalPrompt]:
    alpha_file = tmp_path / "alpha.v1.md"
    alpha_file.write_text("alpha prompt body\n", encoding="utf-8")
    beta_file = tmp_path / "beta.md"
    beta_file.write_text("beta prompt body\n", encoding="utf-8")
    alpha = LocalPrompt(name="alpha", family="runtime", path=alpha_file, version=1)
    beta = LocalPrompt(name="beta", family="sdlc", path=beta_file)
    monkeypatch.setattr(phoenix_sync, "iter_local_prompts", lambda: [alpha, beta])
    return alpha, beta


@pytest.fixture()
def audit_events(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, dict[str, Any]]]:
    events: list[tuple[str, dict[str, Any]]] = []
    monkeypatch.setattr(
        phoenix_sync.ProvenanceLogger,
        "log_event",
        staticmethod(lambda event_type, payload: events.append((event_type, payload))),
    )
    return events


def _existing_version(text: str) -> dict[str, Any]:
    return {
        "data": {
            "id": "pv-old",
            "template": {
                "type": "chat",
                "messages": [{"role": "system", "content": text}],
            },
        }
    }


class TestBaseUrlResolution:
    def test_explicit_setting_wins(self, settings: Any) -> None:
        settings.PHOENIX_BASE_URL = "http://explicit:6006/"
        settings.PHOENIX_COLLECTOR_ENDPOINT = "http://other:6006/v1/traces"
        assert phoenix_sync.phoenix_base_url() == "http://explicit:6006"

    def test_derived_from_collector_endpoint(self, settings: Any) -> None:
        settings.PHOENIX_BASE_URL = None
        settings.PHOENIX_COLLECTOR_ENDPOINT = "http://phoenix:6006/v1/traces"
        assert phoenix_sync.phoenix_base_url() == "http://phoenix:6006"

    def test_unconfigured_returns_none_and_sync_refuses(self, settings: Any) -> None:
        settings.PHOENIX_BASE_URL = None
        settings.PHOENIX_COLLECTOR_ENDPOINT = None
        assert phoenix_sync.phoenix_base_url() is None
        with pytest.raises(RuntimeError, match="PHOENIX_BASE_URL"):
            phoenix_sync.sync_prompts()


@respx.mock
def test_fresh_sync_creates_and_tags(
    two_prompts: tuple[LocalPrompt, LocalPrompt],
    audit_events: list[tuple[str, dict[str, Any]]],
) -> None:
    respx.get(f"{BASE}/v1/prompts/alpha/tags/v1").mock(httpx.Response(404))
    respx.get(f"{BASE}/v1/prompts/beta/latest").mock(httpx.Response(404))
    create = respx.post(f"{BASE}/v1/prompts").mock(
        httpx.Response(200, json={"data": {"id": "pv-new"}})
    )
    tag = respx.post(f"{BASE}/v1/prompt_versions/pv-new/tags").mock(httpx.Response(204))

    report = phoenix_sync.sync_prompts(base_url=BASE)

    assert report.ok
    assert report.count("created") == 2
    assert create.call_count == 2
    # only the versioned prompt gets a tag
    assert tag.call_count == 1
    assert audit_events and audit_events[0][0] == "prompt_sync"
    assert audit_events[0][1]["created"] == 2


@respx.mock
def test_unchanged_resync_skips_everything(
    two_prompts: tuple[LocalPrompt, LocalPrompt],
    audit_events: list[tuple[str, dict[str, Any]]],
) -> None:
    alpha, beta = two_prompts
    respx.get(f"{BASE}/v1/prompts/alpha/tags/v1").mock(
        httpx.Response(200, json=_existing_version(alpha.text))
    )
    respx.get(f"{BASE}/v1/prompts/beta/latest").mock(
        httpx.Response(200, json=_existing_version(beta.text))
    )
    create = respx.post(f"{BASE}/v1/prompts").mock(httpx.Response(200))

    report = phoenix_sync.sync_prompts(base_url=BASE)

    assert report.ok
    assert report.count("skipped") == 2
    assert not create.called


@respx.mock
def test_changed_content_updates_and_retags(
    two_prompts: tuple[LocalPrompt, LocalPrompt],
    audit_events: list[tuple[str, dict[str, Any]]],
) -> None:
    _, beta = two_prompts
    respx.get(f"{BASE}/v1/prompts/alpha/tags/v1").mock(
        httpx.Response(200, json=_existing_version("stale alpha body"))
    )
    respx.get(f"{BASE}/v1/prompts/beta/latest").mock(
        httpx.Response(200, json=_existing_version(beta.text))
    )
    create = respx.post(f"{BASE}/v1/prompts").mock(
        httpx.Response(200, json={"data": {"id": "pv-2"}})
    )
    tag = respx.post(f"{BASE}/v1/prompt_versions/pv-2/tags").mock(httpx.Response(204))

    report = phoenix_sync.sync_prompts(base_url=BASE)

    assert report.ok
    assert report.count("updated") == 1
    assert report.count("skipped") == 1
    assert create.call_count == 1
    assert tag.call_count == 1


@respx.mock
def test_server_error_yields_error_outcome(
    two_prompts: tuple[LocalPrompt, LocalPrompt],
    audit_events: list[tuple[str, dict[str, Any]]],
) -> None:
    respx.get(f"{BASE}/v1/prompts/alpha/tags/v1").mock(httpx.Response(500))
    respx.get(f"{BASE}/v1/prompts/beta/latest").mock(httpx.Response(404))
    respx.post(f"{BASE}/v1/prompts").mock(
        httpx.Response(200, json={"data": {"id": "pv-3"}})
    )

    report = phoenix_sync.sync_prompts(base_url=BASE)

    assert not report.ok
    assert report.count("error") == 1
    assert report.count("created") == 1
    # errors are still reported in the audit payload
    assert audit_events[0][1]["errors"] == 1


@respx.mock
def test_dry_run_never_writes(
    two_prompts: tuple[LocalPrompt, LocalPrompt],
    audit_events: list[tuple[str, dict[str, Any]]],
) -> None:
    respx.get(f"{BASE}/v1/prompts/alpha/tags/v1").mock(httpx.Response(404))
    respx.get(f"{BASE}/v1/prompts/beta/latest").mock(httpx.Response(404))
    create = respx.post(f"{BASE}/v1/prompts").mock(httpx.Response(200))

    report = phoenix_sync.sync_prompts(base_url=BASE, dry_run=True)

    assert report.count("created") == 2  # would-be outcomes
    assert not create.called
    assert audit_events == []  # AC-5: no audit write on dry-run
