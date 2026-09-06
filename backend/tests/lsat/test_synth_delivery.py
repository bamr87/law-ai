"""Delivery: command, executor, the bounded promotion gate, and polish.

Spec 049 T-030/T-031/T-032/T-040 (FR-13..FR-18, AC-7, AC-8, AC-9).
"""

from __future__ import annotations

import asyncio
import json
from io import StringIO
from pathlib import Path

import pytest
from django.conf import settings
from django.core.management import CommandError, call_command

from law_ai.lsat.factory.coverage import GenerationTarget
from law_ai.lsat.factory.executors import ExecutionError, SynthExecutor
from law_ai.lsat.factory.manifest import GenerationJob
from law_ai.lsat.synth.generate import generate
from law_ai.lsat.synth.promote import (
    PromotionRefused,
    promote_to_bank,
    queue_for_review,
)


@pytest.fixture(autouse=True)
def _isolate(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "AUDIT_PATH", str(tmp_path / "audit.jsonl"))
    monkeypatch.setattr(
        settings, "LSAT_PROPOSALS_DIR", str(tmp_path / "proposals"), raising=False
    )
    monkeypatch.setattr(settings, "LSAT_SYNTH_AUTOPROMOTE", False, raising=False)


def _run(*args: str, **opts: object) -> str:
    out = StringIO()
    call_command("lsat_synth", *args, stdout=out, **opts)
    return out.getvalue()


class TestCommand:
    def test_list_names_schemas_and_domains(self) -> None:
        text = _run("list")
        assert "lr-quantifier-most-overlap" in text
        assert "municipal-policy" in text
        # The two guarantees must be distinguishable at a glance.
        assert "proved" in text and "built" in text

    def test_preview_renders_an_item_and_its_proof(self) -> None:
        text = _run(
            "preview",
            "--schema",
            "lr-necessary-assumption",
            "--domain",
            "field-biology",
        )
        assert "key:" in text
        assert "verified" in text
        assert "premises_satisfiable" in text
        assert "solve guide" in text

    def test_preview_requires_both_arguments(self) -> None:
        with pytest.raises(CommandError, match="needs --schema and --domain"):
            _run("preview", "--schema", "lr-necessary-assumption")

    def test_verify_covers_every_pair_for_a_schema(self) -> None:
        text = _run("verify", "--schema", "lr-quantifier-all-some")
        assert text.count("verified") >= 4

    def test_sweep_reports_success(self) -> None:
        assert "every generated item verified" in _run("sweep", "--seeds", "2")

    def test_generate_to_jsonl(self, tmp_path: Path) -> None:
        out = tmp_path / "items.jsonl"
        _run(
            "generate",
            "--schema",
            "lr-conditional-chain-forward",
            "--domain",
            "municipal-policy",
            "--count",
            "3",
            "--emit",
            "jsonl",
            "--out",
            str(out),
        )
        rows = [json.loads(line) for line in out.read_text().splitlines()]
        assert len(rows) == 3
        for row in rows:
            assert row["verification"]["proof_kind"] == "logical"
            assert row["provenance"]["seed"] is not None
            assert row["guide"]["steps"]

    def test_generate_to_the_review_queue(self) -> None:
        from law_ai.lsat.services import proposals as store

        _run(
            "generate",
            "--schema",
            "lr-causal-weaken",
            "--domain",
            "field-biology",
            "--count",
            "2",
            "--emit",
            "proposals",
        )
        pending = store.list_proposals("pending")
        assert len(pending) == 2
        assert all(p["proposal_kind"] == "question" for p in pending)

    def test_bank_emit_requires_the_explicit_flag(self) -> None:
        """The setting alone is not consent to skip review."""
        with pytest.raises(CommandError, match="requires --promote"):
            _run(
                "generate",
                "--schema",
                "lr-conditional-chain-forward",
                "--domain",
                "municipal-policy",
                "--emit",
                "bank",
            )


class TestSynthExecutor:
    def _job(
        self, archetype: str, *, section: str = "LR", count: int = 2
    ) -> GenerationJob:
        return GenerationJob(
            job_id=f"job-{archetype}",
            tier="bulk",
            model_hint="n/a",
            template_version="n/a",
            prompt="",
            target=GenerationTarget(
                section=section,
                archetype_id=archetype,
                difficulty="med",
                count=count,
                concepts=[],
                tier="bulk",
                priority=1.0,
                rationale="test",
            ),
        )

    def test_fulfils_a_job_with_no_network(self) -> None:
        batch = asyncio.run(
            SynthExecutor().execute(self._job("lr-necessary-assumption"))
        )
        assert batch.model_label.startswith("deterministic/")
        assert len(batch.payload["drafts"]) == 2
        for draft in batch.payload["drafts"]:
            assert "id" not in draft
            assert draft["confidence"] == 1.0
            assert [c["label"] for c in draft["choices"]] == ["A", "B", "C", "D", "E"]

    def test_structural_drafts_carry_a_lower_confidence(self) -> None:
        batch = asyncio.run(SynthExecutor().execute(self._job("lr-weaken")))
        assert all(d["confidence"] == 0.5 for d in batch.payload["drafts"])

    def test_an_uncovered_archetype_says_so_rather_than_substituting(self) -> None:
        with pytest.raises(ExecutionError, match="no synthesis schema covers"):
            asyncio.run(SynthExecutor().execute(self._job("lr-main-conclusion")))

    def test_the_same_job_replays_to_the_same_drafts(self) -> None:
        job = self._job("lr-sufficient-assumption")
        first = asyncio.run(SynthExecutor().execute(job))
        second = asyncio.run(SynthExecutor().execute(job))
        assert first.payload == second.payload

    def test_drafts_pass_the_factory_intake_gates(self) -> None:
        """Spec 049 AC-7: the same path an LLM draft takes."""
        from law_ai.lsat.factory.config import FactoryConfig
        from law_ai.lsat.factory.intake import ingest_batch

        job = self._job("lr-necessary-assumption", count=2)
        batch = asyncio.run(SynthExecutor().execute(job))
        result = ingest_batch(
            batch.payload,
            job=job,
            config=FactoryConfig(),
            executor_name="synth",
            model_label=batch.model_label,
        )
        assert len(result.accepted) >= 1, [r.model_dump() for r in result.rejected]


class TestPromotionGate:
    def test_queue_for_review_is_the_default_path(self) -> None:
        from law_ai.lsat.services import proposals as store

        item = generate("lr-conditional-chain-forward", "municipal-policy", seed=1)
        proposal_id = queue_for_review(item)
        row = store.get_proposal(proposal_id)
        assert row is not None
        assert row["status"] == "pending"
        assert row["meta"]["schema_id"] == "lr-conditional-chain-forward"

    def test_structural_items_are_never_promotable(self) -> None:
        """A construction guarantee is not a proof, and the gate knows it."""
        item = generate("lr-causal-weaken", "municipal-policy", seed=1)
        with pytest.raises(PromotionRefused, match="proof kind is 'structural'"):
            promote_to_bank(item)

    def test_setting_off_refuses_even_a_proved_item(self) -> None:
        item = generate("lr-conditional-chain-forward", "municipal-policy", seed=1)
        with pytest.raises(PromotionRefused, match="LSAT_SYNTH_AUTOPROMOTE is off"):
            promote_to_bank(item)

    def test_an_item_from_an_older_engine_is_refused(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A newer engine draws a different arrangement from the same seed, so
        re-verifying against it would prove a different item (BL-20260903-15)."""
        from dataclasses import replace

        monkeypatch.setattr(settings, "LSAT_SYNTH_AUTOPROMOTE", True, raising=False)
        item = generate("lr-conditional-chain-forward", "municipal-policy", seed=1)
        stale = replace(
            item,
            provenance=item.provenance.model_copy(update={"engine_version": "synth/1"}),
        )
        with pytest.raises(PromotionRefused, match="generated by synth/1"):
            promote_to_bank(stale)

    def test_provenance_records_the_drawn_arrangement(self) -> None:
        from law_ai.lsat.services import proposals as store

        item = generate("lg-sequencing-acceptability", "field-biology", seed=2)
        row = store.get_proposal(queue_for_review(item))
        assert row is not None
        assert row["meta"]["arrangement"]["rule_count"] >= 2
        assert row["meta"]["engine_version"] == item.provenance.engine_version

    def test_promotion_writes_the_item_and_audits_the_proof(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from law_ai.core import audit_jsonl as audit_store
        from law_ai.lsat.services import bank as bank_mod

        sandbox = tmp_path / "lsat_data"
        sandbox.mkdir()
        for name in ("lr_bank.json", "rc_bank.json", "lg_bank.json", "concepts.json"):
            src = bank_mod.DATA_DIR / name
            if src.is_file():
                (sandbox / name).write_text(src.read_text(encoding="utf-8"))
        monkeypatch.setattr(bank_mod, "DATA_DIR", sandbox)
        bank_mod.load_bank.cache_clear()
        monkeypatch.setattr(settings, "LSAT_SYNTH_AUTOPROMOTE", True, raising=False)

        item = generate("lr-conditional-chain-forward", "municipal-policy", seed=1)
        promote_to_bank(item, reviewer="tester")

        written = json.loads((sandbox / "lr_bank.json").read_text())
        assert item.question.id in {q["id"] for q in written["items"]}

        events = [
            e for e in audit_store.tail(100) if e.get("type") == "lsat_synth.promoted"
        ]
        assert len(events) == 1
        proof = events[0]["proof"]
        assert proof["premise_models"] > 0
        assert "credited_is_entailed" in proof["checks"]
        bank_mod.load_bank.cache_clear()

    def test_promotion_refuses_a_duplicate(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from law_ai.lsat.services import bank as bank_mod

        sandbox = tmp_path / "lsat_data"
        sandbox.mkdir()
        for name in ("lr_bank.json", "rc_bank.json", "lg_bank.json", "concepts.json"):
            src = bank_mod.DATA_DIR / name
            if src.is_file():
                (sandbox / name).write_text(src.read_text(encoding="utf-8"))
        monkeypatch.setattr(bank_mod, "DATA_DIR", sandbox)
        bank_mod.load_bank.cache_clear()
        monkeypatch.setattr(settings, "LSAT_SYNTH_AUTOPROMOTE", True, raising=False)

        item = generate("lr-conditional-chain-forward", "municipal-policy", seed=1)
        promote_to_bank(item)
        with pytest.raises(PromotionRefused, match="already in the bank"):
            promote_to_bank(item)
        bank_mod.load_bank.cache_clear()


class TestPolish:
    def test_lint_rejects_logical_vocabulary(self) -> None:
        from law_ai.lsat.synth.polish import lint_property

        entry = {
            "id": "conditional",
            "vp_affirm": "was approved only if the board met",
            "vp_affirm_plural": "were approved after the board met",
            "vp_negate": "was not approved after the board met",
            "vp_negate_plural": "were not approved after the board met",
            "modifier": "approved after the board met",
        }
        assert "only" in str(lint_property(entry, existing=set()))

    def test_lint_accepts_a_clean_predicate(self) -> None:
        from law_ai.lsat.synth.polish import lint_property

        entry = {
            "id": "audited",
            "vp_affirm": "was audited by the state office",
            "vp_affirm_plural": "were audited by the state office",
            "vp_negate": "was not audited by the state office",
            "vp_negate_plural": "were not audited by the state office",
            "modifier": "audited by the state office",
        }
        assert lint_property(entry, existing=set()) is None

    def test_lint_rejects_a_duplicate_id(self) -> None:
        from law_ai.lsat.synth.polish import lint_property

        entry = {
            "id": "audited",
            "vp_affirm": "was audited by the state office",
            "vp_affirm_plural": "were audited by the state office",
            "vp_negate": "was not audited by the state office",
            "vp_negate_plural": "were not audited by the state office",
            "modifier": "audited by the state office",
        }
        assert "duplicate" in str(lint_property(entry, existing={"audited"}))

    def test_no_provider_returns_the_unpolished_item(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """AC-9: polish is a nicety, never a dependency."""
        from law_ai.core import llm
        from law_ai.lsat.synth.polish import polish_item

        async def _unavailable(prompt, *, system=None, agent=None):
            raise llm.LLMUnavailableError("no provider")

        monkeypatch.setattr(llm, "agenerate", _unavailable)
        item = generate("lr-conditional-chain-forward", "municipal-policy", seed=1)
        assert polish_item(item).question.model_dump() == item.question.model_dump()

    def test_a_polished_item_is_re_verified(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The vocabulary changes; the proof is re-run and still holds."""
        from law_ai.core import llm
        from law_ai.lsat.synth.polish import polish_item

        proposals = {
            "properties": [
                {
                    "id": f"proposed_{i}",
                    "vp_affirm": f"was logged in register {i} at the depot",
                    "vp_affirm_plural": f"were logged in register {i} at the depot",
                    "vp_negate": f"was not logged in register {i} at the depot",
                    "vp_negate_plural": f"were not logged in register {i} at the depot",
                    "modifier": f"logged in register {i} at the depot",
                }
                for i in range(5)
            ]
        }

        class _Result:
            # Mirrors law_ai.core.llm.base.LLMResult: the polish yield records
            # which tier answered, so the stub must carry the route too.
            text = json.dumps(proposals)
            provider = "test"
            model_label = "test/model"

        async def _agenerate(prompt, *, system=None, agent=None):
            return _Result()

        monkeypatch.setattr(llm, "agenerate", _agenerate)
        item = generate("lr-conditional-chain-forward", "municipal-policy", seed=1)
        polished = polish_item(item)
        assert polished.report.ok
        assert "register" in polished.question.stem
        # Same schema and seed, so the proof is the same proof.
        assert polished.report.premise_models == item.report.premise_models
        assert polished.question.correct == item.question.correct
