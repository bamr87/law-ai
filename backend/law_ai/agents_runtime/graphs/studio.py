"""Entry point that loads :class:`LegalWorkflow` into a LangGraph host.

BL-20260502-01. The self-hosted ``langchain/langgraph-api`` server (compose
profile ``studio``, see ``backend/langgraph.json``) imports this module in a
bare Python process — no Django management command, no ASGI application — so
the app registry has to be populated *before* the workflow module is imported.
``law_ai.core.provenance`` writes ``AuditEvent`` rows and the retriever reads
Django settings, and both blow up with ``AppRegistryNotReady`` otherwise.

Nothing here is on the product runtime path: the API and the Celery worker
build their graphs through :class:`LegalWorkflow` directly. This module exists
only so a designer can step through the same graph visually.
"""

from __future__ import annotations

import os
from typing import Any


def _ensure_django() -> None:
    """Populate the Django app registry, idempotently.

    ``django.setup()`` is a no-op once the registry is ready, so importing
    this module from inside the test suite (where the harness already
    configured settings) costs nothing and changes nothing.
    """
    # django ships no py.typed marker; the repo's mypy config does not
    # blanket-ignore it, so the ignores are per-import here.
    import django
    from django.apps import apps

    if apps.ready:
        return
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "law_ai.settings.dev")
    django.setup()


def make_graph() -> Any:
    """Compiled graph for the LangGraph host to serve.

    No checkpointer: the LangGraph server owns thread persistence (it injects
    its own) and rejects a graph that arrives with one already attached. Runs
    started from Studio therefore live in the server's store, not in the
    ``LANGGRAPH_CHECKPOINTER=postgres`` tables the API uses.
    """
    _ensure_django()
    from law_ai.agents_runtime.graphs.legal_workflow import build_legal_workflow_graph

    return build_legal_workflow_graph()
