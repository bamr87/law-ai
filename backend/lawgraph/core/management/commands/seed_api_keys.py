"""``manage.py seed_api_keys`` — idempotently provision env-driven tokens.

Reads ``AGENT_API_KEY``, ``ANALYSIS_API_KEY``, ``GRAPH_API_KEY``, and
``LSAT_API_KEY`` from settings; for each non-empty value, ensures a
matching :class:`ApiToken` row exists with the same ``key_hash``.
"""

from __future__ import annotations

from django.conf import settings
from django.core.management.base import BaseCommand

from lawgraph.core.models import ApiToken

_PAIRS = (
    ("agent", "AGENT_API_KEY"),
    ("analysis", "ANALYSIS_API_KEY"),
    ("graph", "GRAPH_API_KEY"),
    ("lsat", "LSAT_API_KEY"),
)


class Command(BaseCommand):
    help = "Seed ApiToken rows from *_API_KEY environment variables."

    def handle(self, *args: object, **options: object) -> None:
        created = 0
        skipped = 0
        for scope, setting_name in _PAIRS:
            raw = getattr(settings, setting_name, None)
            if not raw:
                continue
            digest = ApiToken.hash_key(raw)
            _obj, was_new = ApiToken.objects.get_or_create(
                key_hash=digest,
                defaults={"scope": scope, "name": "env"},
            )
            if was_new:
                created += 1
            else:
                skipped += 1
        self.stdout.write(
            self.style.SUCCESS(
                f"seed_api_keys: created={created} already_present={skipped}"
            )
        )
