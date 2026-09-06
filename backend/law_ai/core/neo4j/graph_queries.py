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

# Case picker feed. Every filter is optional and empty-string-disabled so the
# statement stays a single plan-cacheable query (BL-20260429-23). `decided_at`
# is stored as an ISO-8601 string, so lexical >= / <= is a date comparison.
LIST_CASES_CYPHER = """
MATCH (c:Case)
WHERE c.archived_at IS NULL
  AND ($q = '' OR toLower(c.title) CONTAINS toLower($q) OR c.id CONTAINS $q)
  AND ($court = '' OR toLower(coalesce(c.court, '')) CONTAINS toLower($court))
  AND ($decided_from = '' OR coalesce(c.decided_at, '') >= $decided_from)
  AND ($decided_to = '' OR (c.decided_at IS NOT NULL
                            AND c.decided_at <= $decided_to))
RETURN c.id AS id,
       c.title AS title,
       c.court AS court,
       c.decided_at AS decided_at,
       c.source AS source,
       c.source_url AS source_url,
       c.confidence AS confidence
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
    session: AsyncSession,
    q: str = "",
    limit: int = 25,
    *,
    court: str = "",
    decided_from: str = "",
    decided_to: str = "",
) -> list[dict[str, Any]]:
    """Return up to ``limit`` cases matching the picker's filters.

    ``q`` matches title or id; ``court`` is a case-insensitive substring
    (court values are free-form strings, not an enum); ``decided_from`` /
    ``decided_to`` are inclusive ISO-8601 dates. An empty string disables the
    filter it belongs to. All five are parameter-bound (NFR-SEC-1).
    """
    result = await session.run(
        LIST_CASES_CYPHER,
        {
            "q": q,
            "limit": limit,
            "court": court,
            "decided_from": decided_from,
            "decided_to": decided_to,
        },
    )
    out: list[dict[str, Any]] = []
    async for record in result:
        out.append(
            {
                "id": record["id"],
                "title": record["title"],
                "court": record["court"],
                "decided_at": record["decided_at"],
                "source": record["source"],
                "source_url": record["source_url"],
                "confidence": record["confidence"],
            }
        )
    return out


def _case_node(c: Any) -> dict[str, Any]:
    """Cytoscape node for a ``Case`` mapping.

    Carries the full provenance-bearing property set (BL-20260429-23) so the
    sidebar inspector can show what the graph actually knows about a node
    without a second round-trip. Absent properties come back as ``None``
    rather than being omitted, so the client renders a stable key list.
    """
    return {
        "data": {
            "id": c["id"],
            "label": c.get("title") or c["id"],
            "type": "Case",
            "title": c.get("title"),
            "court": c.get("court"),
            "decided_at": c.get("decided_at"),
            "source": c.get("source"),
            "source_url": c.get("source_url"),
            "confidence": c.get("confidence"),
            "ingest_timestamp": c.get("ingest_timestamp"),
            "agent_version": c.get("agent_version"),
        }
    }


def _citation_node(x: Any) -> dict[str, Any]:
    return {
        "data": {
            "id": f"cit:{x['normalized']}",
            "label": x.get("text") or x["normalized"],
            "type": "Citation",
            "normalized": x["normalized"],
            "text": x.get("text"),
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


# ---------------------------------------------------------------------------
# Precedent chains (BL-20260429-22)
# ---------------------------------------------------------------------------

# ``shortestPath`` needs its upper bound written into the pattern — Neo4j does
# not accept a parameter there — so ``max_hops`` is validated to a small int by
# :func:`shortest_path` before it reaches this template. Every other value is
# still parameter-bound (NFR-SEC-1). The relationship is matched in both
# directions: a precedent chain between two cases is rarely one-way, and the
# caller only wants to know that the two are connected by citation.
SHORTEST_PATH_CYPHER = """
MATCH (a:Case {{id: $from_id}})
MATCH (b:Case {{id: $to_id}})
WHERE a.archived_at IS NULL AND b.archived_at IS NULL
MATCH p = shortestPath((a)-[:CITES*..{max_hops}]-(b))
RETURN [n IN nodes(p) | n] AS path_nodes,
       [r IN relationships(p) |
         {{src: startNode(r).id, dst: endNode(r).id}}] AS path_rels
"""

MAX_PATH_HOPS = 10


async def shortest_path(
    session: AsyncSession, from_id: str, to_id: str, max_hops: int = 6
) -> dict[str, Any]:
    """Return the shortest ``CITES`` chain between two cases, Cytoscape-shaped.

    The payload matches :func:`neighborhood` (``{"nodes", "edges"}``) so the
    viewer can render it with the same code path, plus ``found`` and ``hops``
    so the UI can say "no chain within N hops" instead of drawing nothing.
    Every node and edge carries ``on_path: True``; the front end uses that to
    style the chain.

    NFR-PERF-1: bounded by ``max_hops`` (clamped to ``MAX_PATH_HOPS``) so an
    unconnected pair can never trigger an unbounded traversal.
    """
    hops = max(1, min(int(max_hops), MAX_PATH_HOPS))
    empty: dict[str, Any] = {"nodes": [], "edges": [], "found": False, "hops": 0}

    if from_id == to_id:
        # A case is trivially its own precedent chain; skip the traversal.
        result = await session.run(
            "MATCH (c:Case {id: $id}) WHERE c.archived_at IS NULL RETURN c",
            {"id": from_id},
        )
        record = await result.single()
        if record is None or record["c"] is None:
            return empty
        node = _case_node(record["c"])
        node["data"]["on_path"] = True
        return {"nodes": [node], "edges": [], "found": True, "hops": 0}

    result = await session.run(
        SHORTEST_PATH_CYPHER.format(max_hops=hops),
        {"from_id": from_id, "to_id": to_id},
    )
    record = await result.single()
    if record is None or not record["path_nodes"]:
        return empty

    nodes: list[dict[str, Any]] = []
    for raw in record["path_nodes"]:
        node = _case_node(raw)
        node["data"]["on_path"] = True
        nodes.append(node)

    edges: list[dict[str, Any]] = []
    for rel in record["path_rels"] or []:
        edges.append(
            {
                "data": {
                    "id": f"cites:{rel['src']}->{rel['dst']}",
                    "source": rel["src"],
                    "target": rel["dst"],
                    "type": "CITES",
                    "on_path": True,
                }
            }
        )

    return {"nodes": nodes, "edges": edges, "found": True, "hops": len(edges)}
