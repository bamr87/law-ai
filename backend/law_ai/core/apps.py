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

# BL-20261112-01 (#221): the public development default from settings/base.py,
# and Django's own ``security.W009`` thresholds. ``law_ai.E002`` turns W009 into
# an error in production, where SECRET_KEY signs API access tokens
# (core/jwt_auth.py) and LSAT answer-shuffle tokens (lsat/services/shuffle.py).
DEFAULT_SECRET_KEY = "change-this-in-production-please"
SECRET_KEY_MIN_LENGTH = 50
SECRET_KEY_MIN_UNIQUE_CHARACTERS = 5
SECRET_KEY_INSECURE_PREFIX = "django-insecure-"


class CoreConfig(AppConfig):
    name = "law_ai.core"
    label = "core"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self) -> None:
        # BL-20261112-01 (#221): production must not boot on a guessable
        # SECRET_KEY or with ALLOWED_HOSTS=*. Deliberately above the once-guard:
        # it only reads settings, so repeating it costs nothing, and an
        # inherited LAWGRAPH_READY_ONCE must never switch it off.
        refuse_insecure_production_settings()

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


def _secret_key_weakness(secret_key: str) -> str | None:
    """Why ``secret_key`` is unfit to sign anything in production, or None.

    Django's ``security.W009`` rule, plus this repo's public default. The
    reason never quotes the key itself::

        >>> _secret_key_weakness(DEFAULT_SECRET_KEY)
        'is the public development default from settings/base.py'
        >>> _secret_key_weakness("ab" * 30)
        'has fewer than 5 unique characters'
    """
    if secret_key == DEFAULT_SECRET_KEY:
        return "is the public development default from settings/base.py"
    if len(secret_key) < SECRET_KEY_MIN_LENGTH:
        return f"is shorter than {SECRET_KEY_MIN_LENGTH} characters"
    if len(set(secret_key)) < SECRET_KEY_MIN_UNIQUE_CHARACTERS:
        return f"has fewer than {SECRET_KEY_MIN_UNIQUE_CHARACTERS} unique characters"
    if secret_key.startswith(SECRET_KEY_INSECURE_PREFIX):
        return f"starts with {SECRET_KEY_INSECURE_PREFIX!r}, a throwaway-key prefix"
    return None


@checks.register(Tags.security, deploy=True)
def check_secret_key_configured(
    app_configs: object = None, **kwargs: object
) -> list[checks.CheckMessage]:
    """``manage.py check --deploy`` fails on a guessable production SECRET_KEY.

    Django's own ``security.W009`` only warns, so ``check --deploy`` exited 0
    on the public default. Here the key signs API access tokens
    (``core/jwt_auth.py``) and the LSAT answer-shuffle tokens the grade path
    trusts (``lsat/services/shuffle.py``) on top of Django's own signing, so a
    public or guessable value lets anyone forge those signatures
    (BL-20261112-01, #221).

    Example: with ``ENVIRONMENT=production`` and ``SECRET_KEY`` left at the
    base default this returns ``[Error(id="law_ai.E002")]``; with a long random
    key, or in any other environment, it returns ``[]``.
    """
    from django.conf import settings

    if getattr(settings, "ENVIRONMENT", "development") != "production":
        return []
    try:
        secret_key = str(settings.SECRET_KEY)
    except ImproperlyConfigured:
        # Django refuses to hand out an empty SECRET_KEY at all.
        secret_key = ""
    weakness = _secret_key_weakness(secret_key)
    if weakness is None:
        return []
    return [
        checks.Error(
            f"SECRET_KEY {weakness}. It signs API access tokens, LSAT "
            "answer-shuffle tokens and Django's own signed values, so anyone "
            "who knows it can forge signatures the app trusts.",
            hint=(
                "Set SECRET_KEY in the production environment to a long random "
                "value, e.g. the output of `openssl rand -hex 32`."
            ),
            id="law_ai.E002",
        )
    ]


@checks.register(Tags.security, deploy=True)
def check_allowed_hosts_configured(
    app_configs: object = None, **kwargs: object
) -> list[checks.CheckMessage]:
    """``manage.py check --deploy`` fails when production accepts any Host.

    ``"*"`` in ``ALLOWED_HOSTS`` switches off Django's Host-header validation,
    so a forged ``Host`` reaches every absolute URL the app builds
    (BL-20261112-01, #221). Explicit names pass, subdomain wildcards such as
    ``.example.com`` included.

    Example: with ``ENVIRONMENT=production`` and ``ALLOWED_HOSTS`` left at the
    base default (``["*"]``) this returns ``[Error(id="law_ai.E003")]``; with
    ``["law-ai.example.com"]``, or in any other environment, it returns ``[]``.
    """
    from django.conf import settings

    if getattr(settings, "ENVIRONMENT", "development") != "production":
        return []
    if "*" not in getattr(settings, "ALLOWED_HOSTS", []):
        return []
    return [
        checks.Error(
            "ALLOWED_HOSTS contains '*', so production answers any Host header "
            "and builds absolute URLs from whatever a client sends.",
            hint=(
                "Set ALLOWED_HOSTS in the production environment to the "
                "deployment's own host names, comma-separated."
            ),
            id="law_ai.E003",
        )
    ]


def refuse_insecure_production_settings() -> None:
    """Refuse to boot production on a guessable SECRET_KEY or ALLOWED_HOSTS=*.

    The boot-time form of ``law_ai.E002`` and ``law_ai.E003``, run from
    ``CoreConfig.ready()`` so it stops every process that loads production
    settings: daphne, Celery and every management command, ``check --deploy``
    included, which therefore fails with the check id in its error. Outside
    production it does nothing, so the ``settings/base.py`` defaults still boot
    development and the test suite.

    Example: ``ENVIRONMENT=production`` with ``SECRET_KEY`` left at the base
    default raises ``ImproperlyConfigured("Refusing to start in production.
    law_ai.E002: SECRET_KEY is the public development default ...")``.
    """
    problems = [*check_secret_key_configured(), *check_allowed_hosts_configured()]
    if not problems:
        return
    details = " ".join(
        f"{problem.id}: {problem.msg}" + (f" {problem.hint}" if problem.hint else "")
        for problem in problems
    )
    raise ImproperlyConfigured(f"Refusing to start in production. {details}")
