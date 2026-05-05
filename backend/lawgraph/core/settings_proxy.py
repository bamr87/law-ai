"""Settings proxy (spec 011 FR-4).

Relocated framework-agnostic modules used to import ``app.core.config.settings``
(a Pydantic Settings instance with attribute access). They now import this
module instead so they keep working without knowing about ``django.conf``.

Usage::

    from lawgraph.core.settings_proxy import settings_proxy as settings

    print(settings.NEO4J_URI)
"""

from __future__ import annotations

from django.conf import settings as _django_settings


class _SettingsProxy:
    """Attribute-access wrapper around ``django.conf.settings``."""

    def __getattr__(self, item: str):
        return getattr(_django_settings, item)


settings_proxy = _SettingsProxy()
