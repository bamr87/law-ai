"""Add reviewer identity + commit tracking to ``pending_review`` (spec 029).

Closes BL-20260810-03 (approval was a dead end — nothing recorded whether an
approved item ever reached the graph) and the storage half of BL-20260810-08
(review decisions were anonymous and rationale-free).

Follows the 0001/0002 precedent: ``SeparateDatabaseAndState`` so
``state_operations`` keeps the Django graph consistent while
``database_operations`` runs vendor-aware DDL (Postgres ``IF NOT EXISTS`` so
the legacy spec-004 table is adopted in place; SQLite uses the portable
form for the test fixture).

All four columns are nullable / defaulted, so pre-existing rows back-fill to
"never reviewed, never committed" — the correct historical reading.
"""

from __future__ import annotations

from django.db import migrations, models

PG_FORWARD = """
ALTER TABLE pending_review
  ADD COLUMN IF NOT EXISTS reviewer     text        NOT NULL DEFAULT '',
  ADD COLUMN IF NOT EXISTS review_note  text        NOT NULL DEFAULT '',
  ADD COLUMN IF NOT EXISTS committed_at timestamptz NULL,
  ADD COLUMN IF NOT EXISTS commit_error text        NOT NULL DEFAULT '';
CREATE INDEX IF NOT EXISTS pending_review_committed_at_idx
  ON pending_review (committed_at);
CREATE INDEX IF NOT EXISTS pending_review_awaiting_commit_idx
  ON pending_review (approved, committed_at);
"""

PG_REVERSE = """
DROP INDEX IF EXISTS pending_review_awaiting_commit_idx;
DROP INDEX IF EXISTS pending_review_committed_at_idx;
ALTER TABLE pending_review DROP COLUMN IF EXISTS commit_error;
ALTER TABLE pending_review DROP COLUMN IF EXISTS committed_at;
ALTER TABLE pending_review DROP COLUMN IF EXISTS review_note;
ALTER TABLE pending_review DROP COLUMN IF EXISTS reviewer;
"""

SQLITE_FORWARD = """
ALTER TABLE pending_review ADD COLUMN reviewer TEXT NOT NULL DEFAULT '';
ALTER TABLE pending_review ADD COLUMN review_note TEXT NOT NULL DEFAULT '';
ALTER TABLE pending_review ADD COLUMN committed_at TIMESTAMP NULL;
ALTER TABLE pending_review ADD COLUMN commit_error TEXT NOT NULL DEFAULT '';
CREATE INDEX IF NOT EXISTS pending_review_committed_at_idx
  ON pending_review (committed_at);
CREATE INDEX IF NOT EXISTS pending_review_awaiting_commit_idx
  ON pending_review (approved, committed_at);
"""

SQLITE_REVERSE = """
DROP INDEX IF EXISTS pending_review_awaiting_commit_idx;
DROP INDEX IF EXISTS pending_review_committed_at_idx;
-- SQLite cannot DROP COLUMN before 3.35; the test DB is destroyed between
-- runs so leaving the columns is acceptable on reverse.
"""


def _split(sql: str) -> list[str]:
    return [stmt.strip() for stmt in sql.split(";") if stmt.strip()]


def _forward(apps, schema_editor):
    sql = (
        PG_FORWARD
        if schema_editor.connection.vendor == "postgresql"
        else SQLITE_FORWARD
    )
    for stmt in _split(sql):
        schema_editor.execute(stmt)


def _reverse(apps, schema_editor):
    sql = (
        PG_REVERSE
        if schema_editor.connection.vendor == "postgresql"
        else SQLITE_REVERSE
    )
    for stmt in _split(sql):
        schema_editor.execute(stmt)


class Migration(migrations.Migration):

    dependencies = [
        ("ingestionapp", "0002_pending_review_kind"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.AddField(
                    model_name="pendingreview",
                    name="reviewer",
                    field=models.TextField(blank=True, default=""),
                ),
                migrations.AddField(
                    model_name="pendingreview",
                    name="review_note",
                    field=models.TextField(blank=True, default=""),
                ),
                migrations.AddField(
                    model_name="pendingreview",
                    name="committed_at",
                    field=models.DateTimeField(blank=True, db_index=True, null=True),
                ),
                migrations.AddField(
                    model_name="pendingreview",
                    name="commit_error",
                    field=models.TextField(blank=True, default=""),
                ),
            ],
            database_operations=[
                migrations.RunPython(_forward, _reverse),
            ],
        ),
    ]
