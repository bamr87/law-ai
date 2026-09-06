"""Knowledge Graph Explorer API (spec 006 → spec 011 FR-9 port)."""

from __future__ import annotations

import logging
import time
from datetime import date
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Any
from collections.abc import AsyncIterator, Awaitable, Callable

from asgiref.sync import async_to_sync
from django.urls import path
from rest_framework.exceptions import APIException
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from law_ai.core.auth import RequireGraph
from law_ai.core.neo4j import graph_queries
from law_ai.core.neo4j.driver import get_neo4j_driver
from law_ai.core.provenance import provenance

if TYPE_CHECKING:  # pragma: no cover
    from neo4j import AsyncSession

logger = logging.getLogger("law_ai.graph")


@asynccontextmanager
async def _open_session() -> AsyncIterator[AsyncSession]:
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


async def _safe(
    name: str,
    fallback: dict[str, Any],
    coro_factory: Callable[[Any], Awaitable[dict[str, Any]]],
) -> dict[str, Any]:
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
    except Exception as exc:
        logger.warning("graph endpoint %s degraded: %s", name, exc)
        return _degraded(fallback)


class _Unprocessable(APIException):
    """422 for a malformed query parameter."""

    status_code = 422
    default_code = "unprocessable_entity"


def _bounded_int(raw: str | None, *, default: int, lo: int, hi: int) -> int:
    if raw is None:
        return default

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
    def get(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        async def _do(session: Any) -> dict[str, Any]:
            return await graph_queries.stats(session)

        return Response(
            async_to_sync(_safe)(
                "stats", {"cases": 0, "citations": 0, "cites_edges": 0}, _do
            )
        )


def _iso_date(raw: str | None, field: str) -> str:
    """Validate an optional ISO-8601 date filter (BL-20260429-23).

    Returned as the string it will be compared against in Cypher, since
    ``Case.decided_at`` is stored as an ISO string.
    """
    value = (raw or "").strip()
    if not value:
        return ""
    try:
        date.fromisoformat(value)
    except ValueError as exc:
        raise _Unprocessable({field: "must be an ISO-8601 date (YYYY-MM-DD)"}) from exc
    return value


class CasesView(_Base):
    def get(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        q = (request.query_params.get("q") or "")[:200]
        limit = _bounded_int(
            request.query_params.get("limit"), default=25, lo=1, hi=100
        )
        # Court values are free-form strings, so this is a substring filter
        # rather than an enum (BL-20260429-23).
        court = (request.query_params.get("court") or "").strip()[:200]
        decided_from = _iso_date(
            request.query_params.get("decided_from"), "decided_from"
        )
        decided_to = _iso_date(request.query_params.get("decided_to"), "decided_to")
        if decided_from and decided_to and decided_from > decided_to:
            raise _Unprocessable({"decided_from": "must not be after decided_to"})

        async def _do(session: Any) -> dict[str, Any]:
            items = await graph_queries.list_cases(
                session,
                q=q,
                limit=limit,
                court=court,
                decided_from=decided_from,
                decided_to=decided_to,
            )
            return {"cases": items, "count": len(items)}

        return Response(
            async_to_sync(_safe)("list_cases", {"cases": [], "count": 0}, _do)
        )


class NeighborhoodView(_Base):
    def get(
        self, request: Request, case_id: str, *args: Any, **kwargs: Any
    ) -> Response:
        case_id = case_id[:200]
        limit = _bounded_int(
            request.query_params.get("limit"), default=50, lo=1, hi=200
        )

        async def _do(session: Any) -> dict[str, Any]:
            return await graph_queries.neighborhood(session, case_id, limit=limit)

        return Response(
            async_to_sync(_safe)("neighborhood", {"nodes": [], "edges": []}, _do)
        )


class PathView(_Base):
    """``/api/graph/path?from=&to=&max_hops=`` — precedent chain between two cases.

    BL-20260429-22. Both ids are required and non-empty; ``max_hops`` is bounded
    so an unconnected pair can never trigger an unbounded traversal.
    """

    def get(self, request: Any, *args: Any, **kwargs: Any) -> Any:
        from_id = (request.query_params.get("from") or "").strip()[:200]
        to_id = (request.query_params.get("to") or "").strip()[:200]
        if not from_id or not to_id:
            raise _Unprocessable(
                {"from": "required", "to": "required"},
            )
        max_hops = _bounded_int(
            request.query_params.get("max_hops"),
            default=6,
            lo=1,
            hi=graph_queries.MAX_PATH_HOPS,
        )

        async def _do(session: Any) -> dict[str, Any]:
            return await graph_queries.shortest_path(
                session, from_id, to_id, max_hops=max_hops
            )

        return Response(
            async_to_sync(_safe)(
                "shortest_path",
                {"nodes": [], "edges": [], "found": False, "hops": 0},
                _do,
            )
        )


urlpatterns = [
    path("stats", StatsView.as_view(), name="graph-stats"),
    path("cases", CasesView.as_view(), name="graph-cases"),
    path("path", PathView.as_view(), name="graph-path"),
    path(
        "neighborhood/<str:case_id>",
        NeighborhoodView.as_view(),
        name="graph-neighborhood",
    ),
]
