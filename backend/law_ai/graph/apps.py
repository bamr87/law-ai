from __future__ import annotations

from django.apps import AppConfig


class GraphConfig(AppConfig):
    name = "law_ai.graph"
    label = "graph"
    default_auto_field = "django.db.models.BigAutoField"
