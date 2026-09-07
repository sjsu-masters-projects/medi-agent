#!/usr/bin/env bash
# Read-only staging inventory for canonical rows created by the pre-R2 document path.
# It deliberately performs no repair, deletion, or remote migration.

set -euo pipefail

if [[ -z "${MEDIAGENT_DB_URL:-}" ]]; then
  echo "MEDIAGENT_DB_URL is required." >&2
  exit 2
fi

psql "$MEDIAGENT_DB_URL" -v ON_ERROR_STOP=1 <<'SQL'
SELECT 'medications' AS record_type, count(*) AS legacy_rows
FROM public.medications
WHERE source_document_id IS NOT NULL
UNION ALL
SELECT 'obligations' AS record_type, count(*) AS legacy_rows
FROM public.obligations
WHERE source_document_id IS NOT NULL
ORDER BY record_type;

SELECT
  d.id AS document_id,
  d.patient_id,
  d.file_name,
  count(m.id) AS legacy_medications,
  count(o.id) AS legacy_obligations
FROM public.documents d
LEFT JOIN public.medications m ON m.source_document_id = d.id
LEFT JOIN public.obligations o ON o.source_document_id = d.id
WHERE m.id IS NOT NULL OR o.id IS NOT NULL
GROUP BY d.id, d.patient_id, d.file_name
ORDER BY d.created_at DESC;
SQL
