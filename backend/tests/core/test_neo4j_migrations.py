"""Validate the Cypher migration set (spec 015 T-004, AC-1).

This is a unit test (no live Neo4j). It walks every ``.cypher`` file under
``backend/law_ai/core/neo4j/migrations/`` and asserts:

1. Every ``CREATE CONSTRAINT|INDEX|FULLTEXT INDEX`` is ``IF NOT EXISTS``-guarded
   so reruns are safe (NFR-MIGRATION-SAFETY-1).
2. The union of declared constraint / index names covers the labels listed in
   spec 015 §7 (FR-1 / FR-2 / FR-3 / FR-4).

The docker-backed half — applying the DDL and diffing ``SHOW CONSTRAINTS`` /
``SHOW INDEXES`` against :func:`expected_schema_names` — lives in
``tests/db/test_neo4j_migrations_integration.py`` (BL-20260509-03).
"""

from __future__ import annotations

import re
from pathlib import Path

MIGRATIONS_DIR = (
    Path(__file__).resolve().parents[2] / "law_ai" / "core" / "neo4j" / "migrations"
)

# Labels that must each have a unique-id (or unique-code) constraint.
REQUIRED_UNIQUE_LABELS = {
    "Case",  # from 001
    "Citation",  # from 001
    "Jurisdiction",  # from 003 (uses .code)
    "Court",
    "Code",
    "Statute",
    "StatuteSection",
    "Ordinance",
    "OrdinanceSection",
    "Regulation",
    "DerivedDocument",
}

REQUIRED_FULLTEXT_LABELS = {
    "Case",
    "StatuteSection",
    "OrdinanceSection",
    "Regulation",
    "DerivedDocument",
}

REQUIRED_TEMPORAL_LABELS = {
    "Statute",
    "StatuteSection",
    "Ordinance",
    "OrdinanceSection",
    "Regulation",
}


def _all_sql() -> str:
    """Concatenate all migration files into one normalized blob."""
    files = sorted(MIGRATIONS_DIR.glob("*.cypher"))
    assert files, f"no migrations found under {MIGRATIONS_DIR}"
    return "\n".join(f.read_text() for f in files)


CREATE_RE = re.compile(
    r"\bCREATE\s+(CONSTRAINT|INDEX|FULLTEXT\s+INDEX|VECTOR\s+INDEX)\b[^;]*?;",
    re.IGNORECASE | re.DOTALL,
)


# Name is the token right after CREATE [FULLTEXT|VECTOR] CONSTRAINT|INDEX.
_NAME_RE = re.compile(
    r"\bCREATE\s+(?:FULLTEXT\s+|VECTOR\s+)?(CONSTRAINT|INDEX)"
    r"\s+(\w+)\s+IF\s+NOT\s+EXISTS",
    re.IGNORECASE,
)
_FULLTEXT_NAME_RE = re.compile(
    r"\bCREATE\s+FULLTEXT\s+INDEX\s+(\w+)\s+IF\s+NOT\s+EXISTS",
    re.IGNORECASE,
)
_VECTOR_NAME_RE = re.compile(
    r"\bCREATE\s+VECTOR\s+INDEX\s+(\w+)\s+IF\s+NOT\s+EXISTS",
    re.IGNORECASE,
)


def expected_schema_names() -> dict[str, set[str]]:
    """Constraint / index names the migration set declares.

    Shared with the docker-backed parity test
    ``tests/db/test_neo4j_migrations_integration.py`` (BL-20260509-03), which
    asserts ``SHOW CONSTRAINTS`` / ``SHOW INDEXES`` match these exactly after
    applying 001-007 against a live Neo4j.
    """
    blob = _all_sql()
    constraints = {
        name for kind, name in _NAME_RE.findall(blob) if kind.upper() == "CONSTRAINT"
    }
    fulltext = set(_FULLTEXT_NAME_RE.findall(blob))
    vector = set(_VECTOR_NAME_RE.findall(blob))
    indexes = {name for kind, name in _NAME_RE.findall(blob) if kind.upper() == "INDEX"}
    return {
        "constraints": constraints,
        "indexes": indexes - fulltext - vector,
        "fulltext": fulltext,
        "vector": vector,
    }


def test_expected_schema_names_are_non_empty_and_disjoint() -> None:
    names = expected_schema_names()
    assert names["constraints"], "no named constraints found"
    assert names["indexes"], "no named range indexes found"
    assert names["fulltext"], "no named fulltext indexes found"
    # BL-20260810-17 added the vector indexes the GraphRAG vector leg needs.
    assert names["vector"] == {
        "case_embedding_vec",
        "statute_section_embedding_vec",
    }
    assert not names["indexes"] & names["fulltext"]
    assert not names["indexes"] & names["vector"]
    assert not names["fulltext"] & names["vector"]
    assert not names["constraints"] & names["indexes"]


def test_every_create_uses_if_not_exists() -> None:
    """NFR-MIGRATION-SAFETY-1: reruns must be safe."""
    blob = _all_sql()
    statements = CREATE_RE.findall(blob)
    assert statements, "expected CREATE statements in migration set"
    # Re-scan to also capture the matched statement text (findall returns groups only).
    full_statements = [m.group(0) for m in CREATE_RE.finditer(blob)]
    missing = [s for s in full_statements if "IF NOT EXISTS" not in s.upper()]
    assert (
        not missing
    ), "every CREATE must be IF NOT EXISTS-guarded; offenders:\n" + "\n".join(missing)


def test_unique_constraints_cover_required_labels() -> None:
    """FR-1 / FR-4: every declared label has a uniqueness constraint."""
    blob = _all_sql()
    declared = set(
        re.findall(
            r"FOR\s*\(\s*\w+\s*:\s*(\w+)\s*\)\s*REQUIRE\s+\w+\.\w+\s+IS\s+UNIQUE",
            blob,
            flags=re.IGNORECASE,
        )
    )
    missing = REQUIRED_UNIQUE_LABELS - declared
    assert not missing, f"missing UNIQUE constraints for labels: {sorted(missing)}"


def test_fulltext_indexes_cover_required_labels() -> None:
    """FR-2: hybrid retrieval needs lexical pre-filter on these labels."""
    blob = _all_sql()
    declared = set(
        re.findall(
            r"CREATE\s+FULLTEXT\s+INDEX[^;]*FOR\s*\(\s*\w+\s*:\s*(\w+)\s*\)",
            blob,
            flags=re.IGNORECASE | re.DOTALL,
        )
    )
    missing = REQUIRED_FULLTEXT_LABELS - declared
    assert not missing, f"missing FULLTEXT indexes for labels: {sorted(missing)}"


def test_temporal_indexes_cover_required_labels() -> None:
    """FR-3: as-of date queries need a range index on `effective_from`."""
    blob = _all_sql()
    # Match standard CREATE INDEX (not FULLTEXT) statements with an effective_from prop.
    declared = set(
        re.findall(
            r"CREATE\s+INDEX[^;]*FOR\s*\(\s*\w+\s*:\s*(\w+)\s*\)\s+ON\s*\(\s*\w+\.effective_from\s*\)",
            blob,
            flags=re.IGNORECASE | re.DOTALL,
        )
    )
    missing = REQUIRED_TEMPORAL_LABELS - declared
    assert (
        not missing
    ), f"missing range index on `effective_from` for labels: {sorted(missing)}"


def test_derived_document_has_provenance_existence_constraints() -> None:
    """FR-4: AI outputs cannot exist without ``agent_version`` + ``kind``."""
    blob = _all_sql()
    assert re.search(
        r"FOR\s*\(\s*\w+\s*:\s*DerivedDocument\s*\)\s*REQUIRE\s+\w+\.agent_version\s+IS\s+NOT\s+NULL",
        blob,
        flags=re.IGNORECASE,
    ), "DerivedDocument.agent_version existence constraint missing"
    assert re.search(
        r"FOR\s*\(\s*\w+\s*:\s*DerivedDocument\s*\)\s*REQUIRE\s+\w+\.kind\s+IS\s+NOT\s+NULL",
        blob,
        flags=re.IGNORECASE,
    ), "DerivedDocument.kind existence constraint missing"
