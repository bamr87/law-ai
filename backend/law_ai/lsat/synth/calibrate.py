"""Difficulty, folded back from what learners actually did.

BL-20260903-14, second half. :mod:`law_ai.lsat.synth.difficulty` measures an
item's *structure*; this module measures its *effect*. Every graded answer
writes an ``lsat_grade`` audit event carrying the question id, and every
promoted synthesized item writes an ``lsat_synth.promoted`` event carrying that
same id next to its provenance. Joining the two turns a pile of attempts into
one number per schema: the share of learners who got its items right.

Three rules keep that number honest.

**Enough attempts, or nothing.** Below :data:`MIN_ATTEMPTS` a schema keeps its
structural band. Ten attempts on a new schema is noise, and a band that flips
on the eleventh attempt is worse than a band that never moves.

**Documented thresholds, not tuned ones.** :data:`ACCURACY_CUTS` is a constant
in this module. Tuning a cut per schema until the bands look right would make
the measurement unfalsifiable, which is the failure the declared band already
had.

**Disagreements are reported, never silently applied.** A schema whose measured
band differs from its declared one is the interesting output of this module —
that is the evidence someone needs to re-band the schema, or to look at what
the item is actually testing.

The census consumes the result through :func:`measured_bands`: a bank item
whose schema has enough attempts is counted in the band learners put it in.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from law_ai.core import audit_jsonl as audit_store
from law_ai.lsat.services.bank import Difficulty
from law_ai.lsat.synth.schemas import all_schemas

#: Attempts a schema needs before measured accuracy outranks its structural
#: band. Thirty is the smallest sample where a 60%-correct schema is
#: distinguishable from an 80%-correct one at all; it is a documented
#: judgement, not a tuned one.
MIN_ATTEMPTS = 30

#: Accuracy → band. Read as: at least 80% correct is an easy item, 55% to 80%
#: is a mid item, below 55% is a hard one. Chosen once, for every schema.
ACCURACY_CUTS: tuple[tuple[float, Difficulty], ...] = (
    (0.80, "easy"),
    (0.55, "med"),
)

#: Band for accuracy below every cut.
HARDEST_BAND: Difficulty = "hard"

#: How many audit events to scan. The store is append-only, so this is a
#: window over recent history rather than a sample.
DEFAULT_WINDOW = 20_000


def band_for_accuracy(accuracy: float) -> Difficulty:
    """Band one accuracy figure against :data:`ACCURACY_CUTS`."""
    for threshold, band in ACCURACY_CUTS:
        if accuracy >= threshold:
            return band
    return HARDEST_BAND


class SchemaAccuracy(BaseModel):
    """What learners did on one schema's items."""

    schema_id: str
    declared: Difficulty
    attempts: int = 0
    correct: int = 0
    questions: list[str] = Field(default_factory=list)

    @property
    def accuracy(self) -> float:
        return self.correct / self.attempts if self.attempts else 0.0

    @property
    def confident(self) -> bool:
        """Enough attempts for the measured band to outrank the structural one."""
        return self.attempts >= MIN_ATTEMPTS

    @property
    def measured(self) -> Difficulty | None:
        """The band the grades put this schema in, or None when it is too thin."""
        return band_for_accuracy(self.accuracy) if self.confident else None

    @property
    def agrees(self) -> bool | None:
        """True/False against the declared band; None when there is no measurement."""
        measured = self.measured
        return None if measured is None else measured == self.declared

    def dump(self) -> dict[str, Any]:
        return {
            **self.model_dump(mode="json"),
            "accuracy": round(self.accuracy, 4),
            "measured": self.measured,
            "agrees": self.agrees,
        }


def question_schema_index(*, window: int = DEFAULT_WINDOW) -> dict[str, str]:
    """``question_id → schema_id`` for every promoted synthesized item.

    Built from ``lsat_synth.promoted`` audit events, which carry the item's
    provenance verbatim. An item that was never promoted (still a draft, or
    hand-authored) is simply absent, and its grades are not attributed.
    """
    index: dict[str, str] = {}
    try:
        events = audit_store.tail(window)
    except Exception:  # pragma: no cover - audit store issues must not block
        return index
    for event in events:
        if event.get("type") != "lsat_synth.promoted":
            continue
        provenance = event.get("provenance")
        question_id = event.get("question_id")
        if not isinstance(provenance, dict) or not isinstance(question_id, str):
            continue
        schema_id = provenance.get("schema_id")
        if isinstance(schema_id, str) and schema_id:
            index[question_id] = schema_id
    return index


def schema_accuracy(*, window: int = DEFAULT_WINDOW) -> list[SchemaAccuracy]:
    """Per-schema grade accuracy, ordered easiest-measured first then by id."""
    declared = {s.meta.id: s.meta.difficulty for s in all_schemas()}
    index = question_schema_index(window=window)
    rows: dict[str, SchemaAccuracy] = {}
    try:
        events = audit_store.tail(window)
    except Exception:  # pragma: no cover - audit store issues must not block
        events = []
    for event in events:
        if event.get("type") != "lsat_grade":
            continue
        question_id = event.get("question_id")
        schema_id = index.get(str(question_id))
        if schema_id is None:
            continue
        row = rows.setdefault(
            schema_id,
            SchemaAccuracy(
                schema_id=schema_id, declared=declared.get(schema_id, "med")
            ),
        )
        row.attempts += 1
        if event.get("correct") is True:
            row.correct += 1
        if str(question_id) not in row.questions:
            row.questions.append(str(question_id))
    return sorted(rows.values(), key=lambda r: (-r.accuracy, r.schema_id))


def measured_bands(*, window: int = DEFAULT_WINDOW) -> dict[str, Difficulty]:
    """``question_id → measured band`` for items whose schema has the evidence.

    Empty when nothing clears :data:`MIN_ATTEMPTS`, which is the normal state
    early on: the caller then keeps whatever band the item already carries.
    """
    out: dict[str, Difficulty] = {}
    for row in schema_accuracy(window=window):
        band = row.measured
        if band is None:
            continue
        for question_id in row.questions:
            out[question_id] = band
    return out


def disagreements(*, window: int = DEFAULT_WINDOW) -> list[SchemaAccuracy]:
    """Schemas with enough grades whose measured band is not the declared one."""
    return [r for r in schema_accuracy(window=window) if r.agrees is False]
