"""Live-Ollama integration test for the factory run path (BL-20260702-05).

Everything else in ``tests/lsat/`` stubs the model. This one actually
generates: ``lsat_factory run --executor ollama`` against the Docker
``ollama`` service, asserting that the batch reached the local model and that
the run is attributable afterwards — an ``llm_call`` event for the pinned
Ollama provider, an ``agent_call`` for ``LSATContentFactory`` naming the
executor, and factory lineage on whatever survived the gates.

It asserts both halves of the ask: that proposals *land* (``accepted`` is
non-empty and every accepted id is a pending row in the store) and that the
run is attributable. Retries the batch a bounded number of times first, so a
single unlucky schema miss from a small local model does not fail a wiring
test while a genuinely broken pipeline still does.

Opt-in only, and never at import time: the module reads ``OLLAMA_INTEGRATION_URL``
(a plain env read, no network) at collection and does the reachability probe —
which *generates* — inside the test body. Plain ``make test-backend`` neither
probes nor generates, even though compose sets ``OLLAMA_BASE_URL`` on the
backend service. ``make test-integration-ollama`` sets the opt-in var up;
``OLLAMA_INTEGRATION_MODEL`` overrides the model for boxes that cannot hold the
default 7B in RAM.
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


#: How many times the batch may be re-generated before the test gives up on
#: the model producing one schema-clean item. Small local models miss the
#: schema often enough that a single shot is noise; three shots that all miss
#: is a signal.
_MAX_BATCHES = 3

#: A CPU-only Docker VM generates a few tokens a second, and one drafts payload
#: is several hundred tokens. The product default (120 s) is a user-facing
#: latency budget; an integration test that wants a real answer needs to wait
#: for one instead of timing out and calling the wiring broken.
_GENERATION_TIMEOUT_S = 900.0


def _candidate_url() -> str:
    """The Ollama the operator explicitly asked us to use, if any.

    ``OLLAMA_INTEGRATION_URL`` only — deliberately *not* ``OLLAMA_BASE_URL``
    (BL-20260702-05). docker-compose sets ``OLLAMA_BASE_URL`` on the backend
    service, so honouring it here made an ordinary ``make test-backend`` fire a
    live generation from :func:`_reachable` before the test was even deselected.
    Opting in is now a separate, explicit env var that nothing but
    ``make test-integration-ollama`` sets.
    """
    return os.getenv("OLLAMA_INTEGRATION_URL", "").strip()


def _integration_model() -> str:
    """The model to generate with; overridable for small boxes.

    The compose default is a 7B that needs ~5 GiB resident. A laptop Docker VM
    often cannot spare that, and a permanently-skipped test verifies nothing —
    so ``OLLAMA_INTEGRATION_MODEL`` may point the run at a smaller pulled model.
    """
    override = os.getenv("OLLAMA_INTEGRATION_MODEL", "").strip()
    return override or str(dj_settings.OLLAMA_DEFAULT_MODEL)


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
    wanted = _integration_model()
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


#: Cheap, network-free: a plain env read, so collection of an unrelated suite
#: costs nothing. The probe that actually talks to Ollama runs in the test body.
_URL = _candidate_url()


@pytest.mark.skipif(not _URL, reason="set OLLAMA_INTEGRATION_URL to run this")
def test_run_executor_ollama_lands_proposals_with_provenance(
    factory_env: FactoryConfig, monkeypatch: pytest.MonkeyPatch
) -> None:
    from law_ai.core import audit_jsonl as audit_store

    ok, why = _reachable(_URL)
    if not ok:
        pytest.skip(why or "ollama unavailable")

    model = _integration_model()
    monkeypatch.setattr(dj_settings, "OLLAMA_BASE_URL", _URL)
    monkeypatch.setattr(dj_settings, "OLLAMA_DEFAULT_MODEL", model)
    monkeypatch.setattr(
        dj_settings,
        "OLLAMA_REQUEST_TIMEOUT_S",
        max(float(dj_settings.OLLAMA_REQUEST_TIMEOUT_S), _GENERATION_TIMEOUT_S),
    )
    # Full plan (default max_jobs): the top-ranked job is sometimes a
    # passage_set or writing_prompt target, and a one-job manifest would leave
    # the items-mode pick below with nothing to select.
    cfg = factory_env.model_copy(update={"drafts_per_job": 1})
    manifest, _ = compile_plan(cfg)
    job = next(j for j in manifest.jobs if j.target.mode == "items")

    result: dict[str, Any] = {}
    for _attempt in range(_MAX_BATCHES):
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
        if result["accepted"]:
            break

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

    # The proposals-land half of the ask. `accepted` is only the run's own
    # report; the store is the thing the reviewer queue reads, so assert both
    # and assert they agree — a regression that reports ids without writing
    # rows fails here.
    accepted = set(result["accepted"])
    assert accepted, (
        f"no draft survived the intake gates in {_MAX_BATCHES} batches "
        f"(last rejections: {result['rejected']})"
    )
    pending = proposals_store.list_proposals("pending")
    assert pending, "nothing reached the HITL queue"
    pending_ids = {row["id"] for row in pending}
    assert (
        accepted <= pending_ids
    ), f"accepted ids missing from the pending queue: {sorted(accepted - pending_ids)}"

    for row in pending:
        assert row["meta"]["factory"]["executor"] == "ollama"
        assert row["status"] == "pending"

    # The run artifacts stay inside the tmp factory dir the fixture set up.
    assert Path(str(dj_settings.LSAT_FACTORY_DIR)).is_dir()
