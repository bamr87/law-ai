"""Taxonomy + config tests (spec 024 T-001: FR-1, FR-2, FR-10)."""

from __future__ import annotations

import json
from typing import Any

import pytest

from django.conf import settings

from law_ai.lsat.factory import config as config_mod
from law_ai.lsat.factory import taxonomy
from law_ai.lsat.factory.config import (
    DEFAULT_CLAUDE_TIER_MODELS,
    FactoryConfig,
    route_tier,
)
from law_ai.lsat.services import bank as bank_mod


@pytest.fixture(autouse=True)
def _fresh_caches() -> None:
    bank_mod.load_concepts.cache_clear()


class TestRegistry:
    def test_section_minimums(self) -> None:
        assert len(taxonomy.archetypes_for("LR")) >= 14
        assert len(taxonomy.archetypes_for("RC")) >= 6
        assert len(taxonomy.archetypes_for("LG")) >= 5

    def test_validates_against_real_catalog(self) -> None:
        # FR-1 + FR-10: every referenced concept id exists (including the six
        # new catalog entries this spec added).
        taxonomy.validate_taxonomy()

    def test_ids_unique_and_lookup(self) -> None:
        ids = [a.id for a in taxonomy.all_archetypes()]
        assert len(ids) == len(set(ids))
        assert taxonomy.get_archetype("lr-weaken").section == "LR"
        with pytest.raises(KeyError):
            taxonomy.get_archetype("nope")

    def test_new_concepts_present_in_catalog(self) -> None:
        catalog = bank_mod.load_concepts()
        for cid in (
            "main-conclusion",
            "resolve-paradox",
            "method-of-reasoning",
            "principle-application",
            "rc-inference",
            "grouping-game",
        ):
            assert cid in catalog, cid
        assert "LR" in catalog["must-be-true"].sections

    def test_unknown_concept_detected(self, monkeypatch: pytest.MonkeyPatch) -> None:
        bad = taxonomy.Archetype(
            id="lr-bogus",
            section="LR",
            name="Bogus",
            concepts=["no-such-concept"],
            difficulty_weights={"easy": 1.0, "med": 0.0, "hard": 0.0},
            guidance="n/a",
        )
        monkeypatch.setattr(taxonomy, "_ALL", (bad,))
        with pytest.raises(ValueError, match="unknown concept"):
            taxonomy.validate_taxonomy()

    def test_weights_must_sum_to_one(self, monkeypatch: pytest.MonkeyPatch) -> None:
        bad = taxonomy.Archetype(
            id="lr-halfweight",
            section="LR",
            name="Half",
            concepts=["weaken"],
            difficulty_weights={"easy": 0.5, "med": 0.0, "hard": 0.0},
            guidance="n/a",
        )
        monkeypatch.setattr(taxonomy, "_ALL", (bad,))
        with pytest.raises(ValueError, match=r"sum to 1\.0"):
            taxonomy.validate_taxonomy()

    def test_passage_bound_archetypes_marked(self) -> None:
        for arch in taxonomy.archetypes_for("RC") + taxonomy.archetypes_for("LG"):
            assert arch.requires_passage, arch.id


class TestConfig:
    def test_route_tier(self) -> None:
        assert route_tier("easy") == "bulk"
        assert route_tier("med") == "standard"
        assert route_tier("hard") == "premium"
        assert route_tier("easy", "premium") == "premium"

    def test_defaults_map_all_tiers(self) -> None:
        cfg = FactoryConfig()
        assert set(cfg.claude_tier_models) == {"bulk", "standard", "premium", "judge"}
        assert cfg.claude_tier_models == DEFAULT_CLAUDE_TIER_MODELS

    def test_missing_tier_rejected(self) -> None:
        with pytest.raises(ValueError, match="missing tiers"):
            FactoryConfig(claude_tier_models={"bulk": "m"})  # type: ignore[dict-item]

    def test_from_settings_overrides(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(settings, "LSAT_FACTORY_TARGET_PER_CELL", 5, raising=False)
        monkeypatch.setattr(
            settings,
            "LSAT_FACTORY_CLAUDE_TIERS",
            json.dumps({"bulk": "claude-custom-mini"}),
            raising=False,
        )
        cfg = FactoryConfig.from_settings()
        assert cfg.target_per_cell == 5
        assert cfg.claude_tier_models["bulk"] == "claude-custom-mini"
        # Unspecified tiers keep their defaults.
        assert cfg.claude_tier_models["judge"] == DEFAULT_CLAUDE_TIER_MODELS["judge"]

    def test_from_settings_malformed_tiers_falls_back(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            settings, "LSAT_FACTORY_CLAUDE_TIERS", "{not json", raising=False
        )
        cfg = config_mod.FactoryConfig.from_settings()
        assert cfg.claude_tier_models == DEFAULT_CLAUDE_TIER_MODELS

    def test_resolved_output_dir_absolute(self, tmp_path: Any) -> None:
        cfg = FactoryConfig(output_dir=tmp_path)
        assert cfg.resolved_output_dir() == tmp_path
        rel = FactoryConfig(output_dir="backend/var/x")  # type: ignore[arg-type]
        assert rel.resolved_output_dir().is_absolute()
