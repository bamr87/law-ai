"""The polish prompt against a real provider — opt-in, never in CI.

BL-20260903-17. Every other polish test stubs the chain, which proves the lint
and the plumbing but says nothing about the thing that actually matters: how
many of the predicates a real model proposes survive the lint. That number is
a property of the *prompt*, and the only way to measure it is to run it.

This file is skipped unless ``LSAT_SYNTH_LIVE_POLISH=1`` and is marked
``integration`` on top of that, because the default provider chain's first two
tiers are paid (Claude, then xAI) and the test settings deliberately blank LLM
credentials.

The free tier needs one more thing, and it is the reason this test used to be
unrunnable rather than merely unrun: ``settings/test.py`` pins
``OLLAMA_BASE_URL`` at a closed port unconditionally, so exporting
``LLM_PROVIDER_CHAIN=ollama`` alone leaves every round ``unavailable``. Point
the suite at a real Ollama with ``OLLAMA_INTEGRATION_URL`` — the same opt-in
var the factory integration test uses — and optionally at a smaller model with
``OLLAMA_INTEGRATION_MODEL`` when the box cannot hold the 7B default::

    docker compose run --rm --no-deps \\
        -e LSAT_SYNTH_LIVE_POLISH=1 -e LLM_PROVIDER_CHAIN=ollama \\
        -e OLLAMA_INTEGRATION_URL=http://ollama:11434 \\
        -e OLLAMA_INTEGRATION_MODEL=qwen2.5:3b-instruct-q4_K_M \\
        backend pytest tests/lsat/test_synth_polish_live.py \\
        -m integration -q --no-cov

Without ``OLLAMA_INTEGRATION_URL`` the chain is whatever the environment
configures; a hosted tier answers on its own credentials. The yield depends on
which tier answers, so the assertion message names it: a number without its
provider is not comparable to another number.
"""

from __future__ import annotations

import asyncio
import os

import pytest

from law_ai.lsat.synth.generate import generate
from law_ai.lsat.synth.lexicon import DomainPack, load_domains
from law_ai.lsat.synth.polish import (
    POLISH_YIELD_FLOOR,
    PolishYield,
    propose_with_yield,
)

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.environ.get("LSAT_SYNTH_LIVE_POLISH") != "1",
        reason="live polish measurement is opt-in: set LSAT_SYNTH_LIVE_POLISH=1",
    ),
]

#: How many domains the measurement spans. One domain's vocabulary could be
#: unusually easy or hard for the model; three is enough to notice.
_DOMAINS = 3

#: Predicates asked for per domain.
_COUNT = 6


@pytest.fixture(autouse=True)
def _local_tier(monkeypatch: pytest.MonkeyPatch) -> None:
    """Undo the suite-wide Ollama lockout when an operator opts in.

    ``settings/test.py`` aims ``OLLAMA_BASE_URL`` at a closed port so no unit
    test can wander onto a live model. That is right for the suite and fatal
    for this test, which exists to reach one. ``OLLAMA_INTEGRATION_URL`` is the
    single, explicit way back — nothing sets it but a deliberate command.
    """
    from django.conf import settings as dj_settings

    url = os.environ.get("OLLAMA_INTEGRATION_URL", "").strip()
    if not url:
        return
    monkeypatch.setattr(dj_settings, "OLLAMA_BASE_URL", url)
    model = os.environ.get("OLLAMA_INTEGRATION_MODEL", "").strip()
    if model:
        monkeypatch.setattr(dj_settings, "OLLAMA_DEFAULT_MODEL", model)
    # A CPU-only box generates a few tokens a second; the product default of
    # 120 s is a latency budget, not a measurement budget.
    monkeypatch.setattr(
        dj_settings,
        "OLLAMA_REQUEST_TIMEOUT_S",
        max(float(dj_settings.OLLAMA_REQUEST_TIMEOUT_S), 900.0),
    )


def _domains() -> list[DomainPack]:
    packs = [d for d in load_domains().values() if d.supports("prop")]
    if len(packs) < _DOMAINS:  # pragma: no cover - fixture drift
        pytest.skip(f"only {len(packs)} prop domains available")
    return packs[:_DOMAINS]


def test_the_prompt_yield_clears_the_floor() -> None:
    """Across three domains, most proposed predicates survive the lint.

    A single unavailable round does not abandon the measurement. The local tier
    is the free one, it is also the slow one, and on a CPU-only box roughly one
    generation in three times out — skipping the whole test on the first of
    those is how this test stayed unexecuted. Rounds that never reached the
    lint are counted and reported; the yield is computed over the ones that did,
    and the test only stands aside when *nothing* answered.
    """
    aggregate = PolishYield()
    tiers: set[str] = set()
    accepted: dict[str, list] = {}
    unavailable: list[str] = []
    for domain in _domains():
        properties, measured = asyncio.run(propose_with_yield(domain, count=_COUNT))
        if measured.error == "unavailable":
            unavailable.append(domain.id)
            continue
        aggregate.merge(measured)
        accepted[domain.id] = properties
        if measured.model_label:
            tiers.add(measured.model_label)

    route = ", ".join(sorted(tiers)) or "unknown"
    if not aggregate.proposed:
        pytest.skip(
            "no provider in the chain served a polish call "
            f"(unavailable: {unavailable or 'none'}; rounds that answered "
            f"proposed nothing)"
        )
    assert aggregate.proposed > 0, f"the chain ({route}) proposed nothing"
    assert aggregate.rate >= POLISH_YIELD_FLOOR, (
        f"polish yield {aggregate.rate:.2f} from {route} is below the "
        f"{POLISH_YIELD_FLOOR:.2f} floor; rejects: {aggregate.rejected}"
    )

    # Yield is only meaningful if the survivors are usable: every accepted
    # vocabulary must still render an item the verifier proves.
    for domain_id, properties in accepted.items():
        if not properties:
            continue
        domain = load_domains()[domain_id]
        extended = domain.model_copy(
            update={"properties": [*properties, *domain.properties]}
        )
        item = generate(
            "lr-conditional-chain-forward",
            domain_id,
            seed=0,
            domain_override=extended,
        )
        assert item.report.ok, f"{domain_id}: polished item failed verification"
