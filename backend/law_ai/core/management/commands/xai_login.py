"""``xai_login`` — authorise the xAI Grok tier of the runtime chain (spec 050).

Exchanges a SuperGrok / X Premium+ subscription for an OAuth token set and
writes it to ``XAI_CREDENTIALS_PATH``. Run inside the backend container::

    make xai-login                       # device-code flow (the default)
    make xai-login ARGS='--status'       # report what is stored, change nothing
    make manage CMD='xai_login --loopback'   # host-side browser flow

Device-code is the default because it needs no inbound path to this process:
``127.0.0.1:56121`` inside the container is not the operator's browser
loopback, and the redirect URI is fixed by the OAuth client's registration so
it cannot be re-pointed at the host.
"""

from __future__ import annotations

import time
from typing import Any

from asgiref.sync import async_to_sync
from django.core.management.base import BaseCommand, CommandError

from law_ai.core import xai_oauth


class Command(BaseCommand):
    help = "Authorise the xAI Grok tier (chain tier 3) via subscription OAuth."

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument(
            "--loopback",
            action="store_true",
            help="Use the browser PKCE flow on 127.0.0.1:56121 instead of the "
            "device-code flow. Only works where this process and your browser "
            "share a loopback interface (i.e. not from inside Docker).",
        )
        parser.add_argument(
            "--status",
            action="store_true",
            help="Report the stored credential state and exit without changing it.",
        )

    def handle(self, *args: Any, **opts: Any) -> None:
        if opts["status"]:
            self._print_status()
            return
        if opts["loopback"]:
            self._loopback()
        else:
            self._device_code()

    # ------------------------------------------------------------------
    # Flows
    # ------------------------------------------------------------------
    def _device_code(self) -> None:
        self.stdout.write(
            self.style.MIGRATE_HEADING("xAI OAuth — device-code flow (RFC 8628)")
        )
        device = async_to_sync(xai_oauth.request_device_code)()

        self.stdout.write("")
        self.stdout.write(f"  1. Open: {self.style.HTTP_INFO(device.browser_url)}")
        self.stdout.write(f"  2. Enter code: {self.style.SUCCESS(device.user_code)}")
        self.stdout.write("  3. Approve access for the Grok CLI client.")
        self.stdout.write("")
        self.stdout.write("Waiting for approval… (Ctrl-C to abort)")

        try:
            creds = async_to_sync(xai_oauth.poll_device_token)(device)
        except xai_oauth.XaiAuthError as exc:
            raise CommandError(str(exc)) from exc
        self._report_success(creds)

    def _loopback(self) -> None:
        self.stdout.write(self.style.MIGRATE_HEADING("xAI OAuth — loopback PKCE flow"))
        self.stdout.write(
            f"Listening on {xai_oauth.REDIRECT_URI} for the authorization callback."
        )
        self.stdout.write(
            self.style.WARNING(
                "If this process is in Docker, that address is the container's "
                "loopback, not yours — use the device-code flow instead."
            )
        )
        try:
            url, creds = async_to_sync(xai_oauth.loopback_login)()
        except xai_oauth.XaiAuthError as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(f"\nAuthorization URL was:\n  {url}\n")
        self._report_success(creds)

    # ------------------------------------------------------------------
    # Reporting
    # ------------------------------------------------------------------
    def _report_success(self, creds: xai_oauth.Credentials) -> None:
        remaining = max(0, int(creds.expires_at - time.time()))
        self.stdout.write("")
        self.stdout.write(
            self.style.SUCCESS(
                f"Authorised. Credentials written to {xai_oauth.credentials_path()} "
                f"(access token valid ~{remaining // 60} min)."
            )
        )
        self.stdout.write(
            "The refresh token rotates on every use — keep this file, do not copy it."
        )
        self.stdout.write("Verify end-to-end with: make validate-xai")

    def _print_status(self) -> None:
        path = xai_oauth.credentials_path()
        self.stdout.write(self.style.MIGRATE_HEADING("xAI credential status"))
        self.stdout.write(f"  path            : {path}")
        self.stdout.write(f"  file present    : {path.is_file()}")
        creds = xai_oauth.load_credentials()
        if creds is None:
            self.stdout.write(
                self.style.WARNING(
                    f"  configured      : no — {xai_oauth.unconfigured_reason()}"
                )
            )
            return
        remaining = int(creds.expires_at - time.time())
        # Token values are never printed (spec 050 NFR-SEC-1); only their shape.
        self.stdout.write("  configured      : yes")
        self.stdout.write(f"  access present  : {bool(creds.access)}")
        self.stdout.write(
            f"  expires in      : {remaining}s"
            + (" (refresh due)" if creds.is_expiring() else "")
        )
