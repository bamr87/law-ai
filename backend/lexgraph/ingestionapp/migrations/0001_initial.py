"""Initial migration for the ingestion app.

Hand-edited per BL-20260503-19 (resolves spec 011 NFR-MIGRATION-SAFETY-1).

The spec-004 `pending_review` table predates the Django ORM. To keep live
Postgres rows safe across the FastAPI -> Django cutover this migration uses
``SeparateDatabaseAndState``:

* ``state_operations`` = ``CreateModel`` so Django's migration graph and ORM
  state mirror the model defined in ``lexgraph.ingestionapp.models``.
* ``database_operations`` = a ``RunSQL`` block that runs the verbatim DDL
  from the legacy raw-SQL migrations
  (``backend/app/db/postgres_migrations/001_pending_review.sql`` and
  ``002_pg_trgm.sql``) wrapped in idempotent ``IF NOT EXISTS`` clauses,
  plus ``ADD COLUMN IF NOT EXISTS`` for the columns introduced by the
  Django model (``reviewed_at``, ``approved``).

Net effect: a fresh database gets the schema; a legacy database with rows
already in ``pending_review`` is adopted in place without DROP/CREATE.
"""

from __future__ import annotations

from django.db import migrations, models


# --- DDL ----------------------------------------------------------------
#
# The raw DDL below is Postgres-specific (jsonb, timestamptz, pg_trgm).
# For non-Postgres backends (e.g. the SQLite test fixture used by some unit
# tests) we fall back to creating the table from the ORM model so the test
# DB still exercises the same code paths. Production / dev / integration all
# run on Postgres and exercise the legacy-compatible DDL.

# Verbatim DDL from the legacy raw-SQL migrations + idempotent ADDs for the
# columns that Django introduced when the model was promoted into the ORM.
LEGACY_DDL_FORWARD = """
-- 001_pending_review.sql (legacy spec-004 schema, made idempotent)
CREATE TABLE IF NOT EXISTS pending_review (
  id           text PRIMARY KEY,
  source       text NOT NULL,
  payload      jsonb NOT NULL,
  confidence   double precision NOT NULL,
  reason       text NOT NULL DEFAULT '',
  created_at   timestamptz NOT NULL DEFAULT now()
);

-- Columns added when PendingReview moved into the Django ORM (spec 011).
ALTER TABLE pending_review
  ADD COLUMN IF NOT EXISTS reviewed_at timestamptz NULL;
ALTER TABLE pending_review
  ADD COLUMN IF NOT EXISTS approved    boolean     NULL;

-- Match the indexes Django would create for `db_index=True` fields.
CREATE INDEX IF NOT EXISTS pending_review_source_idx
  ON pending_review (source);
CREATE INDEX IF NOT EXISTS pending_review_created_at_idx
  ON pending_review (created_at DESC);

-- 002_pg_trgm.sql (verbatim).
CREATE EXTENSION IF NOT EXISTS pg_trgm;
"""

LEGACY_DDL_REVERSE = """
DROP INDEX IF EXISTS pending_review_created_at_idx;
DROP INDEX IF EXISTS pending_review_source_idx;
DROP TABLE IF EXISTS pending_review;
-- pg_trgm is shared infrastructure; do not drop on reverse.
"""

# Portable DDL used on non-Postgres backends (SQLite test fixture). It mirrors
# the column set produced by Django's ``CreateModel`` for ``PendingReview`` so
# the rest of the app code is exercised identically. Postgres-only types
# (``jsonb``, ``timestamptz``, ``pg_trgm``) are intentionally absent here.
PORTABLE_DDL_FORWARD = """
CREATE TABLE IF NOT EXISTS pending_review (
  id           TEXT PRIMARY KEY,
  source       TEXT NOT NULL,
  payload      TEXT NOT NULL,
  confidence   REAL NOT NULL,
  reason       TEXT NOT NULL DEFAULT '',
  created_at   TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  reviewed_at  TIMESTAMP NULL,
  approved     INTEGER NULL
);
CREATE INDEX IF NOT EXISTS pending_review_source_idx
  ON pending_review (source);
CREATE INDEX IF NOT EXISTS pending_review_created_at_idx
  ON pending_review (created_at);
"""

PORTABLE_DDL_REVERSE = """
DROP INDEX IF EXISTS pending_review_created_at_idx;
DROP INDEX IF EXISTS pending_review_source_idx;
DROP TABLE IF EXISTS pending_review;
"""


def _split_statements(sql: str) -> list[str]:
    """Split a multi-statement SQL blob into individual statements.

    The sqlite3 Python driver refuses multi-statement strings in
    ``cursor.execute``; psycopg accepts them but executes them in order.
    Splitting here keeps both backends happy without changing semantics.
    """
    return [stmt.strip() for stmt in sql.split(";") if stmt.strip()]


def _create_pending_review(apps, schema_editor):
    """Forward DB op: legacy-compatible DDL on Postgres, portable DDL elsewhere."""
    sql = (
        LEGACY_DDL_FORWARD
        if schema_editor.connection.vendor == "postgresql"
        else PORTABLE_DDL_FORWARD
    )
    for stmt in _split_statements(sql):
        schema_editor.execute(stmt)


def _drop_pending_review(apps, schema_editor):
    """Reverse DB op: mirror of the forward op."""
    sql = (
        LEGACY_DDL_REVERSE
        if schema_editor.connection.vendor == "postgresql"
        else PORTABLE_DDL_REVERSE
    )
    for stmt in _split_statements(sql):
        schema_editor.execute(stmt)


class Migration(migrations.Migration):

    initial = True

    dependencies: list[tuple[str, str]] = []

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.CreateModel(
                    name="PendingReview",
                    fields=[
                        (
                            "id",
                            models.TextField(primary_key=True, serialize=False),
                        ),
                        ("source", models.TextField(db_index=True)),
                        ("payload", models.JSONField()),
                        ("confidence", models.FloatField()),
                        (
                            "reason",
                            models.TextField(blank=True, default=""),
                        ),
                        (
                            "created_at",
                            models.DateTimeField(
                                auto_now_add=True, db_index=True
                            ),
                        ),
                        (
                            "reviewed_at",
                            models.DateTimeField(blank=True, null=True),
                        ),
                        (
                            "approved",
                            models.BooleanField(default=None, null=True),
                        ),
                    ],
                    options={
                        "db_table": "pending_review",
                        "ordering": ["-created_at"],
                    },
                ),
            ],
            database_operations=[
                migrations.RunPython(
                    _create_pending_review,
                    _drop_pending_review,
                ),
            ],
        ),
    ]
