#!/usr/bin/env bash

# Read-only verification after applying the migration chain.
set -euo pipefail

if [[ -z "${MEDIAGENT_DB_URL:-}" ]]; then
  echo "MEDIAGENT_DB_URL is required." >&2
  exit 1
fi

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
EXPECTED_MIGRATIONS="$(find "$ROOT_DIR/backend/src/app/db/migrations" -maxdepth 1 -name '*.sql' | wc -l | tr -d ' ')"
APPLIED_MIGRATIONS="$(psql "$MEDIAGENT_DB_URL" -At -v ON_ERROR_STOP=1 -c 'SELECT count(*) FROM public.schema_migrations;')"

if [[ "$APPLIED_MIGRATIONS" != "$EXPECTED_MIGRATIONS" ]]; then
  echo "Expected $EXPECTED_MIGRATIONS applied migrations, found $APPLIED_MIGRATIONS." >&2
  exit 1
fi

psql "$MEDIAGENT_DB_URL" -v ON_ERROR_STOP=1 <<'SQL'
SELECT tablename
FROM pg_tables
WHERE schemaname = 'public'
  AND tablename IN (
    'patients', 'clinicians', 'care_teams', 'clinical_facts',
    'fhir_imports', 'fhir_import_resources', 'clinical_recommendations', 'action_envelopes'
  )
ORDER BY tablename;

SELECT tablename, rowsecurity
FROM pg_tables
WHERE schemaname = 'public'
  AND tablename IN ('clinical_facts', 'fhir_imports', 'clinical_recommendations')
ORDER BY tablename;
SQL

echo "Schema ledger and required tables verified."
