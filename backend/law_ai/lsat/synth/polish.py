"""The one optional model call — and it never touches the logic.

Spec 049 FR-17/FR-18. The engine is deterministic and offline by default. This
module is the opt-in path for fresher vocabulary, and its design is the whole
safety argument:

**The model proposes lexicon entries, not sentences.** Asking a model to reword
a rendered stimulus would let it change the logical form — "if" to "only if" is
one character of difference and a different item — and no cheap check would
catch it. Here the model proposes *properties* (a verb phrase in four forms plus
a modifier), the item is regenerated from the same schema and the same seed
through the unchanged templates, and the logic is preserved **by construction**
rather than by trust. The regenerated item then goes through the same verifier as
everything else.

**Proposals are linted, not repaired.** A property containing a logical operator
is the one thing that could smuggle reasoning into the surface layer, so any
proposal containing one is discarded rather than edited into shape.

**No provider means no polish, not a failure.** The unpolished item is already
valid; degrading to it is the correct behaviour.

**Yield is measured, not assumed** (BL-20260903-17). Every proposal round
produces a :class:`PolishYield` — how many predicates the model proposed, how
many survived the lint, and why each reject fell — keyed on the provider tier
that answered. It rides on the polished item's provenance so the review queue
records it, and ``lsat_synth polish-yield`` aggregates it across domains so the
prompt's real yield is a number rather than a guess.
"""

from __future__ import annotations

import dataclasses
import json
import logging
import re
from typing import Any

from pydantic import BaseModel, Field

from law_ai.core import llm
from law_ai.lsat.synth.generate import SynthItem, generate
from law_ai.lsat.synth.lexicon import DomainPack, Property, get_domain

logger = logging.getLogger("law_ai.lsat.synth.polish")

#: The share of proposed predicates that must survive the lint for the prompt
#: to be considered working. ``polish-yield`` and the opt-in live test both
#: compare against this; a prompt whose yield falls below it is producing more
#: rejects than vocabulary and needs re-authoring, not a bigger ``--count``.
POLISH_YIELD_FLOOR = 0.5

#: Lint reject categories, in the order the report lists them. Each is a
#: single cause the prompt can be tuned against; "unparseable" covers a reply
#: that was not a JSON object at all, and "not-an-object" an entry inside the
#: ``properties`` list that was not a dict.
REJECT_REASONS = (
    "bad-id",
    "duplicate",
    "missing-field",
    "length",
    "forbidden-word",
    "not-an-object",
    "unparseable",
)


class PolishYield(BaseModel):
    """What one proposal round produced, and which tier produced it."""

    proposed: int = 0
    accepted: int = 0
    rejected: dict[str, int] = Field(default_factory=dict)
    provider: str = ""
    model_label: str = ""
    #: Why no proposals were counted at all: "unavailable" when no tier could
    #: serve the call, "unparseable" when the reply was not JSON. Empty on a
    #: round that reached the lint.
    error: str = ""

    @property
    def rate(self) -> float:
        """Accepted over proposed; zero when nothing was proposed."""
        return self.accepted / self.proposed if self.proposed else 0.0

    def reject(self, reason: str) -> None:
        self.rejected[reason] = self.rejected.get(reason, 0) + 1

    def merge(self, other: PolishYield) -> None:
        """Fold another round into this aggregate (provider labels are not kept)."""
        self.proposed += other.proposed
        self.accepted += other.accepted
        for reason, count in other.rejected.items():
            self.rejected[reason] = self.rejected.get(reason, 0) + count


#: Words that carry logical force. A property is meant to be an atomic
#: predicate — "was reviewed by the board" — and one containing "unless" or
#: "only if" would put a second conditional inside what the schema treats as a
#: single proposition, quietly changing the item's logic.
_FORBIDDEN = re.compile(
    r"\b(if|only|unless|all|every|some|most|none|no|not|never|always|"
    r"therefore|because|since|although|whether|either|neither|and|or)\b",
    re.IGNORECASE,
)

_MIN_CHARS = 12
_MAX_CHARS = 70

_SYSTEM = (
    "You extend a controlled vocabulary for LSAT item generation. You never "
    "write questions, arguments, or logic — only short factual predicates. "
    "Respond with a single JSON object and nothing else."
)

_PROMPT = """\
Propose {count} new predicates for a controlled vocabulary describing \
**{subject}** in the domain "{domain}" ({tone} register).

A predicate is one plain, checkable property. Give each in five forms.

Hard rules:
- No logical words at all: if, only, unless, all, every, some, most, no, not,
  never, always, and, or, because, therefore, although, whether.
- No negation in the affirmative forms. The negative forms negate exactly the
  affirmative ones and nothing else.
- Each form between {min_chars} and {max_chars} characters.
- Concrete and domain-specific. Not "was good" or "was processed".

Existing predicates, which you must not duplicate or paraphrase:
{existing}

Respond with:

{{"properties": [
  {{"id": "short_snake_case",
    "vp_affirm": "was reviewed by the planning board",
    "vp_affirm_plural": "were reviewed by the planning board",
    "vp_negate": "was not reviewed by the planning board",
    "vp_negate_plural": "were not reviewed by the planning board",
    "modifier": "reviewed by the planning board"}}
]}}
"""

_FIELDS = (
    "vp_affirm",
    "vp_affirm_plural",
    "vp_negate",
    "vp_negate_plural",
    "modifier",
)


def lint_property_reason(
    raw: dict[str, Any], *, existing: set[str]
) -> tuple[str, str] | None:
    """``(category, detail)`` for an unusable proposal, or None when it is clean.

    The category is one of :data:`REJECT_REASONS` and is what the yield report
    counts; the detail is the human-readable message. Rejects rather than
    repairs: a proposal that needed fixing is a proposal the model did not
    understand, and a silently-corrected one is the kind of thing nobody looks
    at again.
    """
    identifier = str(raw.get("id") or "").strip()
    if not re.fullmatch(r"[a-z][a-z0-9_]{1,30}", identifier):
        return "bad-id", f"bad id {identifier!r}"
    if identifier in existing:
        return "duplicate", f"duplicate id {identifier!r}"
    for field in _FIELDS:
        value = raw.get(field)
        if not isinstance(value, str) or not value.strip():
            return "missing-field", f"missing {field}"
        text = value.strip()
        if not (_MIN_CHARS <= len(text) <= _MAX_CHARS):
            return (
                "length",
                f"{field} is {len(text)} chars, outside {_MIN_CHARS}-{_MAX_CHARS}",
            )
        # The negative forms are *supposed* to contain "not"; every other form
        # must be free of logical vocabulary.
        if field in ("vp_negate", "vp_negate_plural"):
            stripped = re.sub(r"\bnot\b|\bno\b", "", text, flags=re.IGNORECASE)
        else:
            stripped = text
        match = _FORBIDDEN.search(stripped)
        if match is not None:
            return (
                "forbidden-word",
                f"{field} contains the logical word {match.group(0)!r}",
            )
    return None


def lint_property(raw: dict[str, Any], *, existing: set[str]) -> str | None:
    """Return the reason a proposal is unusable, or None when it is clean."""
    found = lint_property_reason(raw, existing=existing)
    return None if found is None else found[1]


def parse_proposals_with_yield(
    raw_text: str, *, existing: set[str]
) -> tuple[list[Property], PolishYield]:
    """Parse and lint a model response, counting every reject by reason.

    A reply that is not a JSON object yields no properties and an
    ``unparseable`` error rather than raising: for the yield report that *is*
    the measurement, not an exception to it.
    """
    result = PolishYield()
    try:
        payload = llm.loads_first_json(raw_text)
    except json.JSONDecodeError as exc:
        logger.info("polish response was not JSON: %s", exc)
        result.error = "unparseable"
        result.reject("unparseable")
        return [], result
    if not isinstance(payload, dict):
        result.error = "unparseable"
        result.reject("unparseable")
        return [], result
    out: list[Property] = []
    seen = set(existing)
    for entry in payload.get("properties") or []:
        result.proposed += 1
        if not isinstance(entry, dict):
            result.reject("not-an-object")
            continue
        found = lint_property_reason(entry, existing=seen)
        if found is not None:
            category, detail = found
            logger.info("discarding proposed property: %s", detail)
            result.reject(category)
            continue
        out.append(Property.model_validate({k: entry[k] for k in ("id", *_FIELDS)}))
        seen.add(str(entry["id"]))
        result.accepted += 1
    return out, result


def parse_proposals(raw_text: str, *, existing: set[str]) -> list[Property]:
    """Parse and lint a model response into usable properties.

    Raises ``ValueError`` when the reply is not a JSON object, for callers that
    want the failure rather than a zero-yield record.
    """
    properties, result = parse_proposals_with_yield(raw_text, existing=existing)
    if result.error == "unparseable":
        raise ValueError("polish response was not a JSON object")
    return properties


def _prompt_for(domain: DomainPack, *, count: int) -> str:
    subject = domain.subjects[0]
    return _PROMPT.format(
        count=count,
        subject=subject.plural,
        domain=domain.name,
        tone=domain.tone,
        min_chars=_MIN_CHARS,
        max_chars=_MAX_CHARS,
        existing="\n".join(f"- {p.vp_affirm}" for p in domain.properties),
    )


async def propose_with_yield(
    domain: DomainPack, *, count: int = 4
) -> tuple[list[Property], PolishYield]:
    """Ask the provider chain for new vocabulary and measure what survived.

    The call goes through :func:`law_ai.core.llm.agenerate`, so it is logged as
    an ``llm_call`` provenance event like every other model call. The yield
    records which tier answered — the same prompt yields differently on a
    frontier model and a local one, and a number without its tier is not
    comparable to anything.
    """
    try:
        result = await llm.agenerate(
            _prompt_for(domain, count=count), system=_SYSTEM, agent="lsat_synth_polish"
        )
    except Exception as exc:
        logger.info("polish unavailable, keeping the generated vocabulary: %s", exc)
        return [], PolishYield(error="unavailable")
    properties, measured = parse_proposals_with_yield(
        result.text, existing={p.id for p in domain.properties}
    )
    measured.provider = result.provider
    measured.model_label = result.model_label
    return properties, measured


async def propose_properties(domain: DomainPack, *, count: int = 4) -> list[Property]:
    """Ask the provider chain for new vocabulary. Returns [] when unavailable."""
    properties, _ = await propose_with_yield(domain, count=count)
    return properties


def _with_yield(item: SynthItem, measured: PolishYield) -> SynthItem:
    """The same item, with the polish round recorded on its provenance."""
    return dataclasses.replace(
        item,
        provenance=item.provenance.model_copy(
            update={"polish": measured.model_dump(mode="json")}
        ),
    )


def polish_item(item: SynthItem, *, count: int = 4) -> SynthItem:
    """Regenerate one item over an extended vocabulary, then re-verify it.

    Same schema, same seed, same templates — so the blueprint, the premises and
    every entailment are identical. Only which words fill the slots can change,
    and the result is verified again before it is returned. Whatever happens,
    the returned item's provenance carries the round's :class:`PolishYield`,
    so the review queue records what the prompt produced.
    """
    from asgiref.sync import async_to_sync

    domain = get_domain(item.provenance.domain_id)
    proposals, measured = async_to_sync(propose_with_yield)(domain, count=count)
    if not proposals:
        return _with_yield(item, measured)

    extended = domain.model_copy(
        update={"properties": [*proposals, *domain.properties]}
    )
    try:
        polished = generate(
            item.provenance.schema_id,
            item.provenance.domain_id,
            seed=item.provenance.seed,
            domain_override=extended,
        )
    except Exception as exc:
        # A polished item that will not verify is discarded, not shipped with a
        # warning: the unpolished one is already correct.
        logger.info("polished item failed verification, keeping the original: %s", exc)
        return _with_yield(item, measured)
    return _with_yield(polished, measured)
