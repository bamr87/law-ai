"""Base Django settings for LexGraph AI (spec 011 FR-3, FR-5).

Mirrors every env knob from the legacy ``app.core.config.Settings`` so that
relocated framework-agnostic modules see the same values via
``lexgraph.core.settings_proxy``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import environ

BASE_DIR = Path(__file__).resolve().parent.parent.parent

env = environ.Env(
    DEBUG=(bool, False),
    ENVIRONMENT=(str, "development"),
    SECRET_KEY=(str, "change-this-in-production-please"),
    ALLOWED_HOSTS=(list, ["*"]),
    APP_NAME=(str, "LexGraph AI"),
    # LLM
    OLLAMA_BASE_URL=(str, "http://ollama:11434"),
    DEFAULT_MODEL=(str, "llama3.1:70b-q4_K_M"),
    FALLBACK_MODEL=(str, "mistral:7b-instruct-q4_K_M"),
    OLLAMA_DEFAULT_MODEL=(str, "mistral:7b-instruct-q4_K_M"),
    OLLAMA_REQUEST_TIMEOUT_S=(float, 120.0),
    LANGGRAPH_CHECKPOINTER=(str, "postgres"),
    LANGGRAPH_CHECKPOINTER_SCHEMA=(str, "langgraph"),
    PHOENIX_COLLECTOR_ENDPOINT=(str, ""),
    PHOENIX_UI_URL=(str, "http://localhost:6006"),
    PHOENIX_PROJECT_NAME=(str, "lexgraph"),
    # Databases
    POSTGRES_URL=(
        str,
        "postgresql+asyncpg://lexgraph:lexgraph-dev@postgres:5432/lexgraph",
    ),
    DATABASE_URL=(str, ""),  # Django ORM (sync_psycopg form)
    NEO4J_URI=(str, "bolt://neo4j:7687"),
    NEO4J_USER=(str, "neo4j"),
    NEO4J_PASSWORD=(str, "lexgraph-dev"),
    REDIS_URL=(str, "redis://redis:6379/0"),
    # External
    COURTLISTENER_API_KEY=(str, ""),
    RECAP_EMAIL=(str, ""),
    RECAP_PASSWORD=(str, ""),
    # Feature flags
    ENABLE_LEGALBENCH_EVAL=(bool, True),
    ENABLE_HUMAN_APPROVAL_GATES=(bool, True),
    LOCAL_ONLY_MODE=(bool, True),
    # Auth / API keys
    AGENT_API_KEY=(str, ""),
    ANALYSIS_API_KEY=(str, ""),
    GRAPH_API_KEY=(str, ""),
    LSAT_API_KEY=(str, ""),
    ACCESS_TOKEN_EXPIRE_MINUTES=(int, 60 * 24 * 7),
    # Audit
    AUDIT_PATH=(str, ".audit/provenance.jsonl"),
    MAX_AUDIT_LINES=(int, 10_000),
    KEEP_AUDIT_LINES=(int, 5_000),
)

env.read_env(str(BASE_DIR / ".env"), overwrite=False)


# ---------------------------------------------------------------------------
# Mirror of the legacy Pydantic Settings surface (read by relocated modules
# via ``lexgraph.core.settings_proxy``).
# ---------------------------------------------------------------------------
APP_NAME: str = env("APP_NAME")
ENVIRONMENT: str = env("ENVIRONMENT")
DEBUG: bool = env.bool("DEBUG")

OLLAMA_BASE_URL: str = env("OLLAMA_BASE_URL")
DEFAULT_MODEL: str = env("DEFAULT_MODEL")
FALLBACK_MODEL: str = env("FALLBACK_MODEL")
OLLAMA_DEFAULT_MODEL: str = env("OLLAMA_DEFAULT_MODEL")
OLLAMA_REQUEST_TIMEOUT_S: float = env.float("OLLAMA_REQUEST_TIMEOUT_S")
LANGGRAPH_CHECKPOINTER: str = env("LANGGRAPH_CHECKPOINTER")
LANGGRAPH_CHECKPOINTER_SCHEMA: str = env("LANGGRAPH_CHECKPOINTER_SCHEMA")

PHOENIX_COLLECTOR_ENDPOINT: str | None = env("PHOENIX_COLLECTOR_ENDPOINT") or None
PHOENIX_UI_URL: str = env("PHOENIX_UI_URL")
PHOENIX_PROJECT_NAME: str = env("PHOENIX_PROJECT_NAME")

POSTGRES_URL: str = env("POSTGRES_URL")
NEO4J_URI: str = env("NEO4J_URI")
NEO4J_USER: str = env("NEO4J_USER")
NEO4J_PASSWORD: str = env("NEO4J_PASSWORD")
REDIS_URL: str = env("REDIS_URL")

COURTLISTENER_API_KEY: str | None = env("COURTLISTENER_API_KEY") or None
RECAP_EMAIL: str | None = env("RECAP_EMAIL") or None
RECAP_PASSWORD: str | None = env("RECAP_PASSWORD") or None

ENABLE_LEGALBENCH_EVAL: bool = env.bool("ENABLE_LEGALBENCH_EVAL")
ENABLE_HUMAN_APPROVAL_GATES: bool = env.bool("ENABLE_HUMAN_APPROVAL_GATES")
LOCAL_ONLY_MODE: bool = env.bool("LOCAL_ONLY_MODE")

AGENT_API_KEY: str | None = env("AGENT_API_KEY") or None
ANALYSIS_API_KEY: str | None = env("ANALYSIS_API_KEY") or None
GRAPH_API_KEY: str | None = env("GRAPH_API_KEY") or None
LSAT_API_KEY: str | None = env("LSAT_API_KEY") or None
ACCESS_TOKEN_EXPIRE_MINUTES: int = env.int("ACCESS_TOKEN_EXPIRE_MINUTES")

AUDIT_PATH: str = env("AUDIT_PATH")
MAX_AUDIT_LINES: int = env.int("MAX_AUDIT_LINES")
KEEP_AUDIT_LINES: int = env.int("KEEP_AUDIT_LINES")


# ---------------------------------------------------------------------------
# Django configuration
# ---------------------------------------------------------------------------
SECRET_KEY = env("SECRET_KEY")
ALLOWED_HOSTS = env.list("ALLOWED_HOSTS")

INSTALLED_APPS = [
    "daphne",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "channels",
    # LexGraph apps
    "lexgraph.core.apps.CoreConfig",
    "lexgraph.audit.apps.AuditConfig",
    "lexgraph.analysis.apps.AnalysisConfig",
    "lexgraph.graph.apps.GraphConfig",
    "lexgraph.lsat.apps.LsatConfig",
    "lexgraph.ingestionapp.apps.IngestionappConfig",
    "lexgraph.agentsapi.apps.AgentsapiConfig",
    "lexgraph.agents_runtime.apps.AgentsRuntimeConfig",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "lexgraph.core.middleware.CorsHeadersMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "lexgraph.core.middleware.ProvenanceMiddleware",
]

ROOT_URLCONF = "lexgraph.urls"
ASGI_APPLICATION = "lexgraph.asgi.application"
WSGI_APPLICATION = "lexgraph.wsgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]


def _build_database_config() -> dict[str, dict[str, Any]]:
    db_url = env("DATABASE_URL")
    if db_url:
        return {"default": env.db_url("DATABASE_URL")}
    # Translate the asyncpg-style POSTGRES_URL into a sync psycopg config so
    # Django ORM (sync) and Channels' Redis layer can share the same env
    # without forcing operators to set two URLs.
    return {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "HOST": (
                env("POSTGRES_URL").split("@")[-1].split(":")[0]
                if "@" in env("POSTGRES_URL")
                else "postgres"
            ),
            "PORT": "5432",
            "NAME": "lexgraph",
            "USER": "lexgraph",
            "PASSWORD": "lexgraph-dev",
        }
    }


DATABASES = _build_database_config()
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

AUTH_PASSWORD_VALIDATORS: list[dict[str, str]] = []
LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True
STATIC_URL = "/static/"
STATIC_ROOT = str(BASE_DIR / "staticfiles")
# Whitenoise: serve admin + collectstatic output through daphne in dev/prod.
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}

# DRF
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": ("lexgraph.core.auth.ApiKeyAuthentication",),
    "DEFAULT_PERMISSION_CLASSES": ("rest_framework.permissions.AllowAny",),
    "UNAUTHENTICATED_USER": None,
}

# Channels
CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels_redis.core.RedisChannelLayer",
        "CONFIG": {"hosts": [env("REDIS_URL")]},
    }
}

# Celery
CELERY_BROKER_URL = env("REDIS_URL")
CELERY_RESULT_BACKEND = env("REDIS_URL")
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TIMEZONE = TIME_ZONE
CELERY_TASK_ALWAYS_EAGER = False

# CORS — preserves the FastAPI app/main.py allow-list verbatim
CORS_ALLOWED_ORIGINS = ["http://localhost:3000", "http://127.0.0.1:3000"]
