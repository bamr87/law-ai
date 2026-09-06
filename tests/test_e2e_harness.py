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


def test_the_static_viewport_suite_is_run_by_a_workflow(repo_root: Path) -> None:
    """BL-20260901-03: a measurement nothing runs is not an automated check.

    The static site's responsive numbers were verified by hand; the point of
    the harness is that they stop being verified by hand. ``make
    lsat-static-e2e`` is a build plus a browser image, so it runs nightly
    alongside the frontend suite rather than per-PR — but it has to run
    *somewhere*, which is what this pins.
    """
    workflows = repo_root / ".github" / "workflows"
    runners = [
        path.name
        for path in sorted(workflows.glob("*.yml"))
        if "make lsat-static-e2e" in path.read_text(encoding="utf-8")
    ]
    assert runners, (
        "no workflow runs `make lsat-static-e2e` — the viewport measurements "
        "would be automatable but never automatic"
    )


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


def test_the_analysis_spec_has_a_healthy_run_to_render(repo_root: Path) -> None:
    """BL-20260429-27: the IRAC/precedents/trace-id assertions need a real result.

    The e2e sidecar is pinned to an unreachable Ollama on purpose, so a live
    ``POST /api/analysis`` there can only produce the degraded engine-state
    panel — which renders no IRAC card, no precedent list and no trace-id copy
    control. The healthy branch is reached by replaying a *persisted* run, so
    ``make test-e2e`` has to seed one and the specs have to name the same id.
    """
    makefile = (repo_root / "Makefile").read_text(encoding="utf-8")
    target = makefile.split("\ntest-e2e:", 1)[1].split("\n\n", 1)[0]
    assert "seed_analysis_run" in target, (
        "make test-e2e must seed the persisted analysis the specs replay"
    )

    command = (
        repo_root
        / "backend"
        / "law_ai"
        / "analysis"
        / "management"
        / "commands"
        / "seed_analysis_run.py"
    )
    assert command.is_file(), "the seeded run's management command is missing"
    source = command.read_text(encoding="utf-8")
    analysis_id = re.search(r'^ANALYSIS_ID = "([^"]+)"', source, re.M)
    trace_id = re.search(r'^TRACE_ID = "([^"]+)"', source, re.M)
    assert analysis_id and trace_id, "seed_analysis_run must pin both ids"
    # The chip elides to eight characters, so a shorter id would make the
    # "the clipboard carries the whole id" assertion vacuous.
    assert len(trace_id.group(1)) > 8

    e2e_dir = repo_root / "frontend" / "e2e"
    analysis_spec = (e2e_dir / "analysis.spec.ts").read_text(encoding="utf-8")
    assert analysis_id.group(1) in analysis_spec
    assert trace_id.group(1) in analysis_spec
    # The live half must assert the panel the pinned sidecar really produces.
    assert "engine-state" in analysis_spec
    assert (e2e_dir / "api-auth.spec.ts").read_text(encoding="utf-8").count(
        analysis_id.group(1)
    ) >= 1


def test_the_auth_spec_covers_every_scope_and_page(repo_root: Path) -> None:
    """BL-20260430-11: a page that calls nothing cannot prove a key was attached."""
    spec = (repo_root / "frontend" / "e2e" / "api-auth.spec.ts").read_text(
        encoding="utf-8"
    )
    endpoints = spec.split("const ENDPOINTS = [", 1)[1].split("]", 1)[0]
    # All four scopes law_ai/core/auth.py defines, analysis included.
    for fragment in ("/api/agents/", "/api/analysis/", "/api/graph/", "/api/lsat/"):
        assert fragment in endpoints, f"ENDPOINTS is missing the {fragment} scope"
    # Each page names the router it must actually have reached.
    pages = spec.split("const PAGES = [", 1)[1].split("\n]", 1)[0]
    assert pages.count("served:") == 4, "every page needs a `served` endpoint"
    assert spec.count("await expectReachedItsRouter(") == 2, (
        "both postures must assert the page really called its router — "
        "otherwise the 'no 401' assertion passes on a page that called nothing"
    )
    # The wait has to outlast `next dev`'s first compile of the proxy route,
    # which is what made the original assertion vacuous.
    assert "expect\n    .poll(" in spec or "expect.poll" in spec, (
        "a fixed networkidle wait can settle before the page's first API call"
    )


def test_the_gated_auth_posture_runs_in_ci(repo_root: Path) -> None:
    """BL-20260430-11: the gated half is skipped unless CI supplies a key.

    ``test.skip(!KEY, …)`` means a bare ``make test-e2e`` never exercises the
    gate. Nothing would go red if the backend check or the proxy's server-side
    key injection regressed, so the nightly needs a second, keyed leg.
    """
    workflow = (repo_root / ".github" / "workflows" / "nightly-tests.yml").read_text(
        encoding="utf-8"
    )
    steps = workflow.split("\n      - name: ")
    gated = [
        step
        for step in steps
        if "api-auth.spec.ts" in step
        and re.search(r'E2E_AGENT_API_KEY="([^"]+)"', step)
    ]
    assert gated, "no nightly step runs the api-auth spec with a key"
    body = gated[0]
    assert "make test-e2e" in body
    key = re.search(r'E2E_AGENT_API_KEY="([^"]+)"', body)
    assert key and key.group(1).strip(), (
        "the gated leg must pass a non-empty E2E_AGENT_API_KEY"
    )


def test_the_a11y_smoke_runs_on_every_pull_request(repo_root: Path) -> None:
    """BL-20260831-09 asked for CI on every PR, not a weekly nightly.

    ``scripts/ux_audit.py`` cannot compute a contrast ratio or watch focus
    move; axe-core in a browser can. A gate that only fires once a week finds
    the regression after it shipped.
    """
    ci = (repo_root / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert "\n  pull_request:" in ci, "ci.yml must still be a pull_request workflow"
    assert "a11y.spec.ts" in ci, (
        "no ci.yml job runs the axe-core smoke — a nightly-only a11y gate is "
        "not 'checked on every PR'"
    )
    job = ci.split("\n  a11y:", 1)
    assert len(job) == 2, "ci.yml is missing the `a11y` job"
    body = job[1].split("\n  # ---", 1)[0]
    assert "make test-e2e" in body
    # Gated on the frontend paths filter so docs-only PRs stay cheap.
    assert "needs.changes.outputs.frontend == 'true'" in body


def test_the_a11y_baseline_gates_contrast_not_just_rule_ids(repo_root: Path) -> None:
    """A baselined rule id must not be a permanent amnesty for new failures.

    With a rule-id-only gate, `color-contrast` was baselined on every route, so
    a PR adding low-contrast text could not fail. The baseline now records the
    signatures already accepted (for contrast: the colour pair and type size),
    and an unrecorded signature fails.
    """
    spec = (repo_root / "frontend" / "e2e" / "a11y.spec.ts").read_text(
        encoding="utf-8"
    )
    assert "fgColor" in spec and "bgColor" in spec, (
        "the contrast signature must carry the colour pair"
    )
    assert "unrecorded" in spec, "no assertion on unrecorded failure signatures"

    baseline = json.loads(
        (repo_root / "frontend" / "e2e" / "a11y-baseline.json").read_text(
            encoding="utf-8"
        )
    )
    for route, rules in baseline.items():
        for rule, signatures in rules.items():
            assert isinstance(signatures, list), (
                f"{route}/{rule}: the baseline records signatures, not counts — "
                "re-record with E2E_A11Y_UPDATE_BASELINE=1"
            )


def test_the_a11y_spec_covers_every_catalog_route(repo_root: Path) -> None:
    """`/matters` shipped as a seventh module and went unchecked for a release."""
    catalog = (repo_root / "frontend" / "lib" / "modules" / "catalog.ts").read_text(
        encoding="utf-8"
    )
    hrefs = set(re.findall(r"nav:\s*\{[^}]*?href:\s*'([^']+)'", catalog, re.S))
    assert hrefs, "no nav hrefs found — did catalog.ts move?"

    spec = (repo_root / "frontend" / "e2e" / "a11y.spec.ts").read_text(
        encoding="utf-8"
    )
    routes = set(re.findall(r"'(/[^']*)'", spec.split("const ROUTES = [", 1)[1]
                            .split("]", 1)[0]))
    assert routes == hrefs, (
        f"a11y.spec.ts covers {sorted(routes)} but the catalog has {sorted(hrefs)}"
    )
