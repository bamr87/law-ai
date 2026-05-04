from __future__ import annotations

from django.apps import AppConfig


class GraphConfig(AppConfig):
    name = "lexgraph.graph"
    label = "graph"
    default_auto_field = "django.db.models.BigAutoField"
