"""Lock-in test for the hand-edited PendingReview initial migration (BL-20260503-19).

The migration uses ``SeparateDatabaseAndState`` so that:

* Django's ORM/state thinks ``PendingReview`` was created by a normal
  ``CreateModel`` (so ``makemigrations`` stays a no-op).
* The actual database side is an idempotent SQL block that matches the
  pre-existing spec-004 schema verbatim on Postgres, preserving live rows
  on the FastAPI -> Django cutover.

This test exercises only what we can verify portably: that the migration's
shape is what we promised. The Postgres-specific live-rows-survive scenario
is covered by ``backend/tests/integration/test_migrate_parity.py`` (spec
011 T-005), which is integration-marked and runs against a real Postgres
container.
"""

from __future__ import annotations

import importlib

from django.db import migrations


def _load_migration():
    return importlib.import_module("lexgraph.ingestionapp.migrations.0001_initial")


def test_initial_migration_uses_separate_database_and_state() -> None:
    """The first ingestionapp migration must split state from database ops.

    Anything else (e.g. plain ``CreateModel``) means a fresh ``migrate`` on a
    Postgres DB that already has the legacy ``pending_review`` table would
    fail with "relation already exists".
    """
    mod = _load_migration()
    op = mod.Migration.operations[0]
    assert isinstance(op, migrations.SeparateDatabaseAndState), (
        "Initial migration must wrap state vs. database ops; got "
        f"{type(op).__name__}"
    )
    state_ops = list(op.state_operations)
    assert len(state_ops) == 1
    assert isinstance(state_ops[0], migrations.CreateModel)
    assert state_ops[0].name == "PendingReview"
    db_ops = list(op.database_operations)
    assert len(db_ops) == 1
    assert not isinstance(db_ops[0], migrations.CreateModel), (
        "database_operations must not duplicate state CreateModel; use "
        "RunPython/RunSQL so the legacy table can be adopted."
    )


def test_legacy_postgres_ddl_preserves_spec004_schema() -> None:
    """The Postgres DDL must keep the exact column set spec-004 shipped.

    Guards against accidentally renaming/dropping a column in a future
    edit, which would corrupt live HITL rows on cutover.
    """
    mod = _load_migration()
    sql = mod.LEGACY_DDL_FORWARD.lower()
    for column in (
        "id",
        "source",
        "payload",
        "confidence",
        "reason",
        "created_at",
    ):
        assert column in sql, f"legacy column '{column}' missing from forward DDL"
    assert "jsonb" in sql, "payload column must be jsonb to match legacy schema"
    assert "timestamptz" in sql, "created_at must be timestamptz to match legacy schema"
    # Spec 011 columns added via ALTER TABLE so legacy rows survive.
    assert "add column if not exists reviewed_at" in sql
    assert "add column if not exists approved" in sql
    # Idempotency markers — the legacy table may already exist.
    assert "create table if not exists pending_review" in sql
    # pg_trgm extension preserved from 002_pg_trgm.sql.
    assert "create extension if not exists pg_trgm" in sql
