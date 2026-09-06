"""Rate limiting on LLM-invoking endpoints (BL-20260810-11).

The gap these close: `/api/analysis` and the LSAT tutor each fan out to a
single local Ollama with a 120 s timeout behind an open-by-default auth
gate, so one client could starve every other user.

Note on technique: the throttle rate is forced by monkeypatching
``ScopedRateThrottle.get_rate`` rather than ``override_settings``. DRF caches
its settings in ``rest_framework.settings.api_settings``, and inside async
tests the restore did not take effect — a 1/min override leaked into every
later test in the session. ``monkeypatch`` is scoped to the test and undone
unconditionally.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import pytest
import pytest_asyncio
from django.core.cache import cache
from httpx import ASGITransport, AsyncClient
from rest_framework.throttling import ScopedRateThrottle

from django.conf import settings
from law_ai.asgi import application as app


@pytest.fixture(autouse=True)
def _isolate(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setattr(settings, "AUDIT_PATH", str(tmp_path / "audit.jsonl"))
    # DRF keeps throttle history in the cache — clear it so each test starts
    # from an empty bucket regardless of execution order.
    cache.clear()
    yield
    cache.clear()


@pytest_asyncio.fixture
async def client() -> AsyncIterator[AsyncClient]:
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac


def _force_rate(monkeypatch: pytest.MonkeyPatch, rate: str) -> None:
    monkeypatch.setattr(ScopedRateThrottle, "get_rate", lambda self: rate)


_BODY = {"text": "Contract dispute.", "use_langgraph": False}


@pytest.mark.asyncio
async def test_analysis_is_throttled_after_the_limit(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _force_rate(monkeypatch, "1/min")
    first = await client.post("/api/analysis", json=_BODY)
    second = await client.post("/api/analysis", json=_BODY)
    assert first.status_code == 200
    assert second.status_code == 429


@pytest.mark.asyncio
async def test_analysis_not_throttled_under_the_limit(client: AsyncClient) -> None:
    """The suite's configured rate must not trip on ordinary use."""
    for _ in range(3):
        res = await client.post("/api/analysis", json=_BODY)
        assert res.status_code == 200


@pytest.mark.asyncio
async def test_cheap_read_endpoints_are_not_throttled(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Only LLM-invoking endpoints carry the `llm` scope."""
    _force_rate(monkeypatch, "1/min")
    for _ in range(5):
        res = await client.get("/api/lsat/sections")
        assert res.status_code == 200


def test_llm_scope_is_applied_to_the_right_views() -> None:
    from law_ai.analysis.urls import AnalysisView
    from law_ai.lsat.urls import GradeView, TutorView

    assert AnalysisView.throttle_scope == "llm"
    assert TutorView.throttle_scope == "llm"
    # Grading is deterministic (no model call) — must stay unthrottled.
    assert getattr(GradeView, "throttle_scope", None) is None


def test_production_default_rate_is_configured() -> None:
    """base.py ships a real limit even though the suite raises it."""
    from law_ai.settings import base

    assert base.REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"]["llm"] == "20/min"


# ---------------------------------------------------------------------------
# Per-principal buckets (BL-20260811-06, BL-20260503-12)
# ---------------------------------------------------------------------------
def _force_rate_for_every_principal(monkeypatch: pytest.MonkeyPatch, rate: str) -> None:
    """Force *rate* on the per-principal throttle itself.

    ``_force_rate`` patches ``ScopedRateThrottle.get_rate``, which the subclass
    overrides — an identified caller would otherwise pick up the (huge) test
    ``llm_keyed`` rate and never trip the limit. Patching the subclass makes
    every principal share one rate, which is exactly what an "independent
    buckets" assertion needs.
    """
    from law_ai.core.throttling import ScopedActorRateThrottle

    monkeypatch.setattr(ScopedActorRateThrottle, "get_rate", lambda self: rate)


def _seed_key(scope: str = "analysis", **extra: object):
    """Provision an ApiToken and return ``(token, raw_key)``."""
    from law_ai.core.models import ApiToken

    token, raw = ApiToken.generate(scope=scope, name="throttle-test")
    for field, value in extra.items():
        setattr(token, field, value)
    if extra:
        token.save()
    return token, raw


@pytest.mark.django_db
@pytest.mark.asyncio
async def test_a_keyed_request_does_not_explode(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Regression: `request.user.pk` used to raise on every throttled view.

    ``_AnonymousActor`` set ``is_authenticated = True`` without a ``pk``, and
    nothing sent a provisioned key at a throttled endpoint, so a 500 sat
    latent behind the one path a real deployment uses (BL-20260503-12).
    """
    from asgiref.sync import sync_to_async

    _token, raw = await sync_to_async(_seed_key)()
    res = await client.post("/api/analysis", json=_BODY, headers={"X-API-Key": raw})
    assert res.status_code == 200


@pytest.mark.django_db
@pytest.mark.asyncio
async def test_two_keys_behind_one_ip_get_independent_buckets(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The BL-20260811-06 complaint: one shared proxy, many legitimate users."""
    from asgiref.sync import sync_to_async

    _force_rate_for_every_principal(monkeypatch, "1/min")
    _t1, first_key = await sync_to_async(_seed_key)()
    _t2, second_key = await sync_to_async(_seed_key)()

    a1 = await client.post(
        "/api/analysis", json=_BODY, headers={"X-API-Key": first_key}
    )
    a2 = await client.post(
        "/api/analysis", json=_BODY, headers={"X-API-Key": first_key}
    )
    b1 = await client.post(
        "/api/analysis", json=_BODY, headers={"X-API-Key": second_key}
    )
    assert a1.status_code == 200
    assert a2.status_code == 429  # same key, same bucket
    assert b1.status_code == 200  # different key, same IP → untouched


@pytest.mark.django_db
@pytest.mark.asyncio
async def test_an_anonymous_caller_is_unaffected_by_a_keyed_burst(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from asgiref.sync import sync_to_async

    _force_rate_for_every_principal(monkeypatch, "1/min")
    _token, raw = await sync_to_async(_seed_key)()
    await client.post("/api/analysis", json=_BODY, headers={"X-API-Key": raw})
    await client.post("/api/analysis", json=_BODY, headers={"X-API-Key": raw})

    anonymous = await client.post("/api/analysis", json=_BODY)
    assert anonymous.status_code == 200


@pytest.mark.django_db
def test_the_cache_key_is_the_token_key_hash() -> None:
    """BL-20260503-12 asked for a bucket keyed on ``request.auth.key_hash``."""
    from rest_framework.test import APIRequestFactory

    from law_ai.analysis.urls import AnalysisView
    from law_ai.core.throttling import ScopedActorRateThrottle

    token, _raw = _seed_key()
    request = APIRequestFactory().post("/api/analysis")
    request.auth = token
    request.user = None

    throttle = ScopedActorRateThrottle()
    throttle.scope = AnalysisView.throttle_scope
    throttle._principal = ("key", token.key_hash, token)
    assert throttle.get_cache_key(request, AnalysisView()) == (
        f"throttle_llm_key:{token.key_hash}"
    )


@pytest.mark.django_db
def test_a_signed_in_user_buckets_on_their_pk() -> None:
    from django.contrib.auth import get_user_model
    from rest_framework.test import APIRequestFactory

    from law_ai.analysis.urls import AnalysisView
    from law_ai.core.throttling import ScopedActorRateThrottle, resolve_principal

    user = get_user_model().objects.create_user(username="ada", password="pw-123456")
    request = APIRequestFactory().post("/api/analysis")
    request.auth = None
    request.user = user

    kind, ident, token = resolve_principal(request, "203.0.113.4")
    assert (kind, ident, token) == ("user", str(user.pk), None)

    throttle = ScopedActorRateThrottle()
    throttle.scope = AnalysisView.throttle_scope
    throttle._principal = (kind, ident, token)
    assert throttle.get_cache_key(request, AnalysisView()) == (
        f"throttle_llm_user:{user.pk}"
    )


def test_an_unidentified_caller_still_buckets_on_ip() -> None:
    from rest_framework.test import APIRequestFactory

    from law_ai.core.throttling import resolve_principal

    request = APIRequestFactory().post("/api/analysis")
    request.auth = None
    request.user = None
    assert resolve_principal(request, "203.0.113.4") == ("ip", "203.0.113.4", None)


@pytest.mark.django_db
def test_an_identified_caller_gets_the_keyed_rate() -> None:
    from law_ai.core.throttling import ScopedActorRateThrottle

    throttle = ScopedActorRateThrottle()
    throttle.scope = "llm"
    throttle.THROTTLE_RATES = {"llm": "20/min", "llm_keyed": "60/min"}

    throttle._principal = ("ip", "203.0.113.4", None)
    assert throttle.get_rate() == "20/min"

    throttle._principal = ("user", "7", None)
    assert throttle.get_rate() == "60/min"


@pytest.mark.django_db
def test_a_per_token_rate_limit_overrides_both() -> None:
    from law_ai.core.throttling import ScopedActorRateThrottle

    token, _raw = _seed_key(rate_limit="200/min")
    throttle = ScopedActorRateThrottle()
    throttle.scope = "llm"
    throttle.THROTTLE_RATES = {"llm": "20/min", "llm_keyed": "60/min"}
    throttle._principal = ("key", token.key_hash, token)
    assert throttle.get_rate() == "200/min"


def test_production_keyed_rate_is_configured() -> None:
    from law_ai.settings import base

    rates = base.REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"]
    assert rates["llm_keyed"] == "60/min"
    # The keyed bucket must be at least as generous as the anonymous one, or
    # identifying yourself would be a punishment.
    assert int(rates["llm_keyed"].split("/")[0]) >= int(rates["llm"].split("/")[0])


def test_llm_views_use_the_per_principal_throttle() -> None:
    from law_ai.analysis.urls import AnalysisView
    from law_ai.core.throttling import ScopedActorRateThrottle
    from law_ai.lsat.urls import TutorView

    assert AnalysisView.throttle_classes == [ScopedActorRateThrottle]
    assert TutorView.throttle_classes == [ScopedActorRateThrottle]


# ---------------------------------------------------------------------------
# /api/agents/* — the audit-log surface (BL-20260503-12, absorbing
# BL-20260430-09: "a leaked key must not scrape the audit log at line speed")
# ---------------------------------------------------------------------------
def _force_audit_rate(monkeypatch: pytest.MonkeyPatch, rate: str) -> None:
    from law_ai.core.throttling import ScopedActorRateThrottle

    monkeypatch.setattr(ScopedActorRateThrottle, "get_rate", lambda self: rate)


@pytest.mark.django_db
@pytest.mark.asyncio
async def test_a_keyed_burst_at_the_audit_log_is_throttled(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The exact scenario BL-20260430-09 named: scraping `/api/agents/runs`."""
    from asgiref.sync import sync_to_async

    _force_audit_rate(monkeypatch, "2/min")
    _token, raw = await sync_to_async(_seed_key)("agent")
    headers = {"X-API-Key": raw}

    first = await client.get("/api/agents/runs", headers=headers)
    second = await client.get("/api/agents/runs", headers=headers)
    third = await client.get("/api/agents/runs", headers=headers)

    assert first.status_code == 200
    assert second.status_code == 200
    assert third.status_code == 429


@pytest.mark.django_db
@pytest.mark.asyncio
async def test_the_run_detail_and_metrics_reads_share_the_audit_quota(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """One key, one bucket across the whole `/api/agents/*` audit surface."""
    from asgiref.sync import sync_to_async

    _force_audit_rate(monkeypatch, "2/min")
    _token, raw = await sync_to_async(_seed_key)("agent")
    headers = {"X-API-Key": raw}

    assert (await client.get("/api/agents/runs", headers=headers)).status_code == 200
    assert (
        await client.get("/api/agents/runs/abc123", headers=headers)
    ).status_code == 200
    assert (await client.get("/api/agents/metrics", headers=headers)).status_code == 429


@pytest.mark.django_db
@pytest.mark.asyncio
async def test_one_scraping_key_does_not_starve_another_at_the_audit_log(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from asgiref.sync import sync_to_async

    _force_audit_rate(monkeypatch, "1/min")
    _t1, first_key = await sync_to_async(_seed_key)("agent")
    _t2, second_key = await sync_to_async(_seed_key)("agent")

    a1 = await client.get("/api/agents/runs", headers={"X-API-Key": first_key})
    a2 = await client.get("/api/agents/runs", headers={"X-API-Key": first_key})
    b1 = await client.get("/api/agents/runs", headers={"X-API-Key": second_key})

    assert a1.status_code == 200
    assert a2.status_code == 429
    assert b1.status_code == 200


def test_agents_views_carry_the_audit_throttle() -> None:
    from law_ai.agentsapi.autonomy_views import _Base as AutonomyBase
    from law_ai.agentsapi.urls import (
        AgentListView,
        AgentMetricsView,
        AgentRunDetailView,
        AgentRunsView,
    )
    from law_ai.core.throttling import ScopedActorRateThrottle

    for view in (
        AgentListView,
        AgentRunsView,
        AgentRunDetailView,
        AgentMetricsView,
        AutonomyBase,
    ):
        assert view.throttle_classes == [ScopedActorRateThrottle], view
        assert view.throttle_scope == "audit", view


def test_production_audit_rate_is_configured() -> None:
    from law_ai.settings import base

    rates = base.REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"]
    assert rates["audit"] == "120/min"
    assert rates["audit_keyed"] == "600/min"
    # Cheap reads, so more generous than `llm` — but finite, which is the point.
    assert int(rates["audit"].split("/")[0]) > int(rates["llm"].split("/")[0])
