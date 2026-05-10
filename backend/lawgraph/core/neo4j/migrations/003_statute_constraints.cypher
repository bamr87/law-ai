// 003 — Statute / Code / Jurisdiction / Court uniqueness constraints (spec 015 FR-1).
// Forward-only and idempotent (NFR-MIGRATION-SAFETY-1). All constraints use
// IF NOT EXISTS so re-running this file against an existing graph is safe.

CREATE CONSTRAINT jurisdiction_code_unique IF NOT EXISTS
  FOR (j:Jurisdiction) REQUIRE j.code IS UNIQUE;

CREATE CONSTRAINT court_id_unique IF NOT EXISTS
  FOR (c:Court) REQUIRE c.id IS UNIQUE;

CREATE CONSTRAINT code_id_unique IF NOT EXISTS
  FOR (c:Code) REQUIRE c.id IS UNIQUE;

CREATE CONSTRAINT statute_id_unique IF NOT EXISTS
  FOR (s:Statute) REQUIRE s.id IS UNIQUE;

CREATE CONSTRAINT statute_section_id_unique IF NOT EXISTS
  FOR (s:StatuteSection) REQUIRE s.id IS UNIQUE;
