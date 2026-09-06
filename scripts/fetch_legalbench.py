#!/usr/bin/env python3
"""Host entry point for the LegalBench dataset fetch (BL-20260811-09).

The fetch itself lives in :mod:`law_ai.eval.fetch` so it is importable and
unit-testable inside the backend image. This wrapper exists because the fetch
is something a human runs from the repo root, and because Docker-first means
the host must never ``pip install`` the backend to do it:

    python3 scripts/fetch_legalbench.py                       # from the host
    python3 scripts/fetch_legalbench.py --subset contract_nli
    make legalbench-cache                                     # same thing

Run from inside the backend container (where ``law_ai`` is importable) it
calls the module directly; run on the host it re-executes itself through
``docker compose run --rm backend``. Stdlib only, like the other
host-sanctioned helpers in this directory.
"""

from __future__ import annotations

import subprocess
import sys

_COMPOSE_CMD = [
    "docker",
    "compose",
    "run",
    "--rm",
    "--no-deps",
    "backend",
    "python",
    "-m",
    "law_ai.eval.fetch",
]


def main(argv: list[str]) -> int:
    """Delegate to ``law_ai.eval.fetch``, in-container or via docker compose."""
    try:
        from law_ai.eval.fetch import main as fetch_main
    except ModuleNotFoundError:
        return subprocess.call([*_COMPOSE_CMD, *argv])

    try:
        fetch_main(argv)
    except SystemExit as exc:  # the module CLI signals failure this way
        return int(exc.code or 0)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
