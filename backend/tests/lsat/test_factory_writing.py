"""Writing-section factory path (BL-20260831-28).

The factory could grow the MCQ bank and nothing else: no ``WS`` archetypes, no
coverage census over the writing library, no way to draft or promote a writing
prompt. These tests cover that loop end to end with no model call: taxonomy →
census → target → compiled prompt → intake gates → HITL promotion.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from law_ai.lsat.factory import taxonomy
from law_ai.lsat.factory.blueprints import (
    DEFAULT_RUBRIC_ID,
    WRITING_TEMPLATE_VERSION,
    compile_prompt,
)
from law_ai.lsat.factory.config import FactoryConfig
from law_ai.lsat.factory.coverage import census, coverage_matrix, plan_targets
from law_ai.lsat.factory.intake import ingest_batch
from law_ai.lsat.factory.manifest import GenerationJob
from law_ai.lsat.factory.pipeline import status
from law_ai.lsat.services import proposals
from law_ai.lsat.services.writing import load_writing_prompts, load_writing_rubrics


def _ws_archetypes() -> tuple[Any, ...]:
    return taxonomy.archetypes_for("WS")


def _ws_target(archetype_id: str = "ws-resource-tradeoff") -> Any:
    from law_ai.lsat.factory.coverage import GenerationTarget

    arch = taxonomy.get_archetype(archetype_id)
    return GenerationTarget(
        section="WS",
        archetype_id=arch.id,
        difficulty="med",
        count=1,
        concepts=list(arch.concepts),
        mode="writing_prompt",
        tier="premium",
        priority=1.0,
        rationale="test",
    )


def _ws_job(archetype_id: str = "ws-resource-tradeoff") -> GenerationJob:
    return GenerationJob(
        job_id="mfst-ws-job01",
        target=_ws_target(archetype_id),
        tier="premium",
        model_hint="claude-opus-4-8",
        template_version=WRITING_TEMPLATE_VERSION,
        prompt="PROMPT",
    )


def _criteria() -> list[str]:
    rubric = load_writing_rubrics()[DEFAULT_RUBRIC_ID]
    return [c.id for c in rubric.criteria]


def _draft(
    issue: str = "Should the county fund the ferry or the bridge?",
) -> dict[str, Any]:
    crit = _criteria()[0]
    return {
        "title": "Ferry or bridge",
        "issue": issue,
        "context": "The county has one grant and two shovel-ready projects. "
        "It cannot be split, deferred, or matched with local funds.",
        "positions": [
            {
                "id": "fund-ferry",
                "name": "Fund the ferry",
                "summary": "Serves the isles.",
            },
            {
                "id": "fund-bridge",
                "name": "Fund the bridge",
                "summary": "Serves commuters.",
            },
        ],
        "perspectives": [
            {
                "id": "p1",
                "text": "The harbourmaster notes ferry ridership is seasonal.",
            },
            {"id": "p2", "text": "A planner notes the bridge locks in car traffic."},
            {
                "id": "p3",
                "text": "A resident of the isles has no other route in winter.",
            },
        ],
        "task": "Argue for one position and answer the other.",
        "concepts": ["thesis-position", "warrant"],
        "model_response": {
            "position_id": "fund-ferry",
            "thesis": "The ferry serves the people with no alternative.",
            "essay": "The grant should extend the ferry. " * 30,
            "annotations": [{"criterion_id": crit, "note": "States a position early."}],
        },
        "self_check": [{"criterion_id": crit, "prompt": "Did you state a position?"}],
    }


def _ingest(payload: dict[str, Any], cfg: FactoryConfig) -> Any:
    return ingest_batch(
        payload,
        job=_ws_job(),
        config=cfg,
        executor_name="test",
        model_label="test/model",
    )


class TestWritingTaxonomy:
    def test_ws_archetypes_are_registered_and_valid(self) -> None:
        ws = _ws_archetypes()
        assert ws, "the factory has no WS archetypes"
        assert all(a.section == "WS" for a in ws)
        # Every WS archetype is premium: an annotated model essay is the most
        # quality-sensitive thing the factory writes.
        assert all(a.tier_hint == "premium" for a in ws)
        taxonomy.validate_taxonomy()  # concepts must exist in the catalog

    def test_ws_archetypes_have_distinct_primary_concepts(self) -> None:
        primaries = [a.concepts[0] for a in _ws_archetypes()]
        assert len(set(primaries)) == len(primaries)


class TestWritingCensus:
    def test_the_library_is_counted_not_the_bank(
        self, factory_env: FactoryConfig
    ) -> None:
        counts = census()
        prompts = load_writing_prompts()
        ws_ids = {a.id for a in _ws_archetypes()}
        counted = sum(v for (arch_id, _), v in counts.items() if arch_id in ws_ids)
        assert prompts and counted > 0
        # Each seed prompt is counted under whichever archetype it drills.
        assert counted <= len(prompts) * len(ws_ids)

    def test_coverage_matrix_has_ws_cells(self, factory_env: FactoryConfig) -> None:
        cells = coverage_matrix(factory_env)
        ws_cells = [c for c in cells if c.section == "WS"]
        assert ws_cells
        assert any(c.want > 0 for c in ws_cells)

    def test_planner_emits_writing_targets(self, factory_env: FactoryConfig) -> None:
        targets = plan_targets(factory_env.model_copy(update={"max_jobs": 60}))
        ws_targets = [t for t in targets if t.section == "WS"]
        assert ws_targets, "the loop still cannot grow the writing section"
        for t in ws_targets:
            assert t.mode == "writing_prompt"
            # One authored task per job; never batched like MCQ items.
            assert t.count == 1
            assert t.tier == "premium"
            assert "library has" in t.rationale


class TestWritingBlueprint:
    def test_prompt_carries_the_rubric_and_an_exemplar(
        self, factory_env: FactoryConfig
    ) -> None:
        compiled = compile_prompt(_ws_target(), factory_env)
        assert compiled.template_version == WRITING_TEMPLATE_VERSION
        text = compiled.text
        assert "Argumentative Writing" in text
        assert "## Rubric" in text
        assert _criteria()[0] in text
        assert "## Exemplar" in text
        assert '"mode": "writing_prompt"' in text
        # The exemplar's model essay is truncated, not shipped whole.
        first = sorted(load_writing_prompts().values(), key=lambda p: p.id)[0]
        assert first.model_response.essay not in text


class TestWritingIntake:
    def test_valid_draft_lands_as_a_pending_writing_proposal(
        self, factory_env: FactoryConfig
    ) -> None:
        result = _ingest({"drafts": [_draft()]}, factory_env)
        assert len(result.accepted) == 1 and not result.rejected
        row = proposals.get_proposal(result.accepted[0])
        assert row is not None
        assert row["proposal_kind"] == "writing_prompt"
        assert row["status"] == "pending"
        assert row["meta"]["factory"]["mode"] == "writing_prompt"
        # Platform-owned fields are stamped, never taken from the model.
        assert row["draft"]["rubric_id"] == DEFAULT_RUBRIC_ID
        assert row["draft"]["difficulty"] == "med"

    def test_schema_gate_rejects_a_malformed_draft(
        self, factory_env: FactoryConfig
    ) -> None:
        bad = _draft()
        bad["positions"] = bad["positions"][:1]  # needs at least two
        result = _ingest({"drafts": [bad, "not-an-object"]}, factory_env)
        assert not result.accepted
        assert [r.reason for r in result.rejected] == ["schema", "schema"]

    def test_unknown_rubric_criterion_is_rejected(
        self, factory_env: FactoryConfig
    ) -> None:
        bad = _draft()
        bad["self_check"] = [{"criterion_id": "not-a-criterion", "prompt": "?"}]
        result = _ingest({"drafts": [bad]}, factory_env)
        assert [r.reason for r in result.rejected] == ["concept"]
        assert "criterion" in result.rejected[0].detail

    def test_unknown_concept_is_rejected(self, factory_env: FactoryConfig) -> None:
        bad = _draft()
        bad["concepts"] = ["not-a-concept"]
        result = _ingest({"drafts": [bad]}, factory_env)
        assert [r.reason for r in result.rejected] == ["concept"]

    def test_restating_a_library_issue_is_rejected(
        self, factory_env: FactoryConfig
    ) -> None:
        existing = sorted(load_writing_prompts().values(), key=lambda p: p.id)[0]
        result = _ingest({"drafts": [_draft(issue=existing.issue)]}, factory_env)
        assert [r.reason for r in result.rejected] == ["duplicate"]
        assert existing.id in result.rejected[0].detail

    def test_batch_writes_one_provenance_event(
        self, factory_env: FactoryConfig
    ) -> None:
        from law_ai.core import audit_jsonl as audit_store

        result = _ingest({"drafts": [_draft()]}, factory_env)
        events = [
            ev
            for ev in audit_store.tail(20)
            if ev.get("type") == "agent_call"
            and ev.get("agent") == "LSATContentFactory"
        ]
        assert len(events) == 1
        assert result.trace_id == events[0]["trace_id"]


class TestWritingPromotion:
    def test_approved_draft_joins_the_library(self, factory_env: FactoryConfig) -> None:
        from law_ai.lsat.services import bank as bank_mod

        before = len(load_writing_prompts())
        result = _ingest({"drafts": [_draft()]}, factory_env)
        promoted = proposals.promote_writing_prompt(
            result.accepted[0], reviewer="tester"
        )
        prompt_id = promoted["writing_prompt_id"]
        assert promoted["status"] == "approved"

        prompts = load_writing_prompts()
        assert len(prompts) == before + 1
        assert prompt_id in prompts
        # LLM-written model essays are labelled as such (NFR-PROV-1).
        assert "LSATContentFactory" in prompts[prompt_id].source
        blob = json.loads(
            (bank_mod.DATA_DIR / "writing_prompts.json").read_text(encoding="utf-8")
        )
        assert any(item["id"] == prompt_id for item in blob["items"])

    def test_promotion_refuses_a_question_proposal(
        self, factory_env: FactoryConfig
    ) -> None:
        pid = proposals.record_proposal(
            {"section": "LR", "stem": "x"},
            agent_trace_id="",
            model="test",
            confidence=0.5,
        )
        with pytest.raises(ValueError, match="writing_prompt"):
            proposals.promote_writing_prompt(pid)

    def test_status_reports_the_writing_library(
        self, factory_env: FactoryConfig
    ) -> None:
        snapshot = status(factory_env)
        assert snapshot["writing_prompts"] == len(load_writing_prompts())
        assert snapshot["writing_by_difficulty"]
