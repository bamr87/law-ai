"""``/health`` endpoint port (spec 011 FR-9).

Tests monkeypatch :func:`get_neo4j_driver` and :func:`get_last_ingest_at`
on this module — keep them as top-level imports so the patches stick.
"""

from __future__ import annotations

import logging

from asgiref.sync import async_to_sync
from django.urls import path
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from lexgraph.core.neo4j.driver import get_neo4j_driver
from lexgraph.core.neo4j.queries import get_last_ingest_at

logger = logging.getLogger("lexgraph.health")


async def _last_ingest_iso() -> str | None:
    try:
        driver = get_neo4j_driver()
        async with driver.session() as session:
            stamp = await get_last_ingest_at(session)
            return stamp.isoformat() if stamp else None
    except Exception as exc:
        logger.warning("health: neo4j unavailable (%s)", exc)
        return None


class HealthView(APIView):
    permission_classes = [AllowAny]
    authentication_classes: list = []

    def get(self, request, *args, **kwargs):
        last_ingest_at = async_to_sync(_last_ingest_iso)()
        return Response(
            {
                "status": "healthy",
                "service": "lexgraph-backend",
                "version": "0.1.0",
                "last_ingest_at": last_ingest_at,
            }
        )


urlpatterns = [path("", HealthView.as_view(), name="health")]
