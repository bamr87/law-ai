from __future__ import annotations

from django.apps import AppConfig


class AgentsRuntimeConfig(AppConfig):
    name = "lexgraph.agents_runtime"
    label = "agents_runtime"
    default_auto_field = "django.db.models.BigAutoField"
