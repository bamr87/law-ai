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


def graph_labels_for(node_id: str) -> list[str] | None:
    """Labels of a candidate authority in the graph (BL-20260906-16).

    ``MatterAuthority.node_id`` was an unvalidated string, so an export bundle
    could point at an authority that is not in the corpus at all — a typo, or
    a node that was never ingested. This checks it against Neo4j.

    Returns ``[]`` when the graph is reachable and holds no such node, and
    ``None`` when the graph is *unreachable*: a Neo4j outage must degrade
    recording rather than block a reviewer, so the caller records the
    authority and says the check did not run.
    """
    from asgiref.sync import async_to_sync

    from law_ai.core.neo4j.driver import get_neo4j_driver
    from law_ai.core.neo4j.queries import authority_node_labels

    async def _run() -> list[str]:
        driver = get_neo4j_driver()
        async with driver.session() as session:
            return await authority_node_labels(session, node_id)

    try:
        return async_to_sync(_run)()
    except Exception:
        return None


__all__ = ["boost_set_for_matter", "graph_labels_for", "verified_authority_ids"]
