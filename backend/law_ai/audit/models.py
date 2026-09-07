"""Audit ORM model (spec 011 FR-6, NFR-AUDIT-1).

Replaces the JSONL-only audit store. The JSONL writer survives as a
Celery sink invoked when DB writes fail, preserving spec-003 forensic
continuity.
"""

from __future__ import annotations

from django.db import models


class AuditEvent(models.Model):
    """One row per provenance event."""

    KIND_HTTP = "http_request"
    KIND_AGENT = "agent_call"
    KIND_GRAPH = "graph_query"
    KIND_NODE = "langgraph_node"
    KIND_LSAT = "lsat_grade"
    #: One event per solve-guide step revealed (spec 045 FR-6, BL-20260830-13).
    #: Grade-time ``hints_used`` only ever said "assisted or not", and only for
    #: questions that were actually submitted.
    KIND_LSAT_HINT = "lsat_hint"
    #: One event per library article marked read or unread (BL-20260903-05).
    KIND_LSAT_ARTICLE_READ = "lsat_article_read"

    kind = models.CharField(max_length=64, db_index=True)
    timestamp = models.DateTimeField(auto_now_add=True, db_index=True)
    trace_id = models.CharField(max_length=64, blank=True, default="", db_index=True)
    agent_version = models.CharField(max_length=64, blank=True, default="")
    payload = models.JSONField(default=dict)

    class Meta:
        indexes = [
            models.Index(fields=["-timestamp"]),
        ]
        ordering = ["-timestamp"]

    def __str__(self) -> str:  # pragma: no cover
        return f"AuditEvent({self.kind}, {self.timestamp.isoformat()})"


class AutonomyRun(models.Model):
    """One row per autonomy cycle (BL-20260511-04).

    Cycles have always been recorded as ``autonomy_cycle.start`` /
    ``autonomy_cycle.end`` ``AuditEvent`` rows, and they still are — the audit
    layer is never bypassed (constitution §4). But a generic ``kind``/``payload``
    pair answers "what happened at 03:00" only by scanning JSON: the digest's
    single ``kind__startswith='autonomy_'`` window filter was the *only* query
    it could support, and the autonomy dashboard needs per-run rows it can
    order, filter and count.

    This table is the promoted, queryable projection of those events. It is
    written **best-effort**: :func:`law_ai.core.autonomy.run_cycle` logs and
    continues when the insert fails, so a Postgres outage degrades a report
    rather than killing a cycle — the same never-block contract
    ``compose_digest`` has.
    """

    STATUS_OK = "ok"
    STATUS_ERROR = "error"
    STATUS_DISABLED = "disabled"
    STATUS_REPLAYED = "replayed"

    #: The ``cycle_id`` shared with this run's provenance events, so a row and
    #: its audit trail are joinable without a scan.
    cycle_id = models.CharField(max_length=64, db_index=True)
    kind = models.CharField(max_length=64, db_index=True)
    source = models.CharField(max_length=128, blank=True, default="")
    trace_id = models.CharField(max_length=64, blank=True, default="")
    started_at = models.DateTimeField(db_index=True)
    ended_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=16, default=STATUS_OK, db_index=True)
    duration_ms = models.FloatField(null=True, blank=True)
    error = models.TextField(blank=True, default="")
    #: Structured cycle result: prs_opened, backlog_ids, quarantined,
    #: legalbench_delta, digest_path, … Free-form because each pillar reports
    #: different counts; the *columns* above are what queries sort on.
    summary = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = "autonomy_run"
        ordering = ["-started_at"]
        indexes = [
            models.Index(fields=["kind", "-started_at"]),
        ]

    def __str__(self) -> str:  # pragma: no cover
        return f"AutonomyRun({self.kind}, {self.status}, {self.cycle_id})"
