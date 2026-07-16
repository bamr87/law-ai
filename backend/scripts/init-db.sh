#!/bin/bash
# init-db.sh — operator/onboarding reset script for Law AI databases.
#
# INVOCATION: run this script from within the backend container or a host env
# where both `python manage.py` (backend venv) and `cypher-shell` (reachable
# neo4j) are available.  The stack must already be running (postgres + neo4j).
#
# This script is NOT auto-executed by docker-compose.  Postgres initialisation
# (DB/user creation) is handled by the postgres:16-alpine image's env-var
# mechanism (POSTGRES_USER/POSTGRES_PASSWORD/POSTGRES_DB).
#
# Usage:
#   make reset-db                  # recommended: uses backend container
#   docker compose run --rm backend bash backend/scripts/init-db.sh
set -euo pipefail

echo "🗄️  Initializing Law AI databases..."
sleep 5

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
NEO4J_MIGRATIONS="$REPO_ROOT/law_ai/core/neo4j/migrations"

NEO4J_USER="${NEO4J_USER:-neo4j}"
NEO4J_PASSWORD="${NEO4J_PASSWORD:-law_ai-dev}"

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
export DJANGO_SETTINGS_MODULE="${DJANGO_SETTINGS_MODULE:-law_ai.settings.dev}"
cd "$REPO_ROOT" && python manage.py migrate --noinput

echo "✅ Database initialization complete."