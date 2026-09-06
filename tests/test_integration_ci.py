"""The Integration Tests workflow must be able to run what it opts into.

BL-20260502-08 asked for a CI entry that *runs* the spec-010 T-007 Postgres
checkpointer test. Wiring the opt-in env alone is not that: the saver connects
with ``options=-csearch_path=langgraph`` and only ``manage.py
ensure_checkpointer`` creates that schema, so a job that starts a fresh
Postgres, runs ``migrate`` and nothing else fails on the test's first
assertion ("no schema has been selected to create in") — a red job for an
environment-setup reason, forever.

These are the properties that would silently un-run the test if deleted, so
they are asserted here rather than left to a nightly nobody watches.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

pytestmark = pytest.mark.specs

WORKFLOW = Path(".github") / "workflows" / "integration-tests.yml"


@pytest.fixture(scope="module")
def integration_job(repo_root: Path) -> dict[str, Any]:
    from tests.conftest import require_yaml
    
    yaml = require_yaml()

    document = yaml.safe_load((repo_root / WORKFLOW).read_text(encoding="utf-8"))
    return dict(document["jobs"]["integration"])


def _steps(job: dict[str, Any]) -> list[dict[str, Any]]:
    return [dict(step) for step in job["steps"]]


def _index_of(steps: list[dict[str, Any]], needle: str) -> int:
    for i, step in enumerate(steps):
        if needle in str(step.get("run", "")):
            return i
    raise AssertionError(f"no step in {WORKFLOW} runs `{needle}`")


def test_the_workflow_opts_into_the_postgres_checkpointer_test(
    integration_job: dict[str, Any],
) -> None:
    """Without these three keys the test skips itself at module level."""
    steps = _steps(integration_job)
    env = steps[_index_of(steps, "pytest -m integration")].get("env", {})
    assert env.get("LANGGRAPH_INTEGRATION") == "1", (
        "the spec-010 T-007 test skips at module level without "
        "LANGGRAPH_INTEGRATION"
    )
    assert env.get("LANGGRAPH_CHECKPOINTER") == "postgres"
    assert "postgresql" in str(env.get("POSTGRES_URL", "")), (
        "POSTGRES_URL must point the saver at this job's Postgres, not the "
        "compose hostname settings.base defaults to"
    )


def test_the_workflow_creates_the_checkpointer_schema_first(
    integration_job: dict[str, Any], repo_root: Path
) -> None:
    """`migrate` alone leaves the `langgraph` schema missing on a fresh DB."""
    steps = _steps(integration_job)
    setup = _index_of(steps, "ensure_checkpointer")
    tests = _index_of(steps, "pytest -m integration")
    assert setup < tests, "ensure_checkpointer must run before the tests"

    env = steps[setup].get("env", {})
    # CREATE SCHEMA goes through Django's connection (DATABASE_URL); the
    # PostgresSaver.setup() that follows it goes through POSTGRES_URL.
    assert "postgresql" in str(env.get("DATABASE_URL", ""))
    assert "postgresql" in str(env.get("POSTGRES_URL", ""))

    command = (
        repo_root
        / "backend"
        / "law_ai"
        / "core"
        / "management"
        / "commands"
        / "ensure_checkpointer.py"
    ).read_text(encoding="utf-8")
    assert "CREATE SCHEMA IF NOT EXISTS" in command, (
        "ensure_checkpointer no longer creates the schema — the workflow step "
        "above is then no longer sufficient"
    )


def test_the_job_starts_from_a_clean_database_every_run(
    integration_job: dict[str, Any],
) -> None:
    """Why the schema step is mandatory rather than a one-time bootstrap."""
    steps = _steps(integration_job)
    teardown = _index_of(steps, "docker compose down")
    assert "-v" in str(steps[teardown]["run"]), (
        "the volume teardown is what makes every run schema-less; if it goes "
        "away, say so deliberately rather than by accident"
    )


# --- BL-20260906-81 / BL-20260906-94: the live-model slice must run somewhere -


def _yaml(repo_root: Path, rel: str) -> dict[str, Any]:
    from tests.conftest import require_yaml
    
    yaml = require_yaml()

    return yaml.safe_load(  # type: ignore[no-any-return]
        (repo_root / rel).read_text(encoding="utf-8")
    )


def test_a_workflow_runs_the_ollama_integration_slice(repo_root: Path) -> None:
    """A target nothing schedules is a target that rots.

    ``make test-integration-ollama`` covers the factory's Ollama executor and
    the autonomy → HITL loop against a real model. Nothing in `.github/` ran
    it, so a regression in executor → intake → proposals reached main
    unnoticed until someone happened to type the target.
    """
    workflows = repo_root / ".github" / "workflows"
    runners = [
        path.name
        for path in sorted(workflows.glob("*.yml"))
        if "make test-integration-ollama" in path.read_text(encoding="utf-8")
    ]
    assert runners, (
        "no workflow runs `make test-integration-ollama` — the live-model "
        "assertions would be automatable but never automatic"
    )


def test_the_ollama_slice_runs_last_before_teardown(repo_root: Path) -> None:
    """Its own trap stops ollama, postgres and redis when it finishes.

    Anything scheduled after it in the same job would find the services gone,
    which is a confusing failure a long way from its cause.
    """
    job = _yaml(repo_root, ".github/workflows/nightly-tests.yml")["jobs"]["nightly"]
    steps = _steps(job)
    slice_at = _index_of(steps, "make test-integration-ollama")
    teardown_at = _index_of(steps, "docker compose down")
    assert slice_at < teardown_at
    between = [
        step
        for step in steps[slice_at + 1 : teardown_at]
        if "run" in step or "uses" in step
    ]
    assert between == [], (
        "a step runs between the ollama slice and teardown; the slice stops "
        f"the services on its way out, so it must be last: {between}"
    )


def test_the_ollama_slice_defaults_to_a_model_a_runner_can_hold(
    repo_root: Path,
) -> None:
    """BL-20260906-24: the 7B default meant these tests skipped, always.

    ~4 GiB is what a stock Docker VM gives Ollama and the compose bootstrap
    model needs ~4.9, so the live-model leg had never executed anywhere. The
    target now defaults to a small instruct model and pulls it.
    """
    makefile = (repo_root / "Makefile").read_text(encoding="utf-8")
    default = next(
        line
        for line in makefile.splitlines()
        if line.startswith("OLLAMA_INTEGRATION_MODEL ?=")
    )
    assert "7b" not in default.lower(), (
        f"the default model must fit a small box; got {default!r}"
    )
    target = makefile.split("\ntest-integration-ollama:", 1)[1].split("\n\n", 1)[0]
    assert "ollama pull" in target, (
        "the target must pull its model — an absent model is exactly how these "
        "tests skipped on every box they were tried on"
    )
