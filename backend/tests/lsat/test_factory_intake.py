"""Intake gate tests (spec 024 T-006: FR-7, FR-9, AC-3, AC-4)."""

from __future__ import annotations

from typing import Any

from law_ai.lsat.factory.config import FactoryConfig
from law_ai.lsat.factory.coverage import GenerationTarget
from law_ai.lsat.factory.intake import ingest_batch
from law_ai.lsat.factory.manifest import GenerationJob
from law_ai.lsat.services import proposals
from law_ai.lsat.services.bank import load_bank


def _job(
    *,
    section: str = "LR",
    archetype_id: str = "lr-weaken",
    mode: str = "items",
    passage_id: str | None = None,
) -> GenerationJob:
    return GenerationJob(
        job_id="mfst-t-job01",
        target=GenerationTarget(
            section=section,  # type: ignore[arg-type]
            archetype_id=archetype_id,
            difficulty="med",
            count=3,
            concepts=["weaken"],
            mode=mode,  # type: ignore[arg-type]
            passage_id=passage_id,
            tier="standard",
            priority=1.0,
            rationale="test",
        ),
        tier="standard",
        model_hint="claude-sonnet-5",
        template_version="lsat_factory_item/1",
        prompt="PROMPT",
    )


def _draft(
    stem: str, *, correct: str = "B", concepts: list[str] | None = None
) -> dict[str, Any]:
    return {
        "section": "LR",
        "difficulty": "med",
        "stem": stem,
        "choices": [
            {"label": label, "text": f"choice {label} for {stem[:12]}"}
            for label in ("A", "B", "C", "D", "E")
        ],
        "correct": correct,
        "explanation": "Key works; others fail for distinct reasons.",
        "concepts": concepts if concepts is not None else ["weaken"],
        "confidence": 0.8,
    }


_STEMS = (
    "Municipal recycling budgets rose while landfill volume also rose; the "
    "mayor concludes recycling failed. Which option most weakens this?",
    "A vineyard switched to drought-resistant vines and yields fell; the "
    "owner blames the new vines. Which finding most undermines that blame?",
    "Hospital wait times dropped after a triage app launched; administrators "
    "credit the app. Which fact most calls that credit into question?",
    "Transit ridership climbed when fares were cut; planners infer price "
    "drove the climb. Which alternative most challenges the inference?",
)


def _ingest(
    payload: dict[str, Any], cfg: FactoryConfig, job: GenerationJob | None = None
) -> Any:
    return ingest_batch(
        payload,
        job=job or _job(),
        config=cfg,
        executor_name="test",
        model_label="test/model",
    )


class TestGates:
    def test_happy_path_records_proposals_with_meta(
        self, factory_env: FactoryConfig
    ) -> None:
        result = _ingest(
            {
                "drafts": [
                    _draft(_STEMS[0], correct="B"),
                    _draft(_STEMS[1], correct="D"),
                ]
            },
            factory_env,
        )
        assert len(result.accepted) == 2 and not result.rejected
        assert result.trace_id
        rows = proposals.list_proposals(status="pending")
        assert len(rows) == 2
        meta = rows[0].get("meta", {}).get("factory", {})
        assert meta.get("job_id") == "mfst-t-job01"
        assert meta.get("archetype_id") == "lr-weaken"
        assert meta.get("tier") == "standard"
        assert meta.get("executor") == "test"

    def test_schema_gate(self, factory_env: FactoryConfig) -> None:
        bad = _draft(_STEMS[0])
        bad["choices"] = bad["choices"][:4]  # only four choices
        result = _ingest({"drafts": [bad, "not-an-object"]}, factory_env)
        assert not result.accepted
        assert {r.reason for r in result.rejected} == {"schema"}

    def test_concept_gate(self, factory_env: FactoryConfig) -> None:
        result = _ingest(
            {"drafts": [_draft(_STEMS[0], concepts=["no-such-concept"])]},
            factory_env,
        )
        assert not result.accepted
        assert result.rejected[0].reason == "concept"
        assert "no-such-concept" in result.rejected[0].detail

    def test_section_gate(self, factory_env: FactoryConfig) -> None:
        wrong = _draft(_STEMS[0])
        wrong["section"] = "RC"
        result = _ingest({"drafts": [wrong]}, factory_env)
        assert result.rejected[0].reason == "section"

    def test_duplicate_of_bank_item_rejected(self, factory_env: FactoryConfig) -> None:
        # AC-3: near-copy of a live bank stem must never reach the store.
        bank_stem = load_bank()["lr-002"].stem
        result = _ingest({"drafts": [_draft(bank_stem)]}, factory_env)
        assert not result.accepted
        assert result.rejected[0].reason == "duplicate"
        assert "lr-002" in result.rejected[0].detail
        assert proposals.list_proposals(status="pending") == []

    def test_intra_batch_duplicate_rejected(self, factory_env: FactoryConfig) -> None:
        result = _ingest(
            {"drafts": [_draft(_STEMS[2]), _draft(_STEMS[2])]}, factory_env
        )
        assert len(result.accepted) == 1
        assert result.rejected[0].reason == "duplicate"

    def test_balance_flag_on_key_skew(self, factory_env: FactoryConfig) -> None:
        # AC-4: 4 distinct drafts all keyed "C" → flagged, not rejected.
        drafts = [_draft(stem, correct="C") for stem in _STEMS]
        result = _ingest({"drafts": drafts}, factory_env)
        assert len(result.accepted) == 4
        assert result.balance_flag and "skew" in result.balance_flag
        for row in proposals.list_proposals(status="pending"):
            assert "balance_flag" in row["meta"]["factory"]

    def test_no_balance_flag_when_spread(self, factory_env: FactoryConfig) -> None:
        drafts = [
            _draft(_STEMS[0], correct="A"),
            _draft(_STEMS[1], correct="C"),
            _draft(_STEMS[2], correct="E"),
        ]
        result = _ingest({"drafts": drafts}, factory_env)
        assert result.balance_flag is None

    def test_passage_linkage_applied(self, factory_env: FactoryConfig) -> None:
        rc = _draft(_STEMS[3], concepts=["rc-inference"])
        rc["section"] = "RC"
        result = _ingest(
            {"drafts": [rc]},
            factory_env,
            job=_job(
                section="RC",
                archetype_id="rc-inference",
                passage_id="rc-passage-001",
            ),
        )
        assert len(result.accepted) == 1
        row = proposals.list_proposals(status="pending")[0]
        assert row["draft"]["passage_id"] == "rc-passage-001"

    def test_model_emitted_passage_id_ignored(self, factory_env: FactoryConfig) -> None:
        sneaky = _draft(_STEMS[0])
        sneaky["passage_id"] = "rc-passage-001"  # LR items carry no passage
        result = _ingest({"drafts": [sneaky]}, factory_env)
        assert len(result.accepted) == 1
        row = proposals.list_proposals(status="pending")[0]
        assert row["draft"].get("passage_id") is None

    def test_passage_set_parks_new_context(self, factory_env: FactoryConfig) -> None:
        lg = _draft(_STEMS[1], concepts=["grouping-game"])
        lg["section"] = "LG"
        payload = {
            "drafts": [lg],
            "passage": {"section": "LG", "title": "New grouping game", "rules": []},
        }
        result = _ingest(
            payload,
            factory_env,
            job=_job(section="LG", archetype_id="lg-grouping", mode="passage_set"),
        )
        assert result.pending_passage_path is not None
        row = proposals.list_proposals(status="pending")[0]
        assert (
            row["meta"]["factory"]["pending_passage_path"]
            == result.pending_passage_path
        )
