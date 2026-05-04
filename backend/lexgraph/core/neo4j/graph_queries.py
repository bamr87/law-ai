"""Read-only Cypher helpers for the Knowledge Graph Explorer (spec 006).

All functions take an ``AsyncSession`` and return plain dicts/lists ready
to JSON-serialise — no driver objects leak past this module.

NFR-SEC-1: every query uses parameter binding; user input is never
interpolated into Cypher strings.
NFR-PERF-1: every traversal is bounded by ``LIMIT $limit`` to keep the
worst-case neighborhood traversal under ~500 ms on a 10k-node graph.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # pragma: no cover - typing only
    from neo4j import AsyncSession


STATS_CYPHER = """
CALL {
  MATCH (c:Case) RETURN count(c) AS cases
}
CALL {
  MATCH (x:Citation) RETURN count(x) AS citations
}
CALL {
  MATCH (:Case)-[r:CITES]->(:Case) RETURN count(r) AS cites_edges
}
RETURN cases, citations, cites_edges
"""

LIST_CASES_CYPHER = """
MATCH (c:Case)
WHERE $q = '' OR toLower(c.title) CONTAINS toLower($q) OR c.id CONTAINS $q
RETURN c.id AS id,
       c.title AS title,
       c.court AS court,
       c.decided_at AS decided_at
ORDER BY c.title
LIMIT $limit
"""

NEIGHBORHOOD_CYPHER = """
MATCH (root:Case {id: $case_id})
OPTIONAL MATCH (root)-[hc:HAS_CITATION]->(cit:Citation)
WITH root, collect(DISTINCT {edge: hc, node: cit}) AS citations_raw
OPTIONAL MATCH (root)-[out:CITES]->(dst:Case)
WITH root, citations_raw, collect(DISTINCT {edge: out, node: dst}) AS out_raw
OPTIONAL MATCH (src:Case)-[inc:CITES]->(root)
WITH root, citations_raw, out_raw,
     collect(DISTINCT {edge: inc, node: src}) AS in_raw
RETURN root, citations_raw[0..$limit] AS citations,
       out_raw[0..$limit] AS outgoing,
       in_raw[0..$limit] AS incoming
"""


async def stats(session: AsyncSession) -> dict[str, int]:
    """Return total counts of ``Case``, ``Citation``, and ``CITES`` edges."""
    result = await session.run(STATS_CYPHER, {})
    record = await result.single()
    if record is None:
        return {"cases": 0, "citations": 0, "cites_edges": 0}
    return {
        "cases": int(record["cases"] or 0),
        "citations": int(record["citations"] or 0),
        "cites_edges": int(record["cites_edges"] or 0),
    }


async def list_cases(
    session: AsyncSession, q: str = "", limit: int = 25
) -> list[dict[str, Any]]:
    """Return up to ``limit`` cases whose title or id contains ``q``."""
    result = await session.run(LIST_CASES_CYPHER, {"q": q, "limit": limit})
    out: list[dict[str, Any]] = []
    async for record in result:
        out.append(
            {
                "id": record["id"],
                "title": record["title"],
                "court": record["court"],
                "decided_at": record["decided_at"],
            }
        )
    return out


def _case_node(c: Any) -> dict[str, Any]:
    """Cytoscape node for a ``Case`` mapping."""
    return {
        "data": {
            "id": c["id"],
            "label": c.get("title") or c["id"],
            "type": "Case",
            "court": c.get("court"),
        }
    }


def _citation_node(x: Any) -> dict[str, Any]:
    return {
        "data": {
            "id": f"cit:{x['normalized']}",
            "label": x.get("text") or x["normalized"],
            "type": "Citation",
        }
    }


async def neighborhood(
    session: AsyncSession, case_id: str, limit: int = 50
) -> dict[str, list[dict[str, Any]]]:
    """Return Cytoscape ``{nodes, edges}`` for the 1-hop neighborhood of a case."""
    result = await session.run(
        NEIGHBORHOOD_CYPHER, {"case_id": case_id, "limit": limit}
    )
    record = await result.single()
    if record is None or record["root"] is None:
        return {"nodes": [], "edges": []}

    root = record["root"]
    nodes: dict[str, dict[str, Any]] = {root["id"]: _case_node(root)}
    edges: list[dict[str, Any]] = []

    for entry in record["citations"] or []:
        node = entry["node"]
        if node is None:
            continue
        cit = _citation_node(node)
        nodes.setdefault(cit["data"]["id"], cit)
        edges.append(
            {
                "data": {
                    "id": f"hc:{root['id']}->{cit['data']['id']}",
                    "source": root["id"],
                    "target": cit["data"]["id"],
                    "type": "HAS_CITATION",
                }
            }
        )

    for entry in record["outgoing"] or []:
        node = entry["node"]
        if node is None:
            continue
        nodes.setdefault(node["id"], _case_node(node))
        edges.append(
            {
                "data": {
                    "id": f"cites:{root['id']}->{node['id']}",
                    "source": root["id"],
                    "target": node["id"],
                    "type": "CITES",
                }
            }
        )

    for entry in record["incoming"] or []:
        node = entry["node"]
        if node is None:
            continue
        nodes.setdefault(node["id"], _case_node(node))
        edges.append(
            {
                "data": {
                    "id": f"cites:{node['id']}->{root['id']}",
                    "source": node["id"],
                    "target": root["id"],
                    "type": "CITES",
                }
            }
        )

    return {"nodes": list(nodes.values()), "edges": edges}
