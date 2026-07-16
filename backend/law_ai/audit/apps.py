from __future__ import annotations

from django.apps import AppConfig


class AuditConfig(AppConfig):
    name = "law_ai.audit"
    label = "audit"
    default_auto_field = "django.db.models.BigAutoField"
