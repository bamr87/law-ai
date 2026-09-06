"""Library search parity with ``lsat-static/lib/search.ts`` (BL-20260903-06).

The static site mirrors the ranker by hand — same tokenizer, stemmer, synonym
table and weights — and nothing but a shared fixture keeps the two copies
honest. ``fixtures/search_parity.json`` is loaded here and by
``lsat-static/__tests__/search.test.ts``; a rule changed on one side and not
the other fails one of the two suites.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from law_ai.lsat.services import library as lib

FIXTURE = Path(__file__).parent / "fixtures" / "search_parity.json"


@pytest.fixture(scope="module")
def parity() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def test_stemmer_matches_the_fixture(parity: dict) -> None:
    got = {word: lib.stem(word) for word in parity["stems"]}
    assert got == parity["stems"]


def test_query_tokens_match_the_fixture(parity: dict) -> None:
    got = {q: lib.query_tokens(q) for q in parity["query_tokens"]}
    assert got == parity["query_tokens"]


def test_corpus_rankings_match_the_fixture(parity: dict) -> None:
    """Top hits over the *real* library — the same content the static site ships."""
    for case in parity["corpus"]:
        hits = lib.search_library(case["query"], limit=5)
        ids = [h["id"] for h in hits]
        if "ids" in case:
            assert ids[: len(case["ids"])] == case["ids"], case["query"]
        elif case["top"] is None:
            assert ids == [], case["query"]
        else:
            assert ids and ids[0] == case["top"], case["query"]


def test_score_vectors_match_the_fixture(parity: dict) -> None:
    """Scores and per-field vectors, not just the order (BL-20260905-52).

    Ranking parity hides arithmetic divergence: a weight, an occurrence cap or
    the half-weight typo fallback can change on one side alone and leave the
    order intact, so the two rankers would only be caught the day some article
    happened to straddle the difference. Pinning the number and the fields it
    came from fails the moment the two disagree about *how much* a hit is
    worth.
    """
    for case in parity["scores"]:
        hits = lib.search_library(case["query"], limit=len(case["hits"]))
        got = [
            {"id": h["id"], "score": h["score"], "matched_in": h["matched_in"]}
            for h in hits
        ]
        assert got == case["hits"], case["query"]


def test_typo_predicate_matches_the_fixture(parity: dict) -> None:
    for case in parity["typo_pairs"]:
        assert lib.is_typo(case["a"], case["b"]) is case["typo"], case
        assert lib.is_typo(case["b"], case["a"]) is case["typo"], case


def test_mistyped_corpus_queries_match_the_fixture(parity: dict) -> None:
    """A one-edit typo lands on the same article on both products."""
    for case in parity["corpus_typos"]:
        ids = [h["id"] for h in lib.search_library(case["query"], limit=5)]
        if case["top"] is None:
            assert ids == [], case["query"]
        else:
            assert ids and ids[0] == case["top"], case["query"]


def test_stemmer_is_idempotent(parity: dict) -> None:
    """Field words are stemmed once, query words once — the two must agree."""
    for word in parity["stems"]:
        once = lib.stem(word)
        assert lib.stem(once) == once, word
