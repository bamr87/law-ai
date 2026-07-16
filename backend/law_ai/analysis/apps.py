from __future__ import annotations

from django.apps import AppConfig


class AnalysisConfig(AppConfig):
    name = "law_ai.analysis"
    label = "analysis"
    default_auto_field = "django.db.models.BigAutoField"
