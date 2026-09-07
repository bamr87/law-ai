"""Unit tests for the Cypher migration runner (BL-20260509-02).

Hermetic: a fake async driver stands in for Neo4j, so the parser, the
skip-what-is-recorded logic and the bookkeeping write are all exercised
without Docker. The live DDL check is the integration test
``tests/db/test_neo4j_migrations_integration.py`` (BL-20260509-03).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from django.core.management import call_command  # type: ignore[import-untyped]

from law_ai.core.neo4j import migrator

MODULE = "law_ai.core.management.commands.migrate_neo4j"


class _FakeResult:
    def __init__(self, records: list[dict[str, Any]]) -> None:
        self._records = records

    def __aiter__(self) -> _FakeResult:
        self._iter = iter(self._records)
        return self

    async def __anext__(self) -> dict[str, Any]:
        try:
            return next(self._iter)
        except StopIteration as exc:  # pragma: no cover - protocol boilerplate
            raise StopAsyncIteration from exc


class FakeSession:
    def __init__(self, driver: FakeDriver) -> None:
        self._driver = driver

    async def run(
        self, cypher: str, params: dict[str, Any] | None = None
    ) -> _FakeResult:
        self._driver.calls.append((cypher, params or {}))
        if "MATCH (m:_Migration) RETURN" in cypher:
            return _FakeResult(
                [{"id": k, "checksum": v} for k, v in self._driver.recorded.items()]
            )
        if "MERGE (m:_Migration" in cypher:
            self._driver.recorded[str(params and params["id"])] = str(
                params and params["checksum"]
            )
        return _FakeResult([])

    async def __aenter__(self) -> FakeSession:
        return self

    async def __aexit__(self, *exc: object) -> None:
        return None


class FakeDriver:
    def __init__(self, recorded: dict[str, str] | None = None) -> None:
        self.recorded: dict[str, str] = dict(recorded or {})
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def session(self) -> FakeSession:
        return FakeSession(self)

    def ddl_calls(self) -> list[str]:
        """Cypher that is neither bookkeeping nor the constraint bootstrap."""
        return [
            c
            for c, _ in self.calls
            if "_Migration" not in c and "MATCH (m:_Migration)" not in c
        ]


@pytest.fixture
def migrations_dir(tmp_path: Path) -> Path:
    d = tmp_path / "migrations"
    d.mkdir()
    (d / "001_first.cypher").write_text(
        "// a comment; with a semicolon in it\n"
        "CREATE CONSTRAINT a IF NOT EXISTS FOR (n:A) REQUIRE n.id IS UNIQUE;\n"
        "\n"
        "CREATE INDEX b IF NOT EXISTS FOR (n:B) ON (n.at);\n"
    )
    (d / "002_second.cypher").write_text(
        "CREATE FULLTEXT INDEX c IF NOT EXISTS\n  FOR (n:C) ON EACH [n.title, n.body];\n"
    )
    return d


# ---------------------------------------------------------------------------
# Statement splitting
# ---------------------------------------------------------------------------


def test_split_statements_drops_comments_and_blank_fragments() -> None:
    text = (
        "// 007 — header; with a semicolon\n"
        "CREATE CONSTRAINT a IF NOT EXISTS FOR (n:A) REQUIRE n.id IS UNIQUE;\n"
        "\n"
        "  // trailing note\n"
    )
    assert migrator.split_statements(text) == [
        "CREATE CONSTRAINT a IF NOT EXISTS FOR (n:A) REQUIRE n.id IS UNIQUE"
    ]


def test_split_statements_keeps_multiline_fulltext_bodies() -> None:
    text = (
        "CREATE FULLTEXT INDEX f IF NOT EXISTS\n"
        "  FOR (c:Case) ON EACH [c.title, c.holding_summary];\n"
    )
    (statement,) = migrator.split_statements(text)
    assert "ON EACH [c.title, c.holding_summary]" in statement
    assert ";" not in statement


def test_real_migration_set_splits_into_runnable_statements() -> None:
    """Every shipped migration parses into complete, comment-free statements."""
    files = migrator.discover()
    assert migrator.migration_id(files[0]) == "001_case_constraints"
    for path in files:
        statements = migrator.split_statements(path.read_text())
        assert statements, f"{path.name} produced no statements"
        for statement in statements:
            assert statement.upper().startswith(("CREATE", "MATCH")), statement
            assert not statement.lstrip().startswith("//")
            assert ";" not in statement


def test_every_ddl_statement_is_guarded_but_data_statements_exist() -> None:
    """The reason the runner needs bookkeeping, stated as a test.

    ``002_case_aliases`` ends in a ``MATCH ... SET`` back-fill: a data
    statement, not guarded DDL, which the old ``cypher-shell`` loop re-ran on
    every boot. ``IF NOT EXISTS`` cannot protect it — only the ``(:_Migration)``
    record can.
    """
    data_statements = [
        (migrator.migration_id(path), statement)
        for path in migrator.discover()
        for statement in migrator.split_statements(path.read_text())
        if not statement.upper().startswith("CREATE")
    ]
    assert data_statements, "expected at least one non-DDL migration statement"
    assert "002_case_aliases" in {mid for mid, _ in data_statements}
    for path in migrator.discover():
        for statement in migrator.split_statements(path.read_text()):
            if statement.upper().startswith("CREATE"):
                assert "IF NOT EXISTS" in statement.upper(), statement


# ---------------------------------------------------------------------------
# apply_migrations
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_apply_runs_every_statement_and_records_each_file(
    migrations_dir: Path,
) -> None:
    driver = FakeDriver()
    plan = await migrator.apply_migrations(driver, migrations_dir)
    assert plan.applied == ["001_first", "002_second"]
    assert plan.skipped == []
    assert plan.statements_run == 3
    assert len(driver.ddl_calls()) == 3
    assert set(driver.recorded) == {"001_first", "002_second"}
    # The uniqueness constraint on _Migration.id is created before anything is
    # recorded, so two concurrent runners cannot double-record a migration.
    assert "CREATE CONSTRAINT migration_id_unique" in driver.calls[0][0]


@pytest.mark.asyncio
async def test_apply_is_idempotent_second_run_is_a_no_op(
    migrations_dir: Path,
) -> None:
    driver = FakeDriver()
    await migrator.apply_migrations(driver, migrations_dir)
    driver.calls.clear()
    plan = await migrator.apply_migrations(driver, migrations_dir)
    assert plan.applied == []
    assert plan.skipped == ["001_first", "002_second"]
    assert plan.statements_run == 0
    assert driver.ddl_calls() == []


@pytest.mark.asyncio
async def test_apply_runs_only_the_new_file(migrations_dir: Path) -> None:
    """The whole point: a non-idempotent migration runs exactly once."""
    driver = FakeDriver()
    await migrator.apply_migrations(driver, migrations_dir)
    (migrations_dir / "003_backfill.cypher").write_text(
        "MATCH (n:A) SET n.touched = coalesce(n.touched, 0) + 1;\n"
    )
    driver.calls.clear()
    plan = await migrator.apply_migrations(driver, migrations_dir)
    assert plan.applied == ["003_backfill"]
    assert driver.ddl_calls() == [
        "MATCH (n:A) SET n.touched = coalesce(n.touched, 0) + 1"
    ]


@pytest.mark.asyncio
async def test_changed_file_is_reported_but_not_re_run(migrations_dir: Path) -> None:
    """Warn, not fail: 001-007 are already applied on live databases."""
    driver = FakeDriver()
    await migrator.apply_migrations(driver, migrations_dir)
    (migrations_dir / "001_first.cypher").write_text(
        "CREATE CONSTRAINT z IF NOT EXISTS FOR (n:Z) REQUIRE n.id IS UNIQUE;\n"
    )
    driver.calls.clear()
    plan = await migrator.apply_migrations(driver, migrations_dir)
    assert plan.checksum_mismatches == ["001_first"]
    assert plan.applied == []
    assert driver.ddl_calls() == []


@pytest.mark.asyncio
async def test_dry_run_touches_nothing(migrations_dir: Path) -> None:
    driver = FakeDriver()
    plan = await migrator.apply_migrations(driver, migrations_dir, dry_run=True)
    assert plan.applied == ["001_first", "002_second"]
    assert driver.ddl_calls() == []
    assert driver.recorded == {}


@pytest.mark.asyncio
async def test_a_crashed_file_is_not_recorded(migrations_dir: Path) -> None:
    """Bookkeeping is last, so a mid-file failure leaves the file pending."""

    class Boom(FakeDriver):
        def session(self) -> FakeSession:
            return _BoomSession(self)

    class _BoomSession(FakeSession):
        async def run(
            self, cypher: str, params: dict[str, Any] | None = None
        ) -> _FakeResult:
            if cypher.startswith("CREATE INDEX b"):
                raise RuntimeError("neo4j said no")
            return await super().run(cypher, params)

    driver = Boom()
    with pytest.raises(RuntimeError):
        await migrator.apply_migrations(driver, migrations_dir)
    assert driver.recorded == {}


# ---------------------------------------------------------------------------
# The management command
# ---------------------------------------------------------------------------


def test_command_applies_and_reports(monkeypatch, migrations_dir, capsys) -> None:
    driver = FakeDriver()
    monkeypatch.setattr(MODULE + ".get_neo4j_driver", lambda: driver)
    monkeypatch.setattr(migrator, "MIGRATIONS_DIR", migrations_dir)
    call_command("migrate_neo4j")
    out = capsys.readouterr().out
    assert "applied: 001_first" in out
    assert "2 applied, 0 already recorded, 0 deferred, 3 statement(s) run." in out


def test_command_dry_run_writes_nothing(monkeypatch, migrations_dir, capsys) -> None:
    driver = FakeDriver()
    monkeypatch.setattr(MODULE + ".get_neo4j_driver", lambda: driver)
    monkeypatch.setattr(migrator, "MIGRATIONS_DIR", migrations_dir)
    call_command("migrate_neo4j", "--dry-run")
    assert "would apply: 001_first" in capsys.readouterr().out
    assert driver.recorded == {}


def test_command_list_shows_pending_and_applied(
    monkeypatch, migrations_dir, capsys
) -> None:
    driver = FakeDriver(recorded={"001_first": "stale", "999_gone": "x"})
    monkeypatch.setattr(MODULE + ".get_neo4j_driver", lambda: driver)
    monkeypatch.setattr(migrator, "MIGRATIONS_DIR", migrations_dir)
    call_command("migrate_neo4j", "--list")
    out = capsys.readouterr().out
    assert "[applied] 001_first" in out
    assert "[pending] 002_second" in out
    assert "[recorded] 999_gone (no file on disk)" in out


# ---------------------------------------------------------------------------
# Enterprise-only DDL on a Community image (BL-20260509-02 / -03)
# ---------------------------------------------------------------------------


def test_is_enterprise_only_matches_neo4j_wording() -> None:
    """Neo4j reports this as a DatabaseError, not a ClientError."""
    from neo4j.exceptions import ClientError, DatabaseError

    exc = DatabaseError(
        "Unable to create Constraint( type='NODE PROPERTY EXISTENCE' ): "
        "Property existence constraint requires Neo4j Enterprise Edition."
    )
    assert migrator.is_enterprise_only(exc)
    assert not migrator.is_enterprise_only(ClientError("Invalid input 'X'"))
    assert not migrator.is_enterprise_only(DatabaseError("disk full"))


@pytest.mark.asyncio
async def test_enterprise_only_statement_defers_the_whole_file(
    migrations_dir: Path,
) -> None:
    """006 asks for existence constraints; neo4j:5-community refuses them.

    The file must be left un-recorded so it applies in full the first time it
    meets an Enterprise database — every statement is IF NOT EXISTS-guarded, so
    re-running the ones that did succeed costs nothing.
    """
    from neo4j.exceptions import DatabaseError

    (migrations_dir / "003_enterprise.cypher").write_text(
        "CREATE CONSTRAINT ok IF NOT EXISTS FOR (n:D) REQUIRE n.id IS UNIQUE;\n"
        "CREATE CONSTRAINT ent IF NOT EXISTS FOR (n:D) REQUIRE n.k IS NOT NULL;\n"
    )

    class _Session(FakeSession):
        async def run(
            self, cypher: str, params: dict[str, Any] | None = None
        ) -> _FakeResult:
            if "IS NOT NULL" in cypher:
                raise DatabaseError(
                    "Property existence constraint requires Neo4j Enterprise Edition."
                )
            return await super().run(cypher, params)

    class _Driver(FakeDriver):
        def session(self) -> FakeSession:
            return _Session(self)

    driver = _Driver()
    plan = await migrator.apply_migrations(driver, migrations_dir)
    assert plan.applied == ["001_first", "002_second"]
    assert plan.deferred == ["003_enterprise"]
    assert [mid for mid, _ in plan.unsupported] == ["003_enterprise"]
    assert "003_enterprise" not in driver.recorded
    # The supported half of the deferred file still ran.
    assert "CREATE CONSTRAINT ok IF NOT EXISTS FOR (n:D) REQUIRE n.id IS UNIQUE" in [
        " ".join(c.split()) for c in driver.ddl_calls()
    ]


@pytest.mark.asyncio
async def test_a_non_edition_client_error_still_propagates(
    migrations_dir: Path,
) -> None:
    from neo4j.exceptions import ClientError

    class _Session(FakeSession):
        async def run(
            self, cypher: str, params: dict[str, Any] | None = None
        ) -> _FakeResult:
            if cypher.startswith("CREATE INDEX b"):
                raise ClientError("Invalid input: syntax error")
            return await super().run(cypher, params)

    class _Driver(FakeDriver):
        def session(self) -> FakeSession:
            return _Session(self)

    with pytest.raises(ClientError):
        await migrator.apply_migrations(_Driver(), migrations_dir)
