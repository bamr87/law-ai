"""Per-task scoring helpers for LegalBench (spec 018 T-002, spec 031).

Scoring is deliberately task-agnostic:

* **Exact match after normalisation** — strip leading/trailing whitespace,
  lowercase, collapse internal whitespace. Covers boolean, short-answer,
  and label tasks (True/False, Yes/No, single-word categories).
* **Prefix match** — the expected answer is a prefix of a longer response.
* **First-label extraction** — instruction-tuned models rarely answer with
  a bare label; they answer "The answer is True." A naive prefix match
  scores that wrong, which understates accuracy and makes a 1 pp regression
  policy meaningless (BL-20260810-04).

The extraction is deliberately conservative: it looks for the *first*
token drawn from a closed label vocabulary and compares **that** to the
expected label. So "The answer is True." scores correct, while
"False — it is not true that…" scores incorrect rather than matching the
later "true". A looser "expected appears anywhere in response" rule would
inflate scores on exactly the verbose answers we care about.
"""

from __future__ import annotations

import re

#: Closed vocabulary of labels LegalBench-style tasks use. Extraction only
#: fires when the expected answer is one of these, so free-text subsets
#: (e.g. case names) keep strict matching.
_LABEL_VOCAB: frozenset[str] = frozenset(
    {
        "true",
        "false",
        "yes",
        "no",
        "entailment",
        "contradiction",
        "neutral",
        "relevant",
        "irrelevant",
    }
)

#: Lead-ins models put before the label. Stripped before first-token match.
_LEAD_INS = re.compile(
    r"^(?:the\s+)?(?:correct\s+)?answer(?:\s+is)?\s*[:\-—]?\s*"
    r"|^a\s*[:\-]\s*"
    r"|^label\s*[:\-]\s*",
    re.IGNORECASE,
)

_WORD_RE = re.compile(r"[a-z]+")


def _normalise(text: str) -> str:
    """Strip, lowercase, and collapse whitespace."""
    return re.sub(r"\s+", " ", text.strip().lower())


def extract_label(response: str) -> str | None:
    """Return the first closed-vocabulary label in ``response``, if any.

    Returns ``None`` when the response contains no known label, so callers
    can fall back to strict matching instead of guessing.
    """
    stripped = _LEAD_INS.sub("", _normalise(response))
    for match in _WORD_RE.finditer(stripped):
        word = match.group(0)
        if word in _LABEL_VOCAB:
            return word
    return None


def score_response(
    response: str,
    expected: str,
    subset: str,
) -> tuple[bool, str]:
    """Score a model response against the expected answer.

    Args:
        response: Raw text returned by the model.
        expected: Ground-truth label from the task item.
        subset: Task subset name (currently unused; present for future dispatch).

    Returns:
        A tuple ``(is_correct, normalised_response)`` where
        ``normalised_response`` is the cleaned model output stored in the report.
    """
    norm_resp = _normalise(response)
    norm_exp = _normalise(expected)

    if not norm_resp:
        return False, norm_resp

    # Strategy 1 — exact match
    if norm_resp == norm_exp:
        return True, norm_resp

    # Strategy 2 — prefix match (response starts with expected label)
    if norm_resp.startswith(norm_exp):
        return True, norm_resp

    # Strategy 3 — expected label appears at the very start of the first word
    # (handles "true." "false." "yes." "no.")
    first_word = norm_resp.split()[0].rstrip(".,;:!?") if norm_resp else ""
    if first_word == norm_exp:
        return True, norm_resp

    # Strategy 4 — first-label extraction, only for closed-vocabulary tasks.
    if norm_exp in _LABEL_VOCAB:
        found = extract_label(norm_resp)
        if found is not None:
            return found == norm_exp, norm_resp

    return False, norm_resp
