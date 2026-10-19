"""End-to-end autonomy → HITL loop against a live local model (BL-20260527-08).

Every other ``run_autonomy`` test stubs the provider. This one runs the real
thing: ``manage.py run_autonomy --kind lsat_content --budget 2`` against the
Docker ``ollama`` service, then approves one of the resulting drafts through
``POST /api/lsat/proposals/<id>/approve`` — the whole propose-then-approve
path the constitution's §5 HITL gate describes, wired end to end for the first
time.

Two deliberate constraints:

* **The chain is pinned to ``ollama``.** ``LSATContentAuthor`` calls
  ``llm.agenerate``, which walks ``LLM_PROVIDER_CHAIN`` — Claude first by
  default. A test that billed the owner's account to prove local wiring works
  would be a bad trade, so the chain is pinned here and the Claude tiers are
  blank in ``settings/test.py`` regardless.
* **It asserts on wiring, not on model quality** — but "wiring" includes the
  model actually answering. Nothing here may pass against a dead Ollama, and
  passing against a dead one was the original defect: ``LSATContentAuthor``
  swallows a provider failure and files ``_fallback_draft`` rows as *pending*
  anyway, and the router writes an ``llm_call`` event even when the whole
  chain fails. So the run is required to be non-degraded and to have produced
  at least one ``llm_call`` with ``ok=True`` and ``provider == "ollama"``.
  What is *not* asserted is anything about the content the model wrote.

Skips cleanly (never fails) unless ``OLLAMA_INTEGRATION_URL`` points at a
reachable Ollama that can run the model. ``OLLAMA_BASE_URL`` is deliberately
*not* an opt-in (bamr87/bamr87#253, the same rule BL-20260702-05 gave
``tests/lsat/test_factory_ollama_integration.py``): docker-compose sets it on
the ``backend`` service, so honouring it made ``make test-coverage`` run this
live cycle against the 7B compose default on the nightly's CPU-only runner,
where every call hit ``OLLAMA_REQUEST_TIMEOUT_S`` and the cycle degraded after
~12 minutes — twice a night. ``make test-integration-ollama`` sets that up, and
``OLLAMA_INTEGRATION_MODEL`` points the run at a smaller pulled model than the
compose default 7B, which needs ~5 GiB resident and does not fit in a typical
laptop Docker VM. A test that skips on every box in reach verifies nothing,
which is why the override exists.
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
from rest_framework.test import APIClient

pytestmark = pytest.mark.integration

_PROBE_TIMEOUT_S = 5.0
#: A cold 7B load is slow; the probe still gives up before the suite does.
_LOAD_TIMEOUT_S = 180.0


def _candidate_url() -> str:
    """The Ollama the operator explicitly asked for — ``OLLAMA_INTEGRATION_URL`` only.

    Only ``make test-integration-ollama`` (and the nightly's live-model slice,
    which calls it with the small model) sets it.
    """
    return os.getenv("OLLAMA_INTEGRATION_URL", "").strip()


def _integration_model() -> str:
    """The model this run should use — override first, compose default after.

    Mirrors ``tests/lsat/test_factory_ollama_integration.py``: the compose
    default is a 7B needing ~5 GiB resident, so a laptop Docker VM skips
    forever unless it can be pointed at something smaller that is pulled.
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
    """Pulled is not runnable: a model that will not fit in RAM 500s."""
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


#: Cheap and network-free: a plain env read, so collecting an unrelated suite
#: costs nothing. The probe that actually loads the model runs in the test body.
_URL = _candidate_url()


def _require_live_ollama() -> None:
    ok, why = _reachable(_URL)
    if not ok:
        pytest.skip(why or "ollama unavailable")


@pytest.fixture()
def local_autonomy_env(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> dict[str, Any]:
    """Isolated stores + a bank sandbox, with the chain pinned to Ollama."""
    from law_ai.lsat.services import bank as bank_mod

    monkeypatch.setattr(dj_settings, "AUTONOMY_ENABLED", True)
    monkeypatch.setattr(dj_settings, "AUDIT_PATH", str(tmp_path / "audit.jsonl"))
    monkeypatch.setattr(
        dj_settings, "LSAT_PROPOSALS_DIR", str(tmp_path / "proposals"), raising=False
    )
    # The harness must never bill a hosted tier to prove local wiring.
    monkeypatch.setattr(dj_settings, "LLM_PROVIDER_CHAIN", "ollama")
    monkeypatch.setattr(dj_settings, "OLLAMA_BASE_URL", _URL)
    monkeypatch.setattr(dj_settings, "OLLAMA_DEFAULT_MODEL", _integration_model())
    monkeypatch.setattr(dj_settings, "LSAT_CONTENT_REVIEW", False, raising=False)
    monkeypatch.setattr(dj_settings, "LSAT_CROSS_CHECK_ON_APPROVE", False)
    monkeypatch.setattr(dj_settings, "LSAT_API_KEY", "", raising=False)
    monkeypatch.setattr(dj_settings, "AGENT_API_KEY", None)

    sandbox = tmp_path / "lsat_data"
    sandbox.mkdir()
    for name in (
        "lr_bank.json",
        "rc_bank.json",
        "lg_bank.json",
        "concepts.json",
        "passages.json",
        "sections.json",
    ):
        src = bank_mod.DATA_DIR / name
        if src.is_file():
            (sandbox / name).write_text(
                src.read_text(encoding="utf-8"), encoding="utf-8"
            )
    monkeypatch.setattr(bank_mod, "DATA_DIR", sandbox)

    def _clear() -> None:
        bank_mod.load_bank.cache_clear()
        bank_mod.load_concepts.cache_clear()
        bank_mod.load_passages.cache_clear()
        bank_mod.load_sections.cache_clear()

    _clear()
    yield {"tmp_path": tmp_path, "sandbox": sandbox}
    _clear()


def _assert_the_local_model_answered(events: list[dict[str, Any]]) -> None:
    """Fail unless a *live* Ollama served this cycle.

    Two escape hatches made "against a live Ollama" unprovable before:
    ``LSATContentAuthor`` returns ``_fallback_draft`` rows when every provider
    call fails (so the pending-drafts assertions pass on a dead model), and
    ``router._log_call`` writes an ``llm_call`` event even on total chain
    failure — with no ``provider`` key, so a bare "no hosted tier" check
    passes vacuously. Both are closed here: the cycle must not be degraded,
    and at least one ``llm_call`` must have succeeded *on the ollama tier*.
    """
    ends = [e for e in events if e.get("type") == "autonomy_cycle.end"]
    assert ends, "the cycle wrote no autonomy_cycle.end event"
    assert ends[-1].get("status") == "ok", ends[-1]
    assert ends[-1].get("degraded") is False, (
        "the cycle degraded to the offline fallback — the local model did not "
        f"serve it: {ends[-1]}"
    )

    llm_calls = [e for e in events if e.get("type") == "llm_call"]
    assert llm_calls, "no llm_call provenance at all"
    served = [
        e
        for e in llm_calls
        if e.get("ok") is True and str(e.get("provider") or "") == "ollama"
    ]
    assert served, (
        "no successful ollama llm_call — an llm_call event is written even "
        f"when the whole chain fails, so this is the real liveness check: "
        f"{[(e.get('ok'), e.get('provider')) for e in llm_calls]}"
    )


@pytest.mark.skipif(not _URL, reason="set OLLAMA_INTEGRATION_URL to run this")
def test_lsat_content_cycle_lands_pending_drafts_and_one_is_approvable(
    local_autonomy_env: dict[str, Any],
) -> None:
    _require_live_ollama()

    from law_ai.core import audit_jsonl as audit_store
    from law_ai.lsat.services import bank as bank_mod
    from law_ai.lsat.services import proposals as proposals_store

    out = StringIO()
    call_command("run_autonomy", "--kind", "lsat_content", "--budget", "2", stdout=out)
    assert "Cycle complete" in out.getvalue()

    # ------------------------------------------------------------------
    # 0. The model actually answered. Without this the whole test passes
    #    against a dead Ollama: LSATContentAuthor swallows the provider
    #    failure and files `_fallback_draft` rows as pending regardless.
    # ------------------------------------------------------------------
    _assert_the_local_model_answered(audit_store.tail(400))

    # ------------------------------------------------------------------
    # 1. The drafts landed in the append-only JSONL store as `pending`.
    # ------------------------------------------------------------------
    jsonl = Path(str(local_autonomy_env["tmp_path"])) / "proposals" / "proposals.jsonl"
    assert jsonl.is_file(), "the cycle wrote no proposals file"
    rows = [json.loads(line) for line in jsonl.read_text().splitlines() if line.strip()]
    assert rows, "proposals.jsonl is empty"

    pending = proposals_store.list_proposals("pending")
    assert pending, "the cycle produced no pending proposals"
    for row in pending:
        assert row["status"] == "pending", "autonomy must never self-approve (§5)"

    # ------------------------------------------------------------------
    # 2. A human approves one through the API, and only then does the
    #    bank grow. This is the HITL gate, exercised rather than asserted.
    # ------------------------------------------------------------------
    # No skip here on purpose: skipping would let a green run leave the HITL
    # leg — the half of the item that says "approves one through the API" —
    # entirely unexercised. A non-degraded cycle always files question drafts.
    target = next(
        (p for p in pending if p.get("proposal_kind", "question") == "question"),
        None,
    )
    assert target is not None, (
        "the cycle produced no question draft to approve; "
        f"kinds seen: {sorted({p.get('proposal_kind', 'question') for p in pending})}"
    )

    bank_before = set(bank_mod.load_bank())
    client = APIClient()
    response = client.post(
        f"/api/lsat/proposals/{target['id']}/approve",
        {"reviewer": "integration-test", "note": "BL-20260527-08"},
        format="json",
    )
    assert response.status_code == 200, response.content

    body = response.json()
    assert body["status"] == "approved"
    assert body["question_id"]

    bank_mod.load_bank.cache_clear()
    bank_after = set(bank_mod.load_bank())
    assert bank_after - bank_before == {body["question_id"]}

    # The store agrees with the API: the row is approved, the rest are not.
    reloaded = proposals_store.get_proposal(target["id"])
    assert reloaded is not None and reloaded["status"] == "approved"


@pytest.mark.skipif(not _URL, reason="set OLLAMA_INTEGRATION_URL to run this")
def test_the_cycle_is_audited_and_never_touched_a_hosted_tier(
    local_autonomy_env: dict[str, Any],
) -> None:
    """Provenance, and the pin that keeps this test free."""
    _require_live_ollama()

    from law_ai.core import audit_jsonl as audit_store

    call_command(
        "run_autonomy", "--kind", "lsat_content", "--budget", "2", stdout=StringIO()
    )

    events = audit_store.tail(400)
    types = [e.get("type") for e in events]
    assert "autonomy_cycle.start" in types
    assert "autonomy_cycle.end" in types

    _assert_the_local_model_answered(events)

    llm_calls = [e for e in events if e.get("type") == "llm_call"]
    providers = {str(e.get("provider") or e.get("model") or "") for e in llm_calls}
    assert not any(
        p.startswith(("claude", "anthropic", "xai")) for p in providers
    ), f"a hosted tier was billed by an integration test: {providers}"
