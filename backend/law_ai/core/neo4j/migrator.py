"""Cypher migration runner with ``(:_Migration)`` bookkeeping (BL-20260509-02).

Before this module the only safety net for ``core/neo4j/migrations/*.cypher``
was ``IF NOT EXISTS`` on every ``CREATE``, applied by a bash loop in
``backend/scripts/init-db.sh``. That works for schema DDL and nothing else: a
data back-fill written as a migration would re-run on every boot.

:func:`apply_migrations` records each applied file as a ``(:_Migration {id})``
node and skips files already recorded, which makes non-idempotent migrations
safe to add later.

Design notes:

* **One statement per auto-commit transaction.** Neo4j refuses to mix schema
  DDL with writes inside a single transaction, and ``CREATE FULLTEXT INDEX``
  is DDL, so statements are run one at a time via ``session.run``.
* **Checksum policy is warn, not fail.** Migrations 001-007 are idempotent
  ``IF NOT EXISTS`` DDL that has already been applied to live databases by the
  old bash loop; failing on an edited file would wedge those deployments. The
  mismatch is returned to the caller, which reports it.
* **Bookkeeping is last.** A file is marked applied only after every statement
  in it succeeded, so a crash mid-file leaves the migration un-recorded and it
  is retried on the next run.
* **Edition-gated DDL is deferred, not failed.** ``006_derived_document`` asks
  for property-existence constraints, which are Enterprise-only; the pinned
  ``neo4j:5-community`` image rejects them. Those statements are reported in
  ``plan.unsupported`` and the file is deliberately *not* recorded, so the same
  migration applies in full the first time it meets an Enterprise database.
  Every statement is ``IF NOT EXISTS``-guarded, so re-running costs nothing.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from neo4j.exceptions import Neo4jError

if TYPE_CHECKING:  # pragma: no cover - typing only
    from neo4j import AsyncDriver

MIGRATIONS_DIR = Path(__file__).resolve().parent / "migrations"

_MIGRATION_CONSTRAINT = (
    "CREATE CONSTRAINT migration_id_unique IF NOT EXISTS "
    "FOR (m:_Migration) REQUIRE m.id IS UNIQUE"
)
_APPLIED_IDS = "MATCH (m:_Migration) RETURN m.id AS id, m.checksum AS checksum"
_RECORD_MIGRATION = (
    "MERGE (m:_Migration {id: $id}) "
    "SET m.applied_at = datetime(), m.checksum = $checksum, "
    "m.statement_count = $statement_count"
)

# `//` line comments only — Cypher has no block comment, and a `//` inside a
# string literal would be a syntax error in these DDL files anyway.
_COMMENT_RE = re.compile(r"^\s*//.*$", re.MULTILINE)

# Neo4j's wording when Community rejects an Enterprise-only schema feature.
_ENTERPRISE_ONLY = "requires neo4j enterprise edition"


def is_enterprise_only(exc: BaseException) -> bool:
    """True when *exc* is Neo4j refusing an Enterprise-only schema feature."""
    return _ENTERPRISE_ONLY in str(exc).lower()


@dataclass
class MigrationPlan:
    """What :func:`apply_migrations` did, or would do."""

    applied: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    checksum_mismatches: list[str] = field(default_factory=list)
    #: Migrations left un-recorded because this edition rejected a statement.
    deferred: list[str] = field(default_factory=list)
    #: ``(migration_id, statement)`` pairs this Neo4j edition cannot run.
    unsupported: list[tuple[str, str]] = field(default_factory=list)
    statements_run: int = 0

    def as_dict(self) -> dict[str, object]:
        return {
            "applied": list(self.applied),
            "skipped": list(self.skipped),
            "checksum_mismatches": list(self.checksum_mismatches),
            "deferred": list(self.deferred),
            "unsupported": [mid for mid, _ in self.unsupported],
            "statements_run": self.statements_run,
        }


def migration_id(path: Path) -> str:
    """The bookkeeping id for a migration file: its stem (``001_case_...``)."""
    return path.stem


def checksum(text: str) -> str:
    """SHA-256 of the raw file text."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def split_statements(text: str) -> list[str]:
    """Split a ``.cypher`` file into executable statements.

    Strips ``//`` comments first so a semicolon inside a comment cannot end a
    statement, then splits on ``;`` and drops whitespace-only fragments. This
    tolerates the multi-line ``CREATE FULLTEXT INDEX ... ON EACH [...]`` and
    option-map forms used by 007 because neither contains a semicolon.
    """
    stripped = _COMMENT_RE.sub("", text)
    return [part.strip() for part in stripped.split(";") if part.strip()]


def discover(migrations_dir: Path | None = None) -> list[Path]:
    """Every ``*.cypher`` migration, in filename order."""
    return sorted((migrations_dir or MIGRATIONS_DIR).glob("*.cypher"))


async def applied_migrations(driver: AsyncDriver) -> dict[str, str | None]:
    """Return ``{migration_id: checksum}`` for everything already recorded."""
    async with driver.session() as session:
        await session.run(_MIGRATION_CONSTRAINT)
        result = await session.run(_APPLIED_IDS)
        return {record["id"]: record["checksum"] async for record in result}


async def apply_migrations(
    driver: AsyncDriver,
    migrations_dir: Path | None = None,
    *,
    dry_run: bool = False,
) -> MigrationPlan:
    """Apply every un-recorded migration and return what happened.

    Recorded migrations are skipped outright; a recorded migration whose file
    has since changed is skipped *and* reported in
    ``plan.checksum_mismatches`` (warn, not fail — see the module docstring).
    """
    plan = MigrationPlan()
    already = await applied_migrations(driver)

    for path in discover(migrations_dir):
        mid = migration_id(path)
        text = path.read_text()
        digest = checksum(text)
        if mid in already:
            plan.skipped.append(mid)
            recorded = already[mid]
            if recorded is not None and recorded != digest:
                plan.checksum_mismatches.append(mid)
            continue

        statements = split_statements(text)
        if dry_run:
            plan.applied.append(mid)
            plan.statements_run += len(statements)
            continue

        unsupported: list[str] = []
        async with driver.session() as session:
            for statement in statements:
                # Auto-commit, one statement at a time: schema DDL cannot
                # share a transaction with anything else.
                try:
                    await session.run(statement)
                except Neo4jError as exc:
                    # Neo4j reports this as a DatabaseError
                    # (Neo.DatabaseError.Schema.ConstraintCreationFailed), not a
                    # ClientError, so match on the base class and the wording.
                    if not is_enterprise_only(exc):
                        raise
                    unsupported.append(statement)
                    continue
                plan.statements_run += 1
            if unsupported:
                # Leave the file un-recorded so it re-applies in full against
                # an Enterprise database later.
                plan.deferred.append(mid)
                plan.unsupported.extend((mid, s) for s in unsupported)
                continue
            await session.run(
                _RECORD_MIGRATION,
                {
                    "id": mid,
                    "checksum": digest,
                    "statement_count": len(statements),
                },
            )
        plan.applied.append(mid)

    return plan
