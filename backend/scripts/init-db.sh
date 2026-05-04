#!/bin/bash
set -euo pipefail

echo "🗄️  Initializing LexGraph databases..."
sleep 5

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
NEO4J_MIGRATIONS="$REPO_ROOT/app/db/neo4j_migrations"
PG_MIGRATIONS="$REPO_ROOT/app/db/postgres_migrations"

NEO4J_USER="${NEO4J_USER:-neo4j}"
NEO4J_PASSWORD="${NEO4J_PASSWORD:-lexgraph-dev}"

echo "==> Applying Neo4j migrations"
for f in "$NEO4J_MIGRATIONS"/*.cypher; do
  [ -e "$f" ] || continue
  echo "    - $(basename "$f")"
  cypher-shell -u "$NEO4J_USER" -p "$NEO4J_PASSWORD" -f "$f"
done

echo "==> Applying Postgres migrations"
PG_URL="${POSTGRES_URL_PSQL:-postgresql://lexgraph:lexgraph-dev@postgres:5432/lexgraph}"
for f in "$PG_MIGRATIONS"/*.sql; do
  [ -e "$f" ] || continue
  echo "    - $(basename "$f")"
  psql "$PG_URL" -v ON_ERROR_STOP=1 -f "$f"
done

echo "✅ Database initialization complete."