"""Per-task scoring helpers for LegalBench (spec 018 T-002, spec 031, BL-20260811-11).

Scoring dispatches on the subset (:data:`SCORERS`, :func:`get_scorer`); the
name of the rule that produced a number is recorded on every report row. The
default rule below is the floor every subset falls back to, and the per-task
scorers at the bottom of this module are the ceiling for the two subsets the
floor systematically mis-scores.

The default rule is deliberately task-agnostic:

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

import math
import re
from collections.abc import Callable, Sequence

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


def score_default(
    response: str,
    expected: str,
    corpus: Sequence[str] | None = None,
) -> tuple[bool, str]:
    """Task-agnostic matcher: exact / prefix / first-word / closed-vocab label.

    This is the floor every subset falls back to. ``corpus`` is accepted (and
    ignored) so every scorer shares one signature.

    Examples:
        >>> score_default("The answer is True.", "True")
        (True, 'the answer is true.')
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


# ---------------------------------------------------------------------------
# Per-task scorers (BL-20260811-11)
#
# The task-agnostic matcher above is a floor, not a ceiling. Two subsets are
# systematically mis-scored by it:
#
# * ``precedent_retrieval`` — ``citation_prediction_open`` answers are free-text
#   case names ("International Shoe Co. v. Washington"). Exact/prefix matching
#   marks "The best citation is Int'l Shoe Co. v. Washington." wrong, which
#   makes the subset look broken rather than measured.
# * ``contract_nli`` — LegalBench's contract-NLI tasks answer Yes/No while the
#   NLI literature (and our label vocabulary) speaks entailment/contradiction.
#   A model that answers "Entailment" to a "Yes" key is right, not wrong.
# ---------------------------------------------------------------------------

#: Yes/No <-> entailment vocabulary, normalised both ways.
_ENTAILMENT_SYNONYMS: dict[str, str] = {
    "yes": "entailment",
    "true": "entailment",
    "entailment": "entailment",
    "entailed": "entailment",
    "no": "contradiction",
    "false": "contradiction",
    "contradiction": "contradiction",
    "contradicted": "contradiction",
    "neutral": "neutral",
    "not mentioned": "neutral",
}

#: Corporate suffixes and reporter noise dropped from a case name before
#: comparison — "Co.", "Inc." and friends carry no discriminating signal.
_CASE_NOISE: frozenset[str] = frozenset(
    {
        "v",
        "vs",
        "co",
        "corp",
        "inc",
        "llc",
        "lp",
        "ltd",
        "company",
        "the",
        "of",
        "in",
        "re",
        "et",
        "al",
    }
)

#: Fraction of an expected case name's distinctive tokens that must appear in
#: the response when no candidate pool is available. Deliberately high: a low
#: threshold turns "some case about shoes" into a hit and inflates the subset.
RECALL_THRESHOLD = 0.6

_CASE_TOKEN_RE = re.compile(r"[a-z0-9']+")


def tokenise_case_name(text: str) -> list[str]:
    """Tokens of a case name with punctuation, ``v.`` and corporate noise removed.

    Examples:
        >>> tokenise_case_name("International Shoe Co. v. Washington")
        ['international', 'shoe', 'washington']
    """
    words = _CASE_TOKEN_RE.findall(_normalise(text).replace(".", " "))
    return [word for word in words if word not in _CASE_NOISE and len(word) > 1]


class BM25:
    """Minimal Okapi BM25 ranker over a small in-memory candidate pool.

    Deliberately stdlib-only: adding ``rank-bm25`` to the backend image for
    forty lines of arithmetic would cost every developer an image rebuild.

    Examples:
        >>> ranker = BM25([["international", "shoe"], ["erie", "tompkins"]])
        >>> ranker.rank(["shoe", "international"])[0]
        0
    """

    def __init__(
        self, docs: Sequence[Sequence[str]], *, k1: float = 1.5, b: float = 0.75
    ) -> None:
        self.docs = [list(doc) for doc in docs]
        self.k1 = k1
        self.b = b
        self.avgdl = (
            sum(len(doc) for doc in self.docs) / len(self.docs) if self.docs else 0.0
        )
        self.df: dict[str, int] = {}
        for doc in self.docs:
            for term in set(doc):
                self.df[term] = self.df.get(term, 0) + 1

    def _idf(self, term: str) -> float:
        n = len(self.docs)
        df = self.df.get(term, 0)
        return math.log(1 + (n - df + 0.5) / (df + 0.5))

    def scores(self, query: Sequence[str]) -> list[float]:
        """BM25 score of every document against ``query``."""
        out: list[float] = []
        for doc in self.docs:
            length = len(doc) or 1
            score = 0.0
            for term in set(query):
                freq = doc.count(term)
                if not freq:
                    continue
                denom = freq + self.k1 * (1 - self.b + self.b * length / self.avgdl)
                score += self._idf(term) * freq * (self.k1 + 1) / denom
            out.append(score)
        return out

    def rank(self, query: Sequence[str]) -> list[int]:
        """Document indices ordered best-first (ties keep pool order)."""
        scored = self.scores(query)
        return sorted(range(len(scored)), key=lambda i: (-scored[i], i))


def score_precedent(
    response: str,
    expected: str,
    corpus: Sequence[str] | None = None,
) -> tuple[bool, str]:
    """Score a retrieval answer: BM25 recall@1 over the pool, else token recall.

    ``citation_prediction_classification`` answers Yes/No and falls through to
    the default matcher; ``citation_prediction_open`` answers a case name, and
    that is what BM25 handles: rank every candidate answer in the subset
    against the model's response and require the true one to come first. With
    no pool to rank against, fall back to token recall of the expected name.

    Examples:
        >>> ok, _ = score_precedent(
        ...     "The best citation is Int'l Shoe Co. v. Washington.",
        ...     "International Shoe Co. v. Washington",
        ... )
        >>> ok
        True
    """
    correct, norm_resp = score_default(response, expected)
    if correct or _normalise(expected) in _LABEL_VOCAB:
        return correct, norm_resp

    expected_tokens = tokenise_case_name(expected)
    if not expected_tokens or not norm_resp:
        return False, norm_resp

    response_tokens = tokenise_case_name(response)
    candidates = [c for c in (corpus or []) if _normalise(c) != ""]
    if candidates:
        ranker = BM25([tokenise_case_name(c) for c in candidates])
        best = ranker.rank(response_tokens)[0]
        if ranker.scores(response_tokens)[best] <= 0.0:
            return False, norm_resp
        return _normalise(candidates[best]) == _normalise(expected), norm_resp

    present = sum(1 for token in expected_tokens if token in response_tokens)
    return present / len(expected_tokens) >= RECALL_THRESHOLD, norm_resp


def score_entailment(
    response: str,
    expected: str,
    corpus: Sequence[str] | None = None,
) -> tuple[bool, str]:
    """Score contract-NLI by entailment class rather than by surface label.

    Examples:
        >>> ok, _ = score_entailment("Entailment", "Yes")
        >>> ok
        True
        >>> ok, _ = score_entailment("No", "Contradiction")
        >>> ok
        True
    """
    norm_resp = _normalise(response)
    expected_class = _ENTAILMENT_SYNONYMS.get(_normalise(expected))
    if expected_class is None:
        return score_default(response, expected)

    found = extract_label(norm_resp)
    if found is not None:
        return _ENTAILMENT_SYNONYMS.get(found) == expected_class, norm_resp
    return score_default(response, expected)


Scorer = Callable[[str, str, Sequence[str] | None], tuple[bool, str]]

#: Subset -> (scorer name, scorer). Recorded on every report row so a number
#: always says which rule produced it; a scorer change is a baseline reset.
SCORERS: dict[str, tuple[str, Scorer]] = {
    "precedent_retrieval": ("bm25_recall@1", score_precedent),
    "contract_nli": ("entailment_class", score_entailment),
}

_DEFAULT_SCORER: tuple[str, Scorer] = ("default_match", score_default)


def get_scorer(subset: str) -> tuple[str, Scorer]:
    """Return ``(name, scorer)`` for ``subset``, defaulting to the floor matcher."""
    return SCORERS.get(subset, _DEFAULT_SCORER)


def scorer_name(subset: str) -> str:
    """Name of the scoring rule applied to ``subset``.

    Examples:
        >>> scorer_name("precedent_retrieval")
        'bm25_recall@1'
        >>> scorer_name("core_reasoning")
        'default_match'
    """
    return get_scorer(subset)[0]


def score_response(
    response: str,
    expected: str,
    subset: str,
    *,
    corpus: Sequence[str] | None = None,
) -> tuple[bool, str]:
    """Score a model response against the expected answer for ``subset``.

    Args:
        response: Raw text returned by the model.
        expected: Ground-truth label from the task item.
        subset: Task subset name — selects the scorer (see :data:`SCORERS`).
        corpus: Every expected answer in the subset, when the scorer ranks
            candidates (``precedent_retrieval``). Optional everywhere else.

    Returns:
        A tuple ``(is_correct, normalised_response)`` where
        ``normalised_response`` is the cleaned model output stored in the report.

    Examples:
        >>> score_response("Yes", "Entailment", "contract_nli")[0]
        True
    """
    _, scorer = get_scorer(subset)
    return scorer(response, expected, corpus)
