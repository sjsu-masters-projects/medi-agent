#!/usr/bin/env bash

# Apply committed schema changes exactly once to one explicitly selected database.
# Requires MEDIAGENT_DB_URL; never falls back to a local or production default.
set -euo pipefail

if [[ -z "${MEDIAGENT_DB_URL:-}" ]]; then
  echo "MEDIAGENT_DB_URL is required." >&2
  exit 1
fi

if ! command -v psql >/dev/null 2>&1; then
  echo "psql is required. Install PostgreSQL client tools first." >&2
  exit 1
fi

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MIGRATIONS_DIR="$ROOT_DIR/backend/src/app/db/migrations"

psql "$MEDIAGENT_DB_URL" -v ON_ERROR_STOP=1 <<'SQL'
CREATE TABLE IF NOT EXISTS public.schema_migrations (
  filename text PRIMARY KEY,
  checksum text NOT NULL,
  applied_at timestamptz NOT NULL DEFAULT now()
);
SQL

for migration_path in "$MIGRATIONS_DIR"/*.sql; do
  filename="$(basename "$migration_path")"
  checksum="$(shasum -a 256 "$migration_path" | awk '{print $1}')"
  recorded_checksum="$(psql "$MEDIAGENT_DB_URL" -At -v ON_ERROR_STOP=1 \
    -v filename="$filename" \
    -c "SELECT checksum FROM public.schema_migrations WHERE filename = :'filename';")"

  if [[ -n "$recorded_checksum" ]]; then
    if [[ "$recorded_checksum" != "$checksum" ]]; then
      echo "Checksum mismatch for applied migration: $filename" >&2
      exit 1
    fi
    echo "Skipping applied migration: $filename"
    continue
  fi

  echo "Applying migration: $filename"
  psql "$MEDIAGENT_DB_URL" -v ON_ERROR_STOP=1 \
    -v migration_path="$migration_path" \
    -v filename="$filename" \
    -v checksum="$checksum" <<'SQL'
BEGIN;
SELECT pg_advisory_xact_lock(726340181);
\i :migration_path
INSERT INTO public.schema_migrations (filename, checksum)
VALUES (:'filename', :'checksum');
COMMIT;
SQL
done

echo "Migration ledger is synchronized."
