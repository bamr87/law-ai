from __future__ import annotations

from django.apps import AppConfig


class IngestionappConfig(AppConfig):
    name = "lawgraph.ingestionapp"
    label = "ingestionapp"
    default_auto_field = "django.db.models.BigAutoField"
