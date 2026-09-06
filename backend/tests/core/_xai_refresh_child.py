"""Child process for the cross-process xAI refresh race (BL-20260904-04).

``test_xai_oauth.py`` spawns two of these at once against a stub token server.
The refresh token rotates on every use, so the loser of the race must take the
winner's freshly-stored credential rather than replaying a consumed one — a
guarantee only two real OS processes contending on ``fcntl.flock`` can prove.

Reads three env vars:

``TEST_XAI_CREDENTIALS_PATH``
    Shared credential file both children rotate.
``TEST_XAI_AUTH_BASE_URL``
    Base URL of the parent's stub token server.
``TEST_XAI_START_GATE``
    File the parent creates once *both* children are ready; waiting on it is
    what makes the race real instead of a startup-time coin flip. Each child
    announces itself by creating ``<gate>.<pid-slot>`` first.

Prints one JSON object on success; a traceback and a non-zero exit on failure.
Not named ``test_*`` on purpose — pytest must not collect it.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from pathlib import Path

_READY_TIMEOUT_S = 30.0


def _wait_for_gate(ready_marker: str, gate: str) -> None:
    """Tell the parent this process is warm, then wait for the shared start."""
    Path(ready_marker).write_text("ready", encoding="utf-8")
    deadline = time.monotonic() + _READY_TIMEOUT_S
    while not Path(gate).exists():
        if time.monotonic() > deadline:
            raise TimeoutError(f"start gate {gate} never appeared")
        time.sleep(0.01)


def main() -> int:
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "law_ai.settings.test")
    import django

    django.setup()

    from django.conf import settings

    # The test settings module hard-codes an unreachable store and auth host so
    # the suite can never touch xAI; point this child at the parent's stub.
    settings.XAI_CREDENTIALS_PATH = os.environ["TEST_XAI_CREDENTIALS_PATH"]
    settings.XAI_AUTH_BASE_URL = os.environ["TEST_XAI_AUTH_BASE_URL"]
    settings.XAI_ACCESS_TOKEN = ""
    settings.XAI_REFRESH_TOKEN = ""

    from law_ai.core import xai_oauth

    gate = os.environ.get("TEST_XAI_START_GATE")
    if gate:
        _wait_for_gate(os.environ["TEST_XAI_READY_MARKER"], gate)

    access = asyncio.run(xai_oauth.access_token())
    stored = xai_oauth.load_credentials()
    print(
        json.dumps(
            {
                "access": access,
                "refresh": stored.refresh if stored is not None else None,
            }
        )
    )
    return 0


if __name__ == "__main__":  # pragma: no cover - executed as a subprocess
    sys.exit(main())
