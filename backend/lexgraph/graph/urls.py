"""Knowledge Graph Explorer API (spec 006 → spec 011 FR-9 port)."""
from __future__ import annotations

import logging
import time
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Any
from collections.abc import AsyncIterator

from asgiref.sync import async_to_sync
from django.urls import path
from rest_framework import status
from rest_framework.exceptions import APIException
from rest_framework.response import Response
from rest_framework.views import APIView

from lexgraph.core.auth import RequireGraph
from lexgraph.core.neo4j import graph_queries
from lexgraph.core.neo4j.driver import get_neo4j_driver
from lexgraph.core.provenance import provenance

if TYPE_CHECKING:  # pragma: no cover
    from neo4j import AsyncSession

logger = logging.getLogger("lexgraph.graph")


@asynccontextmanager
async def _open_session() -> AsyncIterator["AsyncSession"]:
    driver = get_neo4j_driver()
    async with driver.session() as session:
        yield session


def _degraded(payload: dict[str, Any]) -> dict[str, Any]:
    return {"available": False, **payload}


def _count_for(result: Any) -> int:
    if isinstance(result, dict):
        if "nodes" in result:
            return len(result["nodes"])
        if "cases" in result and isinstance(result["cases"], list):
            return len(result["cases"])
    return 1


async def _safe(name: str, fallback: dict[str, Any], coro_factory):  # noqa: ANN001
    started = time.perf_counter()
    try:
        async with _open_session() as session:
            result = await coro_factory(session)
        latency_ms = (time.perf_counter() - started) * 1000.0
        provenance.log_graph_query(
            cypher=f"graph_queries.{name}",
            params={},
            result_count=_count_for(result),
            latency_ms=latency_ms,
        )
        return {"available": True, **result}
    except Exception as exc:  # noqa: BLE001
        logger.warning("graph endpoint %s degraded: %s", name, exc)
        return _degraded(fallback)


def _bounded_int(raw: str | None, *, default: int, lo: int, hi: int) -> int:
    if raw is None:
        return default

    class _Unprocessable(APIException):
        status_code = 422
        default_code = "unprocessable_entity"

    try:
        value = int(raw)
    except ValueError as exc:
        raise _Unprocessable({"limit": "must be an integer"}) from exc
    if value < lo or value > hi:
        raise _Unprocessable({"limit": f"must be between {lo} and {hi}"})
    return value


class _Base(APIView):
    permission_classes = [RequireGraph]


class StatsView(_Base):
    def get(self, request, *args, **kwargs):  # noqa: ANN001
        async def _do(session: Any) -> dict[str, Any]:
            return await graph_queries.stats(session)

        return Response(
            async_to_sync(_safe)(
                "stats", {"cases": 0, "citations": 0, "cites_edges": 0}, _do
            )
        )


class CasesView(_Base):
    def get(self, request, *args, **kwargs):  # noqa: ANN001
        q = (request.query_params.get("q") or "")[:200]
        limit = _bounded_int(
            request.query_params.get("limit"), default=25, lo=1, hi=100
        )

        async def _do(session: Any) -> dict[str, Any]:
            items = await graph_queries.list_cases(session, q=q, limit=limit)
            return {"cases": items, "count": len(items)}

        return Response(async_to_sync(_safe)("list_cases", {"cases": [], "count": 0}, _do))


class NeighborhoodView(_Base):
    def get(self, request, case_id: str, *args, **kwargs):  # noqa: ANN001
        case_id = case_id[:200]
        limit = _bounded_int(
            request.query_params.get("limit"), default=50, lo=1, hi=200
        )

        async def _do(session: Any) -> dict[str, Any]:
            return await graph_queries.neighborhood(session, case_id, limit=limit)

        return Response(async_to_sync(_safe)("neighborhood", {"nodes": [], "edges": []}, _do))


urlpatterns = [
    path("stats", StatsView.as_view(), name="graph-stats"),
    path("cases", CasesView.as_view(), name="graph-cases"),
    path(
        "neighborhood/<str:case_id>",
        NeighborhoodView.as_view(),
        name="graph-neighborhood",
    ),
]
