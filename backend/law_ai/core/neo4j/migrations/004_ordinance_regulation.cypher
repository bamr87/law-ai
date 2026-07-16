// 004 — Ordinance + Regulation uniqueness constraints (spec 015 FR-1).
// Forward-only, idempotent.

CREATE CONSTRAINT ordinance_id_unique IF NOT EXISTS
  FOR (o:Ordinance) REQUIRE o.id IS UNIQUE;

CREATE CONSTRAINT ordinance_section_id_unique IF NOT EXISTS
  FOR (o:OrdinanceSection) REQUIRE o.id IS UNIQUE;

CREATE CONSTRAINT regulation_id_unique IF NOT EXISTS
  FOR (r:Regulation) REQUIRE r.id IS UNIQUE;
