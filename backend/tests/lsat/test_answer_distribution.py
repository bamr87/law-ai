"""Answer-key distribution regression tests.

Guards against the bias that prompted spec work: the seed bank used to place
every correct answer on B or C (never D or E). These tests assert the bank's
keys stay spread across A-E and that the offline content-author fallback
rotates its placeholder key instead of always emitting "A".
"""

from __future__ import annotations

import collections

from law_ai.lsat.services.bank import load_bank

ALL_LABELS = {"A", "B", "C", "D", "E"}


def _distribution() -> collections.Counter[str]:
    return collections.Counter(q.correct for q in load_bank().values())


def test_every_label_is_used_as_a_correct_answer() -> None:
    """All five positions must appear — the original bug never used D or E."""
    used = set(_distribution())
    missing = ALL_LABELS - used
    assert not missing, f"these answer labels are never correct: {sorted(missing)}"


def test_no_single_label_dominates() -> None:
    """No position may exceed 40% of keys (uniform would be 20%)."""
    dist = _distribution()
    total = sum(dist.values())
    assert total > 0
    worst_label, worst_count = dist.most_common(1)[0]
    share = worst_count / total
    assert share <= 0.40, (
        f"label {worst_label!r} is the key for {share:.0%} of questions "
        f"(distribution: {dict(sorted(dist.items()))})"
    )


def test_bc_combined_share_is_reasonable() -> None:
    """B and C together must not swamp the bank (they were ~85% before)."""
    dist = _distribution()
    total = sum(dist.values())
    bc_share = (dist.get("B", 0) + dist.get("C", 0)) / total
    assert bc_share <= 0.50, (
        f"B/C account for {bc_share:.0%} of keys "
        f"(distribution: {dict(sorted(dist.items()))})"
    )


def test_per_section_uses_more_than_two_labels() -> None:
    """Each section must spread its keys across at least three positions."""
    by_section: dict[str, set[str]] = collections.defaultdict(set)
    for q in load_bank().values():
        by_section[q.section].add(q.correct)
    for section, labels in by_section.items():
        assert len(labels) >= 3, (
            f"section {section} only uses keys {sorted(labels)}; "
            "spread correct answers across more positions"
        )


def test_fallback_draft_rotates_answer_key() -> None:
    """Offline fallback drafts must not all collapse onto label 'A'."""
    from law_ai.agents_runtime.crews.lsat_content_author import (
        GenerateQuestionsInput,
        _fallback_draft,
    )

    inp = GenerateQuestionsInput(section="LR", difficulty="med", count=5)
    keys = [_fallback_draft(inp, i).correct for i in range(5)]
    assert keys == ["A", "B", "C", "D", "E"], keys
