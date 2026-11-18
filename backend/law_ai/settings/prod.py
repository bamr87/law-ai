"""Production settings (spec 011 NFR-SEC-1).

``manage.py check --deploy`` MUST pass with this module before promotion.

``SECRET_KEY`` and ``ALLOWED_HOSTS`` come from the environment. The
``settings/base.py`` defaults exist for development only, and production
refuses to boot on them: ``law_ai.E002`` / ``law_ai.E003`` in
``law_ai.core.apps`` (#221).
"""

from __future__ import annotations

from .base import *  # noqa: F403

DEBUG = False
ENVIRONMENT = "production"

SECURE_SSL_REDIRECT = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_HSTS_SECONDS = 60 * 60 * 24 * 30
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"
