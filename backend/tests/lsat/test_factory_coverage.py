"""Coverage planner tests (spec 024 T-002: FR-3)."""

from __future__ import annotations

import pytest

from law_ai.core import audit_jsonl as audit_store
from law_ai.lsat.factory.config import FactoryConfig
from law_ai.lsat.factory.coverage import (
    census,
    coverage_matrix,
    plan_targets,
)


class TestCensus:
    def test_counts_by_concept_overlap(self, factory_env: FactoryConfig) -> None:
        counts = census()
        # lr-002 is a med weaken item in the seed bank.
        assert counts[("lr-weaken", "med")] >= 1
        # No grouping-game items exist yet.
        assert counts[("lg-grouping", "med")] == 0

    def test_zero_weight_cells_want_nothing(self, factory_env: FactoryConfig) -> None:
        cells = {
            (c.archetype_id, c.difficulty): c for c in coverage_matrix(factory_env)
        }
        # Acceptability questions are never 'hard' on the real exam (weight 0).
        assert cells[("lg-acceptability", "hard")].want == 0


class TestPlanTargets:
    def test_deterministic(self, factory_env: FactoryConfig) -> None:
        first = plan_targets(factory_env)
        second = plan_targets(factory_env)
        assert [t.model_dump() for t in first] == [t.model_dump() for t in second]

    def test_caps_and_counts(self, factory_env: FactoryConfig) -> None:
        targets = plan_targets(factory_env)
        assert 0 < len(targets) <= factory_env.max_jobs
        assert all(1 <= t.count <= factory_env.drafts_per_job for t in targets)

    def test_passage_strategy(self, factory_env: FactoryConfig) -> None:
        targets = plan_targets(factory_env.model_copy(update={"max_jobs": 200}))
        by_arch = {t.archetype_id: t for t in targets}
        # RC archetypes ride an existing passage.
        rc = by_arch.get("rc-inference")
        assert rc is not None and rc.mode == "items"
        assert rc.passage_id is not None and rc.passage_id.startswith("rc-passage-")
        # No grouping game exists → brand-new passage_set on the premium tier.
        grouping = by_arch.get("lg-grouping")
        assert grouping is not None
        assert grouping.mode == "passage_set"
        assert grouping.passage_id is None
        assert grouping.tier == "premium"

    def test_gap_boost_prioritizes_weak_concepts(
        self, factory_env: FactoryConfig
    ) -> None:
        # Learners keep missing 'weaken' items → its cells should be boosted.
        for _ in range(4):
            audit_store.record(
                {
                    "type": "lsat_grade",
                    "section": "LR",
                    "concepts": ["weaken"],
                    "correct": False,
                }
            )
        targets = plan_targets(factory_env.model_copy(update={"max_jobs": 200}))
        boosted = [t for t in targets if t.archetype_id == "lr-weaken"]
        assert boosted, "expected lr-weaken targets"
        for t in boosted:
            assert "learner-weak" in t.rationale
            # priority = deficit × gap_boost ⇒ strictly above the raw deficit.
            assert (
                t.priority > 0
                and t.priority % factory_env.gap_boost == pytest.approx(0.0)
            )
