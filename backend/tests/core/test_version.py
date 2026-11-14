"""``GET /version`` and the shared version source (UPS-BE-11, issue #208)."""

from __future__ import annotations

import json
import tomllib
from importlib import metadata
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from law_ai.asgi import application as app
from law_ai.core import urls_health as health_module
from law_ai.core import version as version_module


class _FakeSession:
    async def __aenter__(self) -> _FakeSession:
        return self

    async def __aexit__(self, *exc: object) -> None:
        return None


class _FakeDriver:
    def session(self) -> _FakeSession:
        return _FakeSession()


async def _get(path: str) -> tuple[int, dict[str, object]]:
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as c:
        resp = await c.get(path)
    return resp.status_code, resp.json()


@pytest.mark.asyncio
async def test_version_shape_without_credentials(monkeypatch) -> None:
    monkeypatch.delenv("GIT_SHA", raising=False)
    monkeypatch.delenv("BUILT_AT", raising=False)

    status, body = await _get("/version")

    assert status == 200
    assert set(body) == {"name", "version", "commit", "built_at"}
    assert body["name"] == "law-ai"
    assert body["version"] == version_module.get_version()
    assert body["commit"] is None
    assert body["built_at"] is None


@pytest.mark.asyncio
async def test_version_reports_build_provenance(monkeypatch) -> None:
    monkeypatch.setenv("GIT_SHA", "abc1234")
    monkeypatch.setenv("BUILT_AT", "2026-11-12T00:00:00Z")

    status, body = await _get("/version/")

    assert status == 200
    assert body["commit"] == "abc1234"
    assert body["built_at"] == "2026-11-12T00:00:00Z"


@pytest.mark.asyncio
async def test_root_health_and_version_agree(monkeypatch) -> None:
    monkeypatch.setattr(version_module.metadata, "version", lambda _name: "9.8.7")
    monkeypatch.setattr(health_module, "get_neo4j_driver", _FakeDriver)

    async def _none(_session: object) -> None:
        return None

    monkeypatch.setattr(health_module, "get_last_ingest_at", _none)

    _, root = await _get("/")
    _, health = await _get("/health")
    _, version = await _get("/version")

    assert root["version"] == health["version"] == version["version"] == "9.8.7"


def test_get_version_falls_back_to_unknown(monkeypatch) -> None:
    def _missing(name: str) -> str:
        raise metadata.PackageNotFoundError(name)

    monkeypatch.setattr(version_module.metadata, "version", _missing)

    assert version_module.get_version() == "unknown"


_REPO_ROOT = Path(__file__).resolve().parents[3]
_MANIFEST = _REPO_ROOT / ".release-please-manifest.json"


@pytest.mark.skipif(
    not _MANIFEST.is_file(), reason="needs the full repo (no release manifest)"
)
def test_package_manifests_match_the_release() -> None:
    release = json.loads(_MANIFEST.read_text())["."]
    pyproject = tomllib.loads((_REPO_ROOT / "backend/pyproject.toml").read_text())
    package = json.loads((_REPO_ROOT / "frontend/package.json").read_text())

    assert pyproject["project"]["version"] == release
    assert package["version"] == release
