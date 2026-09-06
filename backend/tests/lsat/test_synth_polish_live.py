"""The polish prompt against a real provider — opt-in, never in CI.

BL-20260903-17. Every other polish test stubs the chain, which proves the lint
and the plumbing but says nothing about the thing that actually matters: how
many of the predicates a real model proposes survive the lint. That number is
a property of the *prompt*, and the only way to measure it is to run it.

This file is skipped unless ``LSAT_SYNTH_LIVE_POLISH=1`` and is marked
``integration`` on top of that, because the default provider chain's first two
tiers are paid (Claude, then xAI) and the test settings deliberately blank LLM
credentials. Run it deliberately:

    LSAT_SYNTH_LIVE_POLISH=1 docker compose run --rm backend \\
        pytest tests/lsat/test_synth_polish_live.py -m integration -q --no-cov

Pin ``LLM_PROVIDER_CHAIN=ollama`` first if you want the free tier. The yield
depends on which tier answers, so the assertion message names it: a number
without its provider is not comparable to another number.
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


def _domains() -> list[DomainPack]:
    packs = [d for d in load_domains().values() if d.supports("prop")]
    if len(packs) < _DOMAINS:  # pragma: no cover - fixture drift
        pytest.skip(f"only {len(packs)} prop domains available")
    return packs[:_DOMAINS]


def test_the_prompt_yield_clears_the_floor() -> None:
    """Across three domains, most proposed predicates survive the lint."""
    aggregate = PolishYield()
    tiers: set[str] = set()
    accepted: dict[str, list] = {}
    for domain in _domains():
        properties, measured = asyncio.run(propose_with_yield(domain, count=_COUNT))
        if measured.error == "unavailable":
            pytest.skip("no provider in the chain could serve the polish call")
        aggregate.merge(measured)
        accepted[domain.id] = properties
        if measured.model_label:
            tiers.add(measured.model_label)

    route = ", ".join(sorted(tiers)) or "unknown"
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
