"""Development settings — local docker compose default."""
from __future__ import annotations

from .base import *  # noqa: F401,F403

DEBUG = True
ENVIRONMENT = "development"
ALLOWED_HOSTS = ["*"]
