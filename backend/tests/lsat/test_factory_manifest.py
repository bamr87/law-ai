"""Manifest lifecycle tests (spec 024 T-004: FR-5)."""

from __future__ import annotations

import json

import pytest

from law_ai.lsat.factory.config import FactoryConfig
from law_ai.lsat.factory.coverage import plan_targets
from law_ai.lsat.factory.manifest import (
    build_manifest,
    latest_manifest_path,
    read_manifest,
    write_manifest,
)


class TestManifest:
    def test_build_ids_and_hints(self, factory_env: FactoryConfig) -> None:
        targets = plan_targets(factory_env)[:4]
        manifest = build_manifest(targets, factory_env)
        job_ids = [j.job_id for j in manifest.jobs]
        assert len(job_ids) == len(set(job_ids)) == len(targets)
        for job in manifest.jobs:
            assert job.job_id.startswith(manifest.manifest_id)
            assert job.model_hint == factory_env.claude_tier_models[job.tier]
            assert job.prompt  # compiled, not deferred

    def test_roundtrip(self, factory_env: FactoryConfig) -> None:
        manifest = build_manifest(plan_targets(factory_env)[:2], factory_env)
        path = write_manifest(manifest, factory_env)
        assert path.is_file()
        loaded = read_manifest(path)
        assert loaded.model_dump() == manifest.model_dump()
        assert loaded.job(manifest.jobs[0].job_id).tier == manifest.jobs[0].tier
        with pytest.raises(KeyError):
            loaded.job("nope")

    def test_schema_version_guard(self, factory_env: FactoryConfig) -> None:
        manifest = build_manifest(plan_targets(factory_env)[:1], factory_env)
        path = write_manifest(manifest, factory_env)
        blob = json.loads(path.read_text(encoding="utf-8"))
        blob["schema_version"] = 99
        path.write_text(json.dumps(blob), encoding="utf-8")
        with pytest.raises(ValueError, match="schema_version"):
            read_manifest(path)

    def test_latest_manifest_path(self, factory_env: FactoryConfig) -> None:
        assert latest_manifest_path(factory_env) is None
        manifest = build_manifest(plan_targets(factory_env)[:1], factory_env)
        path = write_manifest(manifest, factory_env)
        assert latest_manifest_path(factory_env) == path
