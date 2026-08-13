"""Development settings — local docker compose default."""

from __future__ import annotations

from .base import *  # noqa: F403

DEBUG = True
ENVIRONMENT = "development"
ALLOWED_HOSTS = ["*"]

# Spec 037 FR-7 (OQ-2): capture prompt/completion text in Phoenix spans.
# Deliberately the one env-dependent default in this repo. `base.py` keeps it
# off so no *deployed* environment retains client prompt text without an
# explicit opt-in; the dev stack has no deployed consequence and would be
# useless without content — reading the prompt is the whole point of the
# feature (spec 037 §6). Do not point a `make dev` stack at privileged
# matters: content lands in the `phoenix:/data` volume.
PHOENIX_TRACE_CONTENT = True
