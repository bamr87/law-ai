"""Core app config (spec 011 FR-10)."""

from __future__ import annotations

import logging
import os

from django.apps import AppConfig
from django.core import checks
from django.core.checks import Tags
from django.core.exceptions import (
    ImproperlyConfigured,
)

logger = logging.getLogger("law_ai")


class CoreConfig(AppConfig):
    name = "law_ai.core"
    label = "core"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self) -> None:
        # Guard against double-init under runserver --noreload, tests, and
        # gunicorn pre-fork (FR-10). The RUN_MAIN env var is set by the dev
        # autoreloader on the child process only.
        if os.environ.get("LAWGRAPH_READY_ONCE") == "1":
            return
        os.environ["LAWGRAPH_READY_ONCE"] = "1"

        # Spec 010 FR-1: register CrewAI/LangGraph agents.
        try:
            from law_ai.agents_runtime.registry import register_all_agents

            register_all_agents()
        except Exception as exc:  # pragma: no cover - log-only
            logger.warning("agents_runtime registry not initialised: %s", exc)

        # Spec 010 FR-4: OTEL → Phoenix exporter (no-op when env unset).
        try:
            from law_ai.core.telemetry import init_tracing

            init_tracing()
        except Exception as exc:  # pragma: no cover - log-only
            logger.warning("telemetry init skipped: %s", exc)

        # Spec 008/009 FR-5, run from ``AppConfig.ready`` since the spec-011
        # Django cutover: warn loudly outside development, and refuse to boot
        # in production (BL-20260430-12).
        warn_if_unprotected()


def unprotected_routers() -> list[str]:
    """Which feature routers currently have no key gating them at all.

    ``HasScope`` opens a route whenever its ``*_API_KEY`` setting is empty,
    regardless of ``ENVIRONMENT`` — so this list *is* the set of publicly
    readable routers.
    """
    from django.conf import settings

    agent = getattr(settings, "AGENT_API_KEY", None)
    unprotected: list[str] = []
    if not agent:
        unprotected.append("agents")
    for router, name in (
        ("analysis", "ANALYSIS_API_KEY"),
        ("graph", "GRAPH_API_KEY"),
        ("lsat", "LSAT_API_KEY"),
    ):
        if not (getattr(settings, name, None) or agent):
            unprotected.append(router)
    return unprotected


def warn_if_unprotected() -> None:
    """Warn outside development; refuse to start in production.

    BL-20260430-12: the old behaviour was a single WARNING even in
    production, which is exactly the deployment where nobody reads the log
    until it is too late — an unset ``AGENT_API_KEY`` leaves every gated
    router publicly readable (see docs/security.md, threat-model item 1).
    Staging and other non-development environments keep the warning: they are
    often deliberately open.
    """
    from django.conf import settings

    environment = getattr(settings, "ENVIRONMENT", "development")
    if environment == "development":
        return
    unprotected = unprotected_routers()
    if not unprotected:
        return
    routers = ",".join(unprotected)
    if environment == "production":
        raise ImproperlyConfigured(
            f"AGENT_API_KEY (or a per-router *_API_KEY) is required in "
            f"production; unprotected routers: /api/{{{routers}}}/*"
        )
    logger.warning(
        "AGENT_API_KEY not set — /api/{%s}/* is publicly readable",
        routers,
    )


@checks.register(Tags.security, deploy=True)
def check_api_keys_configured(
    app_configs: object = None, **kwargs: object
) -> list[checks.CheckMessage]:
    """``manage.py check --deploy`` fails when a router is left open.

    The boot-time raise covers a real start; this covers the pre-deploy check
    that prod.py's docstring already requires operators to run, so the mistake
    is caught before anything is running at all.
    """
    from django.conf import settings

    if getattr(settings, "ENVIRONMENT", "development") != "production":
        return []
    unprotected = unprotected_routers()
    if not unprotected:
        return []
    return [
        checks.Error(
            "AGENT_API_KEY (or a per-router *_API_KEY) is unset, leaving "
            f"/api/{{{','.join(unprotected)}}}/* publicly readable.",
            hint="Set AGENT_API_KEY in the production environment.",
            id="law_ai.E001",
        )
    ]
