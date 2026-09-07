from __future__ import annotations

from django.apps import AppConfig


class MattersConfig(AppConfig):
    name = "law_ai.matters"
    label = "matters"
    default_auto_field = "django.db.models.BigAutoField"
