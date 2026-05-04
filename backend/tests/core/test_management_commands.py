"""Smoke for `seed_api_keys` and `ensure_checkpointer` management commands.

Spec 011 FR-13 / AC-6 (checkpointer schema bootstrap) and spec 008/009
default-open posture (env-driven token seeding).
"""
from __future__ import annotations

from io import StringIO

import pytest
from django.core.management import call_command

from lexgraph.core.models import ApiToken


@pytest.mark.django_db
def test_seed_api_keys_creates_one_row_per_env_var(monkeypatch: pytest.MonkeyPatch) -> None:
    from django.conf import settings

    monkeypatch.setattr(settings, "AGENT_API_KEY", "agent-secret", raising=False)
    monkeypatch.setattr(settings, "ANALYSIS_API_KEY", "analysis-secret", raising=False)
    monkeypatch.setattr(settings, "GRAPH_API_KEY", None, raising=False)
    monkeypatch.setattr(settings, "LSAT_API_KEY", "", raising=False)

    out = StringIO()
    call_command("seed_api_keys", stdout=out)

    scopes = sorted(ApiToken.objects.values_list("scope", flat=True))
    assert scopes == ["agent", "analysis"]
    assert "created=2 already_present=0" in out.getvalue()


@pytest.mark.django_db
def test_seed_api_keys_is_idempotent(monkeypatch: pytest.MonkeyPatch) -> None:
    from django.conf import settings

    monkeypatch.setattr(settings, "AGENT_API_KEY", "agent-secret", raising=False)
    monkeypatch.setattr(settings, "ANALYSIS_API_KEY", None, raising=False)
    monkeypatch.setattr(settings, "GRAPH_API_KEY", None, raising=False)
    monkeypatch.setattr(settings, "LSAT_API_KEY", None, raising=False)

    call_command("seed_api_keys")
    out = StringIO()
    call_command("seed_api_keys", stdout=out)
    assert ApiToken.objects.filter(scope="agent").count() == 1
    assert "already_present=1" in out.getvalue()


@pytest.mark.django_db
def test_ensure_checkpointer_skips_non_postgres_engines() -> None:
    out = StringIO()
    call_command("ensure_checkpointer", stdout=out)
    # SQLite test backend → command must short-circuit with a warning, not raise.
    assert "skipping" in out.getvalue().lower()
