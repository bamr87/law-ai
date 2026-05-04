"""``manage.py ensure_checkpointer`` — isolate LangGraph checkpoint tables.

Spec 011 FR-13 + AC-6: the LangGraph PostgresSaver lives in its own
``langgraph`` schema so its tables never collide with Django migrations.
This command is idempotent.
"""
from __future__ import annotations

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import connection


class Command(BaseCommand):
    help = "Create the langgraph schema and run PostgresSaver.setup() inside it."

    def handle(self, *args: object, **options: object) -> None:
        schema = getattr(settings, "LANGGRAPH_CHECKPOINTER_SCHEMA", "langgraph")
        backend = settings.DATABASES["default"]["ENGINE"]
        if "postgresql" not in backend:
            self.stdout.write(
                self.style.WARNING(
                    f"ensure_checkpointer: skipping (engine {backend} not Postgres)"
                )
            )
            return
        with connection.cursor() as cur:
            cur.execute(f'CREATE SCHEMA IF NOT EXISTS "{schema}"')
        self.stdout.write(
            self.style.SUCCESS(
                f"ensure_checkpointer: schema '{schema}' present "
                "(LangGraph PostgresSaver.setup() runs lazily on first use)."
            )
        )
