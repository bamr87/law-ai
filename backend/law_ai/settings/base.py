"""Base Django settings for Law AI (spec 011 FR-3, FR-5).

Mirrors every env knob from the legacy ``app.core.config.Settings`` so that
relocated framework-agnostic modules see the same values via
``law_ai.core.settings_proxy``.
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
    APP_NAME=(str, "Law AI"),
    # LLM
    OLLAMA_BASE_URL=(str, "http://ollama:11434"),
    FALLBACK_MODEL=(str, "mistral:7b-instruct-q4_K_M"),
    OLLAMA_DEFAULT_MODEL=(str, "mistral:7b-instruct-q4_K_M"),
    OLLAMA_REQUEST_TIMEOUT_S=(float, 120.0),
    # Local embedding model (the compose stack pulls it at bootstrap); used by
    # the LSAT factory's paraphrase dedup gate (BL-20260702-01).
    OLLAMA_EMBED_MODEL=(str, "nomic-embed-text"),
    # Total attempts per Ollama generate call on transient failures (connect /
    # read-timeout / 429 / 5xx); 1 disables retry (BL-20260810-05).
    OLLAMA_MAX_RETRIES=(int, 2),
    # Ordered LLM provider chain (spec 034, extended by spec 050). Tried left to
    # right; the first provider that is configured and answers serves the
    # request. Claude is the product-runtime default (constitution §1, amended
    # 2026-08-11), then xAI Grok (amended 2026-09-04), then local Ollama. The
    # xAI tier is inert until an operator runs `make xai-login`, so this default
    # changes nothing for a deployment that has not authorised it.
    LLM_PROVIDER_CHAIN=(str, "claude_code,anthropic_api,xai,ollama"),
    # How long the router remembers that a tier's credential was rejected, so
    # a misconfigured key is skipped instead of re-earning a 401 on every
    # request (BL-20260811-23). Per-process; 0 disables the memory.
    LLM_PERMANENT_FAILURE_TTL_S=(float, 300.0),
    # Off by default: constitution §13 prefers a local answer to no answer, so
    # a permanently failing hosted tier still falls through to Ollama. Set true
    # where a silent downgrade is worse than a loud failure.
    LLM_FAIL_FAST_ON_PERMANENT=(bool, False),
    # Claude credentials. OAuth token comes from `claude setup-token`; the API
    # key is the standard ANTHROPIC_API_KEY used as the second-tier fallback.
    ANTHROPIC_BASE_URL=(str, "https://api.anthropic.com"),
    ANTHROPIC_API_KEY=(str, ""),
    ANTHROPIC_MODEL=(str, ""),
    CLAUDE_CODE_OAUTH_TOKEN=(str, ""),
    CLAUDE_CODE_MODEL=(str, "claude-opus-5"),
    # Thinking is on by default on Claude Opus 5 and max_tokens caps thinking
    # *plus* response text, so the old 2048 truncates real answers mid-document.
    CLAUDE_CODE_MAX_TOKENS=(int, 8192),
    # Reasoning depth: low | medium | high | xhigh | max. Empty = API default.
    CLAUDE_EFFORT=(str, ""),
    CLAUDE_CODE_REQUEST_TIMEOUT_S=(float, 60.0),
    # Retry attempts for transient Anthropic errors (429/5xx/529 overloaded).
    CLAUDE_CODE_MAX_RETRIES=(int, 3),
    # xAI Grok — chain tier 3 (spec 050, constitution §1 as amended 2026-09-04).
    # Auth is a SuperGrok / X Premium+ subscription OAuth token acquired with
    # `make xai-login`; there is no API-key tier. The credentials file rotates
    # on every refresh, so it is written (not just read) at runtime — the path
    # is relative to the process cwd like AUDIT_PATH (/app in Docker).
    XAI_CREDENTIALS_PATH=(str, ".xai/credentials.json"),
    # Optional seed for deployments that inject tokens instead of logging in.
    XAI_ACCESS_TOKEN=(str, ""),
    XAI_REFRESH_TOKEN=(str, ""),
    XAI_AUTH_BASE_URL=(str, "https://auth.x.ai"),
    XAI_BASE_URL=(str, "https://api.x.ai/v1"),
    XAI_MODEL=(str, "grok-4.6"),
    # Optional faster Grok id for user-facing calls only (the LSAT tutor, an
    # interactive IRAC). Blank = use XAI_MODEL everywhere (BL-20260905-11);
    # measure a candidate against a real subscription before setting it, and
    # note it trades answer quality on the fallback tier for latency.
    XAI_INTERACTIVE_MODEL=(str, ""),
    XAI_MAX_TOKENS=(int, 8192),
    # Grok is a reasoning model and is materially slower than Claude on the
    # work this product does: a full IRAC analysis measured 56-103s live, so
    # the 60s that suits the Claude tiers guarantees a timeout here. Measured
    # 2026-09-05 against grok-4.6 (spec 050).
    XAI_REQUEST_TIMEOUT_S=(float, 240.0),
    XAI_MAX_RETRIES=(int, 3),
    # LSAT content factory (spec 024). Artifacts dir is relative to BASE_DIR
    # (/app inside Docker = ./backend on host), like AUTONOMY_DIGEST_DIR.
    LSAT_FACTORY_DIR=(str, "var/lsat_factory"),
    LSAT_FACTORY_TARGET_PER_CELL=(int, 2),
    LSAT_FACTORY_MAX_JOBS=(int, 12),
    LSAT_FACTORY_DRAFTS_PER_JOB=(int, 3),
    LSAT_FACTORY_EXEMPLARS=(int, 2),
    LSAT_FACTORY_DEDUP_THRESHOLD=(float, 0.60),
    # Compare only the question-specific sentences of a stem (drop restated
    # passage/game setup) in the dedup gate (BL-20260702-08).
    LSAT_FACTORY_DEDUP_STRIP_CONTEXT=(bool, True),
    # Second, semantic dedup opinion from the local Ollama embedding model
    # (BL-20260702-01); fails open onto Jaccard when Ollama is unreachable.
    LSAT_FACTORY_EMBED_DEDUP=(bool, True),
    LSAT_FACTORY_EMBED_THRESHOLD=(float, 0.93),
    LSAT_FACTORY_BALANCE_TOLERANCE=(float, 0.40),
    # Adversarial review of each accepted factory draft, attached to its
    # proposal meta for the reviewer (BL-20260702-02). Doubles model calls.
    LSAT_FACTORY_JUDGE=(bool, False),
    # Draft a solve guide alongside each accepted question draft so guide
    # coverage stops trailing the bank (BL-20260901-04).
    LSAT_FACTORY_GUIDES=(bool, True),
    LSAT_FACTORY_GAP_BOOST=(float, 2.0),
    LSAT_FACTORY_MAX_TOKENS=(int, 8192),
    # JSON object mapping tier→Claude model id; empty = built-in defaults.
    LSAT_FACTORY_CLAUDE_TIERS=(str, ""),
    LSAT_CROSS_CHECK_ON_APPROVE=(bool, True),
    # Blind quality review of each authored draft (BL-20260527-04).
    # Pre-flag only: a low score never rejects, it sorts the HITL queue.
    LSAT_CONTENT_REVIEW=(bool, True),
    LSAT_REVIEW_FLAG_THRESHOLD=(float, 0.6),
    LSAT_PROPOSALS_DB_READS=(bool, False),
    LANGGRAPH_CHECKPOINTER=(str, "postgres"),
    LANGGRAPH_CHECKPOINTER_SCHEMA=(str, "langgraph"),
    LANGGRAPH_CHECKPOINTER_REQUIRED=(bool, False),
    PHOENIX_COLLECTOR_ENDPOINT=(str, ""),
    PHOENIX_UI_URL=(str, "http://localhost:6006"),
    PHOENIX_PROJECT_NAME=(str, "law_ai"),
    # BL-20260502-07: which observability backend the OTEL exporter targets.
    # "phoenix" (default, self-hosted Arize Phoenix), "langfuse", or "none" to
    # hard-disable tracing regardless of the endpoints below.
    OBSERVABILITY_BACKEND=(str, "phoenix"),
    LANGFUSE_HOST=(str, "http://localhost:3001"),
    LANGFUSE_PUBLIC_KEY=(str, ""),
    LANGFUSE_SECRET_KEY=(str, ""),
    # Escape hatch for any other OTLP/HTTP collector: when set it overrides
    # the backend's own endpoint, and OTEL_EXPORTER_OTLP_HEADERS ("k=v,k=v")
    # is sent with every export.
    OTEL_EXPORTER_OTLP_ENDPOINT=(str, ""),
    OTEL_EXPORTER_OTLP_HEADERS=(str, ""),
    # Databases
    POSTGRES_URL=(
        str,
        "postgresql+asyncpg://law_ai:law_ai-dev@postgres:5432/law_ai",
    ),
    DATABASE_URL=(str, ""),  # Django ORM (sync_psycopg form)
    NEO4J_URI=(str, "bolt://neo4j:7687"),
    NEO4J_USER=(str, "neo4j"),
    NEO4J_PASSWORD=(str, "law_ai-dev"),
    REDIS_URL=(str, "redis://redis:6379/0"),
    # External
    COURTLISTENER_API_KEY=(str, ""),
    RECAP_EMAIL=(str, ""),
    RECAP_PASSWORD=(str, ""),
    # Feature flags
    ENABLE_LEGALBENCH_EVAL=(bool, True),
    ENABLE_HUMAN_APPROVAL_GATES=(bool, True),
    # Optional spaCy NER pass in IngestionScout (BL-20260429-03). Off by
    # default: it needs the `nlp` extra's model wheel and adds per-document
    # latency, and generic NER on case text is noisy.
    ENABLE_NER=(bool, False),
    INGEST_LLM_SUMMARY=(bool, False),
    LOCAL_ONLY_MODE=(bool, True),
    # Auth / API keys
    AGENT_API_KEY=(str, ""),
    ANALYSIS_API_KEY=(str, ""),
    GRAPH_API_KEY=(str, ""),
    LSAT_API_KEY=(str, ""),
    INGESTION_API_KEY=(str, ""),
    ACCESS_TOKEN_EXPIRE_MINUTES=(int, 60 * 24 * 7),
    # BL-20260503-13: the OAuth2 bearer grant over `core.ApiToken`. The
    # access token is a stateless JWT, so nothing can recall one early —
    # that is why the default life is 15 minutes and the revocable half
    # is the refresh token.
    JWT_ISSUER=(str, "law-ai"),
    JWT_ACCESS_TTL_SECONDS=(int, 900),
    JWT_REFRESH_TTL_SECONDS=(int, 60 * 60 * 24 * 14),
    # Audit
    AUDIT_PATH=(str, ".audit/provenance.jsonl"),
    MAX_AUDIT_LINES=(int, 10_000),
    KEEP_AUDIT_LINES=(int, 5_000),
    # Autonomy (spec 018 — disabled by default per constitution §12)
    AUTONOMY_ENABLED=(bool, False),
    AUTONOMY_ALLOWED_SOURCES=(list, []),
    # var/autonomy is relative to BASE_DIR (/app inside Docker = ./backend on host).
    AUTONOMY_DIGEST_DIR=(str, "var/autonomy"),
    AUTONOMY_MAX_INGEST_PER_CYCLE=(int, 25),
    # Digest delivery (BL-20260511-05). Both default to "off": with neither
    # set the digest file stays the only surface, exactly as before. The
    # webhook URL is a bearer secret — env only, never committed, and
    # redacted from provenance payloads.
    AUTONOMY_DIGEST_SLACK_WEBHOOK_URL=(str, ""),
    AUTONOMY_DIGEST_EMAIL_TO=(list, []),
    AUTONOMY_DIGEST_EMAIL_FROM=(str, "law-ai-autonomy@localhost"),
    # Console backend by default so a misconfigured deployment prints the
    # digest instead of silently failing to send it.
    EMAIL_BACKEND=(str, "django.core.mail.backends.console.EmailBackend"),
    # Repo root for BACKLOG.md + specs/ (outside the backend/ volume mount in Docker).
    # Set REPO_ROOT=/repo in docker-compose when mounting the full repo at /repo.
    REPO_ROOT=(str, ""),
    # Governance triage (BL-20260503-14). Both default to "off": the weekly
    # beat job still runs both validators and logs what they said, it just has
    # nowhere to file an issue. The token is a bearer secret — env only.
    GOVERNANCE_TRIAGE_GITHUB_REPO=(str, ""),
    GOVERNANCE_TRIAGE_GITHUB_TOKEN=(str, ""),
)

env.read_env(str(BASE_DIR / ".env"), overwrite=False)


# ---------------------------------------------------------------------------
# Mirror of the legacy Pydantic Settings surface (read by relocated modules
# via ``law_ai.core.settings_proxy``).
# ---------------------------------------------------------------------------
APP_NAME: str = env("APP_NAME")
ENVIRONMENT: str = env("ENVIRONMENT")
DEBUG: bool = env.bool("DEBUG")

OLLAMA_BASE_URL: str = env("OLLAMA_BASE_URL")
# BL-20260906-43: ``DEFAULT_MODEL`` is gone. Nothing read it — the Ollama
# provider has always selected on OLLAMA_DEFAULT_MODEL — and a dead setting
# advertising a 70B read like the live knob. A ``DEFAULT_MODEL`` line left in
# an existing ``.env`` is simply ignored; OLLAMA_DEFAULT_MODEL is the one to
# change (the GPU overlay sets exactly that).
# FALLBACK_MODEL *is* read (BL-20260810-05): it is the second model the Ollama
# provider tries when the primary answers 404 (not pulled on this box). Blank
# it, or leave it equal to OLLAMA_DEFAULT_MODEL, to make the local tier a
# single-model call.
FALLBACK_MODEL: str = env("FALLBACK_MODEL")
OLLAMA_DEFAULT_MODEL: str = env("OLLAMA_DEFAULT_MODEL")
OLLAMA_REQUEST_TIMEOUT_S: float = env.float("OLLAMA_REQUEST_TIMEOUT_S")
OLLAMA_EMBED_MODEL: str = env("OLLAMA_EMBED_MODEL")
OLLAMA_MAX_RETRIES: int = env.int("OLLAMA_MAX_RETRIES")

# LLM provider chain — Claude first, Anthropic API key second, Ollama last
# (constitution §1 as amended; see law_ai.core.llm.router).
LLM_PROVIDER_CHAIN: str = env("LLM_PROVIDER_CHAIN")
ANTHROPIC_BASE_URL: str = env("ANTHROPIC_BASE_URL")
ANTHROPIC_API_KEY: str = env("ANTHROPIC_API_KEY")
ANTHROPIC_MODEL: str = env("ANTHROPIC_MODEL")
CLAUDE_CODE_OAUTH_TOKEN: str = env("CLAUDE_CODE_OAUTH_TOKEN")
CLAUDE_CODE_MODEL: str = env("CLAUDE_CODE_MODEL")
CLAUDE_CODE_MAX_TOKENS: int = env.int("CLAUDE_CODE_MAX_TOKENS")
CLAUDE_EFFORT: str = env("CLAUDE_EFFORT")
CLAUDE_CODE_REQUEST_TIMEOUT_S: float = env.float("CLAUDE_CODE_REQUEST_TIMEOUT_S")
CLAUDE_CODE_MAX_RETRIES: int = env.int("CLAUDE_CODE_MAX_RETRIES")
# Per-token prices for the hosted tiers, so the ``llm_call`` audit event can
# carry a ``cost_usd`` alongside the token counts (BL-20260811-21). JSON object
# keyed by "provider/model", "model" or "provider" (checked in that order),
# each value {"in_per_mtok": <usd>, "out_per_mtok": <usd>}. Empty by default:
# vendor prices change, so they stay operator configuration and an unpriced
# model logs tokens with a null cost rather than a stale number.
LLM_PRICE_TABLE: dict[str, dict[str, float]] = env.json("LLM_PRICE_TABLE", default={})
LLM_PERMANENT_FAILURE_TTL_S: float = env.float("LLM_PERMANENT_FAILURE_TTL_S")
LLM_FAIL_FAST_ON_PERMANENT: bool = env.bool("LLM_FAIL_FAST_ON_PERMANENT")
XAI_CREDENTIALS_PATH: str = env("XAI_CREDENTIALS_PATH")
XAI_ACCESS_TOKEN: str = env("XAI_ACCESS_TOKEN")
XAI_REFRESH_TOKEN: str = env("XAI_REFRESH_TOKEN")
XAI_AUTH_BASE_URL: str = env("XAI_AUTH_BASE_URL")
XAI_BASE_URL: str = env("XAI_BASE_URL")
XAI_MODEL: str = env("XAI_MODEL")
XAI_INTERACTIVE_MODEL: str = env("XAI_INTERACTIVE_MODEL")
XAI_MAX_TOKENS: int = env.int("XAI_MAX_TOKENS")
XAI_REQUEST_TIMEOUT_S: float = env.float("XAI_REQUEST_TIMEOUT_S")
XAI_MAX_RETRIES: int = env.int("XAI_MAX_RETRIES")

# LSAT content factory (spec 024) — see law_ai.lsat.factory.config.
LSAT_FACTORY_DIR: str = env("LSAT_FACTORY_DIR")
LSAT_FACTORY_TARGET_PER_CELL: int = env.int("LSAT_FACTORY_TARGET_PER_CELL")
LSAT_FACTORY_MAX_JOBS: int = env.int("LSAT_FACTORY_MAX_JOBS")
LSAT_FACTORY_DRAFTS_PER_JOB: int = env.int("LSAT_FACTORY_DRAFTS_PER_JOB")
LSAT_FACTORY_EXEMPLARS: int = env.int("LSAT_FACTORY_EXEMPLARS")
LSAT_FACTORY_DEDUP_THRESHOLD: float = env.float("LSAT_FACTORY_DEDUP_THRESHOLD")
LSAT_FACTORY_DEDUP_STRIP_CONTEXT: bool = env.bool("LSAT_FACTORY_DEDUP_STRIP_CONTEXT")
LSAT_FACTORY_EMBED_DEDUP: bool = env.bool("LSAT_FACTORY_EMBED_DEDUP")
LSAT_FACTORY_EMBED_THRESHOLD: float = env.float("LSAT_FACTORY_EMBED_THRESHOLD")
LSAT_FACTORY_BALANCE_TOLERANCE: float = env.float("LSAT_FACTORY_BALANCE_TOLERANCE")
LSAT_CONTENT_REVIEW: bool = env("LSAT_CONTENT_REVIEW")
LSAT_REVIEW_FLAG_THRESHOLD: float = env.float("LSAT_REVIEW_FLAG_THRESHOLD")
LSAT_FACTORY_JUDGE: bool = env.bool("LSAT_FACTORY_JUDGE")
LSAT_FACTORY_GUIDES: bool = env.bool("LSAT_FACTORY_GUIDES")
LSAT_FACTORY_GAP_BOOST: float = env.float("LSAT_FACTORY_GAP_BOOST")
LSAT_FACTORY_MAX_TOKENS: int = env.int("LSAT_FACTORY_MAX_TOKENS")
LSAT_FACTORY_CLAUDE_TIERS: str = env("LSAT_FACTORY_CLAUDE_TIERS")
# BL-20260527-06: blind-solve every approved question draft once so a
# tutor-grade baseline verdict exists for regression tracking. One provider
# call per approval; set false to make approvals free.
LSAT_CROSS_CHECK_ON_APPROVE: bool = env.bool("LSAT_CROSS_CHECK_ON_APPROVE")
# BL-20260527-05: serve the HITL queue from the indexed LsatProposal table
# instead of replaying the whole JSONL log. Off by default because a mirror
# that predates `manage.py lsat_proposals_backfill` would hide older
# proposals; the JSONL log stays the audit trail in either mode.
LSAT_PROPOSALS_DB_READS: bool = env.bool("LSAT_PROPOSALS_DB_READS")

LANGGRAPH_CHECKPOINTER: str = env("LANGGRAPH_CHECKPOINTER")
LANGGRAPH_CHECKPOINTER_SCHEMA: str = env("LANGGRAPH_CHECKPOINTER_SCHEMA")
# BL-20260811-27: when true, `manage.py ensure_checkpointer` aborts the boot
# chain if the checkpointer cannot be initialized, instead of degrading to an
# unpersisted runtime that only fails on the first workflow call.
LANGGRAPH_CHECKPOINTER_REQUIRED: bool = env("LANGGRAPH_CHECKPOINTER_REQUIRED")

PHOENIX_COLLECTOR_ENDPOINT: str | None = env("PHOENIX_COLLECTOR_ENDPOINT") or None
PHOENIX_UI_URL: str = env("PHOENIX_UI_URL")
PHOENIX_PROJECT_NAME: str = env("PHOENIX_PROJECT_NAME")

# Observability backend (BL-20260502-07). Phoenix stays the default; the
# abstraction exists so a licensing change there is a config edit, not a
# code change. PHOENIX_* remain the phoenix backend's own inputs.
OBSERVABILITY_BACKEND: str = env("OBSERVABILITY_BACKEND").strip().lower()
LANGFUSE_HOST: str = env("LANGFUSE_HOST")
LANGFUSE_PUBLIC_KEY: str = env("LANGFUSE_PUBLIC_KEY")
LANGFUSE_SECRET_KEY: str = env("LANGFUSE_SECRET_KEY")
OTEL_EXPORTER_OTLP_ENDPOINT: str = env("OTEL_EXPORTER_OTLP_ENDPOINT")
OTEL_EXPORTER_OTLP_HEADERS: str = env("OTEL_EXPORTER_OTLP_HEADERS")

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
ENABLE_NER: bool = env.bool("ENABLE_NER")
# BL-20260906-01: optional audited LLM holding-summary pass in IngestionScout.
# Off by default — the rule-based excerpt is deterministic and free, a
# per-document model call is neither.
INGEST_LLM_SUMMARY: bool = env.bool("INGEST_LLM_SUMMARY")
LOCAL_ONLY_MODE: bool = env.bool("LOCAL_ONLY_MODE")

AGENT_API_KEY: str | None = env("AGENT_API_KEY") or None

# BL-20260429-16: push change notifications to the ops dashboard's WebSocket
# instead of leaving it to poll six REST endpoints every five seconds. On by
# default (it costs one small frame per agent call, and only when a dashboard
# is open); the test settings turn it off so the suite's many agent calls do
# not each spawn a socket write no assertion reads.
AGENT_OPS_PUSH_ENABLED: bool = env.bool("AGENT_OPS_PUSH_ENABLED", default=True)

# BL-20260811-14: where the per-stream replay ring buffer lives, so a client
# whose WebSocket dropped can reconnect with `?since=` and catch up. Defaults
# to the same Redis everything else uses; blank in an env file means "the same
# Redis", while a settings module that assigns "" (the test settings do) pins
# the in-process fallback.
AGENT_STREAM_REPLAY_URL: str = env("AGENT_STREAM_REPLAY_URL", default="") or REDIS_URL
ANALYSIS_API_KEY: str | None = env("ANALYSIS_API_KEY") or None
GRAPH_API_KEY: str | None = env("GRAPH_API_KEY") or None
LSAT_API_KEY: str | None = env("LSAT_API_KEY") or None
# BL-20260811-01: the web quarantine review queue gets its own scope so an
# instance can give a domain reviewer the queue without also giving them the
# agent key. Blank falls back to AGENT_API_KEY, then to the open local posture.
INGESTION_API_KEY: str | None = env("INGESTION_API_KEY") or None
ACCESS_TOKEN_EXPIRE_MINUTES: int = env.int("ACCESS_TOKEN_EXPIRE_MINUTES")
# BL-20260503-13: signed with SECRET_KEY (HS256) by law_ai.core.jwt_auth.
JWT_ISSUER: str = env("JWT_ISSUER")
JWT_ACCESS_TTL_SECONDS: int = env.int("JWT_ACCESS_TTL_SECONDS")
JWT_REFRESH_TTL_SECONDS: int = env.int("JWT_REFRESH_TTL_SECONDS")

# BL-20260429-26 / spec 036 NFR-PRIV-1: whether a newly persisted analysis may
# ever be given a public share slug. Deployments handling matters under a
# confidentiality obligation set this false; existing rows keep their flag.
ANALYSIS_SHAREABLE_DEFAULT: bool = env.bool("ANALYSIS_SHAREABLE_DEFAULT", default=True)

# BL-20260817-02: matter task reminders. The in-app calendar always works;
# outbound email is opt-in because mail about a client matter arriving
# unannounced is worse than no reminder at all. Lead time is how far ahead of
# the user-entered due date a reminder fires.
MATTER_TASK_EMAIL_REMINDERS: bool = env.bool(
    "MATTER_TASK_EMAIL_REMINDERS", default=False
)
MATTER_TASK_REMINDER_LEAD_HOURS: int = env.int(
    "MATTER_TASK_REMINDER_LEAD_HOURS", default=24
)

# BL-20260811-07: under async + eager Celery the AuditEvent DB row would be
# skipped entirely (the ORM cannot be reached from a running loop, and an
# eager task runs inline in that same loop). With this on, the insert is
# handed to a worker thread bracketed by close_old_connections(), so dev
# matches prod. Off by default because pytest-django wraps each test in a
# transaction a second connection cannot see; settings/dev.py turns it on.
# Read in that one branch only, so it is INERT in production (a real broker
# means the Celery hand-off already lands in a worker's sync context): the
# base default names no prod/dev divergence (BL-20260906-13).
AUDIT_DB_THREAD_OFFLOAD: bool = env.bool("AUDIT_DB_THREAD_OFFLOAD", default=False)

AUDIT_PATH: str = env("AUDIT_PATH")
MAX_AUDIT_LINES: int = env.int("MAX_AUDIT_LINES")
KEEP_AUDIT_LINES: int = env.int("KEEP_AUDIT_LINES")

# Autonomy (spec 018, constitution §12). Default-off kill-switch + empty allow-list.
AUTONOMY_ENABLED: bool = env.bool("AUTONOMY_ENABLED")
AUTONOMY_ALLOWED_SOURCES: list[str] = env.list("AUTONOMY_ALLOWED_SOURCES")
AUTONOMY_DIGEST_DIR: str = env("AUTONOMY_DIGEST_DIR")
AUTONOMY_MAX_INGEST_PER_CYCLE: int = env.int("AUTONOMY_MAX_INGEST_PER_CYCLE")

# Digest delivery channels (BL-20260511-05). Unset = no-op; the digest file
# remains the only surface. See `law_ai.core.autonomy.deliver_digest`.
AUTONOMY_DIGEST_SLACK_WEBHOOK_URL: str = env("AUTONOMY_DIGEST_SLACK_WEBHOOK_URL")
AUTONOMY_DIGEST_EMAIL_TO: list[str] = env.list("AUTONOMY_DIGEST_EMAIL_TO")
AUTONOMY_DIGEST_EMAIL_FROM: str = env("AUTONOMY_DIGEST_EMAIL_FROM")
EMAIL_BACKEND: str = env("EMAIL_BACKEND")

# Repo root for BACKLOG.md / specs/ — populated by REPO_ROOT env var when
# the full repo is mounted (e.g. ./:/repo in docker-compose). Falls back to
# three directories above BASE_DIR for host/venv runs.
_repo_root_env: str = env("REPO_ROOT")
REPO_ROOT: Path = Path(_repo_root_env) if _repo_root_env else BASE_DIR.parent

# Governance triage (BL-20260503-14): the weekly `governance-triage` beat job
# opens/updates one issue when spec_validator or backlog_lint has something to
# say. Unset = report to the log and provenance only.
GOVERNANCE_TRIAGE_GITHUB_REPO: str = env("GOVERNANCE_TRIAGE_GITHUB_REPO")
GOVERNANCE_TRIAGE_GITHUB_TOKEN: str = env("GOVERNANCE_TRIAGE_GITHUB_TOKEN")


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
    # Law AI apps
    "law_ai.core.apps.CoreConfig",
    "law_ai.audit.apps.AuditConfig",
    "law_ai.analysis.apps.AnalysisConfig",
    "law_ai.graph.apps.GraphConfig",
    "law_ai.lsat.apps.LsatConfig",
    "law_ai.matters.apps.MattersConfig",
    "law_ai.ingestionapp.apps.IngestionappConfig",
    "law_ai.agentsapi.apps.AgentsapiConfig",
    "law_ai.agents_runtime.apps.AgentsRuntimeConfig",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "law_ai.core.middleware.CorsHeadersMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "law_ai.core.middleware.ProvenanceMiddleware",
]

ROOT_URLCONF = "law_ai.urls"
ASGI_APPLICATION = "law_ai.asgi.application"
WSGI_APPLICATION = "law_ai.wsgi.application"

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
            "NAME": "law_ai",
            "USER": "law_ai",
            "PASSWORD": "law_ai-dev",
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
    "DEFAULT_AUTHENTICATION_CLASSES": ("law_ai.core.auth.ApiKeyAuthentication",),
    "DEFAULT_PERMISSION_CLASSES": ("rest_framework.permissions.AllowAny",),
    "UNAUTHENTICATED_USER": None,
    # Throttling (BL-20260810-11). LLM-invoking endpoints fan out to a single
    # local Ollama with a 120 s timeout, and the auth gate is open by default
    # on localhost — so one client (or a crawler) could otherwise starve every
    # other user. Only the `llm` scope is applied, via ScopedRateThrottle on
    # the endpoints that actually invoke a model; cheap read endpoints are
    # deliberately unthrottled.
    "DEFAULT_THROTTLE_CLASSES": (),
    "DEFAULT_THROTTLE_RATES": {
        "llm": env("LLM_THROTTLE_RATE", default="20/min"),
        # BL-20260811-06: an identified caller (API token or signed-in user)
        # gets its own bucket *and* a more generous rate — the per-IP limit
        # under-served everyone behind a shared proxy. `llm` stays the
        # anonymous rate. A single ApiToken may override both via its
        # `rate_limit` column.
        "llm_keyed": env("LLM_KEYED_THROTTLE_RATE", default="60/min"),
        # BL-20260503-12 (which absorbed BL-20260430-09): the `/api/agents/*`
        # reads are cheap — no model call — but they serve the audit log, so
        # a leaked key must not be able to scrape it at line speed. Hence a
        # scope of its own, an order of magnitude more generous than `llm`
        # rather than unthrottled. The ops dashboard polls a handful of these
        # endpoints every few seconds, so the anonymous rate has to clear
        # that comfortably.
        "audit": env("AUDIT_THROTTLE_RATE", default="120/min"),
        "audit_keyed": env("AUDIT_KEYED_THROTTLE_RATE", default="600/min"),
    },
}

# Channels
CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels_redis.core.RedisChannelLayer",
        "CONFIG": {"hosts": [env("REDIS_URL")]},
    }
}

# Django cache (BL-20260810-15). Redis-backed so multi-process deployments
# (daphne + Celery workers) can share cheap cross-process verdicts — first
# consumer is the Ollama availability probe in `agents_runtime.llm`, which keeps
# an in-process L1 and only consults this as L2. Every consumer must treat a
# cache failure as a miss: a Redis outage degrades to per-process behaviour,
# never to an error in the request path.
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": env("REDIS_URL"),
        "KEY_PREFIX": "law_ai",
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

# CORS — the frontend dev origins, and only those
CORS_ALLOWED_ORIGINS = ["http://localhost:3000", "http://127.0.0.1:3000"]


# Spec 049 FR-15. Off by default: a synthesized item with a finite-model proof
# of its key may bypass HITL review, but only when an operator turns this on
# *and* passes --promote explicitly. Structural-proof items are never eligible.
LSAT_SYNTH_AUTOPROMOTE = env.bool("LSAT_SYNTH_AUTOPROMOTE", default=False)
