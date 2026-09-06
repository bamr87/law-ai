"""Contract for the `run-law-ai` skill's driver — BL-20260615-04.

The driver is the agent-facing "does the app actually boot and serve" check,
and its GUI half (`FRONTEND=1`) is the only thing in the repo that exercises
the Next dev server outside the heavyweight `make test-e2e` stack. Nothing
automated covered it: reverting the whole GUI block broke no gate, and the
only evidence it worked was one unrepeatable local run.

These are structural assertions, not a run of the driver — starting two
containers and waiting for a Next first-compile is minutes, which is not a
root-suite cost. What they pin is everything that is easy to break by editing
around it: the proxy wiring the GUI smoke depends on, the container-name
constraint Django's host validation imposes, the assertion set itself, and the
recorded decision about `scripts/`.

Stdlib only, like the rest of `tests/`.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.specs

SKILL_DIR = Path(".claude") / "skills" / "run-law-ai"


@pytest.fixture(scope="module")
def driver(repo_root: Path) -> str:
    path = repo_root / SKILL_DIR / "driver.sh"
    assert path.is_file(), "the run-law-ai driver is missing"
    return path.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def skill_md(repo_root: Path) -> str:
    return (repo_root / SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")


def test_the_driver_is_valid_bash(repo_root: Path) -> None:
    """A syntax error here fails at the end of a slow run, or not at all."""
    bash = shutil.which("bash")
    if bash is None:  # pragma: no cover - every supported host has bash
        pytest.skip("no bash on PATH")
    result = subprocess.run(
        [bash, "-n", str(repo_root / SKILL_DIR / "driver.sh")],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr


def test_the_gui_smoke_exists_and_is_opt_in(driver: str) -> None:
    """`FRONTEND=1` is the whole of BL-20260615-04's first clause."""
    assert "FRONTEND=${FRONTEND:-0}" in driver, (
        "the GUI smoke must stay opt-in — a Next first-compile is a minute "
        "an API-only boot check should not pay"
    )
    assert 'if [ "$FRONTEND" = 1 ]; then' in driver, (
        "the GUI block is gone; the Next frontend is unexercised again"
    )


def test_the_gui_smoke_asserts_rendered_pages_not_just_a_200(driver: str) -> None:
    """A Next dev server answers 200 with a shell while it is still building."""
    block = driver.split('if [ "$FRONTEND" = 1 ]; then', 1)[1]
    # Each route is checked for a marker string that only the rendered page has.
    for route, marker in (("/", "Law AI"), ("/lsat", "LSAT"), ("/analysis", "analysis")):
        assert re.search(rf"page\s+{re.escape(route)}\s+\"{marker}\"", block), (
            f"the GUI smoke no longer asserts a rendered marker for {route}"
        )
    # And the warm-up loop that makes those assertions non-flaky.
    assert "for p in / /lsat /analysis; do" in block


def test_the_gui_smoke_exercises_the_proxy_hop(driver: str, repo_root: Path) -> None:
    """The assertion that catches a misrouted proxy instead of a blank screen.

    `/api/backend/[...path]` is served by the Next server and forwards to
    `BACKEND_INTERNAL_URL`; a browser-side 200 on the page proves nothing
    about it.
    """
    block = driver.split('if [ "$FRONTEND" = 1 ]; then', 1)[1]
    assert "/api/backend/api/lsat/sections" in block
    assert 'BACKEND_INTERNAL_URL="http://${NAME}:8000"' in driver, (
        "the Next server must be pointed at the driver's API container: "
        "localhost inside the frontend container is the frontend"
    )
    route = repo_root / "frontend" / "app" / "api" / "backend" / "[...path]"
    assert (route / "route.ts").is_file(), (
        "the proxy route the GUI smoke asserts on has moved"
    )


def test_the_container_names_carry_no_underscore(driver: str) -> None:
    """Django's host_validation_re rejects an underscore in the Host header.

    With `FRONTEND=1` the Next server reaches the API container by name, so
    `law_ai-api` produced a 400 on every proxied call regardless of
    ALLOWED_HOSTS. The hyphen-only names are load-bearing, not cosmetic.
    """
    for line in driver.splitlines():
        match = re.match(r"^(NAME|FNAME)=(\S+)", line)
        if match:
            assert "_" not in match.group(2), (
                f"{match.group(1)}={match.group(2)} — an underscore in the "
                "container name makes every proxied call a DisallowedHost 400"
            )


def test_the_skill_documents_the_gui_run(skill_md: str) -> None:
    assert "FRONTEND=1" in skill_md
    assert "BL-20260615-04" in skill_md
    # chromium-cli does not exist in this repo; the substitution has to be
    # stated or the next agent goes looking for it.
    assert "chromium-cli" in skill_md and "Playwright MCP" in skill_md


def test_the_scripts_graduation_question_has_a_recorded_answer(
    skill_md: str, repo_root: Path
) -> None:
    """BL-20260615-04's second clause: *consider* moving the launch logic.

    "Considered" is only demonstrable if the consideration was written down.
    A determination in the skill and in docs/e2e-testing.md is what discharges
    it — the alternative being an extracted helper in scripts/, which no
    second caller wants.
    """
    scripts = repo_root / "scripts"
    extracted = [
        p.name
        for p in scripts.iterdir()
        if p.is_file() and re.search(r"driver|launch", p.name)
    ]
    if extracted:  # the other branch: the logic really did graduate
        return

    assert "Should the launch logic move into `scripts/`?" in skill_md, (
        "neither an extracted helper in scripts/ nor a recorded decision — "
        "the clause cannot be shown to have been considered"
    )
    assert "make test-e2e" in skill_md, (
        "the decision has to name the caller that would have reused it"
    )
    doc = (repo_root / "docs" / "e2e-testing.md").read_text(encoding="utf-8")
    assert "why its launch logic stays there" in doc, (
        "the e2e suite's own docs should carry the answer too — that is where "
        "someone asking 'why not reuse the driver?' will look"
    )
