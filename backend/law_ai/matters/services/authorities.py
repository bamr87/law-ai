"""A matter's verified authorities as a retrieval boost set (BL-20260817-05).

Research inside a matter is iterative: the first round surfaces candidate
authorities, a human verifies some of them, and the next round starts from
scratch — re-ranking the same corpus with no memory that three of those cases
were already checked and good. This module supplies that memory.

Two rules keep the boost honest (constitution P1-P5):

* **Only human-verified authorities boost.** An unverified candidate is a
  guess; promoting a guess would launder it into looking like a finding.
* **A boosted result is labelled.** ``GraphRAGRetriever`` records the boost
  count and its source on the coverage envelope, so a reader can see that the
  ranking was influenced by this matter rather than by the corpus alone.
"""

from __future__ import annotations

from typing import Any


def verified_authority_ids(matter: Any) -> set[str]:
    """Graph node ids a human has verified on this matter."""
    from law_ai.matters.models import MatterAuthority

    rows = MatterAuthority.objects.filter(
        matter=matter, verified_at__isnull=False, archived_at__isnull=True
    ).values_list("node_id", flat=True)
    return {str(node_id) for node_id in rows}


def boost_set_for_matter(matter_id: int | None) -> tuple[set[str], str]:
    """``(node ids, label)`` for a matter id, or an empty set when there is none.

    Returns the label the coverage envelope will carry so callers never invent
    their own wording for the same bias.
    """
    if not matter_id:
        return set(), ""
    from law_ai.matters.models import Matter

    matter = Matter.objects.filter(pk=matter_id, archived_at__isnull=True).first()
    if matter is None:
        return set(), ""
    return verified_authority_ids(matter), f"matter:{matter.slug}"


__all__ = ["boost_set_for_matter", "verified_authority_ids"]
