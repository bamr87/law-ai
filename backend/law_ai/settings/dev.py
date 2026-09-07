"""Development settings — local docker compose default."""

from __future__ import annotations

from .base import *  # noqa: F403

DEBUG = True
ENVIRONMENT = "development"
ALLOWED_HOSTS = ["*"]

# BL-20260811-07: dev/prod parity for the audit DB leg. Dev runs eager Celery
# in some flows, where the ORM would otherwise be skipped on every async agent
# path and `AuditEvent` would stay empty while prod filled up.
AUDIT_DB_THREAD_OFFLOAD = True
