// 001 — Case + Citation uniqueness constraints
// Applied by backend/scripts/init-db.sh on container startup.
CREATE CONSTRAINT case_id_unique IF NOT EXISTS
  FOR (c:Case) REQUIRE c.id IS UNIQUE;
CREATE CONSTRAINT citation_normalized_unique IF NOT EXISTS
  FOR (x:Citation) REQUIRE x.normalized IS UNIQUE;
