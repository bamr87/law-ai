"""``manage.py list_sources`` — print the SOURCE_REGISTRY as a table."""

from __future__ import annotations

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "List all registered source adapters and their metadata."

    def handle(self, *args: object, **options: object) -> None:
        from django.conf import settings

        from law_ai.ingestionapp.sources import SOURCE_REGISTRY

        allowed: list[str] = list(getattr(settings, "AUTONOMY_ALLOWED_SOURCES", []))

        header = f"{'NAME':<22} {'JURISDICTION':<14} {'HITL':<6} {'RPS':<6} {'ALLOWLISTED':<12} LICENSE"
        sep = "-" * len(header)
        self.stdout.write(header)
        self.stdout.write(sep)
        for name, adapter in sorted(SOURCE_REGISTRY.items()):
            hitl = "yes" if adapter.requires_human_approval else "no"
            rps = f"{adapter.rate_limit_rps:.1f}"
            allowlisted = "yes" if name in allowed else "no"
            license_str = adapter.license[:45]
            self.stdout.write(
                f"{name:<22} {adapter.jurisdiction:<14} {hitl:<6} {rps:<6} {allowlisted:<12} {license_str}"
            )
        self.stdout.write("")
        self.stdout.write(f"{len(SOURCE_REGISTRY)} source(s) registered.")
