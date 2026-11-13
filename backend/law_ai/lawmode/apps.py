from __future__ import annotations

from django.apps import AppConfig


class LawmodeConfig(AppConfig):
    name = "law_ai.lawmode"
    label = "lawmode"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self) -> None:
        """Refuse to start on a lawmode setting the constitution rules out.

        Spec 057 AC-6: a ``LAWMODE_MODELS`` override naming an Anthropic model
        outside the allowed ids — or a provider that is not in the chain at
        all — stops the process here, at ``django.setup()``, rather than at
        the first scan. That covers daphne, Celery and every management
        command, which a system check would not (checks do not run under
        ASGI).
        """
        from law_ai.lawmode.policy import validate_settings

        validate_settings()
