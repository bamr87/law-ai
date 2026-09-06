"""Structural contract for the browser e2e harness (spec 051 / BL-20260811-16).

The harness has one failure mode that costs an hour to diagnose and a second to
fix: the Playwright image tag and the ``@playwright/test`` version drift apart.
The driver and the browsers ship together, so a mismatch fails at runtime with
"browser not found" — a message that points at the wrong thing entirely. The
rest of this module pins the wiring the harness needs to exist at all, so a
half-removed piece fails here instead of in a nightly run nobody watches.

Stdlib only, in keeping with the rest of ``tests/``.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.specs

#: Every spec file the harness is expected to carry, and the item it closes.
EXPECTED_SPECS = {
    "smoke.spec.ts": "BL-20260811-16",
    "analysis-stream.spec.ts": "BL-20260811-16",
    "analysis.spec.ts": "BL-20260429-27",
    "api-auth.spec.ts": "BL-20260430-11",
    "shell-sticky.spec.ts": "BL-20260831-05",
    "a11y.spec.ts": "BL-20260831-09",
    "admin-hitl.spec.ts": "BL-20260503-17",
}


@pytest.fixture(scope="module")
def dockerfile_e2e(repo_root: Path) -> str:
    return (repo_root / "frontend" / "Dockerfile.e2e").read_text(encoding="utf-8")


def test_playwright_image_tag_matches_the_locked_driver(
    repo_root: Path, dockerfile_e2e: str
) -> None:
    """The image tag and @playwright/test must be the same version."""
    match = re.search(r"mcr\.microsoft\.com/playwright:v([0-9.]+)-", dockerfile_e2e)
    assert match, "Dockerfile.e2e must pin an mcr.microsoft.com/playwright tag"
    image_version = match.group(1)

    lock = json.loads(
        (repo_root / "frontend" / "package-lock.json").read_text(encoding="utf-8")
    )
    locked = lock["packages"]["node_modules/@playwright/test"]["version"]
    assert image_version == locked, (
        f"Dockerfile.e2e pins playwright:v{image_version} but the lockfile has "
        f"@playwright/test {locked} — the browsers and the driver ship together"
    )


def test_compose_service_uses_that_dockerfile(repo_root: Path) -> None:
    compose = (repo_root / "docker-compose.yml").read_text(encoding="utf-8")
    assert "dockerfile: Dockerfile.e2e" in compose
    # Both sidecars stay behind the profile so `make dev`/`make down` ignore them.
    assert compose.count('profiles: [ "e2e" ]') >= 2


def test_e2e_backend_is_pinned_to_an_unreachable_ollama(repo_root: Path) -> None:
    """A billed model must never be reachable from a nightly browser run."""
    compose = (repo_root / "docker-compose.yml").read_text(encoding="utf-8")
    backend_e2e = compose.split("backend-e2e:", 1)[1].split("\n  e2e:", 1)[0]
    assert "LLM_PROVIDER_CHAIN=ollama" in backend_e2e
    assert "OLLAMA_BASE_URL=http://127.0.0.1:9" in backend_e2e
    assert "OLLAMA_MAX_RETRIES=0" in backend_e2e


def test_the_e2e_frontend_points_at_the_sidecar(repo_root: Path) -> None:
    """The browser's REST path must not reach the operator's real backend.

    Since BL-20260430-07 the app calls a same-origin Next proxy, so the API the
    UI talks to is whichever ``BACKEND_INTERNAL_URL`` the *server* holds. If
    ``make test-e2e`` stopped overriding it, every nightly analysis run would
    go through the dev backend's real provider chain — the exact bill the
    pinned-degraded sidecar exists to prevent.
    """
    compose = (repo_root / "docker-compose.yml").read_text(encoding="utf-8")
    assert "BACKEND_INTERNAL_URL=${FRONTEND_BACKEND_URL:-" in compose
    makefile = (repo_root / "Makefile").read_text(encoding="utf-8")
    target = makefile.split("\ntest-e2e:", 1)[1].split("\n\n", 1)[0]
    assert "FRONTEND_BACKEND_URL=http://backend-e2e:8000" in target


def test_make_targets_exist(repo_root: Path) -> None:
    makefile = (repo_root / "Makefile").read_text(encoding="utf-8")
    for target in ("test-e2e:", "test-e2e-typecheck:", "test-e2e-down:"):
        assert f"\n{target}" in makefile, f"Makefile is missing `{target}`"
    # e2e must not be wired into the PR gate: a full-stack boot plus a browser
    # image is minutes, and `make test` is the inner loop.
    aggregate = next(
        line for line in makefile.splitlines() if line.startswith("test: ")
    )
    assert "test-e2e" not in aggregate


def test_every_spec_is_present_and_names_its_item(repo_root: Path) -> None:
    e2e_dir = repo_root / "frontend" / "e2e"
    for filename, item in EXPECTED_SPECS.items():
        path = e2e_dir / filename
        assert path.is_file(), f"missing e2e spec {filename}"
        body = path.read_text(encoding="utf-8")
        assert item in body, f"{filename} should name the item it closes ({item})"


def test_the_static_site_has_its_own_harness(repo_root: Path) -> None:
    static = repo_root / "lsat-static"
    assert (static / "playwright.config.ts").is_file()
    assert (static / "e2e" / "responsive.spec.ts").is_file()
    assert (static / "e2e" / "serve.mjs").is_file()
    # The config is loaded as CommonJS (no "type": "module" in package.json),
    # so `import.meta` there is a runtime error rather than a lint nit.
    package = json.loads((static / "package.json").read_text(encoding="utf-8"))
    assert "type" not in package
    for name in ("playwright.config.ts", "e2e/responsive.spec.ts"):
        code = [
            line
            for line in (static / name).read_text(encoding="utf-8").splitlines()
            # The prohibition is documented in a comment in both files; only
            # actual code counts.
            if not line.lstrip().startswith(("*", "//", "/*"))
        ]
        assert "import.meta" not in "\n".join(code), name


def test_static_playwright_version_matches_the_frontend(repo_root: Path) -> None:
    """One Playwright version across the repo, so one browser image serves both."""
    static_lock = json.loads(
        (repo_root / "lsat-static" / "package-lock.json").read_text(encoding="utf-8")
    )
    frontend_lock = json.loads(
        (repo_root / "frontend" / "package-lock.json").read_text(encoding="utf-8")
    )
    assert (
        static_lock["packages"]["node_modules/@playwright/test"]["version"]
        == frontend_lock["packages"]["node_modules/@playwright/test"]["version"]
    )


def test_api_schema_fixture_is_checked_in(repo_root: Path) -> None:
    """The contract gate needs its fixture in the tree, not generated on demand."""
    fixture = repo_root / "frontend" / "__tests__" / "fixtures" / "api-schema.json"
    assert fixture.is_file(), "run `make manage CMD=export_api_schema`"
    document = json.loads(fixture.read_text(encoding="utf-8"))
    assert "AnalysisResponse" in document["contracts"]
    assert "LsatQuestion" in document["contracts"]


def test_the_harness_is_documented(repo_root: Path) -> None:
    doc = (repo_root / "docs" / "e2e-testing.md").read_text(encoding="utf-8")
    assert "make test-e2e" in doc
    for item in sorted(set(EXPECTED_SPECS.values())):
        assert item in doc, f"docs/e2e-testing.md should mention {item}"
