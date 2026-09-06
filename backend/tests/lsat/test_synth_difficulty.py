"""Measured difficulty: the structural proxy and the graded fold-back.

BL-20260903-14. Two claims are under test. First, that a band is *measured*
from the item rather than copied off its schema — and measured on one scale, so
a hard quantifier item and a hard assumption item mean the same thing. Second,
that real grades outrank both once there are enough of them.
"""

from __future__ import annotations

import json
import statistics
from collections import defaultdict
from io import StringIO
from pathlib import Path

import pytest
from django.conf import settings
from django.core.management import call_command

from law_ai.lsat.services.bank import DIFFICULTY_ORDER
from law_ai.lsat.synth.difficulty import (
    PROXY_BANDS,
    SCORE_CUTS,
    band_for,
    blend,
    measure,
    statement_depth,
)
from law_ai.lsat.synth.generate import generate
from law_ai.lsat.synth.lexicon import load_domains
from law_ai.lsat.synth.logic import And, Atom, Implies, Not
from law_ai.lsat.synth.schemas import all_schemas

#: Seeds per (schema, domain) pair in the sweep the band claims are checked
#: over. Two is enough to see arrangement variation without a slow test.
_SEEDS = 2


@pytest.fixture(autouse=True)
def _isolate_audit(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "AUDIT_PATH", str(tmp_path / "audit.jsonl"))


def _sweep() -> list[tuple[str, str, object]]:
    """``(schema_id, shipped band, complexity dump)`` over the registry."""
    rows: list[tuple[str, str, object]] = []
    domains = list(load_domains().values())
    for schema in all_schemas():
        for domain in domains:
            if not domain.supports(schema.meta.capability):
                continue
            for seed in range(_SEEDS):
                item = generate(schema.meta.id, domain.id, seed=seed)
                rows.append(
                    (
                        schema.meta.id,
                        item.question.difficulty,
                        item.provenance.complexity,
                    )
                )
    return rows


class TestProxy:
    def test_statement_depth_counts_nesting(self) -> None:
        assert statement_depth(Atom("P")) == 1
        assert statement_depth(Not(Atom("P"))) == 2
        assert statement_depth(Implies(Atom("P"), Atom("Q"))) == 2
        nested = Implies(And((Atom("P"), Atom("Q"))), Not(Atom("R")))
        assert statement_depth(nested) == 3

    def test_band_for_uses_the_documented_cuts(self) -> None:
        low, high = SCORE_CUTS
        assert band_for(low - 0.01) == PROXY_BANDS[0]
        assert band_for(low) == PROXY_BANDS[1]
        assert band_for(high) == PROXY_BANDS[2]

    def test_a_proved_item_carries_its_measurement(self) -> None:
        item = generate("lr-conditional-chain-forward", "municipal-policy", seed=1)
        complexity = item.provenance.complexity
        assert complexity is not None
        # Every feature the score is built from stays visible on the item.
        for field in ("premises", "depth", "slots", "closeness", "space", "score"):
            assert field in complexity
        assert item.provenance.declared_difficulty == "easy"

    def test_a_structural_item_keeps_its_declared_band(self) -> None:
        """No model space means nothing to measure, and the proxy says so."""
        item = generate("lr-causal-weaken", "municipal-policy", seed=1)
        assert item.provenance.complexity is None
        assert item.question.difficulty == item.provenance.declared_difficulty == "med"

    def test_the_draw_moves_the_score(self) -> None:
        """Arrangements vary per seed, so one schema is not one difficulty."""
        scores = {
            generate(
                "lr-conditional-chain-forward", "municipal-policy", seed=s
            ).provenance.complexity["score"]
            for s in range(6)
        }
        assert len(scores) > 1

    def test_the_measurement_is_domain_independent(self) -> None:
        """A domain swap changes words, so it must not change the band."""
        a = generate("lr-conditional-chain-forward", "municipal-policy", seed=3)
        b = generate("lr-conditional-chain-forward", "field-biology", seed=3)
        assert a.provenance.complexity == b.provenance.complexity
        assert a.question.difficulty == b.question.difficulty


class TestBandsAcrossTheRegistry:
    def test_shipped_bands_are_monotone_in_measured_complexity(self) -> None:
        """One scale, all families: a harder band means a higher score.

        This is the claim the declared band could not make. It is computed
        across every proved schema at once, so an assumption item banded
        ``hard`` has to be structurally heavier than a quantifier item banded
        ``med``, not merely called heavier by whoever wrote the schema.
        """
        by_band: dict[str, list[float]] = defaultdict(list)
        for _schema_id, shipped, complexity in _sweep():
            if complexity is None:
                continue
            by_band[shipped].append(float(complexity["score"]))
        present = [b for b in DIFFICULTY_ORDER if by_band[b]]
        assert len(present) >= 3, f"only {present} bands were emitted"
        means = [statistics.mean(by_band[b]) for b in present]
        assert means == sorted(means), dict(zip(present, means, strict=True))

    def test_no_item_ships_more_than_one_band_from_its_schema(self) -> None:
        """The proxy is evidence, not a licence to re-band an item wholesale."""
        declared = {s.meta.id: s.meta.difficulty for s in all_schemas()}
        order = list(DIFFICULTY_ORDER)
        for schema_id, shipped, _complexity in _sweep():
            distance = abs(order.index(shipped) - order.index(declared[schema_id]))
            assert distance <= 1, f"{schema_id} shipped {shipped}"

    def test_more_than_one_band_comes_out_of_the_registry(self) -> None:
        bands = {shipped for _s, shipped, _c in _sweep()}
        assert len(bands) >= 3

    def test_blend_clamps_in_both_directions(self) -> None:
        item = generate("lr-conditional-chain-forward", "municipal-policy", seed=0)
        complexity = measure(
            # Re-measure through the public helper to prove blend() is what
            # clamps, not generate().
            _blueprint_of("lr-conditional-chain-forward", 0),
            item.report,
        )
        assert complexity is not None
        assert blend("intro", complexity) in ("intro", "easy")
        assert blend("elite", complexity) in ("hard", "elite")


def _blueprint_of(schema_id: str, seed: int):  # type: ignore[no-untyped-def]
    import random

    from law_ai.lsat.synth import ENGINE_VERSION
    from law_ai.lsat.synth.lexicon import get_domain
    from law_ai.lsat.synth.schemas import get_schema

    schema = get_schema(schema_id)
    rng = random.Random(f"{ENGINE_VERSION}|{schema_id}|{seed}")
    return schema.build(rng, get_domain("municipal-policy"))


def _record_attempts(
    schema_id: str, question_id: str, *, attempts: int, correct: int
) -> None:
    from law_ai.core import audit_jsonl as audit_store

    audit_store.record(
        {
            "type": "lsat_synth.promoted",
            "question_id": question_id,
            "provenance": {"schema_id": schema_id, "domain_id": "municipal-policy"},
        }
    )
    for i in range(attempts):
        audit_store.record(
            {
                "type": "lsat_grade",
                "question_id": question_id,
                "section": "LR",
                "correct": i < correct,
            }
        )


class TestGradedFoldBack:
    def test_a_thin_sample_measures_nothing(self) -> None:
        from law_ai.lsat.synth.calibrate import measured_bands, schema_accuracy

        _record_attempts("lr-necessary-assumption", "syn-lr-aaa", attempts=5, correct=1)
        rows = schema_accuracy()
        assert [r.schema_id for r in rows] == ["lr-necessary-assumption"]
        assert rows[0].attempts == 5
        assert rows[0].measured is None
        assert rows[0].agrees is None
        assert measured_bands() == {}

    def test_enough_attempts_band_the_schema_by_accuracy(self) -> None:
        from law_ai.lsat.synth.calibrate import (
            MIN_ATTEMPTS,
            measured_bands,
            schema_accuracy,
        )

        _record_attempts(
            "lr-necessary-assumption",
            "syn-lr-bbb",
            attempts=MIN_ATTEMPTS,
            correct=MIN_ATTEMPTS // 3,
        )
        row = next(r for r in schema_accuracy())
        assert row.attempts == MIN_ATTEMPTS
        assert row.measured == "hard"
        assert row.agrees is True  # the schema declares hard too
        assert measured_bands() == {"syn-lr-bbb": "hard"}

    def test_a_disagreement_is_reported(self) -> None:
        from law_ai.lsat.synth.calibrate import MIN_ATTEMPTS, disagreements

        # A "hard" schema learners get right nine times in ten is not hard.
        _record_attempts(
            "lr-necessary-assumption",
            "syn-lr-ccc",
            attempts=MIN_ATTEMPTS,
            correct=MIN_ATTEMPTS - 3,
        )
        rows = disagreements()
        assert [r.schema_id for r in rows] == ["lr-necessary-assumption"]
        assert rows[0].measured == "easy"
        assert rows[0].declared == "hard"

    def test_grades_on_unknown_questions_are_not_attributed(self) -> None:
        from law_ai.core import audit_jsonl as audit_store
        from law_ai.lsat.synth.calibrate import schema_accuracy

        for _ in range(40):
            audit_store.record(
                {
                    "type": "lsat_grade",
                    "question_id": "lr-hand-authored",
                    "correct": True,
                }
            )
        assert schema_accuracy() == []

    def test_the_census_counts_the_measured_band(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A bank item whose schema has evidence is censused where it lands."""
        from law_ai.lsat.factory import coverage
        from law_ai.lsat.services.bank import load_bank

        question = next(iter(load_bank().values()))
        assert question.difficulty != "elite"
        monkeypatch.setattr(
            coverage, "_effective_bands", lambda: {question.id: "elite"}
        )
        counts = coverage.census()
        moved = [
            arch for (arch, band), n in counts.items() if band == "elite" and n > 0
        ]
        assert moved, "the measured band did not reach the census"


class TestCalibrateCommand:
    def _run(self, *args: str) -> str:
        out = StringIO()
        call_command("lsat_synth_calibrate", *args, stdout=out)
        return out.getvalue()

    def test_graded_report_lists_schemas_and_writes_json(self, tmp_path: Path) -> None:
        from law_ai.lsat.synth.calibrate import MIN_ATTEMPTS

        _record_attempts(
            "lr-quantifier-most-overlap",
            "syn-lr-ddd",
            attempts=MIN_ATTEMPTS,
            correct=MIN_ATTEMPTS - 1,
        )
        out = tmp_path / "calibration.json"
        text = self._run("--out", str(out))
        assert "lr-quantifier-most-overlap" in text
        assert "disagrees with declared" in text
        report = json.loads(out.read_text(encoding="utf-8"))
        assert report["kind"] == "graded"
        assert report["min_attempts"] == MIN_ATTEMPTS
        assert report["disagreements"] == ["lr-quantifier-most-overlap"]

    def test_structural_report_suggests_cuts(self, tmp_path: Path) -> None:
        out = tmp_path / "structural.json"
        text = self._run("--structural", "--seeds", "1", "--out", str(out))
        assert "Structural difficulty proxy" in text
        assert "declared band stands" in text  # the structural schemas
        report = json.loads(out.read_text(encoding="utf-8"))
        assert report["kind"] == "structural"
        assert report["items"] > 0
        assert len(report["cuts_suggested"]) == 2
        assert report["cuts_in_use"] == list(SCORE_CUTS)

    def test_no_grades_is_a_report_not_a_failure(self, tmp_path: Path) -> None:
        text = self._run("--out", str(tmp_path / "empty.json"))
        assert "no graded attempts" in text
