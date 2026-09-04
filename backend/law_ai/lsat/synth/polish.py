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
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from law_ai.core import llm
from law_ai.lsat.synth.generate import SynthItem, generate
from law_ai.lsat.synth.lexicon import DomainPack, Property, get_domain

logger = logging.getLogger("law_ai.lsat.synth.polish")

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


def lint_property(raw: dict[str, Any], *, existing: set[str]) -> str | None:
    """Return the reason a proposal is unusable, or None when it is clean.

    Rejects rather than repairs: a proposal that needed fixing is a proposal the
    model did not understand, and a silently-corrected one is the kind of thing
    nobody looks at again.
    """
    identifier = str(raw.get("id") or "").strip()
    if not re.fullmatch(r"[a-z][a-z0-9_]{1,30}", identifier):
        return f"bad id {identifier!r}"
    if identifier in existing:
        return f"duplicate id {identifier!r}"
    for field in _FIELDS:
        value = raw.get(field)
        if not isinstance(value, str) or not value.strip():
            return f"missing {field}"
        text = value.strip()
        if not (_MIN_CHARS <= len(text) <= _MAX_CHARS):
            return f"{field} is {len(text)} chars, outside {_MIN_CHARS}-{_MAX_CHARS}"
        # The negative forms are *supposed* to contain "not"; every other form
        # must be free of logical vocabulary.
        if field in ("vp_negate", "vp_negate_plural"):
            stripped = re.sub(r"\bnot\b|\bno\b", "", text, flags=re.IGNORECASE)
        else:
            stripped = text
        match = _FORBIDDEN.search(stripped)
        if match is not None:
            return f"{field} contains the logical word {match.group(0)!r}"
    return None


def parse_proposals(raw_text: str, *, existing: set[str]) -> list[Property]:
    """Parse and lint a model response into usable properties."""
    try:
        payload = llm.loads_first_json(raw_text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"polish response was not JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError("polish response is not a JSON object")
    out: list[Property] = []
    seen = set(existing)
    for entry in payload.get("properties") or []:
        if not isinstance(entry, dict):
            continue
        reason = lint_property(entry, existing=seen)
        if reason is not None:
            logger.info("discarding proposed property: %s", reason)
            continue
        out.append(Property.model_validate({k: entry[k] for k in ("id", *_FIELDS)}))
        seen.add(str(entry["id"]))
    return out


async def propose_properties(domain: DomainPack, *, count: int = 4) -> list[Property]:
    """Ask the provider chain for new vocabulary. Returns [] when unavailable."""
    subject = domain.subjects[0]
    prompt = _PROMPT.format(
        count=count,
        subject=subject.plural,
        domain=domain.name,
        tone=domain.tone,
        min_chars=_MIN_CHARS,
        max_chars=_MAX_CHARS,
        existing="\n".join(f"- {p.vp_affirm}" for p in domain.properties),
    )
    try:
        result = await llm.agenerate(prompt, system=_SYSTEM, agent="lsat_synth_polish")
    except Exception as exc:
        logger.info("polish unavailable, keeping the generated vocabulary: %s", exc)
        return []
    try:
        return parse_proposals(result.text, existing={p.id for p in domain.properties})
    except ValueError as exc:
        logger.info("polish response unusable: %s", exc)
        return []


def polish_item(item: SynthItem, *, count: int = 4) -> SynthItem:
    """Regenerate one item over an extended vocabulary, then re-verify it.

    Same schema, same seed, same templates — so the blueprint, the premises and
    every entailment are identical. Only which words fill the slots can change,
    and the result is verified again before it is returned.
    """
    from asgiref.sync import async_to_sync

    domain = get_domain(item.provenance.domain_id)
    proposals = async_to_sync(propose_properties)(domain, count=count)
    if not proposals:
        return item

    extended = domain.model_copy(
        update={"properties": [*proposals, *domain.properties]}
    )
    try:
        return generate(
            item.provenance.schema_id,
            item.provenance.domain_id,
            seed=item.provenance.seed,
            domain_override=extended,
        )
    except Exception as exc:
        # A polished item that will not verify is discarded, not shipped with a
        # warning: the unpolished one is already correct.
        logger.info("polished item failed verification, keeping the original: %s", exc)
        return item
