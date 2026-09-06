"""Live-Ollama integration test for the factory run path (BL-20260702-05).

Everything else in ``tests/lsat/`` stubs the model. This one actually
generates: ``lsat_factory run --executor ollama`` against the Docker
``ollama`` service, asserting that the batch reached the local model and that
the run is attributable afterwards — an ``llm_call`` event for the pinned
Ollama provider, an ``agent_call`` for ``LSATContentFactory`` naming the
executor, and factory lineage on whatever survived the gates.

It asserts on *provenance*, not on ``accepted > 0``: a 7B local model
legitimately fails the schema or dedup gates some of the time, and a test that
demands a good item would be a model-quality test, not a wiring test.

Skips cleanly (never fails) unless ``OLLAMA_INTEGRATION_URL`` — or a
non-loopback ``OLLAMA_BASE_URL`` — points at a reachable Ollama that has the
configured model pulled. ``make test-integration-ollama`` sets it up; plain
``make test-backend`` and CI without a GPU simply skip.
"""

from __future__ import annotations

import json
import os
from io import StringIO
from pathlib import Path
from typing import Any

import httpx
import pytest

from django.conf import settings as dj_settings
from django.core.management import call_command

from law_ai.lsat.factory.config import FactoryConfig
from law_ai.lsat.factory.pipeline import compile_plan

pytestmark = pytest.mark.integration

_PROBE_TIMEOUT_S = 5.0
#: Loading a 7B model from cold can take a while; the probe still has to give
#: up long before the suite's own patience runs out.
_LOAD_TIMEOUT_S = 180.0


def _candidate_url() -> str:
    """The Ollama the operator asked us to use, if any."""
    explicit = os.getenv("OLLAMA_INTEGRATION_URL", "").strip()
    if explicit:
        return explicit
    env_url = os.getenv("OLLAMA_BASE_URL", "").strip()
    # settings/test.py pins the closed port; an env var pointing there means
    # "no Ollama", not "an Ollama on localhost".
    if env_url and "127.0.0.1:1" not in env_url:
        return env_url
    return ""


def _reachable(url: str) -> tuple[bool, str]:
    if not url:
        return False, "no OLLAMA_INTEGRATION_URL / OLLAMA_BASE_URL configured"
    try:
        response = httpx.get(f"{url.rstrip('/')}/api/tags", timeout=_PROBE_TIMEOUT_S)
        response.raise_for_status()
        tags = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        return False, f"ollama not reachable at {url} ({exc})"
    models = {
        str(m.get("name", "")) for m in tags.get("models", []) if isinstance(m, dict)
    }
    wanted = str(dj_settings.OLLAMA_DEFAULT_MODEL)
    if wanted not in models and not any(m.startswith(wanted) for m in models):
        return False, f"model {wanted!r} not pulled on {url} (have: {sorted(models)})"
    return _can_generate(url, wanted)


def _can_generate(url: str, model: str) -> tuple[bool, str]:
    """Pulled is not the same as runnable.

    A one-token generation is the only honest gate: an Ollama with the model on
    disk but not enough RAM to load it answers ``500 model requires more system
    memory``, and a test that skipped only on a missing model would fail on
    every small box instead of standing aside.
    """
    try:
        response = httpx.post(
            f"{url.rstrip('/')}/api/generate",
            json={
                "model": model,
                "prompt": "ok",
                "stream": False,
                "options": {"num_predict": 1},
            },
            timeout=_LOAD_TIMEOUT_S,
        )
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        return False, f"ollama cannot run {model!r}: {exc.response.text[:200]}"
    except httpx.HTTPError as exc:
        return False, f"ollama cannot run {model!r} ({exc})"
    return True, ""


_URL = _candidate_url()
_OK, _WHY = _reachable(_URL)


@pytest.mark.skipif(not _OK, reason=_WHY or "ollama unavailable")
def test_run_executor_ollama_lands_proposals_with_provenance(
    factory_env: FactoryConfig, monkeypatch: pytest.MonkeyPatch
) -> None:
    from law_ai.core import audit_jsonl as audit_store

    monkeypatch.setattr(dj_settings, "OLLAMA_BASE_URL", _URL)
    cfg = factory_env.model_copy(update={"max_jobs": 1, "drafts_per_job": 1})
    manifest, _ = compile_plan(cfg)
    job = next(j for j in manifest.jobs if j.target.mode == "items")

    out = StringIO()
    call_command(
        "lsat_factory",
        "run",
        "--executor",
        "ollama",
        "--jobs",
        job.job_id,
        "--json",
        stdout=out,
    )
    results: Any = json.loads(out.getvalue())
    assert len(results) == 1
    result = results[0]
    # The local model answered at all: either the batch reached the gates
    # (drafts came back) or the executor recorded why it did not.
    assert result["error"] is None, f"ollama executor failed: {result['error']}"
    assert result["model_label"].startswith("ollama/")
    assert (
        len(result["accepted"]) + len(result["rejected"]) > 0
    ), "the model returned no drafts at all"

    events = audit_store.tail(200)
    llm_calls = [
        ev
        for ev in events
        if ev.get("type") == "llm_call" and ev.get("provider") == "ollama"
    ]
    assert llm_calls, "no llm_call provenance event for the pinned Ollama provider"

    agent_calls = [
        ev
        for ev in events
        if ev.get("type") == "agent_call" and ev.get("agent") == "LSATContentFactory"
    ]
    assert agent_calls, "no agent_call event for the factory intake batch"
    assert "ollama/" in str(agent_calls[-1].get("model"))

    from law_ai.lsat.services import proposals as proposals_store

    for row in proposals_store.list_proposals("pending"):
        assert row["meta"]["factory"]["executor"] == "ollama"
        assert row["status"] == "pending"

    # The run artifacts stay inside the tmp factory dir the fixture set up.
    assert Path(str(dj_settings.LSAT_FACTORY_DIR)).is_dir()
