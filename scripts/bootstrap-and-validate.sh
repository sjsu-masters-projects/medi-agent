#!/usr/bin/env bash

# Create a reproducible local development environment and run the repository gates.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

require_command() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Required command is unavailable: $1" >&2
    exit 1
  fi
}

require_command python3
require_command npm

PYTHON_BIN="python3"
if command -v python3.12 >/dev/null 2>&1; then
  PYTHON_BIN="python3.12"
fi

if [ ! -x backend/.venv/bin/python ]; then
  "$PYTHON_BIN" -m venv backend/.venv
fi

backend/.venv/bin/python -m pip install --upgrade pip
backend/.venv/bin/python -m pip install -r backend/requirements-dev.txt

(cd apps/patient-portal && npm ci)
(cd apps/clinician-portal && npm ci)

backend/.venv/bin/python backend/scripts/check_production_placeholders.py
(cd backend && .venv/bin/python scripts/validate_migrations.py)
(cd backend && .venv/bin/ruff check src/ scripts/)
(cd backend && .venv/bin/ruff format --check src/ scripts/)
(cd backend && .venv/bin/mypy src/ --ignore-missing-imports)

CI_ENV=(
  SUPABASE_URL=https://test.supabase.co
  SUPABASE_ANON_KEY=test-anon-key
  SUPABASE_SERVICE_ROLE_KEY=test-service-role-key
  SUPABASE_JWT_SECRET=test-jwt-secret-for-ci
)
(cd backend && env "${CI_ENV[@]}" .venv/bin/pytest tests/ -v --tb=short)

(cd apps/patient-portal && npm run lint && npm run typecheck && npm run test && npm run build)
(cd apps/clinician-portal && npm run lint && npm run typecheck && npm run test && npm run build)

echo "Bootstrap and validation completed successfully."
