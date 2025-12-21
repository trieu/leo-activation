#!/bin/bash

# ============================================================
# PostgreSQL 16 + PostGIS + pgvector
# Schema Database for Resynap720 with data from Customer360 in LEO CDP
# ============================================================

# --- Docker configs ---
CONTAINER_NAME="pgsql16_vector"
VLAN_NAME="leo-vlan"
DATA_VOLUME="pgdata_vector"

# --- POSTGRES config ---
POSTGRES_USER="postgres"
POSTGRES_PASSWORD="password"
DEFAULT_DB="postgres"
TARGET_DB="resynap720"
HOST_PORT=5432

# --- SQL schema config ---
SCHEMA_VERSION=251222
SCHEMA_DESCRIPTION="upgrade marketing_event + AI embedding pipeline"
SQL_FILE_PATH="./sql-scripts/schema.sql"

# --- Parse options ---
RESET_DB=false
for arg in "$@"; do
  case $arg in
    --reset-db)
      RESET_DB=true
      shift
      ;;
  esac
done

# ============================================================
# Helper: wait for PostgreSQL
# ============================================================
wait_for_postgres() {
  local max_attempts=10
  local attempt=1
  echo "⏳ Waiting for PostgreSQL..."
  until docker exec -u postgres "$CONTAINER_NAME" psql -d "$DEFAULT_DB" -c "SELECT 1;" >/dev/null 2>&1; do
    if [ $attempt -ge $max_attempts ]; then
      echo "❌ PostgreSQL not ready"
      exit 1
    fi
    sleep 2
    ((attempt++))
  done
  echo "🟢 PostgreSQL ready."
}

# ============================================================
# Start or create container
# ============================================================
if docker ps -a --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
  if ! docker ps --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
    docker start "$CONTAINER_NAME"
  fi
else
  docker volume create "$DATA_VOLUME" >/dev/null 2>&1

  docker run -d \
    --name "$CONTAINER_NAME" \
    --network "$VLAN_NAME" \
    -e POSTGRES_USER="$POSTGRES_USER" \
    -e POSTGRES_PASSWORD="$POSTGRES_PASSWORD" \
    -e POSTGRES_DB="$DEFAULT_DB" \
    -p "$HOST_PORT:5432" \
    -v "$DATA_VOLUME:/var/lib/postgresql/data" \
    postgis/postgis:16-3.5
fi

wait_for_postgres

# ============================================================
# Install pgvector (once)
# ============================================================
docker exec -u root "$CONTAINER_NAME" bash -c \
  "apt-get update && apt-get install -y postgresql-16-pgvector" >/dev/null 2>&1 || true

# ============================================================
# Fix collation mismatches (Docker + Debian issue)
# ============================================================
docker exec -u postgres "$CONTAINER_NAME" psql -d postgres \
  -c "ALTER DATABASE postgres REFRESH COLLATION VERSION;" || true

docker exec -u postgres "$CONTAINER_NAME" psql -d template1 \
  -c "ALTER DATABASE template1 REFRESH COLLATION VERSION;" || true

# ============================================================
# Reset DB if requested
# ============================================================
if [ "$RESET_DB" = true ]; then
  docker exec -u postgres "$CONTAINER_NAME" psql -d postgres \
    -c "DROP DATABASE IF EXISTS ${TARGET_DB};"
fi

# ============================================================
# Create DB if missing
# ============================================================
DB_EXISTS=$(docker exec -u postgres "$CONTAINER_NAME" psql -d postgres -t \
  -c "SELECT 1 FROM pg_database WHERE datname='${TARGET_DB}';" | tr -d '[:space:]')

if [ "$DB_EXISTS" != "1" ]; then
  docker exec -u postgres "$CONTAINER_NAME" psql -d postgres \
    -c "CREATE DATABASE ${TARGET_DB};"
fi

# ============================================================
# Enable required extensions
# ============================================================
docker exec -u postgres "$CONTAINER_NAME" psql -d "$TARGET_DB" -c \
  "CREATE EXTENSION IF NOT EXISTS vector;"
docker exec -u postgres "$CONTAINER_NAME" psql -d "$TARGET_DB" -c \
  "CREATE EXTENSION IF NOT EXISTS postgis;"

# ============================================================
# Schema migration table
# ============================================================
docker exec -u postgres "$CONTAINER_NAME" psql -d "$TARGET_DB" -c "
CREATE TABLE IF NOT EXISTS schema_migrations (
  version INTEGER PRIMARY KEY,
  applied_at TIMESTAMPTZ DEFAULT now(),
  description TEXT
);
"

CURRENT_VERSION=$(docker exec -u postgres "$CONTAINER_NAME" psql -d "$TARGET_DB" -t \
  -c "SELECT COALESCE(MAX(version),0) FROM schema_migrations;" | tr -d '[:space:]')

# ============================================================
# Apply migration if needed
# ============================================================
if [ "$CURRENT_VERSION" -lt "$SCHEMA_VERSION" ]; then
  echo "🚀 Applying migration $SCHEMA_VERSION"
  docker exec -i -u postgres "$CONTAINER_NAME" psql -d "$TARGET_DB" \
    < "$SQL_FILE_PATH" || exit 1

  docker exec -u postgres "$CONTAINER_NAME" psql -d "$TARGET_DB" -c "
    INSERT INTO schema_migrations (version, description)
    VALUES ($SCHEMA_VERSION, '$SCHEMA_DESCRIPTION');
  "
else
  echo "ℹ️ Schema already up to date"
fi

# ============================================================
# Verify critical tables (marketing + AI)
# ============================================================
TABLES=(
  tenant
  marketing_event
  embedding_job
  schema_migrations
)

for table in "${TABLES[@]}"; do
  docker exec -u postgres "$CONTAINER_NAME" psql -d "$TARGET_DB" -tc \
    "SELECT 1 FROM pg_tables WHERE tablename='$table';" | grep -q 1 \
    || { echo "❌ Missing table: $table"; exit 1; }
done

# ============================================================
# Restart policy
# ============================================================
docker update --restart unless-stopped "$CONTAINER_NAME"

echo "✅ Marketing Event DB upgrade completed"
echo "   DB: $TARGET_DB"
echo "   Schema version: $SCHEMA_VERSION"
echo "   Tables: ${TABLES[*]}"
echo "   Extensions: postgis, vector"
echo "   Port: $HOST_PORT"
