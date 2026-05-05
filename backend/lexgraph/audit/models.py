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
