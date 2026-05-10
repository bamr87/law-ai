"""Add ``kind`` discriminator to ``pending_review`` (spec 015 FR-6).

Per ``/memories/repo/django-migrations.md`` and the spec 011 precedent
(0001_initial), we use ``SeparateDatabaseAndState`` so:

* ``state_operations`` mirrors the ORM with ``AddField`` (Django graph stays
  consistent and ``makemigrations`` is a no-op going forward).
* ``database_operations`` runs vendor-aware DDL: Postgres uses
  ``ADD COLUMN IF NOT EXISTS`` so legacy rows (the spec-004 table that
  predates the ORM) are adopted in place; SQLite (test fixture) uses the
  portable ``ALTER TABLE ADD COLUMN`` form.

The new column defaults to ``'case'`` so every pre-existing row back-fills
to the historical kind, satisfying spec 015 AC-3.
"""

from __future__ import annotations

from django.db import migrations, models

PG_FORWARD = """
ALTER TABLE pending_review
  ADD COLUMN IF NOT EXISTS kind text NOT NULL DEFAULT 'case';
CREATE INDEX IF NOT EXISTS pending_review_kind_idx
  ON pending_review (kind);
CREATE INDEX IF NOT EXISTS pending_review_kind_created_at_idx
  ON pending_review (kind, created_at DESC);
"""

PG_REVERSE = """
DROP INDEX IF EXISTS pending_review_kind_created_at_idx;
DROP INDEX IF EXISTS pending_review_kind_idx;
ALTER TABLE pending_review DROP COLUMN IF EXISTS kind;
"""

SQLITE_FORWARD = """
ALTER TABLE pending_review ADD COLUMN kind TEXT NOT NULL DEFAULT 'case';
CREATE INDEX IF NOT EXISTS pending_review_kind_idx
  ON pending_review (kind);
CREATE INDEX IF NOT EXISTS pending_review_kind_created_at_idx
  ON pending_review (kind, created_at);
"""

SQLITE_REVERSE = """
DROP INDEX IF EXISTS pending_review_kind_created_at_idx;
DROP INDEX IF EXISTS pending_review_kind_idx;
-- SQLite cannot DROP COLUMN before 3.35; the test DB is destroyed between
-- runs so leaving the column is acceptable on reverse.
"""


def _split(sql: str) -> list[str]:
    return [stmt.strip() for stmt in sql.split(";") if stmt.strip()]


def _add_kind(apps, schema_editor):
    sql = (
        PG_FORWARD
        if schema_editor.connection.vendor == "postgresql"
        else SQLITE_FORWARD
    )
    for stmt in _split(sql):
        schema_editor.execute(stmt)


def _drop_kind(apps, schema_editor):
    sql = (
        PG_REVERSE
        if schema_editor.connection.vendor == "postgresql"
        else SQLITE_REVERSE
    )
    for stmt in _split(sql):
        schema_editor.execute(stmt)


class Migration(migrations.Migration):

    dependencies = [
        ("ingestionapp", "0001_initial"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.AddField(
                    model_name="pendingreview",
                    name="kind",
                    field=models.CharField(
                        default="case", max_length=32, db_index=True
                    ),
                ),
            ],
            database_operations=[
                migrations.RunPython(_add_kind, _drop_kind),
            ],
        ),
    ]
