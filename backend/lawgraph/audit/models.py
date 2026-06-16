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
    # Change-ledger linkage (WS4): groups every event of one agent session/cycle.
    # Populated from an event's ``session_id`` or (for autonomy events) ``cycle_id``.
    session_id = models.CharField(max_length=128, blank=True, default="", db_index=True)
    payload = models.JSONField(default=dict)

    class Meta:
        indexes = [
            models.Index(fields=["-timestamp"]),
            models.Index(fields=["session_id", "-timestamp"]),
        ]
        ordering = ["-timestamp"]

    def __str__(self) -> str:  # pragma: no cover
        return f"AuditEvent({self.kind}, {self.timestamp.isoformat()})"


class SessionRun(models.Model):
    """One row per agent work-session — the navigable change-ledger entry (WS4).

    Links a Claude Code / Copilot / Celery-autonomy session to the spec it
    claimed, the BACKLOG items it added, the PRs it opened, and (via
    ``session_id`` on :class:`AuditEvent`) its full provenance timeline.
    """

    SOURCE_CHOICES = [
        ("claude_code", "claude_code"),
        ("copilot", "copilot"),
        ("celery", "celery"),
        ("human", "human"),
        ("unknown", "unknown"),
    ]
    STATUS_CHOICES = [
        ("running", "running"),
        ("completed", "completed"),
        ("failed", "failed"),
        ("blocked", "blocked"),
        ("disabled", "disabled"),
    ]

    session_id = models.CharField(max_length=128, unique=True, db_index=True)
    agent_source = models.CharField(
        max_length=32, choices=SOURCE_CHOICES, default="unknown"
    )
    agent_name = models.CharField(max_length=128, blank=True, default="")
    kind = models.CharField(max_length=64, blank=True, default="", db_index=True)
    status = models.CharField(
        max_length=32, choices=STATUS_CHOICES, default="running", db_index=True
    )
    started_at = models.DateTimeField(auto_now_add=True, db_index=True)
    ended_at = models.DateTimeField(null=True, blank=True)
    root_trace_id = models.CharField(max_length=64, blank=True, default="")
    spec_claimed = models.CharField(max_length=128, blank=True, default="")
    backlog_items_added = models.JSONField(default=list)
    prs_created = models.JSONField(default=list)
    summary = models.TextField(blank=True, default="")
    metadata = models.JSONField(default=dict)

    class Meta:
        ordering = ["-started_at"]
        indexes = [
            models.Index(fields=["-started_at"]),
            models.Index(fields=["status", "-started_at"]),
        ]

    def __str__(self) -> str:  # pragma: no cover
        return f"SessionRun({self.session_id}, {self.agent_source}, {self.status})"
