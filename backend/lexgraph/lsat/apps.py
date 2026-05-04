from __future__ import annotations

from django.apps import AppConfig


class LsatConfig(AppConfig):
    name = "lexgraph.lsat"
    label = "lsat"
    default_auto_field = "django.db.models.BigAutoField"
