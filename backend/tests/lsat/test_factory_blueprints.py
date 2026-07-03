"""Blueprint compiler tests (spec 024 T-003: FR-4)."""

from __future__ import annotations

from lawgraph.lsat.factory.blueprints import (
    ITEM_TEMPLATE_VERSION,
    PASSAGE_TEMPLATE_VERSION,
    compile_prompt,
    select_exemplars,
)
from lawgraph.lsat.factory.config import FactoryConfig
from lawgraph.lsat.factory.coverage import GenerationTarget
from lawgraph.lsat.factory.taxonomy import get_archetype


def _target(**overrides: object) -> GenerationTarget:
    base: dict[str, object] = {
        "section": "LR",
        "archetype_id": "lr-weaken",
        "difficulty": "med",
        "count": 3,
        "concepts": ["weaken", "alternative-cause"],
        "mode": "items",
        "passage_id": None,
        "tier": "standard",
        "priority": 1.0,
        "rationale": "test",
    }
    base.update(overrides)
    return GenerationTarget.model_validate(base)


class TestExemplars:
    def test_same_archetype_and_cap(self, factory_env: FactoryConfig) -> None:
        exemplars = select_exemplars(_target(), k=2)
        assert 1 <= len(exemplars) <= 2
        wanted = set(get_archetype("lr-weaken").concepts)
        for q in exemplars:
            assert q.section == "LR"
            assert set(q.concepts) & wanted

    def test_k_zero(self, factory_env: FactoryConfig) -> None:
        assert select_exemplars(_target(), k=0) == []

    def test_deterministic(self, factory_env: FactoryConfig) -> None:
        a = [q.id for q in select_exemplars(_target(), k=3)]
        b = [q.id for q in select_exemplars(_target(), k=3)]
        assert a == b


class TestCompile:
    def test_item_prompt_contents(self, factory_env: FactoryConfig) -> None:
        compiled = compile_prompt(_target(), factory_env)
        assert compiled.template_version == ITEM_TEMPLATE_VERSION
        text = compiled.text
        assert "LSAT Factory — Item Generation" in text
        assert get_archetype("lr-weaken").guidance in text
        assert "## Exemplars" in text  # seed bank has weaken items
        assert "## Concept catalog" in text
        assert '"count": 3' in text
        # RC-only concepts must not leak into an LR concept slice.
        assert '"id": "main-point"' not in text

    def test_no_exemplar_section_when_disabled(
        self, factory_env: FactoryConfig
    ) -> None:
        cfg = factory_env.model_copy(update={"exemplar_count": 0})
        assert "## Exemplars" not in compile_prompt(_target(), cfg).text

    def test_items_against_passage_embed_context(
        self, factory_env: FactoryConfig
    ) -> None:
        target = _target(
            section="RC",
            archetype_id="rc-inference",
            concepts=["rc-inference"],
            passage_id="rc-passage-001",
        )
        text = compile_prompt(target, factory_env).text
        assert "## Passage / game context" in text
        assert "rc-passage-001" in text

    def test_passage_set_uses_passage_template(
        self, factory_env: FactoryConfig
    ) -> None:
        target = _target(
            section="LG",
            archetype_id="lg-grouping",
            concepts=["grouping-game", "must-be-true"],
            mode="passage_set",
            tier="premium",
        )
        compiled = compile_prompt(target, factory_env)
        assert compiled.template_version == PASSAGE_TEMPLATE_VERSION
        assert "Passage / Game Set Generation" in compiled.text
        assert "## Format reference" in compiled.text  # lg-game-001 exists
        assert '"mode": "passage_set"' in compiled.text
