"""Per-task scoring helpers for LegalBench (spec 018 T-002).

Scoring is deliberately task-agnostic:

* **Exact match after normalisation** — strip leading/trailing whitespace,
  lowercase, collapse internal whitespace. Covers boolean, short-answer,
  and label tasks (True/False, Yes/No, single-word categories).
* **Prefix match** — for tasks where the expected answer is a prefix of a
  longer model response (e.g. the model explains its reasoning after the
  short label).

Both strategies are applied. The item is marked correct if either passes.
More specialised strategies (BM25 recall, NLI entailment) are deferred to
BL-20260511-12 once the LegalBench dataset is cached and a baseline is
established.
"""

from __future__ import annotations

import re


def _normalise(text: str) -> str:
    """Strip, lowercase, and collapse whitespace."""
    return re.sub(r"\s+", " ", text.strip().lower())


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

    return False, norm_resp
