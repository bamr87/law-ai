from __future__ import annotations

from django.apps import AppConfig


class IngestionappConfig(AppConfig):
    name = "law_ai.ingestionapp"
    label = "ingestionapp"
    default_auto_field = "django.db.models.BigAutoField"
