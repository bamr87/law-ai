from __future__ import annotations

from django.apps import AppConfig


class AnalysisConfig(AppConfig):
    name = "lexgraph.analysis"
    label = "analysis"
    default_auto_field = "django.db.models.BigAutoField"
