"""Live-stack integration test for ``manage.py list_sources`` (BL-20260511-09).

Spec 018 T-110 asked for an *integration* test that runs against the Docker
stack (Postgres + Redis) and asserts the command's adapter metadata matches
``SOURCE_REGISTRY``. The existing unit test in
``tests/ingestion/test_source_registry.py`` only checks that the three names
appear in the output; it neither runs under ``make test-integration`` nor
compares the printed columns to each adapter's metadata.

This module does both: it boots against the live services (``docker_services``
fixture + a real Postgres connection + a Redis ping) and parses every table row
back into a dict, comparing each column to the registry object it came from.
"""

from __future__ import annotations

from io import StringIO
from typing import Any

import pytest
from django.conf import settings
from django.core.management import call_command
from django.db import connection

from law_ai.ingestionapp.sources import SOURCE_REGISTRY

pytestmark = [pytest.mark.integration, pytest.mark.django_db]

COLUMNS = ("name", "jurisdiction", "hitl", "rps", "allowlisted", "license")


def _rows(output: str) -> dict[str, dict[str, str]]:
    """Parse the ``list_sources`` table into ``{name: {column: value}}``."""
    parsed: dict[str, dict[str, str]] = {}
    for line in output.splitlines():
        if not line.strip() or line.startswith(("NAME", "-")) or "registered" in line:
            continue
        fields = line.split(maxsplit=5)
        assert len(fields) == len(COLUMNS), f"unparseable row: {line!r}"
        parsed[fields[0]] = dict(zip(COLUMNS, fields, strict=True))
    return parsed


@pytest.fixture
def live_stack(docker_services: Any) -> None:
    """Assert the Docker services this test claims to run against are live."""
    import redis

    connection.ensure_connection()
    assert connection.vendor == "postgresql", (
        "list_sources integration test must run against the Docker Postgres "
        "(make test-integration sets DATABASE_URL); got "
        f"vendor={connection.vendor!r}"
    )
    assert redis.Redis.from_url(settings.REDIS_URL).ping() is True


def test_list_sources_rows_match_the_registry(live_stack: None) -> None:
    """Every printed row's metadata equals the adapter it names."""
    out = StringIO()
    call_command("list_sources", stdout=out)
    output = out.getvalue()
    rows = _rows(output)

    assert set(rows) == set(
        SOURCE_REGISTRY
    ), "printed rows must be exactly the SOURCE_REGISTRY keys"
    allowed = set(getattr(settings, "AUTONOMY_ALLOWED_SOURCES", []))
    for name, adapter in SOURCE_REGISTRY.items():
        row = rows[name]
        assert adapter.name == name
        assert row["jurisdiction"] == adapter.jurisdiction
        assert row["hitl"] == ("yes" if adapter.requires_human_approval else "no")
        assert float(row["rps"]) == pytest.approx(adapter.rate_limit_rps)
        assert row["allowlisted"] == ("yes" if name in allowed else "no")
        # The command truncates the license at 45 chars; compare the whole
        # printed cell, not just its first 20 characters.
        assert row["license"] == adapter.license[:45].strip()

    assert f"{len(SOURCE_REGISTRY)} source(s) registered." in output


def test_list_sources_footer_counts_every_adapter(live_stack: None) -> None:
    """The footer count is the registry size, not a hard-coded number."""
    out = StringIO()
    call_command("list_sources", stdout=out)
    assert f"{len(SOURCE_REGISTRY)} source(s) registered." in out.getvalue()
    assert len(_rows(out.getvalue())) == len(SOURCE_REGISTRY)
