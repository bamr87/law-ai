"""``manage.py ensure_checkpointer`` — isolate LangGraph checkpoint tables.

Spec 011 FR-13 + AC-6: the LangGraph PostgresSaver lives in its own
``langgraph`` schema so its tables never collide with Django migrations.
This command is idempotent.

BL-20260811-25: creating the schema was never enough — the saver's connection
carries ``options=-csearch_path=<schema>`` now, and this command runs
``setup()`` inside that schema instead of leaving it to happen lazily (in
``public``) on first workflow use.

BL-20260811-27: a broken ``POSTGRES_URL`` used to degrade silently until the
first analysis run. The failure is printed loudly here, and with
``LANGGRAPH_CHECKPOINTER_REQUIRED=true`` it aborts the boot chain instead.
"""

from __future__ import annotations

import asyncio

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
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
            self.style.SUCCESS(f"ensure_checkpointer: schema '{schema}' present.")
        )
        self._run_setup(schema)

    def _run_setup(self, schema: str) -> None:
        """Create the checkpoint tables *inside* the schema, or say why not."""
        from law_ai.agents_runtime.checkpointer import ensure_schema

        status = asyncio.run(ensure_schema())
        required = bool(getattr(settings, "LANGGRAPH_CHECKPOINTER_REQUIRED", False))
        if status.ok:
            style = self.style.SUCCESS if status.state == "ok" else self.style.WARNING
            self.stdout.write(
                style(
                    f"ensure_checkpointer: {status.state} — {status.detail} "
                    f"(search_path={schema})"
                )
            )
            return
        message = (
            f"ensure_checkpointer: FAILED to initialize the LangGraph "
            f"checkpointer — {status.detail}. LangGraph workflows will run "
            "without persistence until this is fixed."
        )
        self.stdout.write(self.style.ERROR(message))
        if required:
            raise CommandError(
                message + " (LANGGRAPH_CHECKPOINTER_REQUIRED=true — aborting boot)"
            )
