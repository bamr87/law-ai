"""Smoke for `seed_api_keys` and `ensure_checkpointer` management commands.

Spec 011 FR-13 / AC-6 (checkpointer schema bootstrap) and spec 008/009
default-open posture (env-driven token seeding).
"""

from __future__ import annotations

from io import StringIO

import pytest
from django.core.management import call_command

from law_ai.core.models import ApiToken


@pytest.mark.django_db
def test_seed_api_keys_creates_one_row_per_env_var(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
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
def test_ensure_checkpointer_skips_non_postgres_engines(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Force the non-postgres branch independent of the runtime DB so this
    # test passes both on local SQLite and on CI where DATABASE_URL points
    # at a real Postgres service.
    from django.conf import settings as dj_settings

    fake_dbs = {
        **dj_settings.DATABASES,
        "default": {
            **dj_settings.DATABASES["default"],
            "ENGINE": "django.db.backends.sqlite3",
        },
    }
    monkeypatch.setattr(dj_settings, "DATABASES", fake_dbs)

    out = StringIO()
    call_command("ensure_checkpointer", stdout=out)
    # Non-postgres backend → command must short-circuit with a warning, not raise.
    assert "skipping" in out.getvalue().lower()


# ---------------------------------------------------------------------------
# BL-20260811-25 (search_path) + BL-20260811-27 (boot visibility / fail fast)
# ---------------------------------------------------------------------------


class TestCheckpointerConnString:
    def test_search_path_is_pinned_to_the_configured_schema(self) -> None:
        from law_ai.agents_runtime.graphs.runtime import checkpointer_conn_string

        url = checkpointer_conn_string(
            "postgresql+asyncpg://u:p@db:5432/law_ai", schema="langgraph"
        )
        # The driver suffix is stripped for psycopg…
        assert "+asyncpg" not in url
        # …and libpq's `options` carries the search_path, `=` percent-encoded.
        assert "options=-csearch_path%3Dlanggraph" in url

    def test_existing_query_params_survive(self) -> None:
        from law_ai.agents_runtime.graphs.runtime import checkpointer_conn_string

        url = checkpointer_conn_string(
            "postgresql://u:p@db:5432/law_ai?sslmode=require", schema="lg"
        )
        assert "sslmode=require" in url
        assert "options=-csearch_path%3Dlg" in url

    def test_operator_supplied_options_are_not_clobbered(self) -> None:
        from law_ai.agents_runtime.graphs.runtime import checkpointer_conn_string

        raw = "postgresql://u:p@db:5432/law_ai?options=-cstatement_timeout%3D5000"
        assert checkpointer_conn_string(raw, schema="langgraph") == raw

    def test_postgres_saver_is_built_with_the_pinned_url(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from law_ai.agents_runtime.graphs import runtime as rt

        seen: list[str] = []

        class _FakeSaver:
            @staticmethod
            def from_conn_string(url: str) -> str:
                seen.append(url)
                return "saver"

        import sys
        import types

        module = types.ModuleType("langgraph.checkpoint.postgres.aio")
        module.AsyncPostgresSaver = _FakeSaver  # type: ignore[attr-defined]
        monkeypatch.setitem(sys.modules, "langgraph.checkpoint.postgres.aio", module)
        monkeypatch.setattr(
            rt.settings, "POSTGRES_URL", "postgresql://u:p@db:5432/law_ai"
        )
        monkeypatch.setattr(rt.settings, "LANGGRAPH_CHECKPOINTER_SCHEMA", "langgraph")

        rt._build_postgres_saver()
        assert seen and "options=-csearch_path%3Dlanggraph" in seen[0]


@pytest.mark.django_db
class TestEnsureCheckpointerVisibility:
    """A broken checkpointer must be loud at boot, not silent until first use."""

    def _force_postgres(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from django.conf import settings as dj_settings

        fake = {
            **dj_settings.DATABASES,
            "default": {
                **dj_settings.DATABASES["default"],
                "ENGINE": "django.db.backends.postgresql",
            },
        }
        monkeypatch.setattr(dj_settings, "DATABASES", fake)

    def test_setup_failure_prints_a_loud_error_by_default(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from law_ai.agents_runtime import checkpointer as cp
        from law_ai.agents_runtime.graphs.runtime import CheckpointerUnavailableError
        from django.conf import settings as dj_settings

        self._force_postgres(monkeypatch)
        monkeypatch.setattr(dj_settings, "LANGGRAPH_CHECKPOINTER_REQUIRED", False)
        monkeypatch.setattr(cp.settings, "LANGGRAPH_CHECKPOINTER", "postgres")
        monkeypatch.setattr(
            cp,
            "build_checkpointer",
            lambda *a, **k: (_ for _ in ()).throw(
                CheckpointerUnavailableError("bad url")
            ),
        )

        out, err = StringIO(), StringIO()
        call_command("ensure_checkpointer", stdout=out, stderr=err)
        combined = out.getvalue() + err.getvalue()
        assert "FAILED to initialize" in combined
        assert "bad url" in combined

    def test_flag_makes_a_failure_abort_the_boot(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from django.conf import settings as dj_settings
        from django.core.management.base import CommandError

        from law_ai.agents_runtime import checkpointer as cp
        from law_ai.agents_runtime.graphs.runtime import CheckpointerUnavailableError

        self._force_postgres(monkeypatch)
        monkeypatch.setattr(dj_settings, "LANGGRAPH_CHECKPOINTER_REQUIRED", True)
        monkeypatch.setattr(cp.settings, "LANGGRAPH_CHECKPOINTER", "postgres")
        monkeypatch.setattr(
            cp,
            "build_checkpointer",
            lambda *a, **k: (_ for _ in ()).throw(
                CheckpointerUnavailableError("bad url")
            ),
        )

        with pytest.raises(CommandError, match="LANGGRAPH_CHECKPOINTER_REQUIRED"):
            call_command("ensure_checkpointer", stdout=StringIO())

    def test_memory_backend_is_reported_as_skipped_not_failed(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from law_ai.agents_runtime import checkpointer as cp

        self._force_postgres(monkeypatch)
        monkeypatch.setattr(cp.settings, "LANGGRAPH_CHECKPOINTER", "memory")

        out = StringIO()
        call_command("ensure_checkpointer", stdout=out)
        assert "skipped" in out.getvalue()


class TestEnsureSchemaStatus:
    @pytest.mark.asyncio
    async def test_memory_backend_skips(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from law_ai.agents_runtime import checkpointer as cp

        monkeypatch.setattr(cp.settings, "LANGGRAPH_CHECKPOINTER", "memory")
        status = await cp.ensure_schema()
        assert status.state == "skipped"
        assert status.ok is True

    @pytest.mark.asyncio
    async def test_setup_error_is_reported_not_raised(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from contextlib import asynccontextmanager

        from law_ai.agents_runtime import checkpointer as cp

        class _Saver:
            async def setup(self) -> None:
                raise OSError("connection refused")

        @asynccontextmanager
        async def cm():  # type: ignore[no-untyped-def]
            yield _Saver()

        monkeypatch.setattr(cp.settings, "LANGGRAPH_CHECKPOINTER", "postgres")
        monkeypatch.setattr(cp, "build_checkpointer", lambda *a, **k: cm())
        status = await cp.ensure_schema()
        assert status.state == "error"
        assert status.ok is False
        assert "connection refused" in status.detail
