"""Pytest configuration and shared fixtures for Law AI (Django edition).

Run with::

    cd backend && pytest -q                          # default fast suite
    pytest -m integration                            # docker-backed
    pytest --cov=law_ai --cov-report=html

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
import shutil
import subprocess
from collections.abc import AsyncGenerator, Generator

import django
import pytest
import pytest_asyncio

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "law_ai.settings.test")
os.environ.setdefault("DATABASE_URL", "sqlite:///./test.sqlite3")
django.setup()

from django.conf import settings  # noqa: E402  (must follow django.setup())
from httpx import ASGITransport, AsyncClient  # noqa: E402
from neo4j import AsyncGraphDatabase  # noqa: E402
from redis.asyncio import Redis  # noqa: E402
from rest_framework.test import APIClient  # noqa: E402

try:
    import asyncpg
except ImportError:
    asyncpg = None  # type: ignore

from law_ai.asgi import application as asgi_app  # noqa: E402


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
    from law_ai.core.models import ApiToken

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
# Docker-backed integration fixtures (spec 013)
# ---------------------------------------------------------------------------
@pytest.fixture(scope="session")
def docker_services():
    """Ensure neo4j + postgres + redis are up for integration tests.

    Uses the existing docker-compose.yml with health checks added in T-001.

    Two run modes (Docker-first per CLAUDE.md):

    * **In-container** (``make test-integration`` → ``docker compose run --rm
      backend pytest -m integration``): there is no ``docker`` CLI inside the
      backend container, and the Makefile target already brought the stack up
      on the host *before* invoking pytest. We detect the missing CLI and
      no-op — the services are reachable on the compose network by name.
    * **Host** (a developer running pytest directly): the ``docker`` CLI is
      present, so we manage the stack's lifecycle here.
    """
    docker = shutil.which("docker")
    if docker is None:
        # No CLI → running inside a container; the orchestrator owns lifecycle.
        yield
        return
    subprocess.run(
        [docker, "compose", "up", "-d", "neo4j", "postgres", "redis", "--wait"],
        check=True,
    )
    yield
    # Teardown: stop services but don't remove volumes (faster for repeated runs)
    subprocess.run([docker, "compose", "down"], check=False)


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def neo4j_integration_driver(docker_services):
    """AsyncDriver connected to the Docker-compose Neo4j.

    FR-2: Session-scoped driver for integration tests. ``loop_scope="session"``
    keeps the driver bound to the same event loop across tests; without it,
    pytest-asyncio creates a new loop per test and the driver's pending
    futures end up "attached to a different loop".

    Endpoint is read from ``NEO4J_URI``/``NEO4J_USER``/``NEO4J_PASSWORD`` so the
    in-container run (Makefile injects ``bolt://neo4j:7687``) and a host run
    (defaults to ``bolt://localhost:7687``) both connect.
    """
    uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
    user = os.getenv("NEO4J_USER", "neo4j")
    password = os.getenv("NEO4J_PASSWORD", "law_ai-dev")
    driver = AsyncGraphDatabase.driver(uri, auth=(user, password))
    await driver.verify_connectivity()
    yield driver
    await driver.close()


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def postgres_integration_pool(docker_services):
    """asyncpg.Pool connected to the Docker-compose Postgres.

    FR-3: Session-scoped pool for integration tests. See note on
    ``neo4j_integration_driver`` for why ``loop_scope="session"`` is required.
    """
    if asyncpg is None:
        pytest.skip("asyncpg not installed")

    # Prefer an injected Postgres DSN (Makefile sets DATABASE_URL to the compose
    # ``postgres`` host). Ignore the module-level sqlite default — asyncpg needs
    # a real postgres:// URL — and fall back to the host-published port.
    dsn = os.getenv("DATABASE_URL", "")
    if not dsn.startswith(("postgresql://", "postgres://")):
        dsn = "postgresql://law_ai:law_ai-dev@localhost:5432/law_ai"
    pool = await asyncpg.create_pool(dsn, min_size=1, max_size=5)
    yield pool
    await pool.close()


@pytest_asyncio.fixture(scope="function", loop_scope="session")
async def clean_neo4j_db(neo4j_integration_driver):
    """Wipe Neo4j before each integration test.

    NFR-ISOLATION-1: Function-scoped for per-test isolation. Loop scope is
    session so this fixture shares the loop of the session-scoped driver.
    """
    async with neo4j_integration_driver.session() as session:
        await session.run("MATCH (n) DETACH DELETE n")
    yield


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
