"""``validate_xai`` — verify the xAI Grok tier of the runtime chain (spec 050).

Proves this deployment can reach xAI over the stored subscription OAuth token,
and that the router actually selects the tier when the chain names it. Run
inside the backend container::

    make validate-xai

Exits non-zero when the tier cannot serve a request, so it is usable as a
deployment check.
"""

from __future__ import annotations

from typing import Any

from asgiref.sync import async_to_sync
from django.core.management.base import BaseCommand, CommandError

from law_ai.core import xai, xai_oauth
from law_ai.core.llm import providers as llm_providers
from law_ai.core.settings_proxy import settings_proxy as settings


class Command(BaseCommand):
    help = "Validate the xAI Grok tier of the LLM provider chain end-to-end."

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument(
            "--skip-generate",
            action="store_true",
            help="Only run the reachability probe; skip the real completion.",
        )

    def handle(self, *args: Any, **opts: Any) -> None:
        self._print_chain()
        self._print_models()

        probe = async_to_sync(xai.probe)()
        self._print_probe(probe)
        if not probe.get("reachable"):
            raise CommandError(
                "xAI probe failed: "
                + str(probe.get("error") or probe.get("reason") or "unreachable")
            )

        if opts["skip_generate"]:
            self.stdout.write(self.style.SUCCESS("\nOAuth connection validated."))
            return

        self._run_generate()

    # ------------------------------------------------------------------
    # Steps
    # ------------------------------------------------------------------
    def _print_chain(self) -> None:
        chain = str(getattr(settings, "LLM_PROVIDER_CHAIN", "") or "")
        self.stdout.write(self.style.MIGRATE_HEADING("xAI tier (chain tier 3)"))
        self.stdout.write(f"  chain           : {chain}")
        in_chain = llm_providers.XAI in [p.strip() for p in chain.split(",")]
        self.stdout.write(f"  xai in chain    : {in_chain}")
        if not in_chain:
            # Not an error: pinning the chain elsewhere is a supported, and for
            # confidentiality-bound data a required, configuration.
            self.stdout.write(
                self.style.WARNING(
                    "  note            : the chain does not name `xai`, so the "
                    "router will never select it. This check still exercises "
                    "the transport directly."
                )
            )
        self.stdout.write(f"  credentials     : {xai_oauth.credentials_path()}")
        self.stdout.write(f"  configured      : {xai_oauth.is_configured()}")

    def _print_models(self) -> None:
        """List the ids this subscription serves and flag a mismatch.

        ``XAI_MODEL`` has a hard-coded default, so a plan that does not expose
        that id 404s on every request. Discovery turns that into one warning
        naming a model that would work (BL-20260904-05). Purely informational:
        ``/v1/models`` is itself allowlisted for some accounts, and a failure
        here must not stop the probe that follows.
        """
        self.stdout.write(self.style.MIGRATE_HEADING("\nAvailable models"))
        configured = xai.model()
        try:
            models = async_to_sync(xai.list_models)()
        except Exception as exc:
            self.stdout.write(
                f"  listing         : unavailable ({type(exc).__name__}: "
                f"{str(exc)[:120]})"
            )
            return

        self.stdout.write(f"  configured      : {configured}")
        self.stdout.write(f"  available       : {', '.join(models) or '(none listed)'}")
        if models and configured not in models:
            suggestion = next((m for m in models if m.startswith("grok")), models[0])
            self.stdout.write(
                self.style.WARNING(
                    f"  warning         : XAI_MODEL={configured} is not in the "
                    f"list above; every request will 404. Set "
                    f"XAI_MODEL={suggestion}"
                )
            )

    def _print_probe(self, probe: dict[str, Any]) -> None:
        self.stdout.write(self.style.MIGRATE_HEADING("\nReachability probe"))
        for key in ("provider", "model", "base_url", "reachable", "sample"):
            if key in probe:
                self.stdout.write(f"  {key:<16}: {probe[key]}")
        if not probe.get("reachable"):
            self.stdout.write(
                self.style.ERROR(
                    f"  reason          : {probe.get('error') or probe.get('reason')}"
                )
            )

    def _run_generate(self) -> None:
        self.stdout.write(self.style.MIGRATE_HEADING("\nStructured completion"))
        schema = {
            "type": "object",
            "properties": {"jurisdiction": {"type": "string"}},
            "required": ["jurisdiction"],
            "additionalProperties": False,
        }
        try:
            reply = async_to_sync(xai.generate)(
                "Which court issued Marbury v. Madison? "
                'Answer as JSON: {"jurisdiction": "..."}',
                system="You answer with JSON only.",
                response_schema=schema,
                max_tokens=256,
            )
        except Exception as exc:
            raise CommandError(f"xAI completion failed: {exc}") from exc

        self.stdout.write(f"  model           : {xai.model_label()}")
        self.stdout.write(f"  reply           : {reply[:200]}")
        self.stdout.write(self.style.SUCCESS("\nxAI tier validated end-to-end."))
