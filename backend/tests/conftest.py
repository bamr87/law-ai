"""Pytest configuration and shared fixtures for LawGraph AI (Django edition).

Run with::

    cd backend && pytest -q                          # default fast suite
    pytest -m integration                            # docker-backed
    pytest --cov=lawgraph --cov-report=html

Spec 011 ports the suite from the FastAPI/httpx layout to Django + DRF.
We expose:

* ``client`` — :class:`rest_framework.test.APIClient` for sync HTTP tests.
* ``async_client`` — :class:`httpx.AsyncClient` bound to the ASGI app for the
  many ``async def`` view tests inherited from spec 005/007/006.
* ``_reset_api_tokens`` — autouse fixture that wipes :class:`ApiToken` rows
  and forces every ``*_API_KEY`` setting to ``None`` so specs 008/009's
  default-open posture is preserved unless a test opts in.
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncGenerator, Generator

import django
import pytest
import pytest_asyncio

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "lawgraph.settings.test")
os.environ.setdefault("DATABASE_URL", "sqlite:///./test.sqlite3")
django.setup()

from django.conf import settings  # noqa: E402  (must follow django.setup())
from httpx import ASGITransport, AsyncClient  # noqa: E402
from neo4j import AsyncGraphDatabase  # noqa: E402
from redis.asyncio import Redis  # noqa: E402
from rest_framework.test import APIClient  # noqa: E402

from lawgraph.asgi import application as asgi_app  # noqa: E402


# ---------------------------------------------------------------------------
# Event loop
# ---------------------------------------------------------------------------
@pytest.fixture(scope="session")
def event_loop() -> Generator[asyncio.AbstractEventLoop, None, None]:
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


# ---------------------------------------------------------------------------
# HTTP clients
# ---------------------------------------------------------------------------
@pytest.fixture
def client() -> APIClient:
    """Sync DRF test client for routes that don't need an ASGI roundtrip."""
    return APIClient()


@pytest_asyncio.fixture
async def async_client() -> AsyncGenerator[AsyncClient, None]:
    """Async ASGI client (matches the FastAPI test ergonomics we ported from)."""
    async with AsyncClient(
        transport=ASGITransport(app=asgi_app), base_url="http://test"
    ) as ac:
        yield ac


# ---------------------------------------------------------------------------
# Auth defaults (specs 008 + 009)
# ---------------------------------------------------------------------------
@pytest.fixture(autouse=True)
def _reset_api_tokens(monkeypatch: pytest.MonkeyPatch, transactional_db) -> None:
    """Default-open posture: clear DB tokens and unset env-key settings.

    Uses ``transactional_db`` (commits between cleanup and the request thread)
    so the async test client running in a separate thread can read the same
    rows the test's main thread just wrote — SQLite's strict locking otherwise
    deadlocks on the first ApiToken read.
    """
    from lawgraph.core.models import ApiToken

    ApiToken.objects.all().delete()
    for name in (
        "AGENT_API_KEY",
        "ANALYSIS_API_KEY",
        "GRAPH_API_KEY",
        "LSAT_API_KEY",
    ):
        monkeypatch.setattr(settings, name, None, raising=False)


# ---------------------------------------------------------------------------
# Neo4j (integration)
# ---------------------------------------------------------------------------
@pytest_asyncio.fixture(scope="session")
async def neo4j_driver():
    uri = os.getenv("NEO4J_TEST_URI", settings.NEO4J_URI)
    user = os.getenv("NEO4J_TEST_USER", settings.NEO4J_USER)
    password = os.getenv("NEO4J_TEST_PASSWORD", settings.NEO4J_PASSWORD)
    driver = AsyncGraphDatabase.driver(uri, auth=(user, password))
    await driver.verify_connectivity()
    async with driver.session() as session:
        await session.run("MATCH (n) DETACH DELETE n")
    yield driver
    await driver.close()


@pytest_asyncio.fixture
async def neo4j_session(neo4j_driver):
    async with neo4j_driver.session() as session:
        yield session
        await session.run("MATCH (n) DETACH DELETE n")


# ---------------------------------------------------------------------------
# Redis (integration)
# ---------------------------------------------------------------------------
@pytest_asyncio.fixture
async def redis_client() -> AsyncGenerator[Redis, None]:
    redis = Redis.from_url(
        os.getenv("REDIS_TEST_URL", "redis://localhost:6379/1"),
        decode_responses=True,
    )
    await redis.flushdb()
    yield redis
    await redis.aclose()


# ---------------------------------------------------------------------------
# Mock LLM
# ---------------------------------------------------------------------------
@pytest.fixture
def mock_ollama(monkeypatch):
    from unittest.mock import AsyncMock

    async def fake_chat(*args, **kwargs):
        return {
            "message": {
                "role": "assistant",
                "content": "This is a mocked legal analysis response for testing.",
            },
            "done": True,
        }

    monkeypatch.setattr("ollama.AsyncClient.chat", AsyncMock(side_effect=fake_chat))
    return fake_chat


# ---------------------------------------------------------------------------
# Domain fixtures
# ---------------------------------------------------------------------------
@pytest.fixture(scope="session")
def legalbench_tasks():
    return {
        "rule_qa": [{"input": "What is the holding in Roe v. Wade?", "output": "..."}],
        "issue_spotting": [
            {"text": "The court held that...", "issues": ["due process"]}
        ],
    }


@pytest.fixture
def sample_case_input():
    return {
        "case_id": "test-roe-v-wade",
        "text": "The Supreme Court held that the right to privacy...",
        "jurisdiction": "US",
        "court": "Supreme Court",
        "year": 1973,
    }


@pytest.fixture
def sample_graph_result():
    return {
        "nodes": [{"id": "case:roe", "type": "Case", "title": "Roe v. Wade"}],
        "edges": [
            {"source": "case:roe", "target": "doctrine:privacy", "type": "HAS_HOLDING"}
        ],
        "summary": "Landmark privacy case establishing...",
    }
