"""Read-only autonomy panels for the operator dashboard (BL-20260511-03).

Four questions an operator asks about a self-driving repo, none of which had
an answer outside a container shell before this module:

* **Is the benchmark moving?** — ``/api/agents/autonomy/legalbench-history``
  reads the append-only ``history.jsonl`` the eval harness writes.
* **Where is the code thinnest?** — ``/api/agents/autonomy/lowest-coverage``
  ranks ``coverage.xml`` ascending and returns the worst five.
* **What is waiting on a human?** — ``/api/agents/autonomy/recent-quarantine``
  returns the ten newest ``PendingReview`` rows.
* **Did the loop actually run?** — ``/api/agents/autonomy/runs`` returns the
  last N ``audit.AutonomyRun`` rows by kind, status and duration.

Every view is **read-only**: no LLM call, no graph write, no cycle trigger.
They sit behind the same ``RequireAgent`` gate as the rest of ``/api/agents/*``.

Absence is reported, never crashed (constitution §4). ``history.jsonl`` and
``coverage.xml`` are CI/container artifacts that legitimately do not exist on
a fresh checkout, and Postgres may be down; each view then returns its normal
envelope with an empty list and an ``available: false`` flag so the UI can say
"no data yet" instead of rendering a 500.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from django.urls import path
from rest_framework.exceptions import APIException
from rest_framework.response import Response
from rest_framework.views import APIView

from law_ai.core.auth import RequireAgent
from law_ai.core.throttling import ScopedActorRateThrottle

logger = logging.getLogger("law_ai.agentsapi.autonomy")


class _Base(APIView):
    """Same gate as the rest of ``/api/agents/*``.

    Declared here rather than imported from ``agentsapi.urls`` on purpose:
    that module appends these urlpatterns at the bottom of itself, and
    importing back out of it would make the pair circular.
    """

    permission_classes = [RequireAgent]
    # …and the same per-principal quota (BL-20260503-12 / BL-20260430-09):
    # these panels read the same audit store `/api/agents/runs` does.
    throttle_classes = [ScopedActorRateThrottle]
    throttle_scope = "audit"


class _Unprocessable(APIException):
    status_code = 422
    default_code = "unprocessable_entity"


def _parse_limit(raw: str | None, *, default: int, lo: int, hi: int) -> int:
    """Return ``int(raw)`` inside ``[lo, hi]`` or raise a 422.

    Mirrors ``agentsapi.urls._parse_int_strict``'s contract so `?limit=` means
    the same thing on every ``/api/agents/*`` endpoint.
    """
    if raw is None:
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise _Unprocessable({"limit": "must be an integer"}) from exc
    if value < lo or value > hi:
        raise _Unprocessable({"limit": f"must be between {lo} and {hi}"})
    return value


#: Panel sizes named by the backlog item: a sparkline, a top-5, a last-10.
HISTORY_DEFAULT = 20
HISTORY_MAX = 200
COVERAGE_LIMIT = 5
QUARANTINE_LIMIT = 10
#: Cycles per page for the runs panel (BL-20260906-23). Bounded like the
#: history panel: this reads a table an operator can grow without limit.
RUNS_DEFAULT = 20
RUNS_MAX = 200


def _read_history(limit: int) -> tuple[list[dict[str, Any]], bool]:
    """Return the newest ``limit`` eval rows (oldest first) + availability.

    Oldest-first is deliberate: the consumer draws a sparkline, and reversing
    a list in the browser to plot left-to-right is a bug waiting to happen.
    """
    from law_ai.eval.paths import HISTORY_PATH

    path_ = Path(HISTORY_PATH)
    if not path_.is_file():
        return [], False

    rows: list[dict[str, Any]] = []
    try:
        with path_.open("r", encoding="utf-8") as fh:
            for raw in fh:
                line = raw.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue  # a truncated write must not blank the panel
                if isinstance(row, dict):
                    rows.append(row)
    except OSError as exc:  # pragma: no cover - defensive
        logger.warning("legalbench history unreadable: %s", exc)
        return [], False

    return rows[-limit:], True


def _subset_series(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Pivot per-run accuracy maps into one series per subset.

    The file stores ``{"accuracies": {subset: acc}}`` per run; a sparkline
    needs the transpose. Runs that did not measure a subset contribute
    ``None`` so the x-axis stays aligned across series.
    """
    subsets: list[str] = []
    for row in rows:
        acc = row.get("accuracies")
        if isinstance(acc, dict):
            for name in acc:
                if name not in subsets:
                    subsets.append(name)

    series: list[dict[str, Any]] = []
    for name in sorted(subsets):
        points: list[float | None] = []
        for row in rows:
            acc = row.get("accuracies")
            value = acc.get(name) if isinstance(acc, dict) else None
            points.append(float(value) if isinstance(value, (int, float)) else None)
        measured = [p for p in points if p is not None]
        series.append(
            {
                "subset": name,
                "points": points,
                "latest": measured[-1] if measured else None,
                "delta_pp": (
                    round((measured[-1] - measured[0]) * 100.0, 2)
                    if len(measured) >= 2
                    else None
                ),
            }
        )
    return series


class AutonomyLegalbenchHistoryView(_Base):
    """Accuracy over time, one series per LegalBench subset."""

    def get(self, request, *args, **kwargs):  # type: ignore[no-untyped-def]
        limit = _parse_limit(
            request.query_params.get("limit"),
            default=HISTORY_DEFAULT,
            lo=1,
            hi=HISTORY_MAX,
        )
        rows, available = _read_history(limit)
        return Response(
            {
                "available": available,
                "runs": [
                    {
                        "run_id": r.get("run_id"),
                        "timestamp": r.get("timestamp"),
                        "model": r.get("model"),
                        "accuracies": r.get("accuracies") or {},
                    }
                    for r in rows
                ],
                "series": _subset_series(rows),
                "count": len(rows),
            }
        )


class AutonomyCoverageView(_Base):
    """The five thinnest-tested modules — the autonomy test pillar's targets."""

    def get(self, request, *args, **kwargs):  # type: ignore[no-untyped-def]
        from law_ai.eval.coverage_audit import (
            COVERAGE_ERROR_THRESHOLD,
            COVERAGE_WARN_THRESHOLD,
            load_coverage_report,
        )

        try:
            records = load_coverage_report()
        except Exception as exc:  # pragma: no cover - parser already degrades
            logger.warning("coverage report unreadable: %s", exc)
            records = []

        modules = [
            {
                "module": rec.module,
                "pct": round(rec.pct, 2),
                "severity": rec.severity,
                "missing_lines": rec.missing_lines[:20],
            }
            for rec in records[:COVERAGE_LIMIT]
        ]
        return Response(
            {
                "available": bool(records),
                "modules": modules,
                "count": len(modules),
                "warn_threshold": COVERAGE_WARN_THRESHOLD,
                "error_threshold": COVERAGE_ERROR_THRESHOLD,
            }
        )


class AutonomyRunsView(_Base):
    """The last N autonomy cycles: kind, status, duration (BL-20260906-23).

    ``audit.AutonomyRun`` existed with a composite ``(kind, -started_at)``
    index and exactly one consumer — ``compose_digest``, which reads a single
    24-hour window. So "did the nightly run, and how did it end" was a question
    only a container shell could answer. This is that query, and ``?kind=`` is
    the index's first column rather than a filter bolted on after the fact.

    Read-only and never fatal: Postgres being down returns the empty envelope
    with ``available: false``, like every other panel in this module.
    """

    def get(self, request, *args, **kwargs):  # type: ignore[no-untyped-def]
        limit = _parse_limit(
            request.query_params.get("limit"),
            default=RUNS_DEFAULT,
            lo=1,
            hi=RUNS_MAX,
        )
        kind = (request.query_params.get("kind") or "").strip()
        try:
            from law_ai.audit.models import AutonomyRun

            query = AutonomyRun.objects.all()
            if kind:
                query = query.filter(kind=kind)
            rows = list(query.order_by("-started_at")[:limit])
            available = True
        except Exception as exc:
            logger.warning("autonomy runs unavailable: %s", exc)
            rows, available = [], False

        runs = [
            {
                "cycle_id": row.cycle_id,
                "kind": row.kind,
                "source": row.source,
                "trace_id": row.trace_id,
                "status": row.status,
                "started_at": row.started_at.isoformat() if row.started_at else None,
                "ended_at": row.ended_at.isoformat() if row.ended_at else None,
                "duration_ms": row.duration_ms,
                # Truncated: an error panel is a signal, not a log viewer.
                "error": (row.error or "")[:300],
                "summary": row.summary or {},
            }
            for row in rows
        ]
        # `runs` holds mixed value types, so mypy infers a union for every
        # read; the status is always a model CharField, hence the narrowing.
        by_status: dict[str, int] = {}
        for run in runs:
            status = str(run["status"])
            by_status[status] = by_status.get(status, 0) + 1
        return Response(
            {
                "available": available,
                "runs": runs,
                "count": len(runs),
                "kind": kind,
                "by_status": by_status,
            }
        )


class AutonomyQuarantineView(_Base):
    """The ten newest quarantined documents still waiting on a human (§5)."""

    def get(self, request, *args, **kwargs):  # type: ignore[no-untyped-def]
        try:
            from law_ai.ingestionapp.models import PendingReview

            rows = list(
                PendingReview.objects.order_by("-created_at")[:QUARANTINE_LIMIT]
            )
            available = True
        except Exception as exc:
            logger.warning("quarantine queue unavailable: %s", exc)
            rows, available = [], False

        docs = [
            {
                "id": row.id,
                "source": row.source,
                "kind": row.kind,
                "confidence": row.confidence,
                "reason": row.reason,
                "created_at": row.created_at.isoformat() if row.created_at else None,
                "reviewed": row.reviewed_at is not None,
                "approved": row.approved,
            }
            for row in rows
        ]
        return Response({"available": available, "documents": docs, "count": len(docs)})


urlpatterns = [
    path(
        "autonomy/legalbench-history",
        AutonomyLegalbenchHistoryView.as_view(),
        name="agents-autonomy-legalbench-history",
    ),
    path(
        "autonomy/lowest-coverage",
        AutonomyCoverageView.as_view(),
        name="agents-autonomy-lowest-coverage",
    ),
    path(
        "autonomy/runs",
        AutonomyRunsView.as_view(),
        name="agents-autonomy-runs",
    ),
    path(
        "autonomy/recent-quarantine",
        AutonomyQuarantineView.as_view(),
        name="agents-autonomy-recent-quarantine",
    ),
]
