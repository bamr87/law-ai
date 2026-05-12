#!/bin/bash
set -euo pipefail

echo "🗄️  Initializing LawGraph databases..."
sleep 5

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
NEO4J_MIGRATIONS="$REPO_ROOT/lawgraph/core/neo4j/migrations"

NEO4J_USER="${NEO4J_USER:-neo4j}"
NEO4J_PASSWORD="${NEO4J_PASSWORD:-lawgraph-dev}"

echo "==> Applying Neo4j migrations"
shopt -s nullglob
cypher_files=("$NEO4J_MIGRATIONS"/*.cypher)
if [[ ${#cypher_files[@]} -eq 0 ]]; then
  echo "WARNING: No .cypher files found under $NEO4J_MIGRATIONS — skipping Neo4j migrations."
fi
for f in "${cypher_files[@]}"; do
  echo "    - $(basename "$f")"
  cypher-shell -u "$NEO4J_USER" -p "$NEO4J_PASSWORD" -f "$f"
done

echo "==> Applying Postgres migrations (Django)"
export DJANGO_SETTINGS_MODULE="${DJANGO_SETTINGS_MODULE:-lawgraph.settings.dev}"
cd "$REPO_ROOT" && python manage.py migrate --noinput

echo "✅ Database initialization complete."