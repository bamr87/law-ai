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


def _add_bank_item(**overrides: object) -> str:
    """Append one item to the sandboxed LR bank; returns its id."""
    import json

    from law_ai.lsat.services import bank as bank_mod

    path = bank_mod.DATA_DIR / "lr_bank.json"
    blob = json.loads(path.read_text(encoding="utf-8"))
    item = {
        "id": "lr-stamped-001",
        "section": "LR",
        "type": "LR",
        "difficulty": "med",
        "stem": "A stamped item used only by this test, long enough to pass.",
        "choices": [
            {"label": label, "text": f"choice {label}"}
            for label in ("A", "B", "C", "D", "E")
        ],
        "correct": "A",
        "explanation": "A holds; the rest do not.",
        "concepts": [],
        "source": "test",
    }
    item.update(overrides)
    blob["items"].append(item)
    path.write_text(
        json.dumps(blob, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    bank_mod.load_bank.cache_clear()
    return str(item["id"])


class TestCensus:
    def test_counts_by_concept_overlap(self, factory_env: FactoryConfig) -> None:
        from law_ai.lsat.factory.taxonomy import get_archetype
        from law_ai.lsat.services.bank import load_bank

        counts = census()
        bank = list(load_bank().values())
        # Census counts a stamped item under its stamp (spec 053 stamped the
        # whole bank) and an unstamped one via the archetype's PRIMARY concept
        # tag; verify against a recomputation so the test is robust to bank
        # growth (no hard-coded per-cell numbers).
        for arch_id in ("lr-weaken", "lg-grouping", "rc-inference"):
            primary = get_archetype(arch_id).concepts[0]
            for diff in ("easy", "med", "hard"):
                expected = sum(
                    1
                    for q in bank
                    if q.difficulty == diff
                    and (
                        q.archetype == arch_id
                        if q.archetype is not None
                        else primary in q.concepts
                    )
                )
                assert counts[(arch_id, diff)] == expected
        # Seed sanity: the bundled lr-002 med weaken item is present.
        assert counts[("lr-weaken", "med")] >= 1

    def test_a_stamped_item_counts_only_under_its_own_archetype(
        self, factory_env: FactoryConfig
    ) -> None:
        """BL-20260905-54 — the stamp is exact where the proxy was a guess."""
        from law_ai.lsat.factory.taxonomy import get_archetype

        before = census()
        weaken_primary = get_archetype("lr-weaken").concepts[0]
        # Carries lr-weaken's primary concept but was generated as a flaw item.
        _add_bank_item(
            archetype="lr-flaw-general",
            concepts=[weaken_primary],
            difficulty="med",
        )
        after = census()
        assert (
            after[("lr-flaw-general", "med")] == before[("lr-flaw-general", "med")] + 1
        )
        # The proxy would have counted it here; the stamp says otherwise.
        assert after[("lr-weaken", "med")] == before[("lr-weaken", "med")]

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

    def test_passage_targets_ride_existing_passages(
        self, factory_env: FactoryConfig
    ) -> None:
        from law_ai.lsat.services.bank import load_passages

        # target_per_cell high so every passage-bound archetype is a target,
        # regardless of how full the bank is.
        cfg = factory_env.model_copy(update={"max_jobs": 300, "target_per_cell": 12})
        targets = plan_targets(cfg)
        pids = set(load_passages())
        rc_riding = [t for t in targets if t.section == "RC" and t.mode == "items"]
        assert rc_riding, "RC passages exist, so RC targets should ride them"
        # No passage-bound 'items' target may carry a dangling passage id.
        for t in targets:
            if t.section in ("RC", "LG") and t.mode == "items":
                assert t.passage_id in pids
            if t.mode == "passage_set":
                assert t.passage_id is None

    def test_passage_set_when_no_passage_exists(
        self, factory_env: FactoryConfig, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # With no passages at all, every passage-bound archetype must author a
        # brand-new set on the premium tier (the passage_set branch).
        import law_ai.lsat.factory.coverage as cov

        monkeypatch.setattr(cov, "load_passages", lambda: {})
        cfg = factory_env.model_copy(update={"max_jobs": 300, "target_per_cell": 12})
        lg_targets = [t for t in plan_targets(cfg) if t.section == "LG"]
        assert lg_targets, "expected LG targets"
        for t in lg_targets:
            assert t.mode == "passage_set"
            assert t.passage_id is None
            assert t.tier == "premium"

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
