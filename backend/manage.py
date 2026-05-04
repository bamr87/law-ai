#!/usr/bin/env python
"""Django's command-line utility for administrative tasks.

Spec 011 (ADR 0001): replaces the FastAPI/uvicorn entrypoint at
``backend/app/main.py``. Run ``python manage.py runserver 0.0.0.0:8000`` for
the dev server (daphne is the prod ASGI server).
"""
from __future__ import annotations

import os
import sys


def main() -> None:
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "lexgraph.settings.dev")
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:  # pragma: no cover
        raise ImportError(
            "Couldn't import Django. Make sure it's installed and available on "
            "PYTHONPATH (run `pip install -e \".[dev]\"` from backend/)."
        ) from exc
    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
