"""Per-attempt answer shuffling, and the stateless token that undoes it.

BL-20260606-01. Until now a question's key sat in the same place forever: the
bank stores ``correct: "C"`` and every learner, on every attempt, saw the
credited answer third. That is a real defect in a drill tool — the second time
through a set, position is a cue, and a cue that has nothing to do with the
reasoning is exactly the wrong thing to learn.

So the serve path may permute the choices, and nothing about that permutation
is stored:

**The token carries the order, signed.** ``permute`` relabels the choices A-E
in display order and returns a token containing the permutation and an HMAC
over ``question_id:permutation`` keyed on ``SECRET_KEY``. The grade path reads
the order back out of the token, so no session, cache or database row is needed
and two servers need share nothing but the key.

**The token is bound to its question.** The signature covers the question id, so
a token minted for one item cannot be replayed against another to move its key.
A tampered or foreign token is rejected rather than ignored: silently grading
against the stored order would mark a correct answer wrong.

**Label references are remapped, not hoped about.** Explanations and solve-guide
steps in the shipped banks say things like "A is correct" and "(D) is the
exception". Under a permutation those sentences would contradict the screen, so
:func:`remap_labels` rewrites them — conservatively, matching only the shapes a
label reference actually takes, so the "A" in "A recent study" is left alone.
"""

from __future__ import annotations

import hmac
import re
import secrets
from collections.abc import Sequence
from hashlib import sha256

from django.conf import settings

from law_ai.lsat.services.bank import Choice, ChoiceLabel

#: Answer labels, in order. Not configurable: the bank model requires A–E.
LABELS: tuple[ChoiceLabel, ...] = ("A", "B", "C", "D", "E")

#: How many hex characters of the HMAC ride in the token. Sixty-four bits is
#: far past what a guessing attacker gains here — the prize is re-ordering
#: one's own practice question — and keeps the token short enough to sit in a
#: query string.
_SIGNATURE_CHARS = 16


class ShuffleError(ValueError):
    """A remap token is malformed, unsigned, or minted for another question."""


def new_order(count: int) -> tuple[int, ...]:
    """A fresh permutation: display position *i* shows original choice ``order[i]``.

    Drawn from :mod:`secrets` rather than :mod:`random` so that two attempts in
    the same second do not share a shuffle, and so nothing about the sequence
    is predictable from another item's.
    """
    order = list(range(count))
    for i in range(count - 1, 0, -1):
        j = secrets.randbelow(i + 1)
        order[i], order[j] = order[j], order[i]
    return tuple(order)


def _signature(question_id: str, digits: str) -> str:
    key = str(settings.SECRET_KEY).encode()
    message = f"{question_id}:{digits}".encode()
    return hmac.new(key, message, sha256).hexdigest()[:_SIGNATURE_CHARS]


def token_for(question_id: str, order: Sequence[int]) -> str:
    """``"<order digits>.<signature>"`` — everything the grade path needs."""
    digits = "".join(str(i) for i in order)
    return f"{digits}.{_signature(question_id, digits)}"


def order_from_token(question_id: str, token: str) -> tuple[int, ...]:
    """The permutation a token carries, if it is genuinely this question's.

    Raises :class:`ShuffleError` on anything else. Failing loudly matters: a
    silent fallback to the stored order would grade a correct answer as wrong
    whenever a token went stale.
    """
    digits, _, signature = token.partition(".")
    if not digits or not signature:
        raise ShuffleError("remap token is malformed")
    if not digits.isdigit() or len(set(digits)) != len(digits):
        raise ShuffleError("remap token does not carry a permutation")
    order = tuple(int(c) for c in digits)
    if sorted(order) != list(range(len(order))):
        raise ShuffleError("remap token does not carry a permutation")
    if not hmac.compare_digest(signature, _signature(question_id, digits)):
        raise ShuffleError("remap token is not signed for this question")
    return order


def permute(
    choices: Sequence[Choice], question_id: str, order: Sequence[int] | None = None
) -> tuple[list[Choice], str, tuple[int, ...]]:
    """Relabel ``choices`` into a display order, with the token that reverses it.

    The returned choices are labelled A-E top to bottom, so every client — the
    platform UI, the static export, a screen reader — sees an ordinary question
    and needs to know nothing about shuffling.
    """
    drawn = tuple(order) if order is not None else new_order(len(choices))
    if sorted(drawn) != list(range(len(choices))):
        raise ShuffleError("order does not permute these choices")
    shown = [
        Choice(label=LABELS[position], text=choices[source].text)
        for position, source in enumerate(drawn)
    ]
    return shown, token_for(question_id, drawn), drawn


def to_canonical(label: str, order: Sequence[int]) -> ChoiceLabel:
    """The stored label behind a label the learner saw."""
    position = LABELS.index(label)
    return LABELS[order[position]]


def to_display(label: str, order: Sequence[int]) -> ChoiceLabel:
    """Where a stored label ended up on screen."""
    source = LABELS.index(label)
    return LABELS[list(order).index(source)]


def display_mapping(order: Sequence[int]) -> dict[str, str]:
    """``canonical label → displayed label`` for every choice in play."""
    return {LABELS[source]: LABELS[position] for position, source in enumerate(order)}


#: The shapes a label reference actually takes in an explanation or a guide
#: step. Anything else — the article "A", an initial, a citation — is left
#: alone, which is the whole point of enumerating them.
_REFERENCE_PATTERNS = (
    # "(A)" / "(A) is" — parenthesised, the exam's own notation.
    re.compile(r"\((?P<label>[A-E])\)"),
    # "choice A", "answer B", "option C", any capitalisation.
    re.compile(r"(?i:\b(?P<word>choice|answer|option)\s+)(?P<label>[A-E])\b"),
    # "A is correct", "B and C", "D, not E" — a bare label doing subject work,
    # recognised by what follows it rather than by hope.
    re.compile(
        r"(?<![A-Za-z0-9(])(?P<label>[A-E])(?=\s*(?:is|are|was|were|and|or|"
        r"remains|says|states|,|;|:|\)|/|\u2014|\u2013)\b|\s*[,;:)/]|\u2014|\u2013)"
    ),
)


def remap_labels(text: str, mapping: dict[str, str]) -> str:
    """Rewrite the label references in ``text`` through ``mapping``.

    Every match is rewritten in one pass over the string, so a mapping that
    swaps two labels cannot rewrite the same reference twice — the bug a naive
    sequence of replacements always has.
    """
    if not text or not mapping:
        return text

    spans: list[tuple[int, int, str]] = []
    for pattern in _REFERENCE_PATTERNS:
        for match in pattern.finditer(text):
            start, end = match.span("label")
            if any(start < e and s < end for s, e, _ in spans):
                continue
            spans.append((start, end, mapping.get(match.group("label"), "")))
    if not spans:
        return text
    out = list(text)
    for start, end, replacement in spans:
        if replacement:
            out[start:end] = replacement
    return "".join(out)


def label_references(text: str) -> list[str]:
    """Every label reference :func:`remap_labels` would rewrite, in order.

    Used by the tests that inventory the shipped banks, and by anything that
    wants to know whether a piece of content is label-bound before shuffling it.
    """
    found: list[tuple[int, str]] = []
    seen: list[tuple[int, int]] = []
    for pattern in _REFERENCE_PATTERNS:
        for match in pattern.finditer(text):
            start, end = match.span("label")
            if any(start < e and s < end for s, e in seen):
                continue
            seen.append((start, end))
            found.append((start, match.group("label")))
    return [label for _start, label in sorted(found)]
