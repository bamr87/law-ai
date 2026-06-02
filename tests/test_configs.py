"""Sanity-check key configuration files parse correctly."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover - repo requires 3.11+
    import tomli as tomllib  # type: ignore[no-redef]

pytestmark = pytest.mark.smoke


def test_backend_pyproject_parses(backend_dir: Path) -> None:
    data = tomllib.loads((backend_dir / "pyproject.toml").read_text())
    assert data["project"]["name"] == "lawgraph-ai"
    assert data["project"]["requires-python"].startswith(">=3.")
    deps = " ".join(data["project"]["dependencies"])
    for required in ("django", "djangorestframework", "pydantic", "neo4j", "crewai", "langgraph"):
        assert required in deps, f"backend missing required dep: {required}"


def test_frontend_package_json_parses(frontend_dir: Path) -> None:
    pkg = json.loads((frontend_dir / "package.json").read_text())
    assert pkg["name"] == "lawgraph-ai-frontend"
    scripts = pkg.get("scripts", {})
    for required in ("dev", "build", "test", "lint"):
        assert required in scripts, f"frontend missing npm script: {required}"
    deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}
    for required in ("next", "react", "vitest", "tailwindcss", "typescript"):
        assert required in deps, f"frontend missing dep: {required}"


def test_docker_compose_has_core_services(repo_root: Path) -> None:
    text = (repo_root / "docker-compose.yml").read_text()
    # We avoid pulling pyyaml as a hard dep — string-level check is enough
    # to catch accidental deletions of core services.
    for service in ("backend", "frontend", "neo4j", "postgres"):
        assert f"{service}:" in text, f"docker-compose missing service: {service}"


def test_makefile_has_core_targets(repo_root: Path) -> None:
    text = (repo_root / "Makefile").read_text()
    for target in ("setup", "dev", "test", "lint"):
        assert f"\n{target}:" in text or text.startswith(f"{target}:"), (
            f"Makefile missing target: {target}"
        )


def test_env_example_documents_known_keys(repo_root: Path) -> None:
    text = (repo_root / ".env.example").read_text()
    # Just make sure the file is non-trivial and uses KEY=VALUE form.
    non_comment = [
        line for line in text.splitlines() if line.strip() and not line.startswith("#")
    ]
    assert non_comment, ".env.example has no key=value lines"
    assert all("=" in line for line in non_comment), (
        ".env.example contains lines without '='"
    )


# ---------------------------------------------------------------------------
# init-db.sh correctness — spec 017 T-002
# ---------------------------------------------------------------------------

def test_init_db_sh_syntax_valid(repo_root: Path) -> None:
    """AC-4: bash -n must exit 0 (no syntax errors)."""
    import subprocess

    script = repo_root / "backend" / "scripts" / "init-db.sh"
    result = subprocess.run(["bash", "-n", str(script)], capture_output=True)
    assert result.returncode == 0, (
        f"init-db.sh has syntax errors:\n{result.stderr.decode()}"
    )


def test_init_db_sh_no_stale_paths(repo_root: Path) -> None:
    """AC-3: old pre-rebrand paths must not appear in the script."""
    script = (repo_root / "backend" / "scripts" / "init-db.sh").read_text()
    for stale in ("app/db/neo4j_migrations", "app/db/postgres_migrations"):
        assert stale not in script, (
            f"init-db.sh still references the stale pre-rebrand path: {stale!r}"
        )


def test_init_db_sh_delegates_postgres_to_django(repo_root: Path) -> None:
    """AC-2: Postgres DDL must be driven by manage.py migrate, not raw psql."""
    script = (repo_root / "backend" / "scripts" / "init-db.sh").read_text()
    assert "manage.py migrate" in script, (
        "init-db.sh must call 'manage.py migrate' to drive Postgres DDL"
    )
    assert "psql" not in script, (
        "init-db.sh must not call psql directly (Postgres DDL now lives in Django migrations)"
    )
