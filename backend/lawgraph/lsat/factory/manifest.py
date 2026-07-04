"""Manifest lifecycle — compiled plans as portable file artifacts.

Spec 024 FR-5. A manifest freezes one factory run: the config snapshot, the
planned targets, and each job's fully compiled prompt + tier + model hint.
Because it is a plain JSON file, *anything* able to read JSON and write a
drafts JSONL can act as the generation plane — in-process executors, a Claude
Code session fanning out tier-mapped subagents, or an external script farm.
That decoupling is what makes the factory horizontally scalable without ever
wiring a closed-source model into the product runtime.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from pydantic import BaseModel, Field

from lawgraph.lsat.factory.blueprints import compile_prompt
from lawgraph.lsat.factory.config import FactoryConfig, ModelTier
from lawgraph.lsat.factory.coverage import GenerationTarget

SCHEMA_VERSION = 1

_MANIFESTS_SUBDIR = "manifests"
_DRAFTS_SUBDIR = "drafts"


class GenerationJob(BaseModel):
    """One unit of generation work an executor can fulfill independently."""

    job_id: str
    target: GenerationTarget
    tier: ModelTier
    model_hint: str = Field(
        description="Suggested dev-time Claude model id for this tier; "
        "executors may substitute (Ollama always uses the local default)."
    )
    template_version: str
    prompt: str


class GenerationManifest(BaseModel):
    """A frozen, executable factory plan."""

    schema_version: int = SCHEMA_VERSION
    manifest_id: str
    created_at: str
    config: FactoryConfig
    jobs: list[GenerationJob]

    def job(self, job_id: str) -> GenerationJob:
        for j in self.jobs:
            if j.job_id == job_id:
                return j
        raise KeyError(f"unknown job {job_id!r} in manifest {self.manifest_id}")


def manifests_dir(config: FactoryConfig) -> Path:
    path = config.resolved_output_dir() / _MANIFESTS_SUBDIR
    path.mkdir(parents=True, exist_ok=True)
    return path


def drafts_dir(config: FactoryConfig) -> Path:
    path = config.resolved_output_dir() / _DRAFTS_SUBDIR
    path.mkdir(parents=True, exist_ok=True)
    return path


def build_manifest(
    targets: list[GenerationTarget], config: FactoryConfig
) -> GenerationManifest:
    """Compile targets into a manifest (prompts rendered now, not at run time)."""
    manifest_id = (
        "mfst-" + datetime.now(UTC).strftime("%Y%m%d-%H%M%S") + "-" + uuid4().hex[:6]
    )
    jobs: list[GenerationJob] = []
    for i, target in enumerate(targets, start=1):
        compiled = compile_prompt(target, config)
        jobs.append(
            GenerationJob(
                job_id=f"{manifest_id}-job{i:02d}",
                target=target,
                tier=target.tier,
                model_hint=config.claude_tier_models[target.tier],
                template_version=compiled.template_version,
                prompt=compiled.text,
            )
        )
    return GenerationManifest(
        manifest_id=manifest_id,
        created_at=datetime.now(UTC).isoformat(),
        config=config,
        jobs=jobs,
    )


def write_manifest(manifest: GenerationManifest, config: FactoryConfig) -> Path:
    path = manifests_dir(config) / f"{manifest.manifest_id}.json"
    path.write_text(manifest.model_dump_json(indent=2) + "\n", encoding="utf-8")
    return path


def read_manifest(path: Path) -> GenerationManifest:
    raw = json.loads(path.read_text(encoding="utf-8"))
    version = raw.get("schema_version")
    if version != SCHEMA_VERSION:
        raise ValueError(
            f"manifest {path} has schema_version={version!r}; "
            f"this build reads version {SCHEMA_VERSION}"
        )
    return GenerationManifest.model_validate(raw)


def latest_manifest_path(config: FactoryConfig) -> Path | None:
    """Most recently created manifest file, or None when none exist."""
    candidates = sorted(manifests_dir(config).glob("mfst-*.json"))
    return candidates[-1] if candidates else None
