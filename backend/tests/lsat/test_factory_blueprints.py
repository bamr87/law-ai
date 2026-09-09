"""Blueprint compiler tests (spec 024 T-003: FR-4)."""

from __future__ import annotations

from law_ai.lsat.factory.blueprints import (
    ITEM_TEMPLATE_VERSION,
    PASSAGE_TEMPLATE_VERSION,
    compile_prompt,
    select_exemplars,
)
from law_ai.lsat.factory.config import FactoryConfig
from law_ai.lsat.factory.coverage import GenerationTarget
from law_ai.lsat.factory.taxonomy import get_archetype


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


class TestExemplarCoverage:
    """BL-20260901-02 — every archetype must have real few-shot material."""

    def test_every_archetype_has_two_items_on_its_primary_concept(
        self, factory_env: FactoryConfig
    ) -> None:
        """One item cannot establish a pattern; the spec-047 archetypes had 0-1."""
        from law_ai.lsat.factory.taxonomy import by_id
        from law_ai.lsat.services.bank import load_bank

        bank = list(load_bank().values())
        thin = {}
        for archetype_id, archetype in by_id().items():
            primary = archetype.concepts[0]
            tagged = [
                q.id
                for q in bank
                if q.section == archetype.section and primary in q.concepts
            ]
            if len(tagged) < 2:
                thin[archetype_id] = tagged
        assert not thin, f"archetypes without two primary-concept exemplars: {thin}"

    def test_a_true_instance_outranks_a_shared_secondary_concept(
        self, factory_env: FactoryConfig
    ) -> None:
        """The ranking fix: an item tagged with the archetype's primary concept
        comes first, even when a broader match matches the target difficulty."""
        from law_ai.lsat.factory.taxonomy import get_archetype

        archetype = get_archetype("lr-point-at-issue")
        primary = archetype.concepts[0]
        target = _target(
            archetype_id="lr-point-at-issue",
            concepts=list(archetype.concepts),
            difficulty="hard",
        )
        exemplars = select_exemplars(target, k=2)
        assert exemplars, "the archetype must have exemplars at all"
        assert all(primary in q.concepts for q in exemplars)

    def test_difficulty_still_breaks_ties_within_the_primary_group(
        self, factory_env: FactoryConfig
    ) -> None:
        from law_ai.lsat.factory.taxonomy import get_archetype
        from law_ai.lsat.services.bank import load_bank

        archetype = get_archetype("lr-flaw-general")
        primary = archetype.concepts[0]
        bank = load_bank()
        # The tie being broken is *within* the top-ranked group: stamped
        # instances of the archetype (spec 053 stamped the bank), or, for an
        # unstamped item, the primary-concept proxy.
        difficulties = {
            q.difficulty
            for q in bank.values()
            if q.archetype == "lr-flaw-general"
            or (q.archetype is None and primary in q.concepts)
        }
        wanted = "easy" if "easy" in difficulties else sorted(difficulties)[0]
        first = select_exemplars(
            _target(
                archetype_id="lr-flaw-general",
                concepts=list(archetype.concepts),
                difficulty=wanted,
            ),
            k=1,
        )[0]
        assert primary in first.concepts
        assert first.difficulty == wanted


class TestStampedArchetype:
    """BL-20260905-54 — an item that says which archetype it instantiates.

    Exemplar selection used to infer the pattern back out of the concept tags,
    which is a guess. A stamped item is an exact instance and outranks every
    guess — and is selectable even when it carries no concept tags at all.
    """

    def test_a_stamped_item_outranks_the_concept_proxy(
        self, factory_env: FactoryConfig
    ) -> None:
        # Spec 053 stamped the whole bank, so the stamped test item now competes
        # with real stamped weaken items and sits behind the ones that also
        # carry the primary concept. The claim under test is the *ordering*:
        # any stamped item, even one with no concept tags, outranks an
        # unstamped item that merely carries the concepts.
        stamped = _add_bank_item(
            id="lr-stamped-001", archetype="lr-weaken", concepts=[]
        )
        proxy = _add_bank_item(
            id="lr-proxy-001", archetype=None, concepts=["weaken", "alternative-cause"]
        )
        ranked = [q.id for q in select_exemplars(_target(), k=500)]
        assert stamped in ranked and proxy in ranked
        assert ranked.index(stamped) < ranked.index(proxy)
        assert all(q.archetype == "lr-weaken" for q in select_exemplars(_target(), k=1))

    def test_an_unstamped_bank_still_selects_by_concept(
        self, factory_env: FactoryConfig
    ) -> None:
        exemplars = select_exemplars(_target(), k=2)
        assert exemplars
        wanted = set(get_archetype("lr-weaken").concepts)
        assert all(set(q.concepts) & wanted for q in exemplars)
