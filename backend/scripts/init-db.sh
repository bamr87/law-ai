#!/bin/bash
# init-db.sh — operator/onboarding reset script for Law AI databases.
#
# INVOCATION: run this script from within the backend container or a host env
# where `python manage.py` (backend venv) is available and both databases are
# reachable.  The stack must already be running (postgres + neo4j).  Both
# migration sets are driven by management commands (`migrate_neo4j`,
# `migrate`), so no database CLI is required.
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

# Exported so `manage.py migrate_neo4j` (which reads them through settings)
# sees the same credentials this script was invoked with.
export NEO4J_USER="${NEO4J_USER:-neo4j}"
export NEO4J_PASSWORD="${NEO4J_PASSWORD:-law_ai-dev}"

echo "==> Applying Neo4j migrations"
shopt -s nullglob
cypher_files=("$NEO4J_MIGRATIONS"/*.cypher)
if [[ ${#cypher_files[@]} -eq 0 ]]; then
  echo "WARNING: No .cypher files found under $NEO4J_MIGRATIONS — skipping Neo4j migrations."
fi
# BL-20260509-02: the old `cypher-shell -f` loop per file had no bookkeeping,
# so a migration that is not idempotent by construction would re-run on every
# boot. `migrate_neo4j` records each applied file as a (:_Migration) node.
export DJANGO_SETTINGS_MODULE="${DJANGO_SETTINGS_MODULE:-law_ai.settings.dev}"
cd "$REPO_ROOT" && python manage.py migrate_neo4j

echo "==> Applying Postgres migrations (Django)"
cd "$REPO_ROOT" && python manage.py migrate --noinput

echo "✅ Database initialization complete."