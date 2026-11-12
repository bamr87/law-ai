"""The running service's release version (UPS-BE-11).

One source for every surface that reports a version — ``GET /``,
``GET /health``, ``GET /version`` and the OpenTelemetry resource. The value
is the installed ``law-ai`` distribution's version, which release-please
keeps equal to ``.release-please-manifest.json`` through the ``extra-files``
entry for ``backend/pyproject.toml``.
"""

from __future__ import annotations

from importlib import metadata

DISTRIBUTION = "law-ai"
UNKNOWN = "unknown"


def get_version() -> str:
    """Return the installed ``law-ai`` version, or ``"unknown"``.

    The fallback covers running from a source tree that was never
    installed (``pip install -e backend`` puts the metadata in place).

    Example::

        >>> get_version()  # doctest: +SKIP
        '0.2.1'
    """
    try:
        return metadata.version(DISTRIBUTION)
    except metadata.PackageNotFoundError:
        return UNKNOWN
