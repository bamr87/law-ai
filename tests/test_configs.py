"""Sanity-check key configuration files parse correctly."""
from __future__ import annotations

import json
import re
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
    assert data["project"]["name"] == "law-ai"
    assert data["project"]["requires-python"].startswith(">=3.")
    deps = " ".join(data["project"]["dependencies"])
    for required in ("django", "djangorestframework", "pydantic", "neo4j", "crewai", "langgraph"):
        assert required in deps, f"backend missing required dep: {required}"
    dev = " ".join(data["project"]["optional-dependencies"]["dev"])
    assert "debugpy" in dev, (
        "dev extra must include debugpy (docker-compose.debug.yml runs python -m debugpy)"
    )


def test_frontend_package_json_parses(frontend_dir: Path) -> None:
    pkg = json.loads((frontend_dir / "package.json").read_text())
    assert pkg["name"] == "law-ai-frontend"
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


def test_init_db_sh_delegates_neo4j_to_the_migration_runner(repo_root: Path) -> None:
    """BL-20260509-02: Cypher must go through `migrate_neo4j`, not `cypher-shell`.

    The bash loop had no bookkeeping, so a migration that is not idempotent by
    construction would re-run on every boot. `migrate_neo4j` records each file
    as a `(:_Migration)` node.
    """
    script = (repo_root / "backend" / "scripts" / "init-db.sh").read_text()
    assert "manage.py migrate_neo4j" in script, (
        "init-db.sh must call 'manage.py migrate_neo4j' to apply Cypher migrations"
    )
    executable = [
        line for line in script.splitlines() if not line.lstrip().startswith("#")
    ]
    assert not [line for line in executable if "cypher-shell" in line], (
        "init-db.sh must not shell out to cypher-shell "
        "(no applied-migration bookkeeping)"
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


# ---------------------------------------------------------------------------
# Dev Containers (BL-20260810-09 backend, BL-20260811-17 frontend). Two
# configurations, one per compose service, so editor tooling never reaches for
# a host interpreter or a host node_modules.
# ---------------------------------------------------------------------------


def _strip_jsonc(raw: str) -> str:
    """devcontainer.json is JSONC; drop whole-line // comments before parsing.

    Deliberately not a general JSONC parser — it only handles the comment
    style these two files actually use, and a `//` inside a string would
    break it, so keep URLs out of the configs.
    """
    return "\n".join(
        "" if line.lstrip().startswith("//") else line for line in raw.splitlines()
    )


def _devcontainer_files(repo_root: Path) -> list[Path]:
    return sorted((repo_root / ".devcontainer").rglob("devcontainer.json"))


def test_devcontainer_configs_parse_and_target_real_services(
    repo_root: Path,
) -> None:
    from tests.conftest import require_yaml
    
    yaml = require_yaml()

    compose = yaml.safe_load((repo_root / "docker-compose.yml").read_text())
    services = set(compose["services"])

    files = _devcontainer_files(repo_root)
    assert files, "expected at least one .devcontainer/**/devcontainer.json"

    seen: dict[str, Path] = {}
    for path in files:
        data = json.loads(_strip_jsonc(path.read_text()))
        rel = path.relative_to(repo_root)
        service = data.get("service")
        assert service in services, (
            f"{rel}: service {service!r} is not a docker-compose.yml service"
        )
        # The compose file path is relative to the config's own directory.
        for compose_ref in data["dockerComposeFile"]:
            assert (path.parent / compose_ref).resolve().is_file(), (
                f"{rel}: dockerComposeFile {compose_ref!r} does not resolve"
            )
        assert data.get("overrideCommand") is True, (
            f"{rel}: overrideCommand must be true or the service's own command "
            "(daphne / next dev) owns the dev-container lifecycle"
        )
        name = data["name"]
        assert name not in seen, f"{rel}: duplicate dev container name {name!r}"
        seen[name] = path

    assert {"backend", "frontend"} <= {
        json.loads(_strip_jsonc(p.read_text()))["service"] for p in files
    }, "both a backend and a frontend dev container configuration must exist"


def test_frontend_devcontainer_uses_container_node_modules(repo_root: Path) -> None:
    """BL-20260811-17: the whole point is not borrowing a host node_modules."""
    path = repo_root / ".devcontainer" / "frontend" / "devcontainer.json"
    data = json.loads(_strip_jsonc(path.read_text()))
    settings = data["customizations"]["vscode"]["settings"]
    tsdk = settings["typescript.tsdk"]
    assert not tsdk.startswith("frontend/"), (
        "tsdk must be relative to the container workspace (/app), not the host "
        f"repo layout; got {tsdk!r}"
    )
    assert tsdk == "node_modules/typescript/lib", tsdk
    assert settings["eslint.workingDirectories"] == ["."], (
        "/app is already the frontend package root inside the container"
    )
    extensions = data["customizations"]["vscode"]["extensions"]
    assert "dbaeumer.vscode-eslint" in extensions


# ---------------------------------------------------------------------------
# Branch-protection ruleset (BL-20260815-01). `markdown-oneline` went red on
# main when #73 merged and stayed red across four stacked PRs because nothing
# blocks a merge on a failing check. The ruleset is checked in so the required
# contexts are reviewable and cannot silently drift away from the job names
# that produce them.
# ---------------------------------------------------------------------------

RULESET = ".github/rulesets/main-required-checks.json"


def _workflow_check_contexts(repo_root: Path) -> set[str]:
    """Every check-run name GitHub could report from this repo's workflows.

    A check context is the job's `name:` when it has one, and its job id
    otherwise — which is why `oneline` (no `name:` key) is the context for
    markdown-oneline.yml. A job that `uses:` a reusable workflow reports one
    context per job the called workflow defines, named
    `"<caller name> / <called job name>"`; the called job names live in the
    hub, so the ones this repo relies on are pinned in REUSABLE_JOB_NAMES.
    """
    from tests.conftest import require_yaml

    yaml = require_yaml()

    contexts: set[str] = set()
    for path in (repo_root / ".github" / "workflows").glob("*.yml"):
        data = yaml.safe_load(path.read_text()) or {}
        for job_id, job in (data.get("jobs") or {}).items():
            name = str((job or {}).get("name") or job_id)
            uses = str((job or {}).get("uses") or "").split("@")[0]
            if uses:
                for called in REUSABLE_JOB_NAMES.get(uses, ()):
                    contexts.add(f"{name} / {called}")
            else:
                contexts.add(name)
    return contexts


# The job names inside the hub's reusable workflows this repo calls. A rename
# on the hub side orphans the ruleset exactly like a local rename would; keep
# this in step with bamr87/bamr87 .github/workflows/<file>.yml `jobs.*.name`.
REUSABLE_JOB_NAMES = {
    "bamr87/bamr87/.github/workflows/spec-gate.yml": ("Spec gate",),
}


def test_required_status_checks_match_real_jobs(repo_root: Path) -> None:
    """A renamed job must not silently orphan the branch protection.

    Renaming a job changes its check context; the ruleset would then require a
    context nothing ever reports, and every PR would wait forever on a check
    that cannot arrive. This test fails on the rename instead.
    """
    ruleset = json.loads((repo_root / RULESET).read_text())
    checks = [
        rule
        for rule in ruleset["rules"]
        if rule["type"] == "required_status_checks"
    ]
    assert len(checks) == 1, "expected exactly one required_status_checks rule"
    required = {
        c["context"]
        for c in checks[0]["parameters"]["required_status_checks"]
    }
    assert required, "the ruleset must require at least one check"

    available = _workflow_check_contexts(repo_root)
    missing = sorted(required - available)
    assert not missing, (
        f"{RULESET} requires check context(s) no workflow job produces: "
        f"{missing}. Either the job was renamed (update the ruleset and "
        f"re-apply it with `gh api -X PUT repos/{{owner}}/{{repo}}/rulesets/"
        f"<id> --input {RULESET}`) or the context is a typo. "
        f"Known contexts: {sorted(available)}"
    )


def test_ruleset_targets_the_default_branch_and_is_active(repo_root: Path) -> None:
    ruleset = json.loads((repo_root / RULESET).read_text())
    assert ruleset["target"] == "branch"
    assert ruleset["enforcement"] == "active", (
        "an 'evaluate'/'disabled' ruleset reports but does not block a merge"
    )
    assert "~DEFAULT_BRANCH" in ruleset["conditions"]["ref_name"]["include"]
    rule_types = {r["type"] for r in ruleset["rules"]}
    assert {"required_status_checks", "pull_request"} <= rule_types, (
        "required checks only gate a merge when a PR is also required"
    )


def test_ruleset_covers_the_four_gates_the_backlog_item_names(
    repo_root: Path,
) -> None:
    """BL-20260815-01 names these four explicitly."""
    ruleset = json.loads((repo_root / RULESET).read_text())
    (checks,) = [
        r for r in ruleset["rules"] if r["type"] == "required_status_checks"
    ]
    required = {
        c["context"] for c in checks["parameters"]["required_status_checks"]
    }
    assert {
        "Spec Drift Gate / Spec gate",
        "Backend Lint + Type-check",
        "Backend Tests + Coverage",
        "oneline",
    } <= required


# ---------------------------------------------------------------------------
# LangGraph Studio host — BL-20260502-01
# ---------------------------------------------------------------------------


def test_studio_services_are_profile_gated(repo_root: Path) -> None:
    """`make dev` must never build the heavy Studio image."""
    text = (repo_root / "docker-compose.yml").read_text()
    for service in ("langgraph-api:", "langgraph-db-init:"):
        assert service in text, f"docker-compose missing service: {service}"
        block = text.split(service, 1)[1].split("\n\n", 1)[0]
        assert 'profiles: [ "studio" ]' in block, (
            f"{service} must sit behind the studio profile"
        )


def test_studio_targets_and_env_are_documented(repo_root: Path) -> None:
    makefile = (repo_root / "Makefile").read_text()
    assert "\nstudio-up:" in makefile and "\nstudio-down:" in makefile
    assert "LANGSMITH_API_KEY" in makefile, (
        "studio-up should fail loudly when the license key is missing"
    )
    env_example = (repo_root / ".env.example").read_text()
    assert "# LANGSMITH_API_KEY=" in env_example, (
        "LANGSMITH_API_KEY stays commented out: the Studio tier is inert by default"
    )
    docs = (repo_root / "docs" / "local-ai.md").read_text()
    assert "LangGraph Studio" in docs
    assert "beacon.langchain.com" in docs, (
        "the license phone-home has to be stated where an operator will see it"
    )


# ---------------------------------------------------------------------------
# CI / Dockerfile extras drift (BL-20260815-02). The container installs
# `.[dev,local-ai]` while CI installed `.[dev]`, so anything importing an
# extras-only package passed locally and died in CI — which is exactly how
# spec 037's telemetry tests failed with ModuleNotFoundError. A fix landed in
# #76 and was lost when specs 037-038 were reworked in #83, so the divergence
# came back unnoticed. This test is the thing that notices.
# ---------------------------------------------------------------------------

_PIP_INSTALL_RE = re.compile(r'pip install -e\s+"\.\[([^\]]+)\]"')


def _extras_sets(text: str) -> list[set[str]]:
    """Every `pip install -e ".[a,b]"` in `text`, as sets of extras.

    A bare `pip install -e .` does not match on purpose: ci.yml's
    clean-install smoke installs with no extras deliberately, and that job's
    whole point is to prove the package imports without them.
    """
    return [
        {part.strip() for part in m.group(1).split(",") if part.strip()}
        for m in _PIP_INSTALL_RE.finditer(text)
    ]


def _unconditional_instructions(dockerfile: str) -> str:
    """The Dockerfile with continuation lines joined and every `RUN` that is
    gated by a shell `if` dropped.

    An ARG-gated install (`INSTALL_OCRMD=1` -> `.[ocrmd]`) is an
    opt-in image variant, not part of the default image, so CI deliberately
    does not mirror it; only the unconditional install defines the extras CI
    must match.
    """
    joined = re.sub(r"\\\n", " ", dockerfile)
    return "\n".join(
        line
        for line in joined.splitlines()
        if not (line.lstrip().startswith("RUN") and re.search(r"\bif \[", line))
    )


def test_ci_extras_match_dockerfile(repo_root: Path) -> None:
    dockerfile = (repo_root / "backend" / "Dockerfile").read_text()
    docker_extras = _extras_sets(_unconditional_instructions(dockerfile))
    assert len(docker_extras) == 1, (
        "expected exactly one unconditional extras-bearing pip install in "
        "backend/Dockerfile; "
        f"found {len(docker_extras)}"
    )
    required = docker_extras[0]

    targets = [
        Path(".github/workflows/ci.yml"),
        Path(".github/workflows/integration-tests.yml"),
        Path("Makefile"),
    ]
    problems: list[str] = []
    for rel in targets:
        text = (repo_root / rel).read_text()
        for extras in _extras_sets(text):
            if not required <= extras:
                problems.append(
                    f"{rel}: installs {sorted(extras)} but backend/Dockerfile "
                    f"installs {sorted(required)}; missing "
                    f"{sorted(required - extras)}"
                )
    assert not problems, (
        "install extras have drifted from backend/Dockerfile — an extras-only "
        "import would pass in the container and fail here:\n  "
        + "\n  ".join(problems)
    )


def test_local_ai_extra_is_the_telemetry_one(repo_root: Path) -> None:
    """Guard the premise: `local-ai` is what core.telemetry lazily imports.

    If the Phoenix/OTel packages ever move to another extra (or to core deps),
    the superset check above is guarding the wrong name and should be updated
    rather than left quietly pointing at an empty set.
    """
    data = tomllib.loads((repo_root / "backend" / "pyproject.toml").read_text())
    local_ai = " ".join(data["project"]["optional-dependencies"]["local-ai"])
    assert "opentelemetry" in local_ai or "phoenix" in local_ai, (
        "the local-ai extra no longer carries the telemetry packages; "
        f"got: {local_ai}"
    )


def test_no_per_repo_autopilot_workflows_remain(repo_root: Path) -> None:
    """2026-10-25: the weekly evolve audit and the GitFactory lines moved out.

    `evolve.yml` (BL-20260818-02's opt-out kill switch lived on it) and the
    three `factory--*.yml` lines were this repo's own SDLC automation. The
    fleet hub runs that loop now — `repo-evolution.yml` (opt-in per repo via
    the registry's `auto_evolve`), `repo-scout.yml`, the issue pipeline — and
    the nightly's `backlog-triage` job is the hub's reusable spec gate. A
    per-repo autopilot workflow reappearing here is the drift this guards.
    """
    workflows = repo_root / ".github" / "workflows"
    strays = sorted(
        p.name for p in workflows.glob("*.yml")
        if p.name == "evolve.yml" or p.name.startswith("factory--")
    )
    assert not strays, f"per-repo SDLC automation is the hub's job now: {strays}"
    assert not (repo_root / ".factory").exists(), ".factory/ blueprints were retired with the lines"


def test_nightly_backlog_triage_is_the_fleet_gate(repo_root: Path) -> None:
    """The stale-backlog issue (BL-20260503-14) is filed by the hub's gate.

    It replaced a hand-rolled `gh issue` step and the backend's
    `governance-triage` beat job. It must stay schedule-only (a dispatch or a
    `make nightly-dry-run` under act must never file an issue) and must be the
    caller that declares `issues: write` — a reusable workflow cannot widen
    the permissions it inherits.
    """
    from tests.conftest import require_yaml

    yaml = require_yaml()

    data = yaml.safe_load((repo_root / ".github" / "workflows" / "nightly-tests.yml").read_text())
    job = data["jobs"]["backlog-triage"]
    assert job["uses"].startswith("bamr87/bamr87/.github/workflows/spec-gate.yml@v")
    assert job["with"]["stale-report"] is True and job["with"]["file-issue"] is True
    assert "schedule" in job["if"], "backlog-triage must be schedule-only"
    assert job["permissions"]["issues"] == "write"
    assert "governance" not in (repo_root / "backend" / "law_ai" / "celery.py").read_text(), (
        "the governance-triage beat job was retired in favour of the fleet gate"
    )


# ---------------------------------------------------------------------------
# Linux + NVIDIA workstation tier — BL-20260502-02
# ---------------------------------------------------------------------------

GPU_OVERLAY = "docker-compose.gpu.yml"


def test_gpu_overlay_reserves_nvidia_devices(repo_root: Path) -> None:
    text = (repo_root / GPU_OVERLAY).read_text()
    assert "driver: nvidia" in text and "capabilities: [ gpu ]" in text
    assert "llama3.1:70b-q4_K_M" in text, "the workstation tier's default model"
    assert "vllm:" in text and 'profiles: [ "vllm" ]' in text, (
        "vLLM stays optional — behind its own profile"
    )


def test_gpu_overlay_does_not_leak_into_the_laptop_default(repo_root: Path) -> None:
    """`make dev` must stay on the 7B set with no GPU reservation."""
    base = (repo_root / "docker-compose.yml").read_text()
    assert "nvidia" not in base
    assert "llama3.1:70b" not in base


def test_gpu_overlay_uses_prefixed_variables(repo_root: Path) -> None:
    """`.env.example` ships the laptop OLLAMA_DEFAULT_MODEL.

    Compose interpolates from that file, so an unprefixed
    ``${OLLAMA_DEFAULT_MODEL:-70b}`` in the overlay would silently serve the
    laptop model on a workstation.
    """
    lines = [
        line
        for line in (repo_root / GPU_OVERLAY).read_text().splitlines()
        if not line.lstrip().startswith("#")
    ]
    text = "\n".join(lines)
    assert "${OLLAMA_DEFAULT_MODEL" not in text
    assert "${GPU_OLLAMA_DEFAULT_MODEL:-llama3.1:70b-q4_K_M}" in text


def test_a_small_model_is_pullable_for_the_local_integration_tests(
    repo_root: Path,
) -> None:
    """BL-20260906-82: the opt-in local-model tests must be runnable by hand-free.

    The bootstrap set is a 7B and an 8B, so on a laptop Docker VM every
    local-model integration test skipped for want of RAM. The small model is
    deliberately a separate target rather than a bootstrap entry: the first
    entry of ``OLLAMA_BOOTSTRAP_MODELS`` is the healthcheck's gate model.
    """
    makefile = (repo_root / "Makefile").read_text()
    assert "\nlocal-ai-pull-small:" in makefile
    assert "LOCAL_AI_SMALL_MODEL ?=" in makefile
    compose = (repo_root / "docker-compose.yml").read_text()
    small = makefile.split("LOCAL_AI_SMALL_MODEL ?=", 1)[1].split("\n", 1)[0].strip()
    assert small, "LOCAL_AI_SMALL_MODEL has no default"
    assert small not in compose, (
        "the small model must stay out of OLLAMA_BOOTSTRAP_MODELS — its first "
        "entry is the healthcheck's gate model"
    )
    docs = (repo_root / "docs" / "local-ai.md").read_text()
    assert "make local-ai-pull-small" in docs


def test_gpu_targets_and_docs_exist(repo_root: Path) -> None:
    makefile = (repo_root / "Makefile").read_text()
    for target in ("local-ai-up-gpu", "dev-gpu", "vllm-up"):
        assert f"\n{target}:" in makefile, f"Makefile missing target: {target}"
    docs = (repo_root / "docs" / "local-ai.md").read_text()
    assert "docker-compose.gpu.yml" in docs
    assert "❌ — tracked as [BL-20260502-02]" not in docs, (
        "hardware-tier table still says the workstation tier is unbuilt"
    )


# ---------------------------------------------------------------------------
# Air-gapped bundle + offline install — BL-20260502-06
# ---------------------------------------------------------------------------

OFFLINE_SCRIPTS = ("scripts/ollama-bundle.sh", "scripts/offline-install.sh")


@pytest.mark.parametrize("script", OFFLINE_SCRIPTS)
def test_offline_scripts_are_executable_and_parse(repo_root: Path, script: str) -> None:
    import subprocess

    path = repo_root / script
    assert path.is_file(), f"missing {script}"
    assert path.stat().st_mode & 0o111, f"{script} is not executable"
    result = subprocess.run(["bash", "-n", str(path)], capture_output=True)
    assert result.returncode == 0, (
        f"{script} has syntax errors:\n{result.stderr.decode()}"
    )


def test_bundle_and_install_agree_on_the_artifact_names(repo_root: Path) -> None:
    """A rename on one side silently produces an empty install on the other."""
    bundle = (repo_root / OFFLINE_SCRIPTS[0]).read_text()
    install = (repo_root / OFFLINE_SCRIPTS[1]).read_text()
    for artifact in ("ollama-models.tar", "images.tar", "bundle.env", "SHA256SUMS"):
        assert artifact in bundle, f"bundle script never writes {artifact}"
        assert artifact in install, f"install script never reads {artifact}"


def test_the_bundle_can_carry_a_subset_of_models(repo_root: Path) -> None:
    """BL-20260906-45: refreshing one model must not re-ship the whole volume."""
    bundle = (repo_root / OFFLINE_SCRIPTS[0]).read_text()
    assert "--models)" in bundle, "no --models filter on the bundle script"
    # The subset is assembled from each manifest and the digests it names —
    # blobs are shared between models, so guessing at paths would ship a
    # manifest whose blobs were never bundled.
    assert "models/manifests/registry.ollama.ai/library" in bundle
    assert "tar -C /models -cf /out/ollama-models.tar -T /tmp/files" in bundle
    # And the receiving side can tell a subset bundle from a whole-volume one.
    assert "BUNDLE_MODELS=$MODELS" in bundle
    docs = (repo_root / "docs" / "local-ai.md").read_text()
    assert "--models 'nomic-embed-text'" in docs


def test_bootstrap_skips_pulls_when_offline(repo_root: Path) -> None:
    """AC: `ollama pull` must not run on an air-gapped host."""
    script = (repo_root / "backend" / "scripts" / "ollama-bootstrap.sh").read_text()
    assert 'if [ "${OLLAMA_OFFLINE:-0}" = "1" ]; then' in script
    offline_block = script.split('OLLAMA_OFFLINE:-0}" = "1" ]; then', 1)[1].split(
        "\nfi\n", 1
    )[0]
    assert "ollama pull" not in offline_block, (
        "the offline branch must not pull — the registry is unreachable"
    )
    assert "MISSING" in offline_block, (
        "an absent model has to be reported, not silently tolerated"
    )
    compose = (repo_root / "docker-compose.yml").read_text()
    assert "OLLAMA_OFFLINE=${OLLAMA_OFFLINE:-0}" in compose, (
        "the flag never reaches the container without a compose passthrough"
    )


def test_offline_flow_is_documented(repo_root: Path) -> None:
    docs = (repo_root / "docs" / "local-ai.md").read_text()
    assert "Air-gapped deployment" in docs
    assert "OLLAMA_OFFLINE=1" in docs
    assert "SHA256SUMS" in docs, "checksum verification is part of the flow"
    makefile = (repo_root / "Makefile").read_text()
    assert "\nlocal-ai-bundle:" in makefile
    assert "\nlocal-ai-offline-install:" in makefile


# ---------------------------------------------------------------------------
# Server / multi-GPU tier: Prometheus + Grafana — BL-20260502-03
# ---------------------------------------------------------------------------

OBS_OVERLAY = "docker-compose.observability.yml"


def test_observability_overlay_is_profile_gated(repo_root: Path) -> None:
    text = (repo_root / OBS_OVERLAY).read_text()
    for service in ("prometheus:", "grafana:", "redis-exporter:", "dcgm-exporter:"):
        assert service in text, f"{OBS_OVERLAY} missing service: {service}"
    # The GPU exporter needs NVIDIA hardware, so it must NOT share the profile
    # that has to keep working on a laptop.
    assert 'profiles: [ "gpu-metrics" ]' in text
    assert text.count('profiles: [ "observability" ]') == 3
    base = (repo_root / "docker-compose.yml").read_text()
    assert "prometheus" not in base and "grafana" not in base, (
        "the metrics stack must stay in its overlay, out of `make dev`"
    )


def test_prometheus_scrapes_the_three_metrics_the_item_names(repo_root: Path) -> None:
    """token/sec (vLLM), GPU utilization (DCGM), queue depth (redis)."""
    scrape = (repo_root / "infra" / "prometheus" / "prometheus.yml").read_text()
    for target in ("vllm:8000", "dcgm-exporter:9400", "redis-exporter:9121"):
        assert target in scrape, f"prometheus.yml never scrapes {target}"
    overlay = (repo_root / OBS_OVERLAY).read_text()
    assert "REDIS_EXPORTER_CHECK_KEYS=celery,autonomy" in overlay, (
        "queue depth comes from the length of the Celery queues' Redis lists"
    )


def test_grafana_dashboard_is_provisioned_and_covers_the_panels(
    repo_root: Path,
) -> None:
    grafana = repo_root / "infra" / "grafana"
    datasource = (grafana / "provisioning" / "datasources" / "prometheus.yml").read_text()
    assert "http://prometheus:9090" in datasource
    provider = (grafana / "provisioning" / "dashboards" / "dashboards.yml").read_text()
    assert "/var/lib/grafana/dashboards" in provider
    dashboard = json.loads((grafana / "dashboards" / "local-ai.json").read_text())
    exprs = " ".join(
        t["expr"] for panel in dashboard["panels"] for t in panel.get("targets", [])
    )
    assert "vllm:generation_tokens_total" in exprs, "tokens/sec panel"
    assert "DCGM_FI_DEV_GPU_UTIL" in exprs, "GPU utilization panel"
    assert "redis_key_size" in exprs, "queue depth panel"


def test_server_tier_targets_and_docs(repo_root: Path) -> None:
    makefile = (repo_root / "Makefile").read_text()
    for target in ("observability-up", "observability-down", "local-ai-up-server"):
        assert f"\n{target}:" in makefile, f"Makefile missing target: {target}"
    assert "docker-compose.observability.yml" in makefile
    docs = (repo_root / "docs" / "local-ai.md").read_text()
    assert "❌ — tracked as [BL-20260502-03]" not in docs, (
        "hardware-tier table still says the server tier is unbuilt"
    )
    assert "localhost:3002" in docs, "Grafana's port has to be findable"


def test_compose_does_not_pass_a_dead_frontend_variable(repo_root: Path) -> None:
    """BL-20260905-28: no code reads NEXT_PUBLIC_API_URL.

    ``frontend/lib/api.ts`` reads ``NEXT_PUBLIC_API_BASE_URL``. Passing the
    other name into the container implies a second, ignored base URL.
    """
    dead = "NEXT_PUBLIC_API_URL"
    offenders = [
        rel
        for rel in (
            "docker-compose.yml",
            "docker-compose.debug.yml",
            ".claude/skills/run-law-ai/driver.sh",
        )
        if dead in (repo_root / rel).read_text()
    ]
    assert not offenders, (
        "NEXT_PUBLIC_API_URL is read by no code; drop it rather than implying "
        f"a second frontend base URL: {offenders}"
    )


def test_env_example_ships_a_priced_starter_table(repo_root: Path) -> None:
    """BL-20260905-70: the price table has a starter row per billed tier.

    ``LLM_PRICE_TABLE`` defaults to ``{}``, so ``cost_usd`` is null out of the
    box. The commented starter in ``.env.example`` is what turns that into a
    one-line uncomment — but only while it still names the models the chain
    actually serves, so this pins it to the shipped defaults in
    ``settings/base.py``.
    """
    env_example = (repo_root / ".env.example").read_text()
    line = next(
        (ln for ln in env_example.splitlines() if ln.startswith("# LLM_PRICE_TABLE=")),
        None,
    )
    assert line is not None, ".env.example has no commented LLM_PRICE_TABLE starter"
    table = json.loads(line.split("=", 1)[1])
    for key, entry in table.items():
        assert set(entry) == {"in_per_mtok", "out_per_mtok"}, key
        assert all(isinstance(v, int | float) and v > 0 for v in entry.values()), key

    base = (repo_root / "backend" / "law_ai" / "settings" / "base.py").read_text()
    defaults = dict(
        re.findall(
            r"^\s{4}(CLAUDE_CODE_MODEL|XAI_MODEL)=\(str, \"([^\"]+)\"\)", base, re.M
        )
    )
    assert set(defaults) == {"CLAUDE_CODE_MODEL", "XAI_MODEL"}, defaults
    for model in defaults.values():
        assert any(key.endswith(model) for key in table), (
            f"the starter price table does not price the shipped default {model!r}"
        )

    # A price with no date is a price nobody can tell is stale.
    assert re.search(r"checked\b.{0,120}?20\d\d-\d\d-\d\d", env_example, re.S), (
        "the starter table needs the date its prices were checked"
    )


def test_lint_scope_is_stated_where_someone_would_look(repo_root: Path) -> None:
    """`make lint` misses repo-root Python; that has to be said, not discovered.

    BL-20260906-36: `lint`/`format` run with the containers' working
    directories (./backend, ./frontend), so scripts/*.py and tests/*.py are
    outside their reach. That is a deliberate choice, and an undocumented
    deliberate choice is indistinguishable from an oversight — the next person
    to notice re-opens the same question. The declaration lives in the
    Makefile next to the targets and in AGENTS.md next to the standard, and
    `make lint-root` is the opt-in way to look at the drift.
    """
    makefile = (repo_root / "Makefile").read_text()
    assert "\nlint-root:" in makefile, "Makefile is missing the lint-root target"
    assert "BL-20260906-36" in makefile, (
        "the lint scope note above `lint:` is gone; state it or delete the target"
    )
    agents = (repo_root / "AGENTS.md").read_text()
    assert "lint-root" in agents, "AGENTS.md does not state the lint scope"
