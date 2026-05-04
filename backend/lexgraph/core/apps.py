"""Core app config (spec 011 FR-10)."""
from __future__ import annotations

import logging
import os

from django.apps import AppConfig

logger = logging.getLogger("lexgraph")


class CoreConfig(AppConfig):
    name = "lexgraph.core"
    label = "core"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self) -> None:
        # Guard against double-init under runserver --noreload, tests, and
        # gunicorn pre-fork (FR-10). The RUN_MAIN env var is set by the dev
        # autoreloader on the child process only.
        if os.environ.get("LEXGRAPH_READY_ONCE") == "1":
            return
        os.environ["LEXGRAPH_READY_ONCE"] = "1"

        # Spec 010 FR-1: register CrewAI/LangGraph agents.
        try:
            from lexgraph.agents_runtime.registry import register_all_agents

            register_all_agents()
        except Exception as exc:  # pragma: no cover - log-only
            logger.warning("agents_runtime registry not initialised: %s", exc)

        # Spec 010 FR-4: OTEL → Phoenix exporter (no-op when env unset).
        try:
            from lexgraph.core.telemetry import init_tracing

            init_tracing(None)
        except Exception as exc:  # pragma: no cover - log-only
            logger.warning("telemetry init skipped: %s", exc)

        # Spec 008/009 FR-5 (ported from app/main.py lifespan): warn loudly
        # if any feature router is unauthenticated outside of development.
        warn_if_unprotected()


def warn_if_unprotected() -> None:
    """Emit a single WARNING when running outside development without API keys."""
    from django.conf import settings

    if getattr(settings, "ENVIRONMENT", "development") == "development":
        return
    unprotected: list[str] = []
    if not getattr(settings, "AGENT_API_KEY", None):
        unprotected.append("agents")
    if not (
        getattr(settings, "ANALYSIS_API_KEY", None)
        or getattr(settings, "AGENT_API_KEY", None)
    ):
        unprotected.append("analysis")
    if not (
        getattr(settings, "GRAPH_API_KEY", None)
        or getattr(settings, "AGENT_API_KEY", None)
    ):
        unprotected.append("graph")
    if not (
        getattr(settings, "LSAT_API_KEY", None)
        or getattr(settings, "AGENT_API_KEY", None)
    ):
        unprotected.append("lsat")
    if unprotected:
        logger.warning(
            "AGENT_API_KEY not set — /api/{%s}/* is publicly readable",
            ",".join(unprotected),
        )
