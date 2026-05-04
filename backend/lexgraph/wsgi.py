"""WSGI entrypoint (kept for tooling that does not understand ASGI).

Production deploys MUST use ``lexgraph.asgi:application`` via daphne.
"""
from __future__ import annotations

import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "lexgraph.settings.dev")

application = get_wsgi_application()
