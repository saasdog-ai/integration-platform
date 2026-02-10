#!/bin/bash
set -e

# Extract connection info from DATABASE_URL to create database if needed
# DATABASE_URL format: postgresql+asyncpg://user:pass@host:port/dbname
if [ -n "$DATABASE_URL" ]; then
  # Parse the URL - strip the driver prefix for psql compatibility
  SYNC_URL=$(echo "$DATABASE_URL" | sed 's|postgresql+asyncpg://|postgresql://|')
  DB_NAME=$(echo "$SYNC_URL" | sed 's|.*/||')
  BASE_URL=$(echo "$SYNC_URL" | sed "s|/$DB_NAME$|/postgres|")

  # Add sslmode=require for RDS connections
  if [[ "$BASE_URL" == *"rds.amazonaws.com"* ]]; then
    BASE_URL="${BASE_URL}?sslmode=require"
  fi

  echo "Checking if database '$DB_NAME' exists..."
  if ! psql "$BASE_URL" -tAc "SELECT 1 FROM pg_database WHERE datname='$DB_NAME'" | grep -q 1; then
    echo "Creating database '$DB_NAME'..."
    psql "$BASE_URL" -c "CREATE DATABASE $DB_NAME;"
    echo "Database '$DB_NAME' created."
  else
    echo "Database '$DB_NAME' already exists."
  fi
fi

echo "Running database migrations..."
alembic upgrade head

echo "Starting application..."
exec uvicorn app.main:app --host 0.0.0.0 --port "${API_PORT:-8000}"
