#!/usr/bin/env bash
# ============================================================
# Checks backend and frontend env files against their
# corresponding .env.example templates. Run this before
# starting dev servers.
#
# Usage: ./scripts/check-env.sh
# ============================================================

set -euo pipefail

# Find project root so script works regardless of where it's called from
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

ERRORS=0
WARNINGS=0

get_var_value() {
  local env_file="$1"
  local var_name="$2"
  local value

  value=$(rg "^[[:space:]]*${var_name}=" "$env_file" | sed -E "s/^[[:space:]]*${var_name}=//" | tail -n 1 || true)
  value="${value%%#*}"
  value="$(printf '%s' "$value" | sed -E 's/^[[:space:]]+//; s/[[:space:]]+$//')"
  echo "$value"
}

print_copy_hint() {
  local example_file="$1"
  local env_file="$2"

  echo "   Run:  cp ${example_file#$ROOT_DIR/} ${env_file#$ROOT_DIR/}"
  echo "   Then fill in your values (see ${example_file#$ROOT_DIR/} for details)."
}

check_env_file() {
  local label="$1"
  local env_file="$2"
  local example_file="$3"
  local required_vars_raw="$4"
  local optional_vars_raw="$5"
  local missing_is_error="${6:-true}"
  local required_vars=()
  local optional_vars=()
  local var
  local value
  local example_vars
  local env_vars
  local new_in_example

  # Bash 3-compatible array expansion for macOS.
  eval "required_vars=(${required_vars_raw})"
  eval "optional_vars=(${optional_vars_raw})"

  echo "🔍  Checking ${label}"
  echo "    env:     ${env_file#$ROOT_DIR/}"
  echo "    example: ${example_file#$ROOT_DIR/}"
  echo ""

  if [ ! -f "$env_file" ]; then
    if [ "$missing_is_error" = "true" ]; then
      echo "  ❌  Missing ${env_file#$ROOT_DIR/}"
      print_copy_hint "$example_file" "$env_file"
      ERRORS=$((ERRORS + 1))
    else
      echo "  ⚠️   ${env_file#$ROOT_DIR/} not found"
      print_copy_hint "$example_file" "$env_file"
      WARNINGS=$((WARNINGS + 1))
    fi
    echo ""
    return
  fi

  for var in "${required_vars[@]}"; do
    value=$(get_var_value "$env_file" "$var")
    if [ -z "$value" ]; then
      echo "  ❌  $var  — required but missing or empty"
      ERRORS=$((ERRORS + 1))
    else
      echo "  ✅  $var"
    fi
  done

  echo ""

  for var in "${optional_vars[@]}"; do
    if rg -q "^[[:space:]]*${var}=" "$env_file"; then
      echo "  ✅  $var"
    else
      echo "  ⚠️   $var  — not in ${env_file#$ROOT_DIR/} (optional)"
      WARNINGS=$((WARNINGS + 1))
    fi
  done

  echo ""

  example_vars=$(rg -o '^[[:space:]]*[A-Z0-9_]+=' "$example_file" | sed -E 's/^[[:space:]]*//; s/=$//' | sort -u || true)
  env_vars=$(rg -o '^[[:space:]]*[A-Z0-9_]+=' "$env_file" | sed -E 's/^[[:space:]]*//; s/=$//' | sort -u || true)
  new_in_example=$(comm -23 <(echo "$example_vars") <(echo "$env_vars") 2>/dev/null || true)

  if [ -n "$new_in_example" ]; then
    echo "🆕  Vars in ${example_file#$ROOT_DIR/} missing from ${env_file#$ROOT_DIR/}:"
    echo "$new_in_example" | while read -r var; do
      echo "    → $var"
    done
    echo ""
  fi
}

# Backend/root env
BACKEND_REQUIRED_VARS=(
  "SUPABASE_URL"
  "SUPABASE_ANON_KEY"
  "SUPABASE_SERVICE_ROLE_KEY"
  "SUPABASE_JWT_SECRET"
  "GOOGLE_API_KEY"
)

BACKEND_OPTIONAL_VARS=(
  "GOOGLE_PROJECT_ID"
  "DEEPGRAM_API_KEY"
  "RESEND_API_KEY"
  "SYNCFUSION_LICENSE_KEY"
  "GEMINI_FLASH_MODEL"
  "GEMINI_PRO_MODEL"
  "MEDGEMMA_MODEL"
  "GOOGLE_EMBEDDING_MODEL"
  "RAG_EMBEDDING_DIMENSIONS"
  "RAG_MIN_SIMILARITY"
  "BACKEND_SENTRY_DSN"
  "BACKEND_SENTRY_PROJECT"
  "SENTRY_ENVIRONMENT"
  "SENTRY_RELEASE"
  "SENTRY_DEBUG"
  "SENTRY_ORG"
  "SENTRY_AUTH_TOKEN"
  "BACKEND_URL"
  "PATIENT_PORTAL_URL"
  "CLINICIAN_PORTAL_URL"
  "CRON_AUTH_TOKEN"
  "ENVIRONMENT"
  "LOG_LEVEL"
)

# Patient portal env
PATIENT_REQUIRED_VARS=(
  "NEXT_PUBLIC_BACKEND_URL"
  "NEXT_PUBLIC_SUPABASE_URL"
  "NEXT_PUBLIC_SUPABASE_ANON_KEY"
)

PATIENT_OPTIONAL_VARS=(
  "NEXT_PUBLIC_SYNCFUSION_LICENSE_KEY"
  "PATIENT_PORTAL_SENTRY_DSN"
  "NEXT_PUBLIC_PATIENT_PORTAL_SENTRY_DSN"
  "PATIENT_PORTAL_SENTRY_PROJECT"
  "SENTRY_ENVIRONMENT"
  "SENTRY_RELEASE"
  "SENTRY_DEBUG"
  "SENTRY_ORG"
  "SENTRY_AUTH_TOKEN"
)

# Clinician portal env
CLINICIAN_REQUIRED_VARS=(
  "NEXT_PUBLIC_BACKEND_URL"
  "NEXT_PUBLIC_SUPABASE_URL"
  "NEXT_PUBLIC_SUPABASE_ANON_KEY"
)

CLINICIAN_OPTIONAL_VARS=(
  "CLINICIAN_PORTAL_SENTRY_DSN"
  "NEXT_PUBLIC_CLINICIAN_PORTAL_SENTRY_DSN"
  "CLINICIAN_PORTAL_SENTRY_PROJECT"
  "SENTRY_ENVIRONMENT"
  "SENTRY_RELEASE"
  "SENTRY_DEBUG"
  "SENTRY_ORG"
  "SENTRY_AUTH_TOKEN"
)

check_env_file \
  "backend/root env" \
  "$ROOT_DIR/.env" \
  "$ROOT_DIR/.env.example" \
  "\"\${BACKEND_REQUIRED_VARS[@]}\"" \
  "\"\${BACKEND_OPTIONAL_VARS[@]}\"" \
  "true"

check_env_file \
  "patient portal env" \
  "$ROOT_DIR/apps/patient-portal/.env.local" \
  "$ROOT_DIR/apps/patient-portal/.env.example" \
  "\"\${PATIENT_REQUIRED_VARS[@]}\"" \
  "\"\${PATIENT_OPTIONAL_VARS[@]}\"" \
  "false"

check_env_file \
  "clinician portal env" \
  "$ROOT_DIR/apps/clinician-portal/.env.local" \
  "$ROOT_DIR/apps/clinician-portal/.env.example" \
  "\"\${CLINICIAN_REQUIRED_VARS[@]}\"" \
  "\"\${CLINICIAN_OPTIONAL_VARS[@]}\"" \
  "false"

if [ "$ERRORS" -gt 0 ]; then
  echo "💥  $ERRORS required variable(s) missing. Fix the env files above."
  exit 1
else
  echo "✅  All required variables set for available env files."
  if [ "$WARNINGS" -gt 0 ]; then
    echo "⚠️   $WARNINGS optional or missing-file warning(s)."
  fi
fi
